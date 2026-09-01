"""Başlık tespiti, bölüm ayrıştırma ve şablon uyum kontrolü (MVP 1-3).

İki aşamalı çalışır:
  1) ADAY BAŞLIK TESPİTİ — tipografi (font büyüklüğü/kalınlık) + biçim sinyalleri
     (numaralandırma, kısa satır, büyük harf). Tipografi yoksa (kötü PDF)
     yalnız biçim sinyalleriyle devam eder; yani asla tek sinyale bağımlı değil.
  2) ŞABLONLA EŞLEME — normalize edilmiş başlıklar, şablon başlıkları ve
     alias'larıyla bulanık eşleştirilir (token Jaccard + dizi benzerliği).

Çıktı: her şablon maddesi için bulundu/bulunmadı, eşleşme güveni, kelime sayısı
ve önem derecesi. Hakem ekranı bunu doğrudan gösterebilir.
"""

from __future__ import annotations

import re
import statistics
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher

from ..models import Heading, Section, SectionFinding, Severity, TemplateReport
from .extractor import ExtractionResult, page_of_offset
from .templates import ReportTemplate, SectionSpec

# "1.", "1.2", "II.", "A)" gibi ön ekler
NUMBERING_RE = re.compile(
    r"^\s*((?:\d+(?:\.\d+)*)|(?:[IVXLC]+)|(?:[A-ZÇĞİÖŞÜ]))\s*[\.\)\-–]\s+"
)
TRAILING_DOTS_RE = re.compile(r"[\.\s]{3,}\d+\s*$")  # içindekiler tablosu satırı

# --- Gerçek raporlardan çıkarılan gürültü desenleri ---
#: "Şekil 3.5 Tam Eğitim Sonuçları" · "Tablo 2. Karşılaştırma" · "Figure 4:"
CAPTION_RE = re.compile(
    r"^\s*(şekil|sekil|tablo|çizelge|cizelge|grafik|resim|figure|table|fig\.?|chart)"
    r"\s*[\d\.\:\-–]", re.IGNORECASE
)
#: "[6] Mela veri seti..." · "1. Yazar, A. (2020)." biçimli kaynakça maddeleri
REFERENCE_RE = re.compile(r"^\s*\[\d+\]")
#: Kapak sayfası bilgileri
COVER_META_RE = re.compile(
    r"(takım\s*(adı|id|ismi)|takim\s*(adi|id)|başvuru\s*id|basvuru\s*id"
    r"|teknofest|havacılık,\s*uzay|havacilik,\s*uzay"
    r"|danışman|danisman|üniversitesi\s*$|universitesi\s*$)",
    re.IGNORECASE,
)
PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
WS_RE = re.compile(r"\s+")

TR_LOWER_MAP = str.maketrans("IİĞÜŞÖÇ", "iiğüşöç")


def normalize(text: str) -> str:
    """Türkçe-duyarlı normalizasyon: aksanları düşür, noktalama/boşluk sadeleştir.

    'Yenilikçi (İnovatif) Yönü' -> 'yenilikci inovatif yonu'
    """
    t = text.translate(TR_LOWER_MAP).lower()
    t = unicodedata.normalize("NFKD", t)
    t = "".join(ch for ch in t if not unicodedata.combining(ch))
    t = t.replace("ı", "i").replace("ğ", "g").replace("ş", "s")
    t = t.replace("ö", "o").replace("ü", "u").replace("ç", "c")
    t = PUNCT_RE.sub(" ", t)
    return WS_RE.sub(" ", t).strip()


