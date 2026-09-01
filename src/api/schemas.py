"""
Pydantic API Veri Modelleri ve Şemaları (Problem 4 PRD 3 Kullanıcı Akışı ile Uyumlu)
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

# --- 1. Rapor Yükleme ve Durum Şemaları ---
class ReportUploadResponse(BaseModel):
    report_id: str
    filename: str
    status: str
    message: str
    timestamp: str
    storage_backend: Optional[str] = Field(
        default=None, description="Dosyanın saklandığı yer: R2 | LOCAL"
    )
    security_risk_level: str = Field(
        default="LOW", description="Yükleme sırasındaki güvenlik taraması: LOW | MEDIUM | HIGH"
    )

# --- 2. 6 Zorunlu MVP Kontrol Şemaları ---
class LanguageCheckResult(BaseModel):
    detected_lang: str
    expected_lang: str = "tr"
    is_valid: bool
    confidence: float

class TemplateCheckResult(BaseModel):
    page_count: int
    max_allowed: int = 15
    is_valid: bool
    font_family_detected: Optional[str] = "Arial/Calibri"
    warnings: List[str] = Field(default_factory=list)

class SectionStatus(BaseModel):
    section_name: str
    exists: bool
    word_count: int
    status: str  # "OK", "EMPTY", "MISSING"

class SectionCheckResult(BaseModel):
    total_required: int
    found_count: int
    is_complete: bool
    sections: Dict[str, SectionStatus]

class CategoryCheckResult(BaseModel):
    applied_category: str
    is_aligned: bool
    semantic_similarity: float
    explanation: str

class SimilarProjectMatch(BaseModel):
    matched_report_id: str
    project_title: str
    similarity_ratio: float = Field(..., description="0.0 - 1.0 arası kosinüs benzerliği")
    matched_paragraphs: List[str] = Field(default_factory=list)

class SimilarityCheckResult(BaseModel):
    highest_similarity: float
    is_high_risk: bool = Field(..., description="%70 üzeri ise True (Kırmızı Bayrak)")
    risk_level: str  # "LOW", "MEDIUM", "HIGH"
    matches: List[SimilarProjectMatch] = Field(default_factory=list)

# --- 3. Kriter Bazlı AI 4. Göz Değerlendirme Şemaları ---
class CriterionScore(BaseModel):
    criterion_id: str
    criterion_name: str
    ai_score: float
    max_score: float = 20.0
    reasoning: str
    strengths: List[str]
    weaknesses: List[str]

class AIEvaluationSummary(BaseModel):
    total_ai_score: float
    executive_summary: str
    referee_recommendation: str  # KABUL, REVIZYON, RET
    confidence_score: float
    criteria: List[CriterionScore]

# --- 3b. Siber Güvenlik / KVKK Tarama Sonucu ---
class SecurityCheckResult(BaseModel):
    """
    Yükleme sırasında SecurityGuard tarafından üretilir; hakem panelinde
    kırmızı bayrak olarak gösterilir.
    """
    file_validated: bool = Field(..., description="Dosya PDF doğrulamasını geçti mi")
    injection_detected: bool = Field(..., description="Prompt injection girişimi var mı")
    injection_patterns: List[str] = Field(
        default_factory=list,
        description="Tespit edilen manipülasyon ifadeleri (hakeme gösterilir)"
    )
    pii_masked: Dict[str, int] = Field(
        default_factory=dict,
        description="Maskelenen kişisel veri sayıları: tckn, phone, email"
    )
    risk_level: str = Field(default="LOW", description="LOW | MEDIUM | HIGH")
    notes: List[str] = Field(default_factory=list, description="Hakeme Türkçe açıklamalar")


# --- 4. Hakem Karar Destek Ekranı İçin Bütünleşik Analiz Yanıtı ---
class ComprehensiveReportAnalysisResponse(BaseModel):
    report_id: str
    filename: str
    category: str
    overall_status: str
    language_check: LanguageCheckResult
    template_check: TemplateCheckResult
    section_check: SectionCheckResult
    category_check: CategoryCheckResult
    similarity_check: SimilarityCheckResult
    security_check: SecurityCheckResult
    ai_evaluation: AIEvaluationSummary
    check_warnings: List[str] = Field(
        default_factory=list,
        description="Çalıştırılamayan kontroller; hakemin manuel doğrulaması gereken alanlar"
    )

# --- 5. Hakem Nihai Karar Kayıt İsteği (Akış 02) ---
class RefereeEvaluationRequest(BaseModel):
    report_id: str
    referee_id: str
    final_score: float = Field(..., ge=0, le=100)
    decision: str = Field(..., description="APPROVED, REJECTED, NEEDS_REVISION")
    referee_notes: Optional[str] = None
    override_reasons: Optional[str] = None

class RefereeDecisionResponse(BaseModel):
    report_id: str
    referee_id: str
    status: str
    final_score: float
    decision: str
    message: str

# --- 6. Hakem İnteraktif Chat Şemaları ---
class RefereeChatRequest(BaseModel):
    report_id: str
    question: str
    chat_history: Optional[List[Dict[str, str]]] = Field(default_factory=list)

class RefereeChatResponse(BaseModel):
    report_id: str
    question: str
    answer: str
    status: str

# --- 7. Yarışmacı Gelişim Karnesi Yanıtı (Akış 03) ---
class ContestantFeedbackResponse(BaseModel):
    report_id: str
    total_score: float
    status: str
    message: str
    strengths: List[str]
    areas_to_improve: List[str]
    actionable_roadmap: List[str]
    pedagogical_advice: str

# --- 7. Yönetici / Admin Metrikleri ---
class AdminMetricsResponse(BaseModel):
    total_reports_submitted: int
    total_evaluated_by_referees: int
    pending_evaluations: int
    average_score: float
    high_similarity_alerts_count: int
    category_distribution: Dict[str, int]
    decision_distribution: Dict[str, int] = Field(
        default_factory=dict,
        description="Hakem kararlarının dağılımı: APPROVED / REJECTED / NEEDS_REVISION"
    )

# --- 8. Yarışma Şartname & Rubric Şemaları (Admin) ---
class RubricCriterionItem(BaseModel):
    id: Optional[str] = None
    name: str = Field(..., description="Kriter Adı (Örn: Algoritmalar ve Sistem Mimarisi)")
    max_score: float = Field(..., ge=1.0, le=100.0, description="Maksimum puan")
    description: Optional[str] = ""
    guiding_questions: List[str] = Field(default_factory=list)

class CompetitionRubricRequest(BaseModel):
    category_name: str = Field(..., description="Yarışma/Kategori Adı (Örn: Havacılıkta Yapay Zekâ)")
    stage: Optional[str] = Field(
        default="GENEL",
        description="Rapor aşaması: ÖTR / KTR / FTR (boşsa GENEL). Aynı yarışmanın her aşaması ayrı şartname taşır."
    )
    description: Optional[str] = Field(default="", description="Şartname / Kategori açıklaması")
    criteria: List[RubricCriterionItem] = Field(..., description="Resmi şartname değerlendirme kriterleri")
    required_sections: Optional[Dict[str, str]] = Field(
        default_factory=dict,
        description="Şartnamenin zorunlu kıldığı başlıklar (Örn: {'sonuclar': 'Sonuçlar ve İnceleme'})"
    )
    max_pages: Optional[int] = Field(default=15, description="Maksimum izin verilen sayfa sayısı")

class CompetitionRubricResponse(BaseModel):
    category_id: str
    category_name: str
    stage: str = "GENEL"
    description: str
    criteria: List[Dict[str, Any]]
    required_sections: Dict[str, Any]
    max_pages: int
    created_at: str
    message: str = "Şartname rubric başarıyla kaydedildi."

