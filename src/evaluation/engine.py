"""T-Sistem · AI degerlendirme motoru (ADIM 3 ve ADIM 4).

KULLANICI ISTERLERI (gecmis konusmadan)
---------------------------------------
#215  "ADIM 3: yarismanin sartnamesi gonderilsin ve oradaki zorunluluklar
       kontrol edilsin, ardindan yarismaci raporu ve bilgileri gitsin"
#216  "ADIM 4: o asama icin var olan yarisma rapor sablonu gonderilsin, neye ne
       kadar puan veriliyor neden veriliyor anlasin, ardindan yarismaci raporu
       gonderilsin ve detayli analizler ve puanlama, neden puanlama, kanitlar"
#199  "3. kisimdaki ai baslatildiginda sadece 3. kisim icin, 4. kisimdaki ai
       basladiginda sadece 4. kisim icin bilgiler dogrulanmali"
#202  "rapordaki kanitlarda sadece ilk degil tumunu almali, TUM KANITLARI"
#204  "hepsi icin ayni kanit mi geliyor yoksa her bolum icin ayri kanitlar mi"
#179  "kanit olarak cikarilabilecekse cikarilsin, cikarilamayacaksa genel bir
       cevap verilsin, raporu inceleyen ai ona karar versin"
#253  "ai YENI KRITERLER VE GEREKLILIK OLUSTURMAMALI, ADMIN NE CIKARMISSA ONU
       KULLANMALI"

ONCEKI DURUMDAN FARKLAR
-----------------------
* Sahte heuristik puanlama KALDIRILDI. Eski kod LLM'ler dustugunde
  `oranlar[idx % 6]` ile rapora BAKMADAN %82-92 arasi puan uretiyor, ustune
  sabit `confidence: 0.92` yaziyordu.
* Bozuk PDF'te uydurma metin URETILMEZ. Eski kod okunamayan PDF icin tek
  cumlelik uydurma bir metin gonderip raporu onun uzerinden puanliyordu.
* Kanit dogrulama (2. katman) korundu ve guclendirildi: her alinti rapor
  metninde aranir, bulunamayan alinti silinir.
* Puan tavani SUNUCUDA zorlanir; LLM tavani asamaz.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable

from src.ai.llm import LLMUnavailable, get_llm, MAX_VISION_IMAGES
from src.data.models import CriterionScore, Requirement, RubricCriterion

log = logging.getLogger("tsistem.evaluation")

MAX_REPORT_CHARS = 90_000
EVIDENCE_MIN_RATIO = 0.78
ENGINE_VERSION = "engine-2.0"


# ═══════════════════════════════════════════════════════════════════════════
# Veri yapilari
# ═══════════════════════════════════════════════════════════════════════════
@dataclass
class Evidence:
    quote: str
    page: int | None = None
    start: int | None = None
    end: int | None = None
    verified: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"quote": self.quote, "page": self.page,
                "start": self.start, "end": self.end, "verified": self.verified}


@dataclass
class RuleVerdict:
    """ADIM 3 — tek bir sartname kuralinin denetim sonucu."""

    req_id: str
    title: str
    rule_type: str
    status: str                      # UYGUN | UYGUN_DEGIL | BELIRSIZ
    explanation: str
    evidence: list[Evidence] = field(default_factory=list)
    rule_quote: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"req_id": self.req_id, "title": self.title, "rule_type": self.rule_type,
                "status": self.status, "explanation": self.explanation,
                "rule_quote": self.rule_quote,
                "evidence": [e.to_dict() for e in self.evidence]}


@dataclass
class ComplianceResult:
    """ADIM 3 ciktisi."""

    verdicts: list[RuleVerdict]
    format_findings: list[str]
    overall: str                     # UYGUN | KISMEN | UYGUN_DEGIL
    summary: str
    provider: str
    model: str
    warnings: list[str] = field(default_factory=list)
    engine_version: str = ENGINE_VERSION

    @property
    def counts(self) -> dict[str, int]:
        out = {"UYGUN": 0, "UYGUN_DEGIL": 0, "BELIRSIZ": 0}
        for verdict in self.verdicts:
            out[verdict.status] = out.get(verdict.status, 0) + 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {"verdicts": [v.to_dict() for v in self.verdicts],
                "format_findings": self.format_findings, "overall": self.overall,
                "summary": self.summary, "counts": self.counts,
                "provider": self.provider, "model": self.model,
                "warnings": self.warnings, "engine_version": self.engine_version}


@dataclass
class CriterionVerdict:
    """ADIM 4 — tek bir rubrik kriterinin AI degerlendirmesi."""

    criterion_code: str
    criterion_name: str
    max_score: float
    ai_score: float
    rationale: str
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    evidence_mode: str = "kanitli"   # kanitli | genel_yorum
    parent_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"criterion_code": self.criterion_code, "criterion_name": self.criterion_name,
                "max_score": self.max_score, "ai_score": self.ai_score,
                "rationale": self.rationale, "strengths": self.strengths,
                "weaknesses": self.weaknesses, "evidence_mode": self.evidence_mode,
                "parent_code": self.parent_code,
                "evidence": [e.to_dict() for e in self.evidence]}

    def as_score(self) -> CriterionScore:
        return CriterionScore(
            criterion_code=self.criterion_code,
            criterion_name=self.criterion_name,
            max_score=self.max_score,
            ai_score=self.ai_score,
            referee_score=self.ai_score,   # hakem degistirene kadar oneri
            ai_rationale=self.rationale,
            evidence_json=json.dumps([e.to_dict() for e in self.evidence], ensure_ascii=False),
        )


@dataclass
class ScoringResult:
    """ADIM 4 ciktisi."""

    verdicts: list[CriterionVerdict]
    total_score: float
    max_total_score: float
    recommendation: str              # KABUL | REVIZYON | RET
    summary: str
    provider: str
    model: str
    dropped_evidence: int = 0
    warnings: list[str] = field(default_factory=list)
    engine_version: str = ENGINE_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {"verdicts": [v.to_dict() for v in self.verdicts],
                "total_score": self.total_score, "max_total_score": self.max_total_score,
                "recommendation": self.recommendation, "summary": self.summary,
                "provider": self.provider, "model": self.model,
                "dropped_evidence": self.dropped_evidence,
                "warnings": self.warnings, "engine_version": self.engine_version}

    def as_scores(self) -> list[CriterionScore]:
        return [v.as_score() for v in self.verdicts]


# ═══════════════════════════════════════════════════════════════════════════
# Kanit dogrulama (2. katman · fact-checker)
# ═══════════════════════════════════════════════════════════════════════════
_WS = re.compile(r"\s+")


def _norm(text: str) -> str:
    return _WS.sub(" ", text.lower()).strip()


class EvidenceVerifier:
    """LLM'in urettigi alintilarin rapor metninde GERCEKTEN gectigini dogrular.

    Kullanicinin #171/#173/#178'deki "ai yanlis yerleri isaretliyor" sikayeti
    tam olarak bu katmanin isidir.
    """

    def __init__(self, report_text: str, page_offsets: list[tuple[int, int]] | None = None) -> None:
        self.raw = report_text
        self.norm = _norm(report_text)
        self.page_offsets = page_offsets or []

    def verify(self, quote: str) -> Evidence | None:
        needle = _norm(quote)
        if len(needle) < 15:
            return None

        pos = self.norm.find(needle)
        if pos != -1:
            return self._build(quote, pos, len(needle))

        words = needle.split()
        for size in (14, 11, 8, 6):
            if len(words) < size:
                continue
            window = " ".join(words[:size])
            pos = self.norm.find(window)
            if pos != -1:
                return self._build(quote, pos, len(window))

        sample = needle[:200]
        step = max(1, len(sample) // 3)
        best_ratio, best_pos = 0.0, -1
        for start in range(0, max(1, len(self.norm) - len(sample)), step):
            ratio = SequenceMatcher(None, sample, self.norm[start:start + len(sample)]).ratio()
            if ratio > best_ratio:
                best_ratio, best_pos = ratio, start
            if best_ratio >= 0.95:
                break
        if best_ratio >= EVIDENCE_MIN_RATIO and best_pos >= 0:
            return self._build(quote, best_pos, len(sample))
        return None

    def _build(self, quote: str, norm_pos: int, norm_len: int) -> Evidence:
        ratio = norm_pos / max(1, len(self.norm))
        approx = int(ratio * len(self.raw))
        return Evidence(quote=quote.strip(), page=self._page_at(approx),
                        start=approx, end=approx + norm_len, verified=True)

    def _page_at(self, char_index: int) -> int | None:
        for page_no, offset in self.page_offsets:
            if char_index < offset:
                return page_no
        return self.page_offsets[-1][0] if self.page_offsets else None

    def filter(self, quotes: Iterable[str]) -> tuple[list[Evidence], int]:
        kept: list[Evidence] = []
        dropped = 0
        seen: set[str] = set()
        for quote in quotes:
            if not quote or not str(quote).strip():
                continue
            key = _norm(str(quote))[:120]
            if key in seen:
                continue
            seen.add(key)
            evidence = self.verify(str(quote))
            if evidence is None:
                dropped += 1
                continue
            kept.append(evidence)
        return kept, dropped


# ═══════════════════════════════════════════════════════════════════════════
# ADIM 3 · Sartname ve bicim on denetimi
# ═══════════════════════════════════════════════════════════════════════════
STEP3_SYSTEM = (
    "Sen TEKNOFEST bas hakemi duzeyinde bir sartname denetcisisin. "
    "Gorevin, YALNIZCA sana verilen resmi sartname kurallarina gore raporu denetlemektir. "
    "Kendi kuralini uydurma, verilen listenin disina cikma. "
    "Her karar icin rapordan birebir alinti ver. Yalnizca gecerli JSON dondur."
)

STEP3_TEMPLATE = """ADIM 3 · SARTNAME VE BICIM ON DENETIMI

