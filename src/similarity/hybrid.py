"""T-Sistem - HIBRIT benzerlik / intihal motoru.

NEDEN HIBRIT
------------
Tek katman yetmiyor:

* Sadece `difflib` (eski `vector_store.py`): birebir kopyayi mukemmel yakalar,
  ama cumleyi yeniden yazan (parafraz) ogrenciyi kacirir.
* Sadece embedding: parafrazi yakalar, ama saglayici yoksa hic calismaz ve
  ayni alandaki iki DURUST rapora da yuksek skor verebilir (konu benzerligi
  intihal degildir).

Bu yuzden iki katman BIRLIKTE calisir ve hakeme AYRI AYRI raporlanir:

    literal_score   -> birebir/kopyala-yapistir kaniti (her zaman uretilir)
    semantic_score  -> anlamsal ortusme (saglayici varsa uretilir)
    combined_score  -> karar icin birlesik skor

Hakem ikisini ayri gorur; "%80 benzer" yerine "birebir %12, anlamsal %86"
dedigimizde itiraz sureci de saglam olur.

ESKI KODDAKI KRITIK HATA
------------------------
Eski akista `run_all_checks`'e korpus HIC gecilmiyordu; motor bos korpusla
calisip her raporda sabit ~%8 gosteriyordu. Bu modul bos korpusu SESSIZCE
gecmez: `highest = 0.0` doner ve `notes` icinde acikca "Karsilastirilacak
baska rapor yok" yazar. Ayni sekilde embedding saglayicisi yoksa SAHTE vektor
uretilmez; `semantic_available = False` doner.

VERI
----
* `similarity_results`  -> sonuclar (persist=True ile)
* `report_embeddings`   -> chunk kayitlari (index_report ile)
* `report_embedding_vectors` -> Vectorize yokken yerel kosinus icin vektor
  govdesi. schema.sql'de vektor govdesi icin kolon olmadigindan bu yardimci
  tablo ilk kullanimda `CREATE TABLE IF NOT EXISTS` ile acilir.
* `calibration_settings` -> esikler (yoksa modul varsayilanlari)

BAGIMLILIK
----------
Katman 1 icin harici bagimlilik YOKTUR (yalnizca stdlib). Katman 2 HTTP icin
`requests` varsa onu, yoksa `urllib` kullanir.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable, Sequence

log = logging.getLogger("tsistem.similarity")

ENGINE_VERSION = "hibrit-1.0"

# ── Varsayilan esikler (calibration_settings yoksa bunlar gecerlidir) ───────
DEFAULT_LITERAL_HIGH = 0.35      # birebir kopya tek basina yuksek risk
DEFAULT_SEMANTIC_HIGH = 0.82     # anlamsal ortusme tek basina yuksek risk
DEFAULT_COMBINED_HIGH = 0.70
DEFAULT_COMBINED_MEDIUM = 0.40

# Katman 1 ic sabitleri
SHINGLE_SIZE = 5                 # n-gram (shingle) uzunlugu - kelime bazli
SENTENCE_MATCH_THRESHOLD = 0.60  # cumle eslesmesi icin alt sinir
SENTENCE_PREFILTER = 0.25        # difflib'e girmeden once kelime-kumesi Jaccard
MIN_SENTENCE_WORDS = 6           # bundan kisa cumleler gurultudur
MIN_BLOCK_TOKENS = 8             # "kopyala-yapistir" sayilan en kisa blok
MAX_TOKENS_FOR_DIFF = 4000       # bir raporun difflib'e giren token tavani
DEEP_CANDIDATE_LIMIT = 40        # agir analiz yalnizca en umit vaadeden N aday

# Katman 2 ic sabitleri
CHUNK_WORDS = 500
CHUNK_OVERLAP_WORDS = 100
MAX_QUERY_CHUNKS = 40            # cok uzun raporlarda embedding maliyet tavani
SEMANTIC_PEAK_WEIGHT = 0.60      # semantic = 0.60*zirve + 0.40*kapsama
SEMANTIC_COMBINE_WEIGHT = 0.90   # combined = max(literal, 0.90*semantic)

_CF_ACCOUNT_ENV = "CLOUDFLARE_ACCOUNT_ID"
_CF_TOKEN_ENV = "CLOUDFLARE_API_TOKEN"
_CF_MODEL_ENV = "CLOUDFLARE_EMBEDDING_MODEL"
_CF_VECTORIZE_ENV = "CLOUDFLARE_VECTORIZE_INDEX"
_OPENAI_KEY_ENV = "OPENAI_API_KEY"
_OPENAI_MODEL_ENV = "OPENAI_EMBEDDING_MODEL"

_CF_DEFAULT_MODEL = "@cf/baai/bge-m3"
_CF_DEFAULT_DIM = 1024
_OPENAI_DEFAULT_MODEL = "text-embedding-3-small"
_OPENAI_DEFAULT_DIM = 1536

_HTTP_TIMEOUT = 45


# ═══════════════════════════════════════════════════════════════════════════
# Hatalar
# ═══════════════════════════════════════════════════════════════════════════
class SimilarityError(RuntimeError):
    """Benzerlik motoru hatalarinin tabani."""


class EmbeddingUnavailable(SimilarityError):
    """Embedding saglayicisi yapilandirilmamis ya da cevap veremiyor."""


# ═══════════════════════════════════════════════════════════════════════════
# Metin normalizasyonu
# ═══════════════════════════════════════════════════════════════════════════
# Turkce'de str.lower() dogru calismaz: "I" -> "i" olur ama "İ" -> "i̇"
# (birlesik nokta) uretir. Once harf haritasi uygulanir.
_TR_LOWER_MAP = str.maketrans({"I": "ı", "İ": "i", "Â": "â", "Î": "î", "Û": "û"})

# Karsilastirmada s-cedilla'li "sartname" ile ASCII yazimi ayni sayilmalidir.
_TR_FOLD_MAP = str.maketrans(
    {
        "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
        "â": "a", "î": "i", "û": "u", "é": "e",
    }
)

_WORD_RE = re.compile(r"\w+", re.UNICODE)
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*", re.UNICODE)
_WS_RE = re.compile(r"\s+", re.UNICODE)


def turkish_lower(text: str) -> str:
    """Turkce'ye dogru kucuk harf donusumu."""
    return (text or "").translate(_TR_LOWER_MAP).lower()


def normalize(text: str) -> str:
    """Karsilastirma icin metni sadelestirir.

    Kucuk harf -> Turkce karakter katlama -> noktalama temizligi ->
    tek bosluk. Kaynak metin DEGISTIRILMEZ; yalnizca olcum icin kullanilir.
    """
    if not text:
        return ""
    folded = unicodedata.normalize("NFC", text)
    folded = turkish_lower(folded).translate(_TR_FOLD_MAP)
    # Noktalama ve simgeleri bosluga cevir (rakam + harf kalir).
    folded = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in folded)
    return _WS_RE.sub(" ", folded).strip()


def _fold_word(word: str) -> str:
    """Tek kelimeyi normalize eder (token listeleri icin)."""
    return turkish_lower(word).translate(_TR_FOLD_MAP)


# ═══════════════════════════════════════════════════════════════════════════
# Belge gorunumu - Report modeli, dict veya duz nesne kabul eder
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class _Token:
    text: str
    start: int
    end: int


