"""PDF -> yapılandırılmış metin çıkarma katmanı.

Sorumluluk:
  * Sayfa sayfa metin + karakter ofseti (sonraki katmanlar bölüm sınırlarını
    ofsetle bulacağı için ofset tutarlılığı kritik).
  * Satır/span düzeyinde font bilgisi (başlık tespiti bunun üzerine kurulu).
  * Taranmış (metinsiz) PDF tespiti ve isteğe bağlı OCR fallback.
  * Türkçe PDF'lerde sık görülen bozuk tireleme / satır kırılması onarımı.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..models import DocumentMeta, ExtractedDocument, PageText
from .language import detect_language

logger = logging.getLogger(__name__)

# Satır sonu tirelemesi: "değerlen-\ndirme" -> "değerlendirme"
HYPHEN_BREAK_RE = re.compile(r"(\w)-\s*\n\s*(\w)")
# Tek satır kırılması (paragraf ortası) -> boşluk; çift satır sonu korunur
SINGLE_NEWLINE_RE = re.compile(r"(?<![\n\.\:\;\?\!])\n(?![\n•\-\d])")
MULTI_SPACE_RE = re.compile(r"[ \t ]{2,}")
MULTI_NEWLINE_RE = re.compile(r"\n{3,}")


@dataclass
class SpanInfo:
    """Başlık tespiti için taşınan tipografik bilgi."""

    text: str
    page_no: int
    #: full_text içindeki mutlak karakter ofseti
    char_start: int
    font_size: float
    is_bold: bool
    bbox: tuple[float, float, float, float]


@dataclass
class ExtractionResult:
    document: ExtractedDocument
    spans: list[SpanInfo] = field(default_factory=list)
    #: Sayfa başına full_text ofset başlangıcı
    page_offsets: list[int] = field(default_factory=list)
    #: DOCX girdilerinde Word stilinden gelen KESİN başlıklar. PDF'lerde boş
    #: kalır; dolu olduğunda tipografi tahmini atlanır (bkz. detect_headings).
    docx_headings: list = field(default_factory=list)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def clean_text(raw: str) -> str:
    """PDF metnini analiz edilebilir hale getirir (ofsetler bu metne göre kurulur)."""
    txt = raw.replace("\r\n", "\n").replace("\r", "\n")
    txt = txt.replace("­", "")            # yumuşak tire
    txt = txt.replace("ﬁ", "fi").replace("ﬂ", "fl")  # ligatür
    txt = HYPHEN_BREAK_RE.sub(r"\1\2", txt)
    txt = SINGLE_NEWLINE_RE.sub(" ", txt)
    txt = MULTI_SPACE_RE.sub(" ", txt)
    txt = MULTI_NEWLINE_RE.sub("\n\n", txt)
    return txt.strip()


def _is_bold(span: dict) -> bool:
    flags = span.get("flags", 0)
    # PyMuPDF flag bit 4 (16) = bold
    if flags & 16:
        return True
    return "bold" in str(span.get("font", "")).lower()


def extract_pdf(
    path: str | Path,
    *,
    ocr_if_scanned: bool = False,
    ocr_language: str = "tur+eng",
) -> ExtractionResult:
    """Bir PDF'i çıkarır.

    Args:
        path: PDF yolu.
        ocr_if_scanned: Gömülü metin yoksa Tesseract ile OCR dene.
                        (PyMuPDF'in tessdata desteği kuruluysa çalışır.)
        ocr_language: OCR dil paketi.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"PDF bulunamadı: {path}")

    doc = pymupdf.open(path)
    pages: list[PageText] = []
    spans: list[SpanInfo] = []
    page_offsets: list[int] = []
    parts: list[str] = []
    cursor = 0

    try:
        for page_index in range(doc.page_count):
            page = doc.load_page(page_index)
            page_no = page_index + 1

            raw = page.get_text("text") or ""
            needs_ocr = len(raw.strip()) < 20

            if needs_ocr and ocr_if_scanned:
                try:
                    tp = page.get_textpage_ocr(language=ocr_language, dpi=300, full=True)
                    raw = page.get_text("text", textpage=tp) or raw
                    needs_ocr = len(raw.strip()) < 20
                except Exception as exc:  # pragma: no cover - ortama bağlı
                    logger.warning("Sayfa %s OCR başarısız: %s", page_no, exc)

            cleaned = clean_text(raw)
            page_offsets.append(cursor)

            # Tipografik span'leri topla (başlık tespiti için)
            if not needs_ocr:
                try:
                    d = page.get_text("dict")
                    for block in d.get("blocks", []):
                        for line in block.get("lines", []):
                            line_spans = line.get("spans", [])
                            if not line_spans:
                                continue
                            line_text = "".join(s.get("text", "") for s in line_spans).strip()
                            if not line_text:
                                continue
                            first = line_spans[0]
                            # Satırın konumunu temizlenmiş metinde ara
                            local = cleaned.find(line_text[:60])
                            char_start = cursor + (local if local >= 0 else 0)
                            spans.append(
                                SpanInfo(
                                    text=line_text,
                                    page_no=page_no,
                                    char_start=char_start,
                                    font_size=round(float(first.get("size", 0.0)), 2),
                                    is_bold=any(_is_bold(s) for s in line_spans),
                                    bbox=tuple(line.get("bbox", (0, 0, 0, 0))),
                                )
                            )
                except Exception as exc:  # pragma: no cover
                    logger.debug("Span çıkarma hatası s.%s: %s", page_no, exc)

            pages.append(
                PageText(
                    page_no=page_no,
                    text=cleaned,
                    char_count=len(cleaned),
                    needs_ocr=needs_ocr,
                )
            )
            parts.append(cleaned)
            cursor += len(cleaned) + 2  # "\n\n" ayırıcı

        full_text = "\n\n".join(parts)
        total_chars = sum(p.char_count for p in pages)
        scanned_pages = sum(1 for p in pages if p.needs_ocr)

        meta = DocumentMeta(
            file_name=path.name,
            file_sha256=_sha256(path),
            page_count=doc.page_count,
            pdf_title=(doc.metadata or {}).get("title") or None,
            pdf_author=(doc.metadata or {}).get("author") or None,
            pdf_producer=(doc.metadata or {}).get("producer") or None,
            is_scanned=doc.page_count > 0 and scanned_pages >= doc.page_count * 0.5,
            total_chars=total_chars,
        )
    finally:
        doc.close()

    lang, conf = detect_language(full_text)
    extracted = ExtractedDocument(
        meta=meta,
        pages=pages,
        full_text=full_text,
        language=lang,
        language_confidence=conf,
    )
    return ExtractionResult(document=extracted, spans=spans, page_offsets=page_offsets)