YARISMA : {competition_name}
ASAMA   : {stage_code}
{branch_line}
=== BOLUM A · YONETICININ ONAYLADIGI RESMI SARTNAME KURALLARI ===
{rules_block}

=== BOLUM B · BICIM KOSULLARI ===
Sayfa siniri     : {max_pages}
Zorunlu bolumler : {required_sections}
Yazi tipi / marj : {font_rules}

=== BOLUM C · TAKIM VE BASVURU BILGILERI ===
{team_block}

=== BOLUM D · YARISMACI RAPORU ===
\"\"\"
{report_text}
\"\"\"

GOREV
Yukaridaki HER kural icin raporun ve takim bilgilerinin uygun olup olmadigini karara bagla.

KATI KURALLAR
1. YALNIZCA Bolum A'daki kurallari degerlendir. Yeni kural EKLEME.
2. Her kural icin `status`: "UYGUN", "UYGUN_DEGIL" veya "BELIRSIZ".
   Rapordan/takim bilgisinden karar veremiyorsan "BELIRSIZ" de; tahmin etme.
3. `evidence` alanina rapordan BIREBIR alinti(lar) koy. Birden fazla kanit varsa
   HEPSINI ver. Kanit gosterilemeyen kararlarda `evidence` bos kalabilir ama
   `explanation` neden kanit olmadigini acikca yazmalidir.