@dataclass
class _Sentence:
    raw: str
    norm: str
    words: frozenset[str]
    start: int
    end: int


class Document:
    """Bir raporun benzerlik analizi icin on-islenmis hali."""

    __slots__ = ("report_id", "label", "text", "tokens", "shingles",
                 "sentences", "_token_words")

    def __init__(self, report_id: str, label: str, text: str) -> None:
        self.report_id = report_id
        self.label = label
        self.text = text or ""
        self.tokens: list[_Token] = _tokenize(self.text)
        self._token_words: list[str] = [t.text for t in self.tokens]
        self.shingles: frozenset[str] = _shingles(self._token_words, SHINGLE_SIZE)
        self.sentences: list[_Sentence] = _sentences(self.text)

    @property
    def token_words(self) -> list[str]:
        return self._token_words

    @property
    def word_set(self) -> frozenset[str]:
        return frozenset(self._token_words)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.tokens)


def _tokenize(text: str) -> list[_Token]:
    """Kaynak metindeki karakter konumlarini KORUYARAK token listesi uretir.

    Konumlarin korunmasi sart: hakeme gosterilecek span'ler orijinal metnin
    karakter araligina isaret etmek zorunda.
    """
    out: list[_Token] = []
    for match in _WORD_RE.finditer(text or ""):
        folded = _fold_word(match.group())
        if not folded:
            continue
        out.append(_Token(text=folded, start=match.start(), end=match.end()))
    return out


def _shingles(words: Sequence[str], size: int) -> frozenset[str]:
    """Kelime bazli n-gram (shingle) kumesi.

    Kopyala-yapistir tespitinde difflib'den cok daha hizli ve olcek
    bagimsizdir: iki metin ayni 5'li kelime dizilerini paylasiyorsa bu
    tesadufi degildir.
    """
    if len(words) < size:
        return frozenset([" ".join(words)]) if words else frozenset()
    return frozenset(
        " ".join(words[i:i + size]) for i in range(len(words) - size + 1)
    )


def _sentences(text: str) -> list[_Sentence]:
    """Metni kaba cumlelere boler; her cumlenin karakter araligini saklar."""
    out: list[_Sentence] = []
    for match in _SENTENCE_RE.finditer(text or ""):
        raw = match.group()
        stripped = raw.strip()
        if len(stripped.split()) < MIN_SENTENCE_WORDS:
            continue
        offset = match.start() + (len(raw) - len(raw.lstrip()))
        norm = normalize(stripped)
        if not norm:
            continue
        out.append(
            _Sentence(
                raw=stripped,
                norm=norm,
                words=frozenset(norm.split()),
                start=offset,
                end=offset + len(stripped),
            )
        )
    return out


def _jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    if not left or not right:
        return 0.0
    inter = len(left & right)
    if not inter:
        return 0.0
    return inter / len(left | right)


def as_document(source: Any) -> Document:
    """Report modeli / dict / duz nesneden Document uretir.

    UI ve testler ayni motoru farkli tiplerle cagirabilsin diye tek giris
    noktasi burasidir.
    """
    if isinstance(source, Document):
        return source
    if isinstance(source, dict):
        report_id = str(source.get("report_id") or source.get("id") or "")
        label = str(
            source.get("label")
            or source.get("file_name")
            or source.get("project_title")
            or ""
        )
        text = str(source.get("report_text") or source.get("text") or "")
    else:
        report_id = str(getattr(source, "report_id", "") or getattr(source, "id", "") or "")
        label = str(
            getattr(source, "label", None)
            or getattr(source, "file_name", None)
            or getattr(source, "project_title", None)
            or ""
        )
        text = str(getattr(source, "report_text", None) or getattr(source, "text", None) or "")
    if not report_id:
        raise SimilarityError("Belgede report_id yok; benzerlik analizi yapilamaz.")
    return Document(report_id=report_id, label=label or report_id[:8], text=text)


# ═══════════════════════════════════════════════════════════════════════════
# Cikti tipleri
# ═══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class MatchSpan:
    """Hakeme gosterilecek somut kanit parcasi."""

    kind: str                 # "blok" | "cumle" | "anlamsal"
    quote: str                # sorgu raporundaki metin
    matched_quote: str        # eslesen rapordaki karsiligi
    matched_report_id: str
    ratio: float
    query_start: int          # sorgu raporundaki yaklasik karakter araligi
    query_end: int
    matched_start: int        # eslesen rapordaki yaklasik karakter araligi
    matched_end: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "quote": self.quote,
            "matched_quote": self.matched_quote,
            "matched_report_id": self.matched_report_id,
            "ratio": round(self.ratio, 4),
            "query_range": [self.query_start, self.query_end],
            "matched_range": [self.matched_start, self.matched_end],
        }


@dataclass(frozen=True)
class SimilarityMatch:
    matched_report_id: str
    matched_label: str
    literal_score: float
    semantic_score: float
    combined_score: float
    risk_level: Any                      # RiskLevel (enum yoksa str)
    spans: tuple[MatchSpan, ...] = ()
    literal_detail: dict[str, float] = field(default_factory=dict)
    semantic_available: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "matched_report_id": self.matched_report_id,
            "matched_label": self.matched_label,
            "literal_score": round(self.literal_score, 4),
            "semantic_score": round(self.semantic_score, 4),
            "combined_score": round(self.combined_score, 4),
            "risk_level": getattr(self.risk_level, "value", str(self.risk_level)),
            "semantic_available": self.semantic_available,
            "literal_detail": {k: round(v, 4) for k, v in self.literal_detail.items()},
            "spans": [s.to_dict() for s in self.spans],
        }


@dataclass(frozen=True)
class SimilarityReport:
    report_id: str
    matches: tuple[SimilarityMatch, ...]
    highest: float
    risk_level: Any
    literal_available: bool
    semantic_available: bool
    engine_version: str
    notes: tuple[str, ...] = ()

    @property
    def is_high_risk(self) -> bool:
        return getattr(self.risk_level, "value", str(self.risk_level)) == "YUKSEK"

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "highest": round(self.highest, 4),
            "risk_level": getattr(self.risk_level, "value", str(self.risk_level)),
            "is_high_risk": self.is_high_risk,
            "literal_available": self.literal_available,
            "semantic_available": self.semantic_available,
            "engine_version": self.engine_version,
            "notes": list(self.notes),
            "matches": [m.to_dict() for m in self.matches],
        }


# RiskLevel enum'u veri katmanindan gelir; bagimsiz test icin geri dusulur.
try:  # pragma: no cover - import yolu ortama bagli
    from ..data.enums import RiskLevel
except ImportError:  # pragma: no cover
    try:
        from src.data.enums import RiskLevel  # type: ignore[no-redef]
    except ImportError:
        class RiskLevel(str):  # type: ignore[no-redef]
            """Veri katmani yokken kullanilan asgari yedek."""

            DUSUK = "DUSUK"
            ORTA = "ORTA"
            YUKSEK = "YUKSEK"

        RiskLevel.DUSUK = "DUSUK"       # type: ignore[attr-defined]
        RiskLevel.ORTA = "ORTA"         # type: ignore[attr-defined]
        RiskLevel.YUKSEK = "YUKSEK"     # type: ignore[attr-defined]


