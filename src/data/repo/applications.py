"""Basvuru deposu ve uygunluk kapisi.

Eski kodda `db.create_application()` yazilmisti ama HIC CAGRILMIYORDU; vitrin
butonu yalnizca bir session degiskeni set ediyordu. Bu yuzden `applications`
tablosu hep bos kaliyor, yarismacinin "Basvurularim" ekrani filtresiz
`SELECT * FROM reports` ile TUM yarismacilarin raporlarini gosteriyordu.

Bu modul basvuruyu gercek bir kayda donusturur ve basvuru anindaki iki kapiyi
uygular:
  1. UYGUNLUK — sartnameden cikarilan takim buyuklugu / danisman / seviye kurallari
  2. TAKVIM   — son basvuru tarihi gecmisse basvuru alinmaz
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from ..enums import ApplicationStatus, PublishStatus
from ..models import Application
from .base import BaseRepo, DuplicateRecord, RecordNotFound
from .competitions import CompetitionRepo
from .teams import TeamRepo

_DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y %H:%M")


@dataclass
class EligibilityReport:
    ok: bool = True
    blocking: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def block(self, message: str) -> None:
        self.ok = False
        self.blocking.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def days_left(value: str | None, *, today: date | None = None) -> int | None:
    target = parse_date(value)
    if target is None:
        return None
    return (target - (today or date.today())).days


class ApplicationRepo(BaseRepo):
    def __init__(self, client=None) -> None:  # noqa: ANN001
        super().__init__(client)
        self.competitions = CompetitionRepo(self.db)
        self.teams = TeamRepo(self.db)

    # ── okuma ─────────────────────────────────────────────────────────────
    def get(self, app_id: str) -> Application | None:
        return self._one(Application, "SELECT * FROM applications WHERE app_id = ?;", [app_id])

    def get_or_raise(self, app_id: str) -> Application:
        app = self.get(app_id)
        if app is None:
            raise RecordNotFound(f"Basvuru bulunamadi: {app_id}")
        return app

    def find(self, team_id: str, competition_id: str,
             branch_code: str | None = None) -> Application | None:
        sql = "SELECT * FROM applications WHERE team_id = ? AND competition_id = ?"
        params: list[Any] = [team_id, competition_id]
        if branch_code:
            sql += " AND branch_code = ?"
            params.append(branch_code)
        else:
            sql += " AND branch_code IS NULL"
        return self._one(Application, sql + " LIMIT 1;", params)

    def list_for_team(self, team_id: str) -> list[Application]:
        return self._many(
            Application,
            "SELECT * FROM applications WHERE team_id = ? ORDER BY created_at DESC;",
            [team_id],
        )

    def list_for_user(self, user_id: str) -> list[Application]:
        """Kullanicinin uyesi oldugu tum takimlarin basvurulari."""
        return self._many(
            Application,
            "SELECT a.* FROM applications a "
            "JOIN team_members m ON m.team_id = a.team_id "
            "WHERE m.user_id = ? ORDER BY a.created_at DESC;",
            [user_id],
        )

    def list_for_competition(self, competition_id: str,
                             status: ApplicationStatus | None = None) -> list[Application]:
        sql = "SELECT * FROM applications WHERE competition_id = ?"
        params: list[Any] = [competition_id]
        if status:
            sql += " AND status = ?"
            params.append(status.value)
        return self._many(Application, sql + " ORDER BY created_at DESC;", params)

    def count_for_competition(self, competition_id: str) -> int:
        return self._count(
            "SELECT COUNT(*) FROM applications WHERE competition_id = ? AND status = ?;",
            [competition_id, ApplicationStatus.AKTIF.value],
        )

    # ── uygunluk kapisi ───────────────────────────────────────────────────
    def check_eligibility(
        self, team_id: str, competition_id: str, branch_code: str | None = None
    ) -> EligibilityReport:
        report = EligibilityReport()
        comp = self.competitions.get(competition_id)
        if comp is None:
            report.block("Yarisma bulunamadi.")
            return report
        if comp.publish_status != PublishStatus.YAYINDA:
            report.block("Bu yarisma su anda basvuruya acik degil.")

        team = self.teams.get(team_id)
        if team is None:
            report.block("Takim bulunamadi.")
            return report

        rules = self.competitions.eligibility(competition_id, branch_code)
        size = self.teams.member_count(team_id)

        min_size = rules.get("min_team_size")
        max_size = rules.get("max_team_size")
        if min_size and size < min_size:
            report.block(f"Bu yarisma en az {min_size} kisilik takim istiyor; takiminiz {size} kisi.")
        if max_size and size > max_size:
            report.block(f"Bu yarisma en fazla {max_size} kisilik takim kabul ediyor; takiminiz {size} kisi.")

        if rules.get("advisor_required") and not (team.advisor_name or team.advisor_email):
            report.block("Bu yarisma danisman zorunlu kiliyor. Takim bilgilerinden danisman ekleyiniz.")

        target_levels = rules.get("target_levels") or []
        if target_levels and team.level and team.level not in target_levels:
            report.block(
                f"Bu yarisma {', '.join(target_levels)} seviyesine acik; takiminiz '{team.level}'."
            )

        deadline = self._deadline(comp.schedule_json)
        if deadline:
            remaining = days_left(deadline)
            if remaining is not None and remaining < 0:
                report.block(f"Son basvuru tarihi ({deadline}) gecmis.")
            elif remaining is not None and remaining <= 3:
                report.warn(f"Son basvuruya {remaining} gun kaldi.")

        if not self.competitions.list_stages(competition_id):
            report.warn("Bu yarisma icin henuz asama tanimlanmamis.")

        return report

    @staticmethod
    def _deadline(schedule_json: str | None) -> str | None:
        if not schedule_json:
            return None
        try:
            return (json.loads(schedule_json) or {}).get("son_basvuru")
        except json.JSONDecodeError:
            return None

    # ── yazma ─────────────────────────────────────────────────────────────
    def apply(
        self,
        *,
        team_id: str,
        competition_id: str,
        branch_code: str | None = None,
        level: str | None = None,
        actor: str | None = None,
        force: bool = False,
    ) -> Application:
        existing = self.find(team_id, competition_id, branch_code)
        if existing and existing.status == ApplicationStatus.AKTIF:
            raise DuplicateRecord("Bu takim bu yarismaya zaten basvurmus.")

        if not force:
            report = self.check_eligibility(team_id, competition_id, branch_code)
            if not report.ok:
                raise ValueError("Basvuru yapilamadi:\n- " + "\n- ".join(report.blocking))

        if existing:
            return self.set_status(existing.app_id, ApplicationStatus.AKTIF, actor=actor)

        team = self.teams.get_or_raise(team_id)
        app = Application(
            team_id=team_id,
            competition_id=competition_id,
            branch_code=branch_code,
            level=level or team.level,
        )
        self._insert("applications", app)
        self.audit("application.create", actor_user_id=actor,
                   entity_type="application", entity_id=app.app_id, after=app)
        return app

    def set_status(self, app_id: str, status: ApplicationStatus, *,
                   actor: str | None = None) -> Application:
        before = self.get_or_raise(app_id)
        self._update("applications", "app_id", app_id, {"status": status.value})
        after = self.get_or_raise(app_id)
        self.audit("application.status", actor_user_id=actor,
                   entity_type="application", entity_id=app_id,
                   before={"status": before.status.value}, after={"status": after.status.value})
        return after

    def withdraw(self, app_id: str, *, actor: str | None = None) -> Application:
        return self.set_status(app_id, ApplicationStatus.GERI_CEKILDI, actor=actor)


__all__ = ["ApplicationRepo", "EligibilityReport", "parse_date", "days_left"]