4. Bicim bulgularini (sayfa sayisi, eksik bolum, yazi tipi) `format_findings`
   dizisine yaz.

JSON SEMASI (baska hicbir sey yazma):
{{
  "verdicts": [
    {{"req_id": "...", "status": "UYGUN", "explanation": "...", "evidence": ["birebir alinti"]}}
  ],
  "format_findings": ["Rapor 22 sayfa, sinir 20 sayfa - asilmis."],
  "overall": "UYGUN|KISMEN|UYGUN_DEGIL",
  "summary": "2-3 cumlelik denetim ozeti"
}}"""


def analyze_compliance(
    *,
    report_text: str,
    requirements: list[Requirement],
    competition_name: str,
    stage_code: str,
    branch_code: str | None = None,
    max_pages: int | None = None,
    page_count: int | None = None,
    required_sections: list[str] | None = None,
    font_rules: str | None = None,
    team_info: dict[str, Any] | None = None,
    page_offsets: list[tuple[int, int]] | None = None,
    images: list[dict[str, Any]] | None = None,
) -> ComplianceResult:
    """ADIM 3 — YALNIZCA sartname uygunlugu. Rubrik puanlamasi YAPMAZ.

    `images`: images_to_base64() ciktisi — PDF'ten cikartilan gorsel/sekil listesi.
    Vision destekleyen saglayici varsa gorseller sartname kontrolunda kullanilir.
    """
    _guard_report(report_text)
    if not requirements:
        raise ValueError(
            "Bu yarisma icin onaylanmis sartname kurali bulunamadi. "
            "Once yonetici panelinden sartnameyi analiz edip kurallari onaylayiniz."
        )

    rules_block = "\n".join(
        f"[{r.req_id}] ({r.rule_type.value}) {r.title}\n"
        f"      Aciklama : {r.description or '-'}\n"
        f"      Sartname : \"{(r.source_quote or '-')[:280]}\""
        + (f"\n      Sayisal  : takim {r.min_team_size or '?'}-{r.max_team_size or '?'} kisi"
           if (r.min_team_size or r.max_team_size) else "")
        + ("\n      Danisman : zorunlu" if r.advisor_required else "")
        + (f"\n      Seviye   : {r.target_level}" if r.target_level else "")
        for r in requirements
    )

    team_lines: list[str] = []
    for key, label in (("name", "Takim adi"), ("level", "Seviye"),
                       ("institution", "Kurum"), ("member_count", "Uye sayisi"),
                       ("advisor_name", "Danisman")):
        value = (team_info or {}).get(key)
        if value not in (None, ""):
            team_lines.append(f"{label}: {value}")
    if page_count:
        team_lines.append(f"Rapor sayfa sayisi: {page_count}")

    prompt = STEP3_TEMPLATE.format(
        competition_name=competition_name,
        stage_code=stage_code.upper(),
        branch_line=f"ALT DAL : {branch_code}\n" if branch_code else "",
        rules_block=rules_block,
        max_pages=max_pages if max_pages else "belirtilmemis",
        required_sections=", ".join(required_sections) if required_sections else "belirtilmemis",
        font_rules=font_rules or "belirtilmemis",
        team_block="\n".join(team_lines) or "Takim bilgisi saglanmadi.",
        report_text=report_text[:MAX_REPORT_CHARS],
    )

    llm = get_llm()
    if images:
        payload, result = llm.complete_multimodal_json(
            prompt, images, system=STEP3_SYSTEM, max_tokens=6000, temperature=0.05,
            validator=_validate_step3,
        )
    else:
        payload, result = llm.complete_json(
            prompt, system=STEP3_SYSTEM, max_tokens=6000, temperature=0.05,
            validator=_validate_step3,
        )

    verifier = EvidenceVerifier(report_text, page_offsets)
    by_id = {r.req_id: r for r in requirements}
    verdicts: list[RuleVerdict] = []
    warnings: list[str] = []
    dropped_total = 0

    for raw in payload.get("verdicts", []):
        req = by_id.get(str(raw.get("req_id")))
        if req is None:
            warnings.append(f"AI, listede olmayan bir kural dondurdu ve elendi: {raw.get('req_id')}")
            continue
        evidence, dropped = verifier.filter(raw.get("evidence") or [])
        dropped_total += dropped
        status = str(raw.get("status", "BELIRSIZ")).upper()
        if status not in ("UYGUN", "UYGUN_DEGIL", "BELIRSIZ"):
            status = "BELIRSIZ"
        verdicts.append(RuleVerdict(
            req_id=req.req_id, title=req.title, rule_type=req.rule_type.value,
            status=status, explanation=str(raw.get("explanation") or "").strip(),
            evidence=evidence, rule_quote=req.source_quote,
        ))

    decided = {v.req_id for v in verdicts}
    missing = [r for r in requirements if r.req_id not in decided]
    for req in missing:
        verdicts.append(RuleVerdict(
            req_id=req.req_id, title=req.title, rule_type=req.rule_type.value,
            status="BELIRSIZ",
            explanation="AI bu kural icin karar uretmedi; hakem degerlendirmesi gerekiyor.",
            rule_quote=req.source_quote,
        ))
    if missing:
        warnings.append(f"{len(missing)} kural AI tarafindan degerlendirilmedi, BELIRSIZ isaretlendi.")
    if dropped_total:
        warnings.append(f"{dropped_total} kanit alintisi raporda dogrulanamadigi icin elendi.")

    findings = [str(f) for f in (payload.get("format_findings") or []) if f]
    if max_pages and page_count and page_count > max_pages:
        auto = f"Rapor {page_count} sayfa; sablon siniri {max_pages} sayfa - sinir asilmis."
        if auto not in findings:
            findings.insert(0, auto)

    # 3. katman (synthesizer): genel karar HER ZAMAN tekil kararlarla tutarli
    # olmalidir. LLM'in bildirdigi 'overall' bilgi amaclidir, baglayici degildir.
    counts = {"UYGUN": 0, "UYGUN_DEGIL": 0, "BELIRSIZ": 0}
    for verdict in verdicts:
        counts[verdict.status] += 1
    overall = ("UYGUN_DEGIL" if counts["UYGUN_DEGIL"]
               else "KISMEN" if counts["BELIRSIZ"] else "UYGUN")
    llm_overall = str(payload.get("overall", "")).upper()
    if llm_overall in ("UYGUN", "KISMEN", "UYGUN_DEGIL") and llm_overall != overall:
        warnings.append(
            f"AI genel kararini '{llm_overall}' bildirdi; tekil kararlarla tutarli "
            f"olmasi icin '{overall}' olarak duzeltildi."
        )

    return ComplianceResult(
        verdicts=verdicts, format_findings=findings, overall=overall,
        summary=str(payload.get("summary") or "").strip(),
        provider=result.provider, model=result.model, warnings=warnings,
    )


# ═══════════════════════════════════════════════════════════════════════════
# ADIM 4 · Kriter bazli rubrik puanlama
# ═══════════════════════════════════════════════════════════════════════════
STEP4_SYSTEM = (
    "Sen TEKNOFEST bas hakemi duzeyinde bir rapor degerlendiricisisin ('AI 4. Goz'). "
    "YALNIZCA sana verilen resmi rubrigi kullanirsin; kriter uydurmak veya puan "
    "agirligini degistirmek KESINLIKLE YASAKTIR. Her puan icin rapordan birebir "
    "kanit gosterirsin. Yalnizca gecerli JSON dondur."
)

STEP4_TEMPLATE = """ADIM 4 · KRITER BAZLI RUBRIK PUANLAMA