# ═══════════════════════════════════════════════════════════════════════════
# KATMAN 1 - Literal (difflib + n-gram)
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class LiteralOutcome:
    score: float
    detail: dict[str, float]
    spans: list[MatchSpan]


class LiteralMatcher:
    """Birebir / kopyala-yapistir katmani. Harici bagimlilik yoktur."""

    def __init__(
        self,
        *,
        sentence_threshold: float = SENTENCE_MATCH_THRESHOLD,
        max_spans: int = 5,
        deep_limit: int = DEEP_CANDIDATE_LIMIT,
    ) -> None:
        self.sentence_threshold = sentence_threshold
        self.max_spans = max_spans
        self.deep_limit = deep_limit

    # ── genel API ─────────────────────────────────────────────────────────
    def compare_all(
        self, query: Document, corpus: Sequence[Document]
    ) -> dict[str, LiteralOutcome]:
        """Tum korpusu olcer.

        Maliyet kontrolu: ucuz shingle/kelime Jaccard tum adaylar icin
        hesaplanir, PAHALI difflib analizi yalnizca en umit vaadeden
        `deep_limit` aday icin calisir. Boylece 400 raporluk korpusta da
        surekli calisabilir.
        """
        cheap: list[tuple[float, Document, float, float]] = []
        for cand in corpus:
            shingle_j = _jaccard(query.shingles, cand.shingles)
            word_j = _jaccard(query.word_set, cand.word_set)
            cheap.append((max(shingle_j, 0.5 * word_j), cand, shingle_j, word_j))

        cheap.sort(key=lambda item: item[0], reverse=True)
        deep_ids = {item[1].report_id for item in cheap[: self.deep_limit]}

        out: dict[str, LiteralOutcome] = {}
        for _, cand, shingle_j, word_j in cheap:
            if cand.report_id in deep_ids:
                out[cand.report_id] = self.compare(query, cand, shingle_j, word_j)
            else:
                # Ucuz katman: shingle Jaccard tek basina da gecerli bir
                # kopya gostergesidir; span uretilmez.
                out[cand.report_id] = LiteralOutcome(
                    score=round(shingle_j, 6),
                    detail={"shingle_jaccard": shingle_j, "word_jaccard": word_j,
                            "derin_analiz": 0.0},
                    spans=[],
                )
        return out

    def compare(
        self,
        query: Document,
        candidate: Document,
        shingle_j: float | None = None,
        word_j: float | None = None,
    ) -> LiteralOutcome:
        """Iki belge arasinda tam literal olcumu."""
        if shingle_j is None:
            shingle_j = _jaccard(query.shingles, candidate.shingles)
        if word_j is None:
            word_j = _jaccard(query.word_set, candidate.word_set)

        holistic = self._holistic_ratio(query, candidate)
        sentence_peak, sentence_spans = self._sentence_spans(query, candidate)
        coverage, block_spans = self._block_spans(query, candidate)

        # Dort olcumun EN GUCLU kanidi alinir; hicbiri digerini bastirmaz.
        # DIKKAT: `sentence_peak` yalnizca esigi GECEN bir cumle eslesmesi
        # varsa skora katilir. Ayni dildeki iki alakasiz cumle bile karakter
        # duzeyinde ~0.45 oran verir; esik altini skora katmak her raporu
        # yapay olarak %25 bandina cikariyordu.
        score = max(
            holistic,
            shingle_j,
            coverage,
            0.5 * holistic + 0.5 * sentence_peak,
        )
        score = max(0.0, min(1.0, score))

        spans = block_spans + sentence_spans
        spans.sort(key=lambda s: s.ratio, reverse=True)

        return LiteralOutcome(
            score=round(score, 6),
            detail={
                "holistic": holistic,
                "shingle_jaccard": shingle_j,
                "word_jaccard": word_j,
                "sentence_peak": sentence_peak,
                "block_coverage": coverage,
                "derin_analiz": 1.0,
            },
            spans=spans[: self.max_spans],
        )

    # ── ic olcumler ───────────────────────────────────────────────────────
    @staticmethod
    def _holistic_ratio(query: Document, candidate: Document) -> float:
        """Butunsel SequenceMatcher orani - KELIME dizisi uzerinde.

        Karakter dizisi uzerinde calistirmak (eski kod) ayni dildeki iki
        alakasiz metne bile ~0.45 taban skor verir; kelime dizisi cok daha
        ayirt edicidir ve daha hizlidir.
        """
        left = query.token_words[:MAX_TOKENS_FOR_DIFF]
        right = candidate.token_words[:MAX_TOKENS_FOR_DIFF]
        if not left or not right:
            return 0.0
        matcher = SequenceMatcher(None, left, right, autojunk=False)
        # Ucuz ust sinir once: gercek orani hesaplamaya deger mi?
        if matcher.real_quick_ratio() < 0.05:
            return 0.0
        return matcher.ratio()

    def _sentence_spans(
        self, query: Document, candidate: Document
    ) -> tuple[float, list[MatchSpan]]:
        """Cumle bazli en yuksek ortusmeler + alinti span'leri.

        Once ucuz kelime-kumesi Jaccard on elemesi yapilir; difflib yalnizca
        on elemeyi gecen cumle ciftlerinde calisir.

        Donen zirve degeri, YALNIZCA `sentence_threshold` esigini gecen
        eslesmeler uzerinden hesaplanir; esigi gecen yoksa 0.0 doner.
        """
        best_overall = 0.0
        spans: list[MatchSpan] = []
        if not query.sentences or not candidate.sentences:
            return 0.0, spans

        for q_sent in query.sentences:
            best_ratio = 0.0
            best_match: _Sentence | None = None
            for c_sent in candidate.sentences:
                if _jaccard(q_sent.words, c_sent.words) < SENTENCE_PREFILTER:
                    continue
                ratio = SequenceMatcher(None, q_sent.norm, c_sent.norm).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = c_sent
            if best_ratio >= self.sentence_threshold and best_match is not None:
                if best_ratio > best_overall:
                    best_overall = best_ratio
                spans.append(
                    MatchSpan(
                        kind="cumle",
                        quote=q_sent.raw,
                        matched_quote=best_match.raw,
                        matched_report_id=candidate.report_id,
                        ratio=best_ratio,
                        query_start=q_sent.start,
                        query_end=q_sent.end,
                        matched_start=best_match.start,
                        matched_end=best_match.end,
                    )
                )
        spans.sort(key=lambda s: s.ratio, reverse=True)
        return best_overall, spans[: self.max_spans]

    def _block_spans(
        self, query: Document, candidate: Document
    ) -> tuple[float, list[MatchSpan]]:
        """Kesintisiz ortak kelime bloklari - en net kopyala-yapistir kaniti.

        Donen kapsama orani: sorgu raporunun kac katinin uzun ortak bloklar
        icinde oldugudur.
        """
        left = query.token_words[:MAX_TOKENS_FOR_DIFF]
        right = candidate.token_words[:MAX_TOKENS_FOR_DIFF]
        if not left or not right:
            return 0.0, []

        matcher = SequenceMatcher(None, left, right, autojunk=False)
        covered = 0
        spans: list[MatchSpan] = []
        for block in matcher.get_matching_blocks():
            if block.size < MIN_BLOCK_TOKENS:
                continue
            covered += block.size
            q_start = query.tokens[block.a].start
            q_end = query.tokens[block.a + block.size - 1].end
            c_start = candidate.tokens[block.b].start
            c_end = candidate.tokens[block.b + block.size - 1].end
            spans.append(
                MatchSpan(
                    kind="blok",
                    quote=query.text[q_start:q_end],
                    matched_quote=candidate.text[c_start:c_end],
                    matched_report_id=candidate.report_id,
                    # Blok tam ortusme oldugu icin oran 1.0; agirligi uzunlugu belirler.
                    ratio=1.0,
                    query_start=q_start,
                    query_end=q_end,
                    matched_start=c_start,
                    matched_end=c_end,
                )
            )
        coverage = covered / len(left) if left else 0.0
        spans.sort(key=lambda s: s.query_end - s.query_start, reverse=True)
        return coverage, spans[: self.max_spans]


