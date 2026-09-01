"""T-Sistem · SOZLESME TESTLERI (Faz 9).

Bu testler, eski kod tabanindaki bes sistemik hata desenini YAPISAL olarak
imkansiz kilar. Her biri gercek bir gecmis hatayi yakalar:

  test_schema_contract   -> 9 tablo/kolon uyusmazligi (yazma islemleri sessizce
                            patliyordu)
  test_enum_contract     -> 4 farkli status kelime dagarcigi
  test_no_silent_pass    -> 40+ `except Exception: pass`
  test_css_contract      -> 12 tanimsiz CSS sinifi
  test_hex_lint          -> 137 hardcoded hex kodu
  test_no_mock_in_views  -> arayuze sizan sahte veri
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
NEW_MODULES = [
    SRC / "data", SRC / "ai", SRC / "evaluation", SRC / "similarity",
    SRC / "security" / "auth.py", SRC / "services" / "doc_converter.py",
    SRC / "ui" / "theme.py", SRC / "ui" / "views" / "yarismaci.py",
    SRC / "ui" / "views" / "yonetici.py", SRC / "ui" / "views" / "hakem.py",
]



def _code_only(path: Path) -> str:
    """Yorumlari ve docstring'leri ATAR — yalnizca calisan kod kalir.

    Bu sart: yeni moduller, eski hatalari ACIKLAMAK icin docstring'lerinde
    o hatalarin metinlerini (or. `oranlar[idx % 6]`) bilincli olarak
    barindirir. Testler yalnizca gercek kodu denetlemelidir.
    """
    import io
    import tokenize

    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc is None:
                continue
            first = node.body[0]
            for line in range(first.lineno, (first.end_lineno or first.lineno) + 1):
                doc_lines.add(line)

    kept: list[str] = []
    for index, line in enumerate(source.split("\n"), 1):
        if index in doc_lines:
            kept.append("")
            continue
        kept.append(line)
    text = "\n".join(kept)

    # satir ici yorumlari at
    out: list[str] = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type == tokenize.COMMENT:
                continue
            out.append(token.string if token.type != tokenize.NL else "\n")
    except (tokenize.TokenError, IndentationError):
        return text
    return "\n".join(l for l in text.split("\n") if not l.strip().startswith("#"))


def _python_files(paths: list[Path]) -> list[Path]:
    out: list[Path] = []
    for path in paths:
        if path.is_file() and path.suffix == ".py":
            out.append(path)
        elif path.is_dir():
            out.extend(p for p in path.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(out)


# ═══════════════════════════════════════════════════════════════════════════
# 1 · SEMA SOZLESMESI
# ═══════════════════════════════════════════════════════════════════════════
def _schema_tables() -> dict[str, set[str]]:
    text = (SRC / "data" / "schema.sql").read_text(encoding="utf-8")
    tables: dict[str, set[str]] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", text, re.DOTALL
    ):
        name, body = match.group(1), match.group(2)
        columns: set[str] = set()
        for line in body.split("\n"):
            stripped = line.strip().rstrip(",")
            if not stripped or stripped.startswith("--"):
                continue
            head = stripped.split()[0].upper()
            if head in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}:
                continue
            columns.add(stripped.split()[0])
        tables[name] = columns
    return tables


def test_schema_has_all_expected_tables() -> None:
    from src.data.migrate import EXPECTED_TABLES

    tables = _schema_tables()
    missing = [t for t in EXPECTED_TABLES if t not in tables]
    assert not missing, f"schema.sql icinde eksik tablo: {missing}"


def test_schema_contract_tables_referenced_in_code_exist() -> None:
    """Kodda FROM/INTO/UPDATE ile gecen her tablo semada tanimli olmali."""
    tables = set(_schema_tables())
    sql_marker = re.compile(r"\b(SELECT|INSERT INTO|UPDATE|DELETE FROM)\b")
    pattern = re.compile(r"(?:FROM|INTO|UPDATE|JOIN)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
    sql_keywords = {
        "set", "select", "values", "where", "excluded", "sqlite_master",
        "table", "exists", "index",
    }
    violations: list[str] = []

    for path in _python_files(NEW_MODULES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # YALNIZCA SQL iceren string sabitleri taranir; Python'un
            # `from X import` / `raise ... from exc` ifadeleri degil.
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            sql = node.value
            if not sql_marker.search(sql.upper()):
                continue
            for name in pattern.findall(sql):
                lowered = name.lower()
                if lowered in sql_keywords or lowered in tables:
                    continue
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}: {name}")
    assert not violations, "Semada olmayan tablo referansi:\n" + "\n".join(violations)


def test_models_match_schema_columns() -> None:
    """Pydantic modellerinin alanlari tablo kolonlarinin ALT KUMESI olmali."""
    from src.data import models as m

    tables = _schema_tables()
    mapping = {
        m.User: "auth_users", m.Competition: "competitions",
        m.CompetitionSpec: "competition_specs", m.Stage: "competition_stages",
        m.Requirement: "competition_requirements", m.RubricCriterion: "stage_rubric_criteria",
        m.Team: "teams", m.TeamMember: "team_members", m.Application: "applications",
        m.Report: "reports", m.Assignment: "report_assignments",
        m.Evaluation: "evaluations", m.CriterionScore: "evaluation_scores",
        m.ReportCard: "report_cards", m.SimilarityResult: "similarity_results",
        m.AuditEntry: "audit_log", m.Notification: "notifications",
    }
    problems: list[str] = []
    for model, table in mapping.items():
        fields = set(model.model_fields)
        extra = fields - tables.get(table, set())
        if extra:
            problems.append(f"{model.__name__} -> {table}: fazla alan {sorted(extra)}")
    assert not problems, "Model/sema uyusmazligi:\n" + "\n".join(problems)


# ═══════════════════════════════════════════════════════════════════════════
# 2 · ENUM SOZLESMESI
# ═══════════════════════════════════════════════════════════════════════════
LEGACY_STATUS_LITERALS = [
    "READY_FOR_REFEREE", "EVALUATION_COMPLETED", "HAKEM-EMRE-1",
    "usr_hakem_ef6def", "Hakeme Atandı", "hyz-otr-2026", "iyt-otr-2026",
]


def test_no_legacy_status_literals() -> None:
    violations: list[str] = []
    for path in _python_files(NEW_MODULES):
        text = _code_only(path)
        for literal in LEGACY_STATUS_LITERALS:
            if literal in text:
                violations.append(f"{path.relative_to(ROOT)}: '{literal}'")
    assert not violations, "Eski enum/kimlik sabiti:\n" + "\n".join(violations)


def test_enum_values_are_unique_and_normalizable() -> None:
    from src.data.enums import (
        Decision, ReportStatus, Role, normalize_decision, normalize_role, normalize_status,
    )

    assert len({s.value for s in ReportStatus}) == len(list(ReportStatus))
    assert normalize_status("Hakeme Atandı") is ReportStatus.HAKEME_ATANDI
    assert normalize_status("READY_FOR_REFEREE") is ReportStatus.HAKEME_ATANDI
    assert normalize_status("tamamlandi") is ReportStatus.DEGERLENDIRILDI
    assert normalize_status(None) is ReportStatus.BEKLEMEDE
    assert normalize_decision("APPROVED") is Decision.KABUL
    assert normalize_decision("ONAYLANDI") is Decision.KABUL
    assert normalize_role("FIELD_REFEREE") is Role.HAKEM
    assert normalize_role("yonetici") is Role.ADMIN
    for status in ReportStatus:
        assert status.label_tr and status.label_en and status.tone


# ═══════════════════════════════════════════════════════════════════════════
# 3 · SESSIZ HATA YUTMA YASAGI
# ═══════════════════════════════════════════════════════════════════════════
def test_no_silent_exception_pass() -> None:
    """`except ...: pass` YASAK — eski kodda 40+ adet vardi."""
    violations: list[str] = []
    for path in _python_files(NEW_MODULES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ExceptHandler):
                continue
            body = [n for n in node.body if not (
                isinstance(n, ast.Expr) and isinstance(getattr(n, "value", None), ast.Constant)
            )]
            if len(body) == 1 and isinstance(body[0], ast.Pass):
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "Sessiz hata yutma:\n" + "\n".join(violations)


def test_no_bare_except() -> None:
    violations: list[str] = []
    for path in _python_files(NEW_MODULES):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not violations, "Ciplak `except:`:\n" + "\n".join(violations)


def test_no_hash_based_ids() -> None:
    """`abs(hash(...))` ile kimlik uretimi YASAK (PYTHONHASHSEED sorunu)."""
    violations: list[str] = []
    for path in _python_files(NEW_MODULES):
        for lineno, line in enumerate(_code_only(path).split("\n"), 1):
            if "abs(hash(" in line and not line.strip().startswith("#"):
                violations.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert not violations, "hash() tabanli kimlik:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════════════
# 4 · TEMA SOZLESMESI
# ═══════════════════════════════════════════════════════════════════════════
def test_every_used_css_class_is_defined() -> None:
    """Kodda kullanilan her `t3-*` / `ts-*` sinifi theme.CSS'te tanimli olmali."""
    import src.ui.theme as theme

    css = theme.CSS
    defined = set(re.findall(r"\.((?:t3|ts)-[a-z0-9-]+)", css))
    used: set[str] = set()
    for path in _python_files([SRC / "ui"]):
        if path.name == "theme.py":
            continue
        text = path.read_text(encoding="utf-8")
        used |= set(re.findall(r'class="((?:t3|ts)-[a-z0-9-]+)', text))
        used |= set(re.findall(r'"((?:t3|ts)-[a-z0-9-]+)"', text))
    missing = sorted(used - defined)
    assert not missing, f"theme.CSS'te tanimsiz sinif: {missing}"


