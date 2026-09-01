"""Pipeline boyunca taşınan veri sözleşmeleri.

Bu dosya aynı zamanda Mehmet'in backend'i ile aramızdaki API kontratıdır:
FastAPI uç noktaları doğrudan bu modelleri döner.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
#  Ortak / temel tipler
# --------------------------------------------------------------------------- #
class Severity(str, Enum):
    OK = "ok"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"


class Language(str, Enum):
    TR = "tr"
    EN = "en"
    UNKNOWN = "unknown"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
#  1) Çıkarma katmanı
# --------------------------------------------------------------------------- #
class PageText(BaseModel):
    page_no: int = Field(..., description="1'den başlayan sayfa numarası")
    text: str
    char_count: int = 0
    #: Sayfada gömülü metin yoksa (taranmış görüntü) True
    needs_ocr: bool = False


class DocumentMeta(BaseModel):
    file_name: str
    file_sha256: str
    page_count: int
    #: PDF'in kendi metadata'sı (başlık, yazar, üretici yazılım)
    pdf_title: str | None = None
    pdf_author: str | None = None
    pdf_producer: str | None = None
    #: Metin gömülü mü, yoksa taranmış mı
    is_scanned: bool = False
    total_chars: int = 0


class ExtractedDocument(BaseModel):
    meta: DocumentMeta
    pages: list[PageText]
    full_text: str
    language: Language = Language.UNKNOWN
    language_confidence: float = 0.0


# --------------------------------------------------------------------------- #
#  2) Bölüm / şablon katmanı
# --------------------------------------------------------------------------- #
class Heading(BaseModel):
    text: str
    #: Sayfadaki ham satır ("3. Çözüm") — bölüm sınırı bununla hesaplanır
    raw_text: str = ""
    normalized: str
    page_no: int
    #: Metindeki karakter ofseti (full_text içinde)
    char_start: int
    level: int = 1
    #: "1.2 Problem Tanımı" -> "1.2"
    numbering: str | None = None
    font_size: float | None = None
    is_bold: bool = False
    #: "style" = Word başlık stili (kesin) · "bold" = kalın metinden tahmin (belirsiz)
    #: · "layout" = PDF tipografisinden tahmin
    detected_by: str = "layout"
    #: Şablonda başlıkta yazan puan ağırlığı, ör. "(30 Puan)" -> 30.0
    points: float | None = None


class Section(BaseModel):
    """Şablondaki bir başlığa karşılık gelen, metni çıkarılmış bölüm."""

    key: str = Field(..., description="Şablon anahtarı, ör. 'problem_tanimi'")
    title: str = Field(..., description="Raporda geçen gerçek başlık metni")
    expected_title: str = Field(..., description="Şablondaki beklenen başlık")
    page_start: int
    page_end: int
    char_start: int
    char_end: int
    text: str
    word_count: int = 0


class SectionFinding(BaseModel):
    """Tek bir şablon maddesi için kontrol sonucu."""

    key: str
    expected_title: str
    found: bool
    matched_title: str | None = None
    #: Başlık eşleşmesinin güveni (0-1)
    match_score: float = 0.0
    word_count: int = 0
    min_words: int = 0
    #: Şablondaki puan ağırlığı — hakem hangi eksiğin ağır olduğunu görsün
    points: float | None = None
    severity: Severity = Severity.OK
    message: str = ""


class TemplateReport(BaseModel):
    """MVP 1-3: dil, şablon ve başlık/içerik kontrolü."""

    template_id: str
    template_name: str
    expected_language: Language
    detected_language: Language
    language_ok: bool
    language_confidence: float = 0.0

    findings: list[SectionFinding] = Field(default_factory=list)
    missing_sections: list[str] = Field(default_factory=list)
    thin_sections: list[str] = Field(default_factory=list)
    #: 0-100, şablona uyum yüzdesi
    compliance_score: float = 0.0
    #: True ise uyum skoru bölüm puanlarıyla ağırlıklandırıldı, değilse eşit ağırlık
    points_weighted: bool = False
    #: Eksik/zayıf bölümlerin toplam kaç puanı riske attığı
    points_at_risk: float = 0.0
    template_total_points: float = 0.0
    severity: Severity = Severity.OK
    summary: str = ""


# --------------------------------------------------------------------------- #
#  3) Chunk / vektör katmanı
# --------------------------------------------------------------------------- #
class Chunk(BaseModel):
    chunk_id: str
    report_id: str
    competition_id: str
    category_id: str | None = None
    team_id: str | None = None
    section_key: str | None = None
    section_title: str | None = None
    page_start: int
    page_end: int
    ordinal: int
    text: str
    char_count: int = 0
    #: Vektörleştirilirken kullanılan zenginleştirilmiş metin
    embed_text: str | None = None

    def payload(self) -> dict[str, Any]:
        """Qdrant payload'ı — filtreleme bu alanlar üzerinden yapılır."""
        return {
            "chunk_id": self.chunk_id,
            "report_id": self.report_id,
            "competition_id": self.competition_id,
            "category_id": self.category_id,
            "team_id": self.team_id,
            "section_key": self.section_key,
            "section_title": self.section_title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "ordinal": self.ordinal,
            "text": self.text,
            "char_count": self.char_count,
        }