# ═══════════════════════════════════════════════════════════════════════════
# HTTP yardimcilari (requests varsa o, yoksa urllib)
# ═══════════════════════════════════════════════════════════════════════════
def _http_post(
    url: str,
    *,
    token: str,
    body: bytes,
    content_type: str,
    timeout: int = _HTTP_TIMEOUT,
) -> tuple[int, Any]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": content_type,
        "User-Agent": "T-Sistem/1.0",
    }
    try:
        import requests  # type: ignore
    except ImportError:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
                return resp.status, _loads_or_text(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            return exc.code, _loads_or_text(raw)

    resp = requests.post(url, data=body, headers=headers, timeout=timeout)
    return resp.status_code, _loads_or_text(resp.text)


def _loads_or_text(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "errors": [{"message": raw[:400]}]}


# ═══════════════════════════════════════════════════════════════════════════
# KATMAN 2 - Embedding saglayicilari
# ═══════════════════════════════════════════════════════════════════════════
class EmbeddingProvider:
    """Embedding saglayicisi arayuzu."""

    name = "abstract"
    model = ""
    dim = 0
    batch_size = 32

    @property
    def available(self) -> bool:  # pragma: no cover - alt siniflar doldurur
        return False

    def embed(self, texts: Sequence[str]) -> list[list[float]]:  # pragma: no cover
        raise NotImplementedError


class CloudflareEmbeddingProvider(EmbeddingProvider):
    """Cloudflare Workers AI - @cf/baai/bge-m3 (cok dilli, Turkce'de iyi)."""

    name = "cloudflare"
    batch_size = 50

    _ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/{acc}/ai/run/{model}"

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        model: str | None = None,
    ) -> None:
        self.account_id = account_id or os.getenv(_CF_ACCOUNT_ENV, "")
        self.api_token = api_token or os.getenv(_CF_TOKEN_ENV, "")
        self.model = model or os.getenv(_CF_MODEL_ENV, "") or _CF_DEFAULT_MODEL
        self.dim = _CF_DEFAULT_DIM

    @property
    def available(self) -> bool:
        return bool(self.account_id and self.api_token)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.available:
            raise EmbeddingUnavailable(
                f"{_CF_ACCOUNT_ENV} / {_CF_TOKEN_ENV} tanimli degil."
            )
        url = self._ENDPOINT.format(acc=self.account_id, model=self.model)
        vectors: list[list[float]] = []
        for batch in _batched(list(texts), self.batch_size):
            payload = json.dumps({"text": list(batch)}).encode("utf-8")
            status, data = _http_post(
                url, token=self.api_token, body=payload, content_type="application/json"
            )
            vectors.extend(self._parse(status, data, len(batch)))
        return vectors

    def _parse(self, status: int, data: Any, expected: int) -> list[list[float]]:
        if not isinstance(data, dict) or not data.get("success"):
            message = _cf_error(data) or f"HTTP {status}"
            raise EmbeddingUnavailable(f"Workers AI reddetti: {message}")
        result = data.get("result") or {}
        raw = result.get("data")
        if raw is None and isinstance(result.get("response"), dict):
            raw = result["response"].get("data")
        if not isinstance(raw, list) or len(raw) != expected:
            raise EmbeddingUnavailable(
                f"Workers AI beklenmeyen yanit sekli (beklenen {expected} vektor)."
            )
        out = [[float(x) for x in vec] for vec in raw]
        if out and out[0]:
            self.dim = len(out[0])
        return out


class OpenAIEmbeddingProvider(EmbeddingProvider):
    """Yedek saglayici - text-embedding-3-small."""

    name = "openai"
    batch_size = 64

    _ENDPOINT = "https://api.openai.com/v1/embeddings"

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self.api_key = api_key or os.getenv(_OPENAI_KEY_ENV, "")
        self.model = model or os.getenv(_OPENAI_MODEL_ENV, "") or _OPENAI_DEFAULT_MODEL
        self.dim = _OPENAI_DEFAULT_DIM

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not self.available:
            raise EmbeddingUnavailable(f"{_OPENAI_KEY_ENV} tanimli degil.")
        vectors: list[list[float]] = []
        for batch in _batched(list(texts), self.batch_size):
            payload = json.dumps({"model": self.model, "input": list(batch)}).encode("utf-8")
            status, data = _http_post(
                self._ENDPOINT, token=self.api_key, body=payload,
                content_type="application/json",
            )
            if not isinstance(data, dict) or "data" not in data:
                message = ""
                if isinstance(data, dict):
                    message = str((data.get("error") or {}).get("message", ""))
                raise EmbeddingUnavailable(
                    f"OpenAI embedding hatasi: {message or f'HTTP {status}'}"
                )
            ordered = sorted(data["data"], key=lambda item: int(item.get("index", 0)))
            vectors.extend([[float(x) for x in item["embedding"]] for item in ordered])
        if vectors and vectors[0]:
            self.dim = len(vectors[0])
        return vectors


def resolve_provider(
    provider: EmbeddingProvider | None = None,
) -> tuple[EmbeddingProvider | None, str]:
    """Saglayicilari SIRAYLA dener: Cloudflare -> OpenAI -> yok.

    Hicbiri yoksa (None, sebep) doner. SAHTE VEKTOR URETILMEZ.
    """
    if provider is not None:
        if provider.available:
            return provider, ""
        return None, f"Verilen saglayici ({provider.name}) yapilandirilmamis."

    cloudflare = CloudflareEmbeddingProvider()
    if cloudflare.available:
        return cloudflare, ""
    openai = OpenAIEmbeddingProvider()
    if openai.available:
        return openai, ""
    return None, (
        "Anlamsal katman devre disi: embedding saglayicisi yok "
        f"({_CF_ACCOUNT_ENV}+{_CF_TOKEN_ENV} veya {_OPENAI_KEY_ENV} tanimlayin)."
    )


def _batched(items: list[Any], size: int) -> Iterable[list[Any]]:
    for i in range(0, len(items), max(1, size)):
        yield items[i:i + size]


def _cf_error(data: Any) -> str:
    if not isinstance(data, dict):
        return ""
    errors = data.get("errors") or []
    return "; ".join(str(e.get("message", e)) for e in errors)


# ═══════════════════════════════════════════════════════════════════════════
# Chunk + kosinus
# ═══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Chunk:
    index: int
    text: str
    start: int
    end: int


