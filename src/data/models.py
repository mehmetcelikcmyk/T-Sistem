"""T-Sistem · Pydantic veri modelleri.

Repository katmani dict degil, BU modelleri alir ve dondurur.
Boylece kolon adi uyusmazliklari (file_name vs filename, stage vs stage_code)
calisma zamaninda degil, dogrulama aninda yakalanir.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import (
    ApplicationStatus,
    AssignmentStatus,
    AuthProvider,
    Decision,
    PublishStatus,
    ReportStatus,
    RiskLevel,
    Role,
    RubricStatus,
    RuleType,
    SpecStatus,
    TeamRole,
    TeamStatus,
    UserStatus,
    normalize_decision,
    normalize_provider,
    normalize_role,
    normalize_status,
    normalize_user_status,
)


def new_id() -> str:
    """Tum kimlikler icin tek uretec. hash() KULLANILMAZ."""
    return str(uuid.uuid4())


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Base(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        populate_by_name=True,
        use_enum_values=False,
        str_strip_whitespace=True,
    )

    def to_row(self) -> dict[str, Any]:
        """SQL parametrelerine uygun duz sozluk (enum -> str, None korunur)."""
        row: dict[str, Any] = {}
        for key, val in self.model_dump(mode="python").items():
            if isinstance(val, bool):
                row[key] = 1 if val else 0
            elif hasattr(val, "value"):
                row[key] = val.value
            else:
                row[key] = val
        return row


# ── Kullanici ──────────────────────────────────────────────────────────────
class User(Base):
    user_id: str = Field(default_factory=new_id)
    username: str | None = None
    name: str
    surname: str | None = None
    email: str
    password_hash: str | None = None
    role: Role = Role.YARISMACI
    institution: str | None = None
    department: str | None = None
    graduation_status: str | None = None
    tc_citizen: str | None = None
    gender: str | None = None
    birth_date: str | None = None
    phone: str | None = None
    address: str | None = None
    education_level: str | None = None
    specialty: str | None = None
    auth_provider: AuthProvider = AuthProvider.LOCAL
    profile_completed: bool = False
    status: UserStatus = UserStatus.AKTIF
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None

    @field_validator("email", mode="before")
    @classmethod
    def _lower_email(cls, v: Any) -> Any:
        return str(v).strip().lower() if v else v

    @field_validator("role", mode="before")
    @classmethod
    def _norm_role(cls, v: Any) -> Any:
        return normalize_role(v) if isinstance(v, str) else v

    @field_validator("auth_provider", mode="before")
    @classmethod
    def _norm_provider(cls, v: Any) -> Any:
        # Eski kayitlarda bu alan serbest metindi (or. 'cloudflare_d1').
        return normalize_provider(v) if isinstance(v, str) else v

    @field_validator("status", mode="before")
    @classmethod
    def _norm_user_status(cls, v: Any) -> Any:
        return normalize_user_status(v) if isinstance(v, str) else v

    @field_validator("profile_completed", mode="before")
    @classmethod
    def _norm_completed(cls, v: Any) -> Any:
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "evet", "yes")
        return v

    @property
    def full_name(self) -> str:
        return f"{self.name} {self.surname}".strip() if self.surname else self.name

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN

    @property
    def is_referee(self) -> bool:
        return self.role == Role.HAKEM


# ── Yarisma ────────────────────────────────────────────────────────────────
class Competition(Base):
    competition_id: str
    name: str
    slug: str
    domain: str
    sub_category: str | None = None
    levels: str | None = None
    description: str | None = None
    logo_r2_key: str | None = None
    schedule_json: str | None = None
    awards_json: str | None = None
    publish_status: PublishStatus = PublishStatus.TASLAK
    spec_status: SpecStatus = SpecStatus.BEKLENIYOR
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None

    @property
    def level_list(self) -> list[str]:
        return [s.strip() for s in (self.levels or "").split(",") if s.strip()]


class CompetitionSpec(Base):
    """Sartname. Cok dalli yarismalarda her dal ayri satirdir (branch_code)."""

    spec_id: str = Field(default_factory=new_id)
    competition_id: str
    title: str
    branch_code: str | None = None
    branch_name: str | None = None
    r2_key: str
    original_name: str | None = None
    page_count: int | None = None
    is_primary: bool = False
    analyzed_at: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None


class Stage(Base):
    stage_id: str = Field(default_factory=new_id)
    competition_id: str
    stage_code: str
    stage_name: str
    level: str = "Genel"
    branch_code: str | None = None
    sablon_docx_r2_key: str | None = None
    sablon_pdf_r2_key: str | None = None
    max_pages: int = 25
    max_score: float = 100.0
    passing_score: float = 70.0
    quota_limit: int | None = None
    revision_min_score: float = 60.0
    stage_status: str = "DEGERLENDIRMEDE"
    deadline: str | None = None
    font_and_margins: str | None = None
    required_sections_json: str | None = None
    is_auto_generated: bool = False
    rubric_status: RubricStatus = RubricStatus.BEKLENIYOR
    order_index: int = 0
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None

    @field_validator("stage_code", mode="before")
    @classmethod
    def _upper_code(cls, v: Any) -> Any:
        return str(v).strip().upper() if v else v


class Requirement(Base):
    """Sartnameden AI ile cikarilan kural. source_quote AI icin ZORUNLUDUR."""

    req_id: str = Field(default_factory=new_id)
    competition_id: str
    spec_id: str | None = None
    branch_code: str | None = None
    rule_type: RuleType = RuleType.DIGER
    title: str
    description: str | None = None
    min_team_size: int | None = None
    max_team_size: int | None = None
    advisor_required: bool = False
    target_level: str | None = None
    is_mandatory: bool = True
    source_quote: str | None = None
    source_page: int | None = None
    approved_by_admin: bool = False
    order_index: int = 0
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None


class RubricCriterion(Base):
    criterion_id: str = Field(default_factory=new_id)
    competition_id: str
    stage_code: str
    level: str = "Genel"
    branch_code: str | None = None
    criterion_code: str
    criterion_name: str
    description: str | None = None
    max_score: float
    parent_code: str | None = None
    source_quote: str | None = None
    approved_by_admin: bool = False
    order_index: int = 0
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None


# ── Takim / basvuru ────────────────────────────────────────────────────────
class Team(Base):
    team_id: str = Field(default_factory=new_id)
    team_code: str
    name: str
    level: str | None = None
    institution: str | None = None
    captain_user_id: str
    advisor_name: str | None = None
    advisor_email: str | None = None
    advisor_title: str | None = None
    status: TeamStatus = TeamStatus.AKTIF
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None


class TeamMember(Base):
    team_id: str
    user_id: str
    role_in_team: TeamRole = TeamRole.UYE
    joined_at: str = Field(default_factory=now_iso)


class Application(Base):
    app_id: str = Field(default_factory=new_id)
    team_id: str
    competition_id: str
    branch_code: str | None = None
    level: str | None = None
    status: ApplicationStatus = ApplicationStatus.AKTIF
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None


# ── Rapor / degerlendirme ──────────────────────────────────────────────────
class Report(Base):
    report_id: str = Field(default_factory=new_id)
    app_id: str
    competition_id: str
    stage_code: str
    level: str = "Genel"
    branch_code: str | None = None
    version: int = 1
    file_name: str
    r2_key: str
    page_count: int | None = None
    report_text: str | None = None
    status: ReportStatus = ReportStatus.BEKLEMEDE
    security_json: str | None = None
    checks_json: str | None = None
    ai_score: float | None = None
    ai_data_json: str | None = None
    referee_score: float | None = None
    referee_id: str | None = None
    referee_notes: str | None = None
    feedback_json: str | None = None
    uploaded_by: str | None = None
    decision: str | None = None
    evaluated_at: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None

    @field_validator("status", mode="before")
    @classmethod
    def _norm_status(cls, v: Any) -> Any:
        return normalize_status(v) if isinstance(v, str) else v

    @field_validator("stage_code", mode="before")
    @classmethod
    def _upper_stage(cls, v: Any) -> Any:
        return str(v).strip().upper() if v else v


class Assignment(Base):
    assignment_id: str = Field(default_factory=new_id)
    report_id: str
    referee_user_id: str
    assigned_by: str
    status: AssignmentStatus = AssignmentStatus.ATANDI
    assigned_at: str = Field(default_factory=now_iso)
    completed_at: str | None = None


class CriterionScore(Base):
    evaluation_id: str = ""
    criterion_code: str
    criterion_name: str
    max_score: float
    ai_score: float | None = None
    referee_score: float
    ai_rationale: str | None = None
    referee_rationale: str | None = None
    evidence_json: str | None = None
    order_index: int = 0


class Evaluation(Base):
    evaluation_id: str = Field(default_factory=new_id)
    assignment_id: str
    report_id: str
    referee_user_id: str
    total_score: float
    ai_total_score: float | None = None
    max_total_score: float = 100.0
    decision: Decision = Decision.REVIZYON
    referee_notes: str | None = None
    spec_compliance_json: str | None = None
    sealed_at: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None

    @field_validator("decision", mode="before")
    @classmethod
    def _norm_decision(cls, v: Any) -> Any:
        return normalize_decision(v) if isinstance(v, str) else v


class ReportCard(Base):
    card_id: str = Field(default_factory=new_id)
    app_id: str
    report_id: str
    evaluation_id: str
    total_score: float
    max_total_score: float = 100.0
    strengths_json: str | None = None
    improvements_json: str | None = None
    roadmap_json: str | None = None
    pedagogical_note: str | None = None
    pdf_r2_key: str | None = None
    published_at: str | None = None
    created_at: str = Field(default_factory=now_iso)
    updated_at: str | None = None


class SimilarityResult(Base):
    result_id: str = Field(default_factory=new_id)
    report_id: str
    matched_report_id: str
    literal_score: float = 0.0
    semantic_score: float = 0.0
    combined_score: float = 0.0
    risk_level: RiskLevel = RiskLevel.DUSUK
    matched_spans_json: str | None = None
    engine_version: str | None = None
    created_at: str = Field(default_factory=now_iso)


class AuditEntry(Base):
    log_id: str = Field(default_factory=new_id)
    actor_user_id: str | None = None
    actor_email: str | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    before_json: str | None = None
    after_json: str | None = None
    ip_hint: str | None = None
    created_at: str = Field(default_factory=now_iso)


class Notification(Base):
    notification_id: str = Field(default_factory=new_id)
    user_id: str
    kind: str
    title: str
    body: str | None = None
    link: str | None = None
    is_read: bool = False
    created_at: str = Field(default_factory=now_iso)


__all__ = [
    "new_id", "now_iso", "Base",
    "User", "Competition", "CompetitionSpec", "Stage", "Requirement", "RubricCriterion",
    "Team", "TeamMember", "Application",
    "Report", "Assignment", "Evaluation", "CriterionScore", "ReportCard",
    "SimilarityResult", "AuditEntry", "Notification",
]