def title_similarity(a: str, b: str) -> float:
    """Normalize edilmiş iki başlık arasında 0-1 benzerlik.

    Token kapsama (kısmi başlıklar için) ve karakter dizisi benzerliğinin
    (yazım hataları için) maksimumu alınır.
    """
    na, nb = normalize(a), normalize(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0

    ta, tb = set(na.split()), set(nb.split())
    inter = len(ta & tb)
    # Kapsama: şablon başlığının kelimelerinin ne kadarı raporda geçiyor
    containment = inter / max(min(len(ta), len(tb)), 1)
    jaccard = inter / max(len(ta | tb), 1)
    seq = SequenceMatcher(None, na, nb).ratio()
    return round(max(0.55 * containment + 0.45 * jaccard, seq), 4)


@dataclass
class _Candidate:
    text: str
    raw_text: str
    page_no: int
    char_start: int
    font_size: float
    is_bold: bool
    numbering: str | None
    score: float


def find_front_matter_pages(result: ExtractionResult) -> set[int]:
    """Kapak, içindekiler, şekil/tablo listesi sayfalarını tespit eder.

    Gerçek TEKNOFEST raporlarında en büyük gürültü kaynağı bu sayfalardı:
    kapakta "TAKIM ADI: ...", "TEKNOFEST", "MANİSA 2022" gibi satırlar
    kalın ve büyük puntoyla yazıldığı için başlık sanılıyor; içindekiler
    sayfasındaki her madde de gerçek başlığın kopyası olarak tekrar ediliyor
    ve bölüm sınırlarını bozuyor (bölüm gövdesi 0 kelime çıkıyor).
    """
    pages: set[int] = set()
    for page in result.document.pages:
        head = normalize(page.text[:400])
        if not head:
            continue
        if page.page_no == 1:
            # 1. sayfayı koşulsuz atlamıyoruz: her raporda kapak olmayabilir,
            # bazı raporlar doğrudan içerikle başlıyor. Kapak imzası: sayfa
            # seyrek (az metin) VE kapak alanları (TAKIM ADI/ID, TEKNOFEST…) var.
            meta_hits = len(COVER_META_RE.findall(page.text))
            if page.char_count < 900 or meta_hits >= 2:
                pages.add(1)
            continue
        if any(k in head[:160] for k in (
            "icindekiler", "sekil listesi", "tablo listesi", "sekiller listesi",
            "kisaltmalar", "simgeler", "table of contents",
            "list of figures", "list of tables",
        )):
            pages.add(page.page_no)
    return pages


def is_not_heading(text: str) -> bool:
    """Başlık gibi biçimlendirilmiş ama başlık OLMAYAN satırları eler.

    Filtreler gerçek 2022 TEKNOFEST raporları incelenerek çıkarıldı:
      * "Şekil 3.5 Tam Eğitim Sonuçları"  → şekil/tablo altyazısı (kalın yazılır)
      * "GaussNoise: Giriş görüntüsüne rastgele Gauss gürültüsü ekler."
                                          → gövde içinde kalın terim tanımı
      * "[6] Mela veri seti (https://...)" → kaynakça maddesi
      * "TAKIM ADI: AbdoMate", "TAKIM ID: 468888", "MANİSA 2022" → kapak bilgisi
    """
    t = text.strip()
    if CAPTION_RE.match(t):
        return True
    if REFERENCE_RE.match(t):
        return True
    if COVER_META_RE.search(t):
        return True
    if "http://" in t or "https://" in t or "www." in t:
        return True
    # "Terim: cümle cümle cümle" — iki nokta sonrası uzun açıklama varsa tanım
    if ":" in t:
        before, _, after = t.partition(":")
        if len(before.split()) <= 3 and len(after.split()) >= 4:
            return True
    # Sadece sayı/noktalama
    if not any(c.isalpha() for c in t):
        return True
    return False


def detect_headings(result: ExtractionResult, *, max_words: int = 12) -> list[Heading]:
    """Dokümandaki aday başlıkları bulur ve ofsete göre sıralı döner.

    DOCX girdilerinde Word'ün başlık stilleri kesin bilgi verdiği için
    tipografi tahmini hiç çalıştırılmıyor — hazır başlıklar döndürülüyor.
    """
    docx_heads = getattr(result, "docx_headings", None)
    if docx_heads:
        return [h for h in docx_heads
                if h.level > 0 and not is_not_heading(h.text)]

    spans = result.spans
    body_size = 0.0
    if spans:
        sizes = [s.font_size for s in spans if s.font_size > 0]
        if sizes:
            body_size = statistics.median(sizes)

    skip_pages = find_front_matter_pages(result)
    seen: set[tuple[int, str]] = set()
    candidates: list[_Candidate] = []

    def consider(text: str, page_no: int, char_start: int,
                 font_size: float, is_bold: bool) -> None:
        stripped = text.strip()
        if not (3 <= len(stripped) <= 120):
            return
        if page_no in skip_pages:               # kapak / içindekiler / listeler
            return
        if TRAILING_DOTS_RE.search(stripped):   # nokta önderli içindekiler satırı
            return
        if is_not_heading(stripped):
            return
        words = stripped.split()
        if len(words) > max_words:
            return
        if stripped.endswith((".", ",", ";", ":")) and not NUMBERING_RE.match(stripped):
            # Cümle gibi bitiyorsa (numarasız) muhtemelen gövde metni
            if len(words) > 6:
                return

        key = (page_no, normalize(stripped))
        if not key[1] or key in seen:
            return

        m = NUMBERING_RE.match(stripped)
        numbering = m.group(1) if m else None
        clean = stripped[m.end():].strip() if m else stripped
        if not clean:
            return

        score = 0.0
        if numbering:
            score += 0.45
        if is_bold:
            score += 0.30
        if body_size and font_size >= body_size + 0.6:
            score += 0.30
        if body_size and font_size >= body_size + 2.0:
            score += 0.10
        if len(words) <= 8:
            score += 0.10
        letters = [c for c in clean if c.isalpha()]
        if letters and sum(1 for c in letters if c.isupper()) / len(letters) > 0.75:
            score += 0.15
        # Başlık gibi görünen ama sinyalsizse eleme
        if score < 0.40:
            return

        seen.add(key)
        candidates.append(
            _Candidate(clean, stripped, page_no, char_start, font_size,
                       is_bold, numbering, score)
        )

    if spans:
        for sp in spans:
            consider(sp.text, sp.page_no, sp.char_start, sp.font_size, sp.is_bold)
    else:
        # Tipografi yok (ör. OCR çıktısı) -> düz metin satırlarından türet
        offset = 0
        for page in result.document.pages:
            for line in page.text.split("\n"):
                consider(line, page.page_no, offset + page.text.find(line), 0.0, False)
            offset += len(page.text) + 2

    candidates.sort(key=lambda c: c.char_start)
    return [
        Heading(
            text=c.text,
            raw_text=c.raw_text,
            normalized=normalize(c.text),
            page_no=c.page_no,
            char_start=c.char_start,
            numbering=c.numbering,
            level=1 + (c.numbering.count(".") if c.numbering else 0),
            font_size=c.font_size or None,
            is_bold=c.is_bold,
        )
        for c in candidates
    ]


def _ranked_headings_for(
    spec: SectionSpec, headings: list[Heading]
) -> list[tuple[Heading, float]]:
    """Şablon maddesine uyan tüm başlıkları skoruna göre sıralı döner.

    Neden tek "en iyi" değil de liste: gerçek raporlarda aynı başlık birden
    fazla yerde geçiyor (özet listesi, bölüm tekrarı, alt başlık). En yüksek
    skorlu eşleşme bazen gövdesi boş olan kopya oluyordu — bölüm 0 kelime
    çıkıyor ve "içerik zayıf" uyarısı yanlış tetikleniyordu. Liste sayesinde
    build_sections gövdesi dolu olan ilk adaya geçebiliyor.
    """
    targets = [spec.expected_title, *spec.aliases]
    out: list[tuple[Heading, float]] = []
    for h in headings:
        score = max(title_similarity(h.text, t) for t in targets)
        if score > 0:
            out.append((h, score))
    out.sort(key=lambda x: (-x[1], x[0].char_start))
    return out


def _best_heading_for(spec: SectionSpec, headings: list[Heading]) -> tuple[Heading | None, float]:
    ranked = _ranked_headings_for(spec, headings)
    return ranked[0] if ranked else (None, 0.0)


def build_sections(
    result: ExtractionResult,
    template: ReportTemplate,
    headings: list[Heading],
    *,
    match_threshold: float = 0.62,
) -> tuple[list[Section], dict[str, float]]:
    """Şablon maddelerini gerçek başlıklarla eşleyip bölüm metinlerini çıkarır."""
    full = result.document.full_text
    matches: dict[str, tuple[Heading, float]] = {}

    ordered_offsets_all = sorted({h.char_start for h in headings})

    def body_length(h: Heading) -> int:
        """Bu başlığın altında kaç karakter metin var (sonraki başlığa kadar)."""
        start = h.char_start + len(h.raw_text or h.text)
        end = len(full)
        for off in ordered_offsets_all:
            if off > h.char_start:
                end = off
                break
        return max(end - start, 0)

    used_offsets: set[int] = set()
    # Yüksek skorlu eşleşmeler önce yerleşsin (aynı başlık iki maddeye gitmesin)
    ranked_by_spec = {
        spec.key: _ranked_headings_for(spec, headings) for spec in template.sections
    }
    scored = [
        (ranked_by_spec[spec.key][0][1] if ranked_by_spec[spec.key] else 0.0, spec)
        for spec in template.sections
    ]
    for _, spec in sorted(scored, key=lambda x: -x[0]):
        # Eşiği geçen adaylar arasından gövdesi DOLU olan ilkini seç.
        # Gerçek raporlarda en yüksek skorlu eşleşme bazen içeriksiz bir
        # tekrar oluyor; onu almak bölümü 0 kelime gösteriyordu.
        candidates = [
            (h, sc) for h, sc in ranked_by_spec[spec.key]
            if sc >= match_threshold and h.char_start not in used_offsets
        ]
        if not candidates:
            continue
        chosen = next(
            ((h, sc) for h, sc in candidates if body_length(h) >= 200),
            candidates[0],
        )
        used_offsets.add(chosen[0].char_start)
        matches[spec.key] = chosen

    # BÖLÜM SINIRI: bir sonraki EŞLEŞMİŞ BÖLÜM başlığına kadar — herhangi bir
    # başlığa kadar DEĞİL.
    #
    # Neden: gerçek raporlarda ana bölümün gövdesi alt başlıklarda duruyor.
    # Savaşan İHA KTR'de "DETAYLI TASARIM ÖZETİ"nin hemen ardından
    # "3.1 Hava Aracının Üç Boyutlu Tasarımı" geliyor; sınırı ilk başlıkta
    # kesince ana bölüm 1 KELİME çıkıyordu ve "içerik zayıf" diye yanlış
    # işaretleniyordu (36 raporluk korpusta 6 bölümde bu oldu).
    #
    # Hakemin sorduğu soru "bu bölüm doyurucu mu?"; cevabı alt bölümlerin
    # içeriğini de kapsar. Bu yüzden sınır yalnızca bir sonraki ANA bölümde.
    section_offsets = sorted(h.char_start for h, _ in matches.values())
    sections: list[Section] = []
    scores: dict[str, float] = {}

    for spec in template.sections:
        if spec.key not in matches:
            continue
        h, score = matches[spec.key]
        scores[spec.key] = score
        start = h.char_start + len(h.raw_text or h.text)
        end = len(full)
        for off in section_offsets:
            if off > h.char_start:
                end = off
                break
        body = full[start:end].strip()
        sections.append(
            Section(
                key=spec.key,
                title=h.text,
                expected_title=spec.expected_title,
                page_start=h.page_no,
                page_end=page_of_offset(result.page_offsets, max(end - 1, start)),
                char_start=start,
                char_end=end,
                text=body,
                word_count=len(body.split()),
            )
        )

    sections.sort(key=lambda s: s.char_start)
    return sections, scores


def check_template(
    result: ExtractionResult,
    template: ReportTemplate,
    sections: list[Section],
    match_scores: dict[str, float],
) -> TemplateReport:
    """MVP 1-3: dil uygunluğu + şablon/başlık/içerik kontrolü."""
    by_key = {s.key: s for s in sections}
    findings: list[SectionFinding] = []
    missing: list[str] = []
    thin: list[str] = []

    for spec in template.sections:
        sec = by_key.get(spec.key)
        if sec is None:
            findings.append(
                SectionFinding(
                    key=spec.key,
                    expected_title=spec.expected_title,
                    found=False,
                    min_words=spec.min_words,
                    points=spec.points,
                    severity=Severity.ERROR if spec.required else Severity.INFO,
                    message=(
                        f"Zorunlu başlık bulunamadı: '{spec.expected_title}'."
                        if spec.required
                        else f"İsteğe bağlı başlık yok: '{spec.expected_title}'."
                    ),
                )
            )
            if spec.required:
                missing.append(spec.expected_title)
            continue

        if spec.min_words and sec.word_count < spec.min_words:
            sev = Severity.WARN
            msg = (
                f"'{sec.title}' bölümü beklenenden kısa: "
                f"{sec.word_count} kelime (asgari {spec.min_words})."
            )
            thin.append(spec.expected_title)
        else:
            sev = Severity.OK
            msg = f"'{sec.title}' bulundu, içerik yeterli ({sec.word_count} kelime)."

        findings.append(
            SectionFinding(
                key=spec.key,
                expected_title=spec.expected_title,
                found=True,
                matched_title=sec.title,
                match_score=round(match_scores.get(spec.key, 0.0), 3),
                word_count=sec.word_count,
                min_words=spec.min_words,
                points=spec.points,
                severity=sev,
                message=msg,
            )
        )

    required = [s for s in template.sections if s.required] or list(template.sections)

    def is_thin(spec) -> bool:
        sec = by_key.get(spec.key)
        return bool(sec and spec.min_words and sec.word_count < spec.min_words)

    # Uyum skoru: şablon puan taşıyorsa PUAN AĞIRLIKLI hesaplanır.
    # Gerekçe: Robotaksi KTR'de "Otonom Sürüş Algoritmaları" 45 puan,
    # "Takım Organizasyonu" 2 puan. İkisinin eksikliğini eşit saymak
    # hakeme yanlış sinyal verir — 45 puanlık bölümü olmayan rapor ile
    # 2 puanlık bölümü olmayan rapor aynı değil.
    points_weighted = template.has_points
    if points_weighted:
        total_w = sum(s.points or 0.0 for s in required) or 1.0
        earned = sum(
            (s.points or 0.0) * (0.0 if s.key not in by_key else (0.5 if is_thin(s) else 1.0))
            for s in required
        )
        compliance = 100.0 * earned / total_w
        points_at_risk = round(total_w - earned, 1)
        template_total = round(total_w, 1)
    else:
        found_req = sum(1 for s in required if s.key in by_key)
        thin_req = sum(1 for s in required if is_thin(s))
        # Eksik başlık tam kayıp, zayıf içerik yarım puan
        compliance = 100.0 * (found_req - 0.5 * thin_req) / max(len(required), 1)
        points_at_risk = 0.0
        template_total = 0.0

    detected = result.document.language
    expected = template.expected_language
    language_ok = detected == expected

    if missing or not language_ok:
        severity = Severity.ERROR
    elif thin:
        severity = Severity.WARN
    else:
        severity = Severity.OK

    bits = []
    if points_weighted and points_at_risk > 0:
        bits.append(
            f"Riske giren puan: {points_at_risk:g}/{template_total:g}."
        )
    if not language_ok:
        bits.append(f"Rapor dili beklenen dille uyuşmuyor (beklenen: {expected.value}, "
                    f"tespit: {detected.value}).")
    if missing:
        bits.append(f"{len(missing)} zorunlu başlık eksik: {', '.join(missing)}.")
    if thin:
        bits.append(f"{len(thin)} bölüm içerik bakımından zayıf: {', '.join(thin)}.")
    if not bits:
        bits.append("Rapor güncel şablona tam uyumlu; tüm zorunlu başlıklar mevcut.")

    return TemplateReport(
        template_id=template.template_id,
        template_name=template.template_name,
        expected_language=expected,
        detected_language=detected,
        language_ok=language_ok,
        language_confidence=result.document.language_confidence,
        findings=findings,
        missing_sections=missing,
        thin_sections=thin,
        compliance_score=round(max(compliance, 0.0), 1),
        points_weighted=points_weighted,
        points_at_risk=points_at_risk,
        template_total_points=template_total,
        severity=severity,
        summary=" ".join(bits),
    )