def chunk_text(
    text: str,
    *,
    words_per_chunk: int = CHUNK_WORDS,
    overlap_words: int = CHUNK_OVERLAP_WORDS,
) -> list[Chunk]:
    """Metni ~500 kelimelik ORTUSEN parcalara boler.

    Ortusme sart: parca sinirina denk gelen kopya paragraf boluneceginden,
    ortusme olmadan kacar.
    """
    matches = list(_WORD_RE.finditer(text or ""))
    if not matches:
        return []
    step = max(1, words_per_chunk - max(0, overlap_words))
    chunks: list[Chunk] = []
    index = 0
    for begin in range(0, len(matches), step):
        window = matches[begin:begin + words_per_chunk]
        if not window:
            break
        start = window[0].start()
        end = window[-1].end()
        chunks.append(Chunk(index=index, text=text[start:end], start=start, end=end))
        index += 1
        if begin + words_per_chunk >= len(matches):
            break
    return chunks


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    """Kosinus benzerligi, 0..1 araligina kirpilir."""
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = 0.0
    norm_l = 0.0
    norm_r = 0.0
    for a, b in zip(left, right):
        dot += a * b
        norm_l += a * a
        norm_r += b * b
    if norm_l <= 0.0 or norm_r <= 0.0:
        return 0.0
    value = dot / (math.sqrt(norm_l) * math.sqrt(norm_r))
    return max(0.0, min(1.0, value))


# ═══════════════════════════════════════════════════════════════════════════
# Vektor deposu - Vectorize, yoksa D1 + yerel kosinus
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class StoredChunk:
    report_id: str
    chunk_index: int
    chunk_text: str
    vector: list[float]


_VECTOR_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS report_embedding_vectors (
    report_id    TEXT NOT NULL,
    chunk_index  INTEGER NOT NULL,
    vector_json  TEXT NOT NULL,
    dim          INTEGER NOT NULL,
    model        TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (report_id, chunk_index)
);
"""


class D1VectorStore:
    """Vectorize yokken calisan yedek: D1'de sakla, yerel kosinus ile ara."""

    def __init__(self, client: Any) -> None:
        self.db = client
        self._ready = False

    def ensure(self) -> None:
        if self._ready:
            return
        self.db.execute(_VECTOR_TABLE_DDL.strip())
        self._ready = True

    def upsert(
        self, report_id: str, model: str, dim: int,
        chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], created_at: str,
    ) -> int:
        self.ensure()
        statements: list[tuple[str, list[Any]]] = []
        for chunk, vector in zip(chunks, vectors):
            vector_id = f"{report_id}:{chunk.index}"
            statements.append((
                "INSERT INTO report_embeddings "
                "(report_id, chunk_index, chunk_text, page_no, vector_id, model, dim, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(report_id, chunk_index) DO UPDATE SET "
                "chunk_text=excluded.chunk_text, vector_id=excluded.vector_id, "
                "model=excluded.model, dim=excluded.dim, created_at=excluded.created_at;",
                [report_id, chunk.index, chunk.text, None, vector_id, model, dim, created_at],
            ))
            statements.append((
                "INSERT INTO report_embedding_vectors "
                "(report_id, chunk_index, vector_json, dim, model, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(report_id, chunk_index) DO UPDATE SET "
                "vector_json=excluded.vector_json, dim=excluded.dim, "
                "model=excluded.model, created_at=excluded.created_at;",
                [report_id, chunk.index,
                 json.dumps([round(float(x), 6) for x in vector]), dim, model, created_at],
            ))
        self.db.batch(statements)
        return len(chunks)

    def fetch(self, report_ids: Sequence[str], model: str) -> dict[str, list[StoredChunk]]:
        """Verilen raporlarin saklanmis chunk vektorlerini okur."""
        self.ensure()
        out: dict[str, list[StoredChunk]] = {}
        for group in _batched(list(report_ids), 100):
            if not group:
                continue
            marks = ", ".join("?" for _ in group)
            rows = self.db.query(
                "SELECT e.report_id, e.chunk_index, e.chunk_text, v.vector_json "
                "FROM report_embeddings e "
                "JOIN report_embedding_vectors v "
                "  ON v.report_id = e.report_id AND v.chunk_index = e.chunk_index "
                f"WHERE e.report_id IN ({marks}) AND e.model = ? "
                "ORDER BY e.report_id, e.chunk_index;",
                list(group) + [model],
            )
            for row in rows:
                vector = json.loads(str(row["vector_json"]))
                out.setdefault(str(row["report_id"]), []).append(
                    StoredChunk(
                        report_id=str(row["report_id"]),
                        chunk_index=int(row["chunk_index"]),
                        chunk_text=str(row["chunk_text"] or ""),
                        vector=[float(x) for x in vector],
                    )
                )
        return out


