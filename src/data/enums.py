"""T-Sistem · Tek enum kaynagi.

KURAL: Kodda hicbir yerde status/decision/role icin string literal yazilmaz.
Hepsi buradan import edilir. CI testi (tests/test_enum_contract.py) bunu dogrular.

Onceki kod tabaninda ayni kavram icin dort farkli kelime dagarcigi vardi
(READY_FOR_REFEREE / COMPLETED / "Hakeme Atandi" / "tamamlandi"). Bu modul
o kaosu tek noktada sonlandirir; LEGACY_STATUS_MAP eski kayitlari cevirir.
"""

from __future__ import annotations

from enum import Enum


class StrEnum(str, Enum):
    """Python 3.10 uyumlu str-enum tabani."""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.value


# ── Kullanici ──────────────────────────────────────────────────────────────
class Role(StrEnum):
    YARISMACI = "yarismaci"
    HAKEM = "hakem"
    ADMIN = "admin"


class UserStatus(StrEnum):
    AKTIF = "aktif"
    PASIF = "pasif"


class AuthProvider(StrEnum):
    LOCAL = "local"
    GOOGLE = "google"


# ── Yarisma ────────────────────────────────────────────────────────────────
class PublishStatus(StrEnum):
    TASLAK = "taslak"
    YAYINDA = "yayinda"
    KAPALI = "kapali"


class SpecStatus(StrEnum):
    BEKLENIYOR = "bekleniyor"
    YUKLENDI = "yuklendi"
    ANALIZ_EDILDI = "analiz_edildi"
    ONAYLANDI = "onaylandi"


class RubricStatus(StrEnum):
    BEKLENIYOR = "bekleniyor"
    CIKARILDI = "cikarildi"
    ONAYLANDI = "onaylandi"


class RuleType(StrEnum):
    TAKIM = "takim"
    DANISMAN = "danisman"
    TEKNIK = "teknik"
    KATILIM = "katilim"
    DIL = "dil"
    DIGER = "diger"


# ── Takim / basvuru ────────────────────────────────────────────────────────
class TeamRole(StrEnum):
    KAPTAN = "kaptan"
    UYE = "uye"
    DANISMAN = "danisman"


class TeamStatus(StrEnum):
    AKTIF = "aktif"
    PASIF = "pasif"
    DAGITILDI = "dagitildi"


class ApplicationStatus(StrEnum):
    AKTIF = "aktif"
    GERI_CEKILDI = "geri_cekildi"
    ELENDI = "elendi"
    TAMAMLANDI = "tamamlandi"


class TeamLevel(StrEnum):
    ORTAOKUL = "Ortaokul"
    LISE = "Lise"
    UNIVERSITE = "Universite"
    MEZUN = "Mezun"
    GENEL = "Genel"


# ── Rapor / degerlendirme ──────────────────────────────────────────────────
class ReportStatus(StrEnum):
    BEKLEMEDE = "BEKLEMEDE"
    HAKEME_ATANDI = "HAKEME_ATANDI"
    DEGERLENDIRILIYOR = "DEGERLENDIRILIYOR"
    DEGERLENDIRILDI = "DEGERLENDIRILDI"
    REVIZYON_ISTENDI = "REVIZYON_ISTENDI"
    REDDEDILDI = "REDDEDILDI"

    @property
    def label_tr(self) -> str:
        return {
            "BEKLEMEDE": "Hakem Atamasi Bekleniyor",
            "HAKEME_ATANDI": "Hakem Degerlendirmesinde",
            "DEGERLENDIRILIYOR": "Inceleniyor",
            "DEGERLENDIRILDI": "Degerlendirme Tamamlandi",
            "REVIZYON_ISTENDI": "Revizyon Istendi",
            "REDDEDILDI": "Reddedildi",
        }[self.value]

    @property
    def label_en(self) -> str:
        return {
            "BEKLEMEDE": "Awaiting Referee Assignment",
            "HAKEME_ATANDI": "Under Referee Review",
            "DEGERLENDIRILIYOR": "In Progress",
            "DEGERLENDIRILDI": "Evaluation Completed",
            "REVIZYON_ISTENDI": "Revision Requested",
            "REDDEDILDI": "Rejected",
        }[self.value]

    @property
    def tone(self) -> str:
        """UI rozet tonu: info | warn | ok | crit"""
        return {
            "BEKLEMEDE": "warn",
            "HAKEME_ATANDI": "info",
            "DEGERLENDIRILIYOR": "info",
            "DEGERLENDIRILDI": "ok",
            "REVIZYON_ISTENDI": "warn",
            "REDDEDILDI": "crit",
        }[self.value]


class AssignmentStatus(StrEnum):
    ATANDI = "ATANDI"
    INCELENIYOR = "INCELENIYOR"
    TAMAMLANDI = "TAMAMLANDI"
    IPTAL = "IPTAL"