# --------------------------------------------------------------------------- #
#  4) Benzerlik / kategori analizi
# --------------------------------------------------------------------------- #
class SimilarPassage(BaseModel):
    """İki rapor arasında eşleşen somut metin çifti — hakeme kanıt olarak sunulur."""

    score: float
    source_chunk_id: str
    source_section: str | None = None
    source_page: int
    source_excerpt: str
    target_chunk_id: str
    target_section: str | None = None
    target_page: int
    target_excerpt: str


class SimilarReport(BaseModel):
    report_id: str
    team_id: str | None = None
    #: Rapor düzeyinde toplu benzerlik (0-1)
    aggregate_score: float
    #: Kaç chunk'ın eşiği aştığı
    matched_chunk_count: int
    #: Kaynak rapordaki chunk'ların yüzde kaçı bu raporla eşleşti
    coverage: float
    severity: Severity
    passages: list[SimilarPassage] = Field(default_factory=list)


class SimilarityReport(BaseModel):
    """MVP 5: başvurular arası yüksek benzerlik tespiti."""

    report_id: str
    competition_id: str
    scope: str = "competition"
    compared_against: int = 0
    matches: list[SimilarReport] = Field(default_factory=list)
    severity: Severity = Severity.OK
    summary: str = ""


class CategoryScore(BaseModel):
    category_id: str
    category_name: str
    score: float
    #: Bu skora en çok katkı yapan rapor parçaları
    evidence: list[str] = Field(default_factory=list)


class CategoryFitReport(BaseModel):
    """MVP 4: kategori uygunluğu analizi."""

    report_id: str
    declared_category_id: str | None = None
    declared_category_name: str | None = None
    declared_score: float = 0.0
    best_category_id: str | None = None
    best_category_name: str | None = None
    best_score: float = 0.0
    ranking: list[CategoryScore] = Field(default_factory=list)
    is_mismatch: bool = False
    severity: Severity = Severity.OK
    message: str = ""


# --------------------------------------------------------------------------- #
#  5) Birleşik çıktı — backend bu nesneyi hakem ekranına taşır
# --------------------------------------------------------------------------- #
class RetrievedContext(BaseModel):
    """Mehmet'in prompt katmanına verilecek, kriter bazlı kanıt paketi."""

    criterion_key: str
    criterion_text: str
    chunks: list[dict[str, Any]] = Field(default_factory=list)


class ReportAnalysis(BaseModel):
    report_id: str
    competition_id: str
    category_id: str | None = None
    team_id: str | None = None
    created_at: datetime = Field(default_factory=_now)

    document: DocumentMeta
    language: Language
    template: TemplateReport | None = None
    category_fit: CategoryFitReport | None = None
    similarity: SimilarityReport | None = None

    chunk_count: int = 0
    indexed: bool = False
    #: Genel ön kontrol durumu — hakem listesinde renk kodu olur
    overall_severity: Severity = Severity.OK
    warnings: list[str] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)