YARISMA : {competition_name}
ASAMA   : {stage_code} ({stage_name})
{branch_line}
=== BOLUM A · RESMI RUBRIK (yoneticinin RAPOR SABLONUNDAN cikarip ONAYLADIGI) ===
Puan agirliklari baglayicidir.

{rubric_block}

TOPLAM TAVAN PUAN: {max_total}

=== BOLUM B · YARISMACI RAPORU ===
\"\"\"
{report_text}
\"\"\"

GOREV
Her kriter icin raporu degerlendir, 0 ile o kriterin tavan puani arasinda puan ver.

KATI KURALLAR
1. YALNIZCA Bolum A'daki kriterleri puanla. Yeni kriter EKLEME, kriter ADINI
   DEGISTIRME, tavan puani DEGISTIRME.
2. `rationale`: neden bu puani verdigini SOMUT olarak acikla. "Bu bolum iyi"
   gibi genel ifadeler KULLANMA; rapordaki gercek veriye, sayiya, yonteme atif yap.
3. `evidence`: rapordan BIREBIR alinti(lar). Bir kriter icin birden fazla kanit
   varsa HEPSINI ver (yalnizca ilkini degil). Her kriterin kaniti KENDI
   bolumunden gelmelidir; ayni alintiyi tum kriterlere kopyalama.
