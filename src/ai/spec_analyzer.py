"""T-Sistem · Sartname analiz motoru (GERCEK LLM).

ONCEKI DURUM
------------
Bu dosya "AI Analiz Modulu" basligini tasiyordu ama hicbir LLM import etmiyordu.
Ciktisi tamamen sabitti:
  * Her yarisma icin BIREBIR AYNI 4 kural metni dondururdu,
  * "%15 intihal siniri" belgeden okunmaz, koda gomuluydu,
  * Danisman sarti `... or "lise" in low_text` ile belirleniyordu; yani
    sartnamede "lise" kelimesi gecen HER belgede danisman zorunlu sayiliyordu,
  * Tarih bulunamazsa `28.02.2026` gibi uydurma tarihler yaziliyordu.

YENI DURUM
----------
* Sartname metni gercek LLM'e gonderilir; her kural icin `source_quote`
  (belgedeki dayanak cumle) ZORUNLUDUR — dogrulanamayan kural elenir.
* Cok dalli yarismalarda her dal AYRI analiz edilir (branch_code) — KARAR #1.
* LLM yoksa SESSIZ SAHTE VERI URETILMEZ; `LLMUnavailable` firlatilir ve
  arayuz kullaniciya "AI analizi yapilamadi" uyarisi gosterir.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.enums import RuleType
from src.data.models import Requirement

from .llm import LLMUnavailable, get_llm

log = logging.getLogger("tsistem.ai.spec")

MAX_CHARS = 60_000          # ~15-20 sayfa; LLM baglam siniri icin
QUOTE_MIN_MATCH = 0.72      # kanit dogrulama esigi

SYSTEM_PROMPT = (
    "Sen TEKNOFEST yarisma sartnamelerini inceleyen bir kural cikarim uzmanisin. "
    "Gorevin, verilen sartname metninden takim ve basvuru kosullarini eksiksiz cikarmaktir. "
    "ASLA metinde olmayan bir kural uydurma. Her kural icin metinden BIREBIR alinti ver. "
    "Yalnizca gecerli JSON dondur."
)

USER_TEMPLATE = """Asagida bir TEKNOFEST yarismasinin resmi sartnamesi yer aliyor.

YARISMA: {competition_name}
{branch_line}
SARTNAME METNI:
\"\"\"
{text}
\"\"\"

GOREV
Bu sartnameden takimlarin UYMASI GEREKEN kosullari cikar. Su kategorilerde ara:
  - takim     : takim uye sayisi alt/ust siniri, kaptan kosullari
  - danisman  : danisman zorunlulugu, danismanin nitelikleri
  - katilim   : hedef egitim seviyesi (Ortaokul/Lise/Universite/Mezun), yas, uyruk
  - teknik    : rapor bicimi disindaki teknik zorunluluklar, malzeme/donanim kisitlari
  - dil       : rapor dili, terminoloji kosullari
  - diger     : yukaridakilere girmeyen baglayici kosullar

KATI KURALLAR
1. Her kural icin `source_quote` alanina metinden BIREBIR bir cumle koy. Cumleyi
   degistirme, kisaltma, ozetleme. Dayanak cumlesi bulamadigin kurali HIC EKLEME.
2. Sayisal degerleri (min/max takim buyuklugu) yalnizca metinde aciksa doldur;
   yoksa null birak. TAHMIN ETME.
3. Metinde gecmeyen genel gecer kurallar ekleme.
4. En fazla 20 kural dondur, en baglayici olanlardan basla.