class Decision(StrEnum):
    KABUL = "KABUL"
    REVIZYON = "REVIZYON"
    RET = "RET"

    @property
    def label_tr(self) -> str:
        return {"KABUL": "Kabul", "REVIZYON": "Revizyon", "RET": "Ret"}[self.value]


class RiskLevel(StrEnum):
    DUSUK = "DUSUK"
    ORTA = "ORTA"
    YUKSEK = "YUKSEK"


# ── Eski veriyi cevirme haritasi ───────────────────────────────────────────
LEGACY_STATUS_MAP: dict[str, ReportStatus] = {
    "beklemede": ReportStatus.BEKLEMEDE,
    "pending": ReportStatus.BEKLEMEDE,
    "hakeme atandi": ReportStatus.HAKEME_ATANDI,
    "hakeme atandı": ReportStatus.HAKEME_ATANDI,
    "ready_for_referee": ReportStatus.HAKEME_ATANDI,
    "atandi": ReportStatus.HAKEME_ATANDI,
    "degerlendiriliyor": ReportStatus.DEGERLENDIRILIYOR,
    "in_review": ReportStatus.DEGERLENDIRILIYOR,
    "degerlendirildi": ReportStatus.DEGERLENDIRILDI,
    "değerlendirildi": ReportStatus.DEGERLENDIRILDI,
    "tamamlandi": ReportStatus.DEGERLENDIRILDI,
    "completed": ReportStatus.DEGERLENDIRILDI,
    "evaluation_completed": ReportStatus.DEGERLENDIRILDI,
    "needs_revision": ReportStatus.REVIZYON_ISTENDI,
    "rejected": ReportStatus.REDDEDILDI,
}

LEGACY_DECISION_MAP: dict[str, Decision] = {
    "approved": Decision.KABUL,
    "onaylandi": Decision.KABUL,
    "onaylandı": Decision.KABUL,
    "kabul": Decision.KABUL,
    "needs_revision": Decision.REVIZYON,
    "revizyon": Decision.REVIZYON,
    "rejected": Decision.RET,
    "ret": Decision.RET,
}

LEGACY_ROLE_MAP: dict[str, Role] = {
    "uye": Role.YARISMACI,
    "üye": Role.YARISMACI,
    "contestant": Role.YARISMACI,
    "yarismaci": Role.YARISMACI,
    "hakem": Role.HAKEM,
    "referee": Role.HAKEM,
    "field_referee": Role.HAKEM,
    "head_referee": Role.HAKEM,
    "admin": Role.ADMIN,
    "yonetici": Role.ADMIN,
    "yönetici": Role.ADMIN,
}


def normalize_status(raw: str | None) -> ReportStatus:
    """Eski/serbest yazilmis durum degerini kanonik enum'a cevirir."""
    if not raw:
        return ReportStatus.BEKLEMEDE
    key = str(raw).strip()
    try:
        return ReportStatus(key.upper())
    except ValueError:
        return LEGACY_STATUS_MAP.get(key.lower(), ReportStatus.BEKLEMEDE)


def normalize_decision(raw: str | None) -> Decision:
    if not raw:
        return Decision.REVIZYON
    key = str(raw).strip()
    try:
        return Decision(key.upper())
    except ValueError:
        return LEGACY_DECISION_MAP.get(key.lower(), Decision.REVIZYON)


def normalize_provider(raw: str | None) -> AuthProvider:
    """Eski kayitlarda `auth_provider` serbest metindi (or. 'cloudflare_d1')."""
    value = (raw or "").strip().lower()
    if "google" in value:
        return AuthProvider.GOOGLE
    return AuthProvider.LOCAL


def normalize_user_status(raw: str | None) -> UserStatus:
    value = (raw or "").strip().lower()
    if value in ("pasif", "passive", "inactive", "disabled", "0"):
        return UserStatus.PASIF
    return UserStatus.AKTIF


def normalize_role(raw: str | None) -> Role:
    if not raw:
        return Role.YARISMACI
    key = str(raw).strip()
    try:
        return Role(key.lower())
    except ValueError:
        return LEGACY_ROLE_MAP.get(key.lower(), Role.YARISMACI)


__all__ = [
    "Role", "UserStatus", "AuthProvider",
    "PublishStatus", "SpecStatus", "RubricStatus", "RuleType",
    "TeamRole", "TeamStatus", "ApplicationStatus", "TeamLevel",
    "ReportStatus", "AssignmentStatus", "Decision", "RiskLevel",
    "normalize_status", "normalize_decision", "normalize_role",
    "normalize_provider", "normalize_user_status",
    "LEGACY_STATUS_MAP", "LEGACY_DECISION_MAP", "LEGACY_ROLE_MAP",
]