4. Bazi kriterler alinti ile kanitlanamaz (or. "genel duzen", "yazim dili",
   "gorsel kalite"). Bu durumda `evidence_mode` = "genel_yorum" yaz, `evidence`
   dizisini bos birak ve gozlemini `rationale` icinde acikla.
   Kanitlanabiliyorsa `evidence_mode` = "kanitli".
5. `strengths` ve `weaknesses`: her biri en fazla 3 madde, somut ve rapora ozgu.
6. Alt kriteri olan (parent_code dolu) kriterleri ayri ayri puanla; ust kriterin
   puani alt kriterlerin toplami olacaktir, ust kritere ayrica puan verme.

JSON SEMASI (baska hicbir sey yazma):
{{
  "criteria": [
    {{
      "criterion_code": "C1",
      "score": 8.5,
      "rationale": "...",
      "strengths": ["..."],
      "weaknesses": ["..."],
      "evidence_mode": "kanitli",
      "evidence": ["birebir alinti 1", "birebir alinti 2"]
    }}
  ],
  "summary": "3-4 cumlelik genel degerlendirme",
  "recommendation": "KABUL|REVIZYON|RET"
}}"""


def score_report(
    *,
    report_text: str,
    rubric: list[RubricCriterion],
    competition_name: str,
    stage_code: str,
    stage_name: str = "",
    branch_code: str | None = None,
    page_offsets: list[tuple[int, int]] | None = None,
    accept_threshold: float = 75.0,
    revision_threshold: float = 60.0,
    images: list[dict[str, Any]] | None = None,
) -> ScoringResult:
    """ADIM 4 — YALNIZCA rubrik puanlamasi. Sartname denetimi YAPMAZ.

    `images`: images_to_base64() ciktisi — PDF'ten cikartilan gorsel/sekil listesi.
    Vision destekleyen saglayici varsa gorseller rubrik puanlamada kullanilir
    (sekiller, grafikler, devre diagraami vb. metin disindaki icerikleri degerlendirir).
    """
    _guard_report(report_text)
    if not rubric:
        raise ValueError(
            "Bu asama icin onaylanmis rubrik bulunamadi. Once yonetici panelinden "
            "rapor sablonunu analiz edip kriterleri onaylayiniz. "
            "Sistem varsayilan bir rubrik URETMEZ."
        )

    order = [c.criterion_code for c in rubric]
    tops = [c for c in rubric if not c.parent_code]
    max_total = round(sum(c.max_score for c in tops), 2)

    def _line(crit: RubricCriterion) -> str:
        indent = "    " if crit.parent_code else ""
        parent = f" (alt kriter -> {crit.parent_code})" if crit.parent_code else ""
        desc = f"\n{indent}      Aciklama: {crit.description}" if crit.description else ""
        quote = f"\n{indent}      Sablon  : \"{crit.source_quote[:200]}\"" if crit.source_quote else ""
        return (f"{indent}[{crit.criterion_code}] {crit.criterion_name} — "
                f"TAVAN {crit.max_score:g} puan{parent}{desc}{quote}")

    prompt = STEP4_TEMPLATE.format(
        competition_name=competition_name,
        stage_code=stage_code.upper(),
        stage_name=stage_name or stage_code.upper(),
        branch_line=f"ALT DAL : {branch_code}\n" if branch_code else "",
        rubric_block="\n".join(_line(c) for c in rubric),
        max_total=f"{max_total:g}",
        report_text=report_text[:MAX_REPORT_CHARS],
    )

    llm = get_llm()
    if images:
        payload, result = llm.complete_multimodal_json(
            prompt, images, system=STEP4_SYSTEM, max_tokens=8000, temperature=0.1,
            validator=_validate_step4,
        )
    else:
        payload, result = llm.complete_json(
            prompt, system=STEP4_SYSTEM, max_tokens=8000, temperature=0.1,
            validator=_validate_step4,
        )

    verifier = EvidenceVerifier(report_text, page_offsets)
    by_code = {c.criterion_code: c for c in rubric}
    verdicts: list[CriterionVerdict] = []
    warnings: list[str] = []
    dropped_total = 0
    seen_codes: set[str] = set()

    for raw in payload.get("criteria", []):
        code = str(raw.get("criterion_code") or "").strip()
        crit = by_code.get(code)
        if crit is None:
            warnings.append(f"AI, rubrikte olmayan '{code}' kriterini dondurdu ve elendi.")
            continue
        if code in seen_codes:
            continue
        seen_codes.add(code)

        try:
            score = float(raw.get("score"))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(score, crit.max_score))   # tavan SUNUCUDA zorlanir

        mode = str(raw.get("evidence_mode") or "kanitli").lower()
        evidence, dropped = verifier.filter(raw.get("evidence") or [])
        dropped_total += dropped
        if mode != "genel_yorum" and not evidence:
            mode = "genel_yorum"

        verdicts.append(CriterionVerdict(
            criterion_code=crit.criterion_code, criterion_name=crit.criterion_name,
            max_score=crit.max_score, ai_score=round(score, 2),
            rationale=str(raw.get("rationale") or "").strip(),
            strengths=[str(s) for s in (raw.get("strengths") or [])][:3],
            weaknesses=[str(w) for w in (raw.get("weaknesses") or [])][:3],
            evidence=evidence, evidence_mode=mode, parent_code=crit.parent_code,
        ))

    # Alt kriteri dondurulmus UST kriterler 'eksik' sayilmaz; puanlari alt
    # kriterlerin toplamindan hesaplanir.
    scored_parents = {
        by_code[c].parent_code for c in seen_codes
        if c in by_code and by_code[c].parent_code
    }
    missing = [
        c for c in rubric
        if c.criterion_code not in seen_codes and c.criterion_code not in scored_parents
    ]
    for crit in [c for c in rubric if c.criterion_code in scored_parents
                 and c.criterion_code not in seen_codes]:
        verdicts.append(CriterionVerdict(
            criterion_code=crit.criterion_code, criterion_name=crit.criterion_name,
            max_score=crit.max_score, ai_score=0.0,
            rationale="Puani alt kriterlerin toplamindan hesaplanmistir.",
            evidence_mode="genel_yorum", parent_code=crit.parent_code,
        ))
    for crit in missing:
        verdicts.append(CriterionVerdict(
            criterion_code=crit.criterion_code, criterion_name=crit.criterion_name,
            max_score=crit.max_score, ai_score=0.0,
            rationale="AI bu kriter icin degerlendirme uretmedi. Hakem puanlamasi gerekiyor.",
            evidence_mode="genel_yorum", parent_code=crit.parent_code,
        ))
    if missing:
        warnings.append(
            f"{len(missing)} kriter AI tarafindan puanlanmadi ve 0 ile isaretlendi; "
            "hakemin elle puanlamasi gerekiyor."
        )
    if dropped_total:
        warnings.append(
            f"{dropped_total} kanit alintisi rapor metninde dogrulanamadigi icin elendi "
            "(halusinasyon filtresi)."
        )

    # Ust kriter puani = alt kriterlerin toplami
    children: dict[str, list[CriterionVerdict]] = {}
    for verdict in verdicts:
        if verdict.parent_code:
            children.setdefault(verdict.parent_code, []).append(verdict)
    by_verdict = {v.criterion_code: v for v in verdicts}
    for parent_code, kids in children.items():
        parent = by_verdict.get(parent_code)
        if parent is not None:
            parent.ai_score = round(sum(k.ai_score for k in kids), 2)

    verdicts.sort(key=lambda v: order.index(v.criterion_code))

    total = round(sum(v.ai_score for v in verdicts if not v.parent_code), 2)
    pct = (total / max_total * 100) if max_total else 0.0
    computed = ("KABUL" if pct >= accept_threshold
                else "REVIZYON" if pct >= revision_threshold else "RET")
    # 3. katman (synthesizer): oneri HER ZAMAN puanla tutarli olmalidir.
    recommendation = computed

    log.info("[step4] %s/%s -> %.1f/%.1f (%s) · %d kriter · %s/%s · vision=%s · gorseller=%d",
             competition_name, stage_code, total, max_total, recommendation,
             len(verdicts), result.provider, result.model,
             getattr(result, "vision_used", False), len(images) if images else 0)

    return ScoringResult(
        verdicts=verdicts, total_score=total, max_total_score=max_total,
        recommendation=recommendation,
        summary=str(payload.get("summary") or "").strip(),
        provider=result.provider, model=result.model,
        dropped_evidence=dropped_total, warnings=warnings,
    )


# ═══════════════════════════════════════════════════════════════════════════
# Yardimcilar
# ═══════════════════════════════════════════════════════════════════════════
def _guard_report(report_text: str) -> None:
    """Bozuk/bos rapor metniyle AI CALISTIRILMAZ."""
    if not report_text or len(report_text.strip()) < 500:
        raise ValueError(
            "Rapor metni cikarilamadi veya cok kisa (500 karakterden az). "
            "PDF taranmis goruntu olabilir. AI degerlendirmesi YAPILMADI — "
            "raporu metin katmani iceren bir PDF olarak yeniden yukleyiniz."
        )


def _validate_step3(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Kok nesne sozluk olmali.")
    if not isinstance(payload.get("verdicts"), list):
        raise ValueError("'verdicts' bir dizi olmali.")
    for item in payload["verdicts"]:
        if not isinstance(item, dict) or "req_id" not in item or "status" not in item:
            raise ValueError("Her karar 'req_id' ve 'status' icermeli.")
    return payload


def _validate_step4(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Kok nesne sozluk olmali.")
    if not isinstance(payload.get("criteria"), list) or not payload["criteria"]:
        raise ValueError("'criteria' dolu bir dizi olmali.")
    for item in payload["criteria"]:
        if not isinstance(item, dict):
            raise ValueError("Her kriter bir nesne olmali.")
        if "criterion_code" not in item or "score" not in item:
            raise ValueError("Her kriter 'criterion_code' ve 'score' icermeli.")
    return payload


def page_offsets_from_pdf(data: bytes) -> tuple[str, list[tuple[int, int]]]:
    """PDF'ten metin + sayfa sinir indekslerini birlikte cikarir.

    Kanitlarin HANGI SAYFADA oldugunu gosterebilmek icin gereklidir.
    """
    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PDF okumak icin pymupdf gerekli.") from exc

    parts: list[str] = []
    offsets: list[tuple[int, int]] = []
    cursor = 0
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page_no, page in enumerate(doc, 1):
            text = page.get_text()
            parts.append(text)
            cursor += len(text)
            offsets.append((page_no, cursor))
    return "".join(parts), offsets


__all__ = [
    "analyze_compliance", "score_report",
    "ComplianceResult", "ScoringResult", "RuleVerdict", "CriterionVerdict",
    "Evidence", "EvidenceVerifier", "page_offsets_from_pdf",
    "LLMUnavailable", "ENGINE_VERSION",
]