JSON SEMASI (baska hicbir sey yazma):
{{
  "requirements": [
    {{
      "rule_type": "takim|danisman|katilim|teknik|dil|diger",
      "title": "kisa baslik (en fazla 70 karakter)",
      "description": "kuralin acik ifadesi (1-3 cumle)",
      "min_team_size": null,
      "max_team_size": null,
      "advisor_required": false,
      "target_level": null,
      "is_mandatory": true,
      "source_quote": "metinden birebir alinti"
    }}
  ],
  "schedule": {{ "son_basvuru": null, "yarisma_tarihi": null, "sonuc_tarihi": null }},
  "summary": "sartnamenin 2 cumlelik ozeti"
}}"""


@dataclass
class SpecAnalysis:
    requirements: list[Requirement]
    schedule: dict[str, str]
    summary: str
    provider: str
    model: str
    dropped_unverified: int = 0
    warnings: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.warnings is None:
            self.warnings = []


# ── metin cikarimi ─────────────────────────────────────────────────────────
def extract_text(source: str | bytes | Path, *, max_pages: int = 40) -> str:
    """PDF veya duz metinden analiz metnini cikarir."""
    if isinstance(source, str) and not Path(source).exists():
        return source[:MAX_CHARS]

    data = source if isinstance(source, bytes) else Path(source).read_bytes()
    if not data[:4] == b"%PDF":
        return data.decode("utf-8", errors="replace")[:MAX_CHARS]

    try:
        import pymupdf  # type: ignore
    except ImportError:
        try:
            import fitz as pymupdf  # type: ignore
        except ImportError as exc:
            raise RuntimeError("PDF okumak icin pymupdf gerekli: pip install pymupdf") from exc

    parts: list[str] = []
    with pymupdf.open(stream=data, filetype="pdf") as doc:
        for page_no, page in enumerate(doc, 1):
            if page_no > max_pages:
                break
            parts.append(page.get_text())
    text = "\n".join(parts)
    if not text.strip():
        raise RuntimeError(
            "PDF'ten metin cikarilamadi (taranmis goruntu olabilir). "
            "OCR gerekiyor; analiz yapilmadi."
        )
    return text[:MAX_CHARS]


# ── kanit dogrulama ────────────────────────────────────────────────────────
def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def verify_quote(quote: str, haystack_norm: str) -> bool:
    """Alintinin metinde GERCEKTEN gecip gecmedigini dogrular.

    Bu, `evaluator.py`'deki 2. katman (fact-checker) ile ayni mantiktir:
    LLM'in uydurdugu 'kanit'lar sessizce elenir.
    """
    needle = _normalize(quote)
    if len(needle) < 12:
        return False
    if needle in haystack_norm:
        return True
    words = needle.split()
    for size in (12, 9, 7, 5):
        if len(words) >= size:
            window = " ".join(words[:size])
            if window in haystack_norm:
                return True
    from difflib import SequenceMatcher

    sample = needle[:180]
    best = 0.0
    step = max(1, len(sample) // 2)
    for start in range(0, max(1, len(haystack_norm) - len(sample)), step):
        ratio = SequenceMatcher(None, sample, haystack_norm[start:start + len(sample)]).ratio()
        best = max(best, ratio)
        if best >= QUOTE_MIN_MATCH:
            return True
    return False


# ── ana giris ──────────────────────────────────────────────────────────────
def analyze_specification(
    source: str | bytes | Path,
    *,
    competition_id: str,
    competition_name: str,
    branch_code: str | None = None,
    branch_name: str | None = None,
    spec_id: str | None = None,
) -> SpecAnalysis:
    """Sartnameden kural setini cikarir. LLM yoksa `LLMUnavailable` firlatir."""
    text = extract_text(source)
    if len(text.strip()) < 400:
        raise RuntimeError("Sartname metni analiz icin fazla kisa (400 karakterden az).")

    branch_line = (
        f"ALT DAL: {branch_name or branch_code}\n"
        "Yalnizca BU DALA ait kosullari cikar; diger dallarin kosullarini karistirma.\n"
        if branch_code else ""
    )
    prompt = USER_TEMPLATE.format(
        competition_name=competition_name, branch_line=branch_line, text=text
    )

    llm = get_llm()
    payload, result = llm.complete_json(
        prompt, system=SYSTEM_PROMPT, max_tokens=6000, temperature=0.1,
        validator=_validate_payload,
    )

    haystack = _normalize(text)
    requirements: list[Requirement] = []
    dropped = 0
    warnings: list[str] = []

    for idx, raw in enumerate(payload.get("requirements", [])):
        quote = str(raw.get("source_quote") or "").strip()
        if not quote or not verify_quote(quote, haystack):
            dropped += 1
            continue
        try:
            rule_type = RuleType(str(raw.get("rule_type", "diger")).lower())
        except ValueError:
            rule_type = RuleType.DIGER
        requirements.append(
            Requirement(
                competition_id=competition_id,
                spec_id=spec_id,
                branch_code=branch_code,
                rule_type=rule_type,
                title=str(raw.get("title") or "Kural")[:120],
                description=(str(raw.get("description")) if raw.get("description") else None),
                min_team_size=_int_or_none(raw.get("min_team_size")),
                max_team_size=_int_or_none(raw.get("max_team_size")),
                advisor_required=bool(raw.get("advisor_required")),
                target_level=(str(raw.get("target_level")) if raw.get("target_level") else None),
                is_mandatory=bool(raw.get("is_mandatory", True)),
                source_quote=quote,
                order_index=idx,
            )
        )

    if dropped:
        warnings.append(
            f"{dropped} kural, sartname metninde dayanak cumlesi dogrulanamadigi icin elendi."
        )
    if not requirements:
        warnings.append(
            "Sartnameden dogrulanabilir kural cikarilamadi. Metin taranmis goruntu olabilir "
            "veya sartname kosul icermiyor olabilir."
        )

    schedule = {
        k: str(v).strip()
        for k, v in (payload.get("schedule") or {}).items()
        if v and str(v).strip().lower() not in ("null", "none", "")
    }

    log.info(
        "[spec] %s%s -> %d kural (%d elendi) · %s/%s",
        competition_id, f"/{branch_code}" if branch_code else "",
        len(requirements), dropped, result.provider, result.model,
    )
    return SpecAnalysis(
        requirements=requirements,
        schedule=schedule,
        summary=str(payload.get("summary") or "").strip(),
        provider=result.provider,
        model=result.model,
        dropped_unverified=dropped,
        warnings=warnings,
    )


def _validate_payload(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("Kok nesne sozluk olmali.")
    reqs = payload.get("requirements")
    if not isinstance(reqs, list):
        raise ValueError("'requirements' bir dizi olmali.")
    for item in reqs:
        if not isinstance(item, dict):
            raise ValueError("Her kural bir nesne olmali.")
        if not item.get("title"):
            raise ValueError("Her kuralin 'title' alani olmali.")
        if "source_quote" not in item:
            raise ValueError("Her kuralin 'source_quote' alani olmali.")
    return payload


def _int_or_none(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["analyze_specification", "SpecAnalysis", "extract_text", "verify_quote", "LLMUnavailable"]