class VectorizeStore:
    """Cloudflare Vectorize v2 istemcisi (ndjson upsert + query)."""

    _BASE = "https://api.cloudflare.com/client/v4/accounts/{acc}/vectorize/v2/indexes/{idx}"

    def __init__(
        self,
        account_id: str | None = None,
        api_token: str | None = None,
        index_name: str | None = None,
    ) -> None:
        self.account_id = account_id or os.getenv(_CF_ACCOUNT_ENV, "")
        self.api_token = api_token or os.getenv(_CF_TOKEN_ENV, "")
        self.index_name = index_name or os.getenv(_CF_VECTORIZE_ENV, "")

    @property
    def available(self) -> bool:
        return bool(self.account_id and self.api_token and self.index_name)

    def _url(self, suffix: str) -> str:
        return self._BASE.format(acc=self.account_id, idx=self.index_name) + suffix

    def upsert(
        self, report_id: str, chunks: Sequence[Chunk],
        vectors: Sequence[Sequence[float]], metadata: dict[str, Any] | None = None,
    ) -> int:
        if not self.available:
            raise SimilarityError("Vectorize yapilandirilmamis.")
        lines: list[str] = []
        for chunk, vector in zip(chunks, vectors):
            meta = dict(metadata or {})
            meta.update({"report_id": report_id, "chunk_index": chunk.index})
            lines.append(json.dumps({
                "id": f"{report_id}:{chunk.index}",
                "values": [float(x) for x in vector],
                "metadata": meta,
            }, ensure_ascii=False))
        body = ("\n".join(lines) + "\n").encode("utf-8")
        status, data = _http_post(
            self._url("/upsert"), token=self.api_token, body=body,
            content_type="application/x-ndjson",
        )
        if not isinstance(data, dict) or not data.get("success"):
            raise SimilarityError(
                f"Vectorize upsert reddedildi: {_cf_error(data) or f'HTTP {status}'}"
            )
        return len(lines)

    def query(
        self, vector: Sequence[float], *, top_k: int = 20,
        vector_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if not self.available:
            raise SimilarityError("Vectorize yapilandirilmamis.")
        payload: dict[str, Any] = {
            "vector": [float(x) for x in vector],
            "topK": int(top_k),
            "returnMetadata": "all",
        }
        if vector_filter:
            payload["filter"] = vector_filter
        status, data = _http_post(
            self._url("/query"), token=self.api_token,
            body=json.dumps(payload).encode("utf-8"),
            content_type="application/json",
        )
        if not isinstance(data, dict) or not data.get("success"):
            raise SimilarityError(
                f"Vectorize query reddedildi: {_cf_error(data) or f'HTTP {status}'}"
            )
        return list((data.get("result") or {}).get("matches") or [])


# ═══════════════════════════════════════════════════════════════════════════
# KATMAN 2 - Anlamsal esleyici
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class SemanticOutcome:
    score: float
    spans: list[MatchSpan]


class SemanticMatcher:
    """Embedding tabanli anlamsal katman.

    Saglayici yoksa `available = False` doner ve HICBIR skor uretmez.
    """

    def __init__(
        self,
        provider: EmbeddingProvider | None = None,
        vectorize: VectorizeStore | None = None,
        d1_store: D1VectorStore | None = None,
    ) -> None:
        self.provider, self.reason = resolve_provider(provider)
        self.vectorize = vectorize if vectorize is not None else VectorizeStore()
        self.d1_store = d1_store

    @property
    def available(self) -> bool:
        return self.provider is not None

    @property
    def model(self) -> str:
        return self.provider.model if self.provider else ""

    def embed_document(self, doc: Document, *, limit: int = MAX_QUERY_CHUNKS
                       ) -> tuple[list[Chunk], list[list[float]]]:
        """Belgeyi parcalara boler ve vektorlestirir."""
        if self.provider is None:
            raise EmbeddingUnavailable(self.reason)
        chunks = chunk_text(doc.text)[:limit]
        if not chunks:
            return [], []
        vectors = self.provider.embed([c.text for c in chunks])
        if len(vectors) != len(chunks):
            raise EmbeddingUnavailable(
                f"Saglayici {len(chunks)} parca icin {len(vectors)} vektor dondu."
            )
        return chunks, vectors

    def compare(
        self,
        query_chunks: Sequence[Chunk],
        query_vectors: Sequence[Sequence[float]],
        candidate: Document,
        stored: Sequence[StoredChunk],
    ) -> SemanticOutcome:
        """Sorgu ile bir adayin chunk vektorlerini karsilastirir.

        Skor = 0.60 * zirve + 0.40 * kapsama
          zirve   : en yuksek chunk cifti kosinusu (tek paragraf kopyasini yakalar)
          kapsama : sorgu parcalarinin ortalama en iyi kosinusu (butunsel ortusme)
        """
        if not query_vectors or not stored:
            return SemanticOutcome(score=0.0, spans=[])

        best_per_query: list[tuple[float, int, StoredChunk]] = []
        for q_index, q_vec in enumerate(query_vectors):
            best_ratio = 0.0
            best_chunk: StoredChunk | None = None
            for item in stored:
                ratio = cosine_similarity(q_vec, item.vector)
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_chunk = item
            if best_chunk is not None:
                best_per_query.append((best_ratio, q_index, best_chunk))

        if not best_per_query:
            return SemanticOutcome(score=0.0, spans=[])

        peak = max(item[0] for item in best_per_query)
        coverage = sum(item[0] for item in best_per_query) / len(best_per_query)
        score = SEMANTIC_PEAK_WEIGHT * peak + (1.0 - SEMANTIC_PEAK_WEIGHT) * coverage

        spans: list[MatchSpan] = []
        for ratio, q_index, item in sorted(best_per_query, key=lambda x: x[0], reverse=True)[:3]:
            if ratio < 0.75:
                continue
            q_chunk = query_chunks[q_index]
            spans.append(
                MatchSpan(
                    kind="anlamsal",
                    quote=_clip(q_chunk.text),
                    matched_quote=_clip(item.chunk_text),
                    matched_report_id=candidate.report_id,
                    ratio=ratio,
                    query_start=q_chunk.start,
                    query_end=q_chunk.end,
                    matched_start=-1,   # saklanan chunk'ta karakter ofseti tutulmuyor
                    matched_end=-1,
                )
            )
        return SemanticOutcome(score=max(0.0, min(1.0, score)), spans=spans)


def _clip(text: str, limit: int = 400) -> str:
    text = (text or "").strip()
    return text if len(text) <= limit else text[:limit].rstrip() + "..."


# ═══════════════════════════════════════════════════════════════════════════
# Esikler
# ═══════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Thresholds:
    literal_high: float = DEFAULT_LITERAL_HIGH
    semantic_high: float = DEFAULT_SEMANTIC_HIGH
    combined_high: float = DEFAULT_COMBINED_HIGH
    combined_medium: float = DEFAULT_COMBINED_MEDIUM

    @classmethod
    def load(cls, client: Any | None) -> tuple["Thresholds", str | None]:
        """calibration_settings'ten okur; okunamazsa varsayilanlara doner."""
        if client is None:
            return cls(), None
        keys = {
            "literal_high_threshold": "literal_high",
            "semantic_high_threshold": "semantic_high",
            "similarity_high_threshold": "combined_high",
            "similarity_medium_threshold": "combined_medium",
        }
        try:
            rows = client.query(
                "SELECT key, value FROM calibration_settings WHERE key IN (?, ?, ?, ?);",
                list(keys.keys()),
            )
        except Exception as exc:  # noqa: BLE001 - hata YUTULMAZ, loglanir
            log.warning("[similarity] calibration_settings okunamadi, "
                        "varsayilan esikler kullanilacak: %s", exc)
            return cls(), f"Esikler okunamadi, varsayilanlar kullanildi: {exc}"

        values = {k: getattr(cls(), v) for k, v in keys.items()}
        for row in rows:
            key = str(row.get("key", ""))
            if key in values and row.get("value") is not None:
                values[key] = float(row["value"])
        return cls(**{keys[k]: v for k, v in values.items()}), None


# ═══════════════════════════════════════════════════════════════════════════
# HIBRIT MOTOR
# ═══════════════════════════════════════════════════════════════════════════
class HybridSimilarityEngine:
    """Iki katmani birlestiren ana motor.

    Kullanim:
        engine = HybridSimilarityEngine()
        korpus = repos().reports.corpus_for(rapor)
        sonuc  = engine.analyze(rapor, korpus)
        for m in sonuc.matches:
            print(m.matched_label, m.literal_score, m.semantic_score)
    """

    def __init__(
        self,
        client: Any | None = None,
        *,
        provider: EmbeddingProvider | None = None,
        vectorize: VectorizeStore | None = None,
        literal: LiteralMatcher | None = None,
        semantic: SemanticMatcher | None = None,
        top_k: int = 5,
        engine_version: str = ENGINE_VERSION,
    ) -> None:
        self.engine_version = engine_version
        self.top_k = max(1, top_k)
        self.literal = literal or LiteralMatcher()
        self._client_override = client
        self._client_resolved = client is not None
        self._client: Any | None = client
        self._client_error: str | None = None
        self.semantic = semantic or SemanticMatcher(provider=provider, vectorize=vectorize)

    # ── veritabani (tembel cozulur; DB yoksa motor yine calisir) ──────────
    @property
    def client(self) -> Any | None:
        if not self._client_resolved:
            self._client_resolved = True
            try:
                from ..data.client import get_client
            except ImportError:
                try:
                    from src.data.client import get_client  # type: ignore[no-redef]
                except ImportError as exc:
                    self._client_error = f"Veri katmani yuklenemedi: {exc}"
                    log.warning("[similarity] %s", self._client_error)
                    self._client = None
                    return None
            try:
                self._client = get_client()
            except Exception as exc:  # noqa: BLE001 - loglanir, motor devam eder
                self._client_error = f"Veritabani baglanamadi: {exc}"
                log.warning("[similarity] %s", self._client_error)
                self._client = None
        return self._client

    @property
    def _d1_store(self) -> D1VectorStore | None:
        if self.semantic.d1_store is not None:
            return self.semantic.d1_store
        client = self.client
        if client is None:
            return None
        self.semantic.d1_store = D1VectorStore(client)
        return self.semantic.d1_store

    # ── ANA GIRIS ─────────────────────────────────────────────────────────
    def analyze(
        self,
        report: Any,
        corpus: Sequence[Any] | None = None,
        *,
        persist: bool = True,
    ) -> SimilarityReport:
        """Raporu korpusa karsi olcer ve hakem icin rapor uretir."""
        query = as_document(report)
        notes: list[str] = []

        thresholds, threshold_note = Thresholds.load(self.client)
        if threshold_note:
            notes.append(threshold_note)

        if not query.text.strip():
            notes.append("Rapor metni bos; benzerlik olculemedi")
            return self._empty(query, notes, thresholds)

        documents = [as_document(item) for item in (corpus or [])]
        documents = [d for d in documents if d.report_id != query.report_id and d.text.strip()]

        # ESKI HATA: korpus bossa sabit oran gosterme. Acikca bildir.
        if not documents:
            notes.append("Karsilastirilacak baska rapor yok")
            return self._empty(query, notes, thresholds)

        # ── Katman 1 ──
        literal_results = self.literal.compare_all(query, documents)

        # ── Katman 2 ──
        semantic_results: dict[str, SemanticOutcome] = {}
        semantic_available = False
        if self.semantic.available:
            semantic_results, semantic_available, semantic_notes = self._run_semantic(
                query, documents
            )
            notes.extend(semantic_notes)
        else:
            notes.append(self.semantic.reason)

        # ── Birlestirme ──
        matches: list[SimilarityMatch] = []
        for doc in documents:
            literal_out = literal_results.get(doc.report_id)
            if literal_out is None:
                continue
            semantic_out = semantic_results.get(doc.report_id)
            semantic_score = semantic_out.score if semantic_out else 0.0

            # Birebir kopya daha agir kanittir; anlamsal skor 0.90 ile carpilir.
            combined = max(literal_out.score, SEMANTIC_COMBINE_WEIGHT * semantic_score)
            risk = self._risk_for(literal_out.score, semantic_score, combined,
                                  thresholds, semantic_available)

            spans = list(literal_out.spans)
            if semantic_out:
                spans.extend(semantic_out.spans)

            matches.append(
                SimilarityMatch(
                    matched_report_id=doc.report_id,
                    matched_label=doc.label,
                    literal_score=round(literal_out.score, 4),
                    semantic_score=round(semantic_score, 4),
                    combined_score=round(combined, 4),
                    risk_level=risk,
                    spans=tuple(spans),
                    literal_detail=literal_out.detail,
                    semantic_available=semantic_available,
                )
            )

        matches.sort(key=lambda m: m.combined_score, reverse=True)
        top = matches[: self.top_k]
        highest = top[0].combined_score if top else 0.0
        overall_risk = _worst_risk([m.risk_level for m in top])

        result = SimilarityReport(
            report_id=query.report_id,
            matches=tuple(top),
            highest=round(highest, 4),
            risk_level=overall_risk,
            literal_available=True,
            semantic_available=semantic_available,
            engine_version=self.engine_version,
            notes=tuple(notes),
        )

        if persist:
            persist_note = self._persist(result)
            if persist_note:
                result = SimilarityReport(
                    report_id=result.report_id,
                    matches=result.matches,
                    highest=result.highest,
                    risk_level=result.risk_level,
                    literal_available=result.literal_available,
                    semantic_available=result.semantic_available,
                    engine_version=result.engine_version,
                    notes=result.notes + (persist_note,),
                )
        return result

    # ── Indeksleme ────────────────────────────────────────────────────────
    def index_report(self, report: Any) -> int:
        """Raporun embedding'lerini uretir ve saklar. Dondurur: chunk sayisi.

        Saglayici yoksa 0 doner ve uyari loglar; SAHTE VEKTOR YAZILMAZ.
        """
        doc = as_document(report)
        if not self.semantic.available:
            log.warning("[similarity] index_report atlandi (%s): %s",
                        doc.report_id, self.semantic.reason)
            return 0
        if not doc.text.strip():
            log.warning("[similarity] index_report atlandi: rapor metni bos (%s)",
                        doc.report_id)
            return 0

        try:
            chunks, vectors = self.semantic.embed_document(doc, limit=10_000)
        except (EmbeddingUnavailable, SimilarityError) as exc:
            log.error("[similarity] embedding uretilemedi (%s): %s", doc.report_id, exc)
            return 0
        if not chunks:
            return 0

        dim = len(vectors[0])
        model = self.semantic.model
        created_at = _now_iso()
        written = 0

        if self.semantic.vectorize.available:
            try:
                self.semantic.vectorize.upsert(
                    doc.report_id, chunks, vectors,
                    metadata=_metadata_for(report),
                )
                written = len(chunks)
            except SimilarityError as exc:
                log.warning("[similarity] Vectorize upsert basarisiz, D1'e dusuluyor: %s", exc)

        store = self._d1_store
        if store is None:
            if written:
                log.warning("[similarity] Vectorize'a yazildi ama D1 kaydi yapilamadi (%s)",
                            self._client_error or "veritabani yok")
                return written
            log.error("[similarity] embedding saklanamadi: %s",
                      self._client_error or "veritabani yok")
            return 0

        try:
            store.upsert(doc.report_id, model, dim, chunks, vectors, created_at)
        except Exception as exc:  # noqa: BLE001 - loglanir, cagirana 0 doner
            log.error("[similarity] report_embeddings yazilamadi (%s): %s",
                      doc.report_id, exc)
            return written
        return len(chunks)

    # ── ic yardimcilar ────────────────────────────────────────────────────
    def _run_semantic(
        self, query: Document, documents: Sequence[Document]
    ) -> tuple[dict[str, SemanticOutcome], bool, list[str]]:
        """Anlamsal katmani calistirir; basarisizsa acikca devre disi birakir."""
        notes: list[str] = []
        try:
            query_chunks, query_vectors = self.semantic.embed_document(query)
        except (EmbeddingUnavailable, SimilarityError) as exc:
            log.error("[similarity] anlamsal katman calistirilamadi: %s", exc)
            notes.append(f"Anlamsal katman devre disi: {exc}")
            return {}, False, notes
        if not query_chunks:
            notes.append("Anlamsal katman devre disi: rapor parcalanamadi")
            return {}, False, notes

        store = self._d1_store
        stored: dict[str, list[StoredChunk]] = {}
        if store is not None:
            try:
                stored = store.fetch([d.report_id for d in documents], self.semantic.model)
            except Exception as exc:  # noqa: BLE001 - loglanir
                log.warning("[similarity] saklanan vektorler okunamadi: %s", exc)
                notes.append(f"Saklanan vektorler okunamadi: {exc}")
                stored = {}
        else:
            notes.append(
                "Vektor deposu yok; korpus vektorleri bu calismada uretildi (saklanmadi)"
            )

        # Deposu olmayan adaylar icin vektorler ANINDA uretilir (ve varsa saklanir).
        missing = [d for d in documents if not stored.get(d.report_id)]
        if missing:
            for doc in missing:
                try:
                    chunks, vectors = self.semantic.embed_document(doc)
                except (EmbeddingUnavailable, SimilarityError) as exc:
                    log.warning("[similarity] aday vektorlestirilemedi (%s): %s",
                                doc.report_id, exc)
                    notes.append(f"Aday {doc.report_id[:8]} vektorlestirilemedi: {exc}")
                    continue
                if not chunks:
                    continue
                stored[doc.report_id] = [
                    StoredChunk(doc.report_id, c.index, c.text, list(v))
                    for c, v in zip(chunks, vectors)
                ]
                if store is not None:
                    try:
                        store.upsert(doc.report_id, self.semantic.model, len(vectors[0]),
                                     chunks, vectors, _now_iso())
                    except Exception as exc:  # noqa: BLE001 - loglanir
                        log.warning("[similarity] aday embedding saklanamadi (%s): %s",
                                    doc.report_id, exc)

        results: dict[str, SemanticOutcome] = {}
        for doc in documents:
            items = stored.get(doc.report_id) or []
            results[doc.report_id] = self.semantic.compare(
                query_chunks, query_vectors, doc, items
            )
        return results, True, notes

    @staticmethod
    def _risk_for(
        literal: float, semantic: float, combined: float,
        thresholds: Thresholds, semantic_available: bool,
    ) -> Any:
        """Risk kurali - TEK dogruluk kaynagi."""
        if literal >= thresholds.literal_high:
            return RiskLevel.YUKSEK
        if semantic_available and semantic >= thresholds.semantic_high:
            return RiskLevel.YUKSEK
        if combined >= thresholds.combined_high:
            return RiskLevel.YUKSEK
        if combined >= thresholds.combined_medium:
            return RiskLevel.ORTA
        return RiskLevel.DUSUK

    def _empty(
        self, query: Document, notes: list[str], thresholds: Thresholds
    ) -> SimilarityReport:
        """Olculecek sey yokken: 0.0 doner. ASLA sabit bir oran uydurmaz."""
        return SimilarityReport(
            report_id=query.report_id,
            matches=(),
            highest=0.0,
            risk_level=RiskLevel.DUSUK,
            literal_available=bool(query.text.strip()),
            semantic_available=False,
            engine_version=self.engine_version,
            notes=tuple(notes),
        )

    def _persist(self, result: SimilarityReport) -> str | None:
        """Sonuclari similarity_results tablosuna yazar."""
        client = self.client
        if client is None:
            return f"Sonuclar kaydedilemedi: {self._client_error or 'veritabani yok'}"
        if not result.matches:
            return None

        created_at = _now_iso()
        statements: list[tuple[str, list[Any]]] = []
        for match in result.matches:
            spans_json = json.dumps(
                [s.to_dict() for s in match.spans], ensure_ascii=False
            )
            statements.append((
                "INSERT INTO similarity_results "
                "(result_id, report_id, matched_report_id, literal_score, semantic_score, "
                " combined_score, risk_level, matched_spans_json, engine_version, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(report_id, matched_report_id) DO UPDATE SET "
                "literal_score=excluded.literal_score, "
                "semantic_score=excluded.semantic_score, "
                "combined_score=excluded.combined_score, "
                "risk_level=excluded.risk_level, "
                "matched_spans_json=excluded.matched_spans_json, "
                "engine_version=excluded.engine_version, "
                "created_at=excluded.created_at;",
                [
                    _new_id(), result.report_id, match.matched_report_id,
                    float(match.literal_score), float(match.semantic_score),
                    float(match.combined_score),
                    getattr(match.risk_level, "value", str(match.risk_level)),
                    spans_json, result.engine_version, created_at,
                ],
            ))
        try:
            client.batch(statements)
        except Exception as exc:  # noqa: BLE001 - loglanir + cagirana bildirilir
            log.error("[similarity] similarity_results yazilamadi (%s): %s",
                      result.report_id, exc)
            return f"Sonuclar kaydedilemedi: {exc}"
        return None

    # ── okuma ─────────────────────────────────────────────────────────────
    def stored_results(self, report_id: str) -> list[dict[str, Any]]:
        """Daha once kaydedilmis sonuclari okur (yeniden hesaplamadan)."""
        client = self.client
        if client is None:
            raise SimilarityError(self._client_error or "Veritabani yok.")
        rows = client.query(
            "SELECT * FROM similarity_results WHERE report_id = ? "
            "ORDER BY combined_score DESC;",
            [report_id],
        )
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            raw = item.get("matched_spans_json")
            if raw:
                try:
                    item["matched_spans"] = json.loads(str(raw))
                except json.JSONDecodeError as exc:
                    log.warning("[similarity] span JSON cozulemedi (%s): %s",
                                item.get("result_id"), exc)
                    item["matched_spans"] = []
            else:
                item["matched_spans"] = []
            out.append(item)
        return out


# ═══════════════════════════════════════════════════════════════════════════
# Yardimcilar
# ═══════════════════════════════════════════════════════════════════════════
_RISK_ORDER = {"DUSUK": 0, "ORTA": 1, "YUKSEK": 2}


def _worst_risk(levels: Sequence[Any]) -> Any:
    worst = RiskLevel.DUSUK
    worst_rank = 0
    for level in levels:
        rank = _RISK_ORDER.get(getattr(level, "value", str(level)), 0)
        if rank > worst_rank:
            worst_rank = rank
            worst = level
    return worst


def _metadata_for(report: Any) -> dict[str, Any]:
    """Vectorize metadata - korpusu yarisma/asama bazinda filtrelemek icin."""
    meta: dict[str, Any] = {}
    for key in ("competition_id", "stage_code", "level", "app_id"):
        value = getattr(report, key, None)
        if value is None and isinstance(report, dict):
            value = report.get(key)
        if value is not None:
            meta[key] = str(value)
    return meta


def _now_iso() -> str:
    try:
        from ..data.models import now_iso
        return now_iso()
    except ImportError:
        from datetime import datetime, timezone
        return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    try:
        from ..data.models import new_id
        return new_id()
    except ImportError:
        import uuid
        return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════════
# Kolaylik fonksiyonu
# ═══════════════════════════════════════════════════════════════════════════
def analyze_report(
    report: Any, corpus: Sequence[Any] | None = None, *, persist: bool = True
) -> SimilarityReport:
    """Tek seferlik kullanim icin kisayol."""
    return HybridSimilarityEngine().analyze(report, corpus, persist=persist)


__all__ = [
    "ENGINE_VERSION",
    "SimilarityError", "EmbeddingUnavailable",
    "normalize", "turkish_lower", "chunk_text", "cosine_similarity",
    "Document", "as_document", "Chunk", "StoredChunk",
    "MatchSpan", "SimilarityMatch", "SimilarityReport",
    "LiteralMatcher", "LiteralOutcome",
    "SemanticMatcher", "SemanticOutcome",
    "EmbeddingProvider", "CloudflareEmbeddingProvider", "OpenAIEmbeddingProvider",
    "resolve_provider",
    "VectorizeStore", "D1VectorStore",
    "Thresholds", "HybridSimilarityEngine", "analyze_report",
]