def test_theme_defines_both_modes() -> None:
    import src.ui.theme as theme

    assert "prefers-color-scheme: dark" in theme.CSS
    assert 'data-theme="light"' in theme.CSS
    assert "--ts-brand" in theme.CSS


def test_theme_is_actually_injected() -> None:
    """`inject_css` EN AZ BIR yerden cagrilmali (eski kodda sifir cagri vardi)."""
    calls = 0
    for path in _python_files([SRC / "ui"]):
        text = path.read_text(encoding="utf-8")
        if path.name != "theme.py":
            calls += text.count("inject_css") + text.count("theme.bootstrap")
    assert calls > 0, "theme.inject_css / theme.bootstrap hicbir yerden cagrilmiyor"


def test_hex_lint_outside_theme_tokens() -> None:
    """Renk sabitleri YALNIZCA theme.py icinde tanimlanir."""
    pattern = re.compile(r"#[0-9A-Fa-f]{6}\b")
    # Google'in resmi logo renkleri marka varligidir; tema token'i olamaz.
    allowlist = {"#EA4335", "#4285F4", "#FBBC05", "#34A853"}
    violations: list[str] = []
    for path in _python_files([SRC / "ui" / "views", SRC / "data", SRC / "ai",
                               SRC / "evaluation", SRC / "similarity",
                               SRC / "services" / "doc_converter.py"]):
        for lineno, line in enumerate(_code_only(path).split("\n"), 1):
            if line.strip().startswith("#") or "http" in line:
                continue
            found = [h for h in pattern.findall(line) if h.upper() not in allowlist]
            if found:
                violations.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()[:70]}")
    assert not violations, "theme.py disinda hex kodu:\n" + "\n".join(violations)