def extract_document(
    path: str | Path,
    *,
    ocr_if_scanned: bool = False,
    ocr_language: str = "tur+eng",
) -> ExtractionResult:
    """Uzantıya göre doğru çıkarıcıyı seçer (PDF veya DOCX).

    Takımların çoğu PDF yüklüyor ama hepsi değil — elimizdeki gerçek veri
    setinde Jet Motor klasöründeki raporlardan biri .docx. Analiz hattının
    dosya biçimi yüzünden durmaması için tek giriş noktası bu.

    DOCX yolunda Word'ün başlık stilleri zaten kesin bilgi verdiği için
    tipografi tahminine gerek kalmıyor; başlıklar doğrudan taşınıyor.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf(path, ocr_if_scanned=ocr_if_scanned,
                           ocr_language=ocr_language)

    if suffix in (".docx", ".docm"):
        from .docx_extractor import extract_docx

        document, headings = extract_docx(path)
        # DOCX tek akış olduğu için sayfa ofseti tek elemanlı; span üretmiyoruz
        # çünkü başlıklar hazır geliyor (bkz. ExtractionResult.docx_headings).
        result = ExtractionResult(document=document, spans=[], page_offsets=[0])
        result.docx_headings = headings
        return result

    raise ValueError(
        f"Desteklenmeyen dosya biçimi: '{suffix}'. PDF veya DOCX bekleniyor."
    )


def page_of_offset(page_offsets: list[int], offset: int) -> int:
    """Karakter ofsetinden 1-tabanlı sayfa numarası bulur."""
    lo, hi = 0, len(page_offsets) - 1
    if hi < 0:
        return 1
    best = 0
    while lo <= hi:
        mid = (lo + hi) // 2
        if page_offsets[mid] <= offset:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best + 1