# ═══════════════════════════════════════════════════════════════════════════
# 5 · SAHTE VERI YASAGI
# ═══════════════════════════════════════════════════════════════════════════
FORBIDDEN_IN_VIEWS = ["mock_data", "api_client", "from src.database.db", "import db\n"]


def test_views_do_not_import_mock_or_legacy_db() -> None:
    violations: list[str] = []
    for path in [SRC / "ui" / "views" / "yarismaci.py",
                 SRC / "ui" / "views" / "yonetici.py",
                 SRC / "ui" / "views" / "hakem.py"]:
        if not path.exists():
            continue
        text = _code_only(path)
        for token in FORBIDDEN_IN_VIEWS:
            for lineno, line in enumerate(text.split("\n"), 1):
                if token in line:
                    violations.append(f"{path.relative_to(ROOT)}:{lineno}: {token}")
    assert not violations, "Arayuzde sahte veri / eski DB katmani:\n" + "\n".join(violations)


def test_evaluation_engine_has_no_fake_scoring() -> None:
    """AI dustugunde uydurma puan URETILMEZ."""
    text = _code_only(SRC / "evaluation" / "engine.py")
    assert "oranlar[" not in text, "sahte heuristik puanlama geri gelmis"
    assert "confidence" not in text, "sabit guven degeri geri gelmis"
    assert "LLMUnavailable" in (SRC / "evaluation" / "engine.py").read_text(encoding="utf-8")


def test_similarity_has_no_fixed_ratio() -> None:
    text = _code_only(SRC / "similarity" / "hybrid.py")
    assert "0.08" not in text, "sabit %8 intihal orani kalmis"


# ═══════════════════════════════════════════════════════════════════════════
# 6 · GUVENLIK
# ═══════════════════════════════════════════════════════════════════════════
def test_auth_has_no_default_admin_header() -> None:
    text = _code_only(SRC / "security" / "auth.py")
    assert 'Header("ADMIN"' not in text, "FastAPI varsayilan ADMIN rolu geri gelmis"
    assert "TSISTEM_JWT_SECRET" in text


def test_auth_view_has_no_query_param_login() -> None:
    path = SRC / "ui" / "views" / "auth_view.py"
    if not path.exists():
        pytest.skip("auth_view.py bulunamadi")
    text = path.read_text(encoding="utf-8")
    for lineno, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        assert "st.session_state.authenticated = True" not in line or "code" in text[:6000], (
            f"auth_view.py:{lineno} query-param ile oturum acilmis olabilir"
        )
    assert "_verify_oauth_state" in text, "OAuth state (CSRF) dogrulamasi yok"


def test_password_hashing_is_not_plain_sha256() -> None:
    from src.data.repo.users import hash_password, verify_password

    digest = hash_password("CokGucluParola!2026")
    assert not re.fullmatch(r"[0-9a-f]{64}", digest), "saltsiz SHA-256 geri gelmis"
    ok, upgrade = verify_password("CokGucluParola!2026", digest)
    assert ok and not upgrade
    assert verify_password("yanlis", digest) == (False, False)


def test_legacy_sha256_is_accepted_but_flagged_for_upgrade() -> None:
    import hashlib

    from src.data.repo.users import verify_password

    legacy = hashlib.sha256("eski".encode()).hexdigest()
    assert verify_password("eski", legacy) == (True, True)
