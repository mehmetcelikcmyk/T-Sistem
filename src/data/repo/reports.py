"""Rapor deposu.

DEGISIKLIKLER
-------------
* Kimlikler `uuid4` (eski kod `abs(hash(...)) % 90000` kullaniyordu; PYTHONHASHSEED
  yuzunden yeniden baslatmada degisiyor ve ~350 raporda %50 cakisiyordu).
* `r2_key` yalnizca OBJECT KEY tutar; URL uretimi `R2Client.url_for` isidir.
  Eski kodda ayni kolona bazen key, bazen tam URL, bazen hata mesaji yaziliyordu.
* GIZLILIK: `list_for_user` her zaman kullanicinin takim uyeliklerine gore
  filtreler. Eski `SELECT * FROM reports` (WHERE'siz) tum yarismacilarin
  raporlarini herkese gosteriyordu.
* Ayni asamaya yeniden yukleme yeni SURUM acar (revizyon destegi).
"""

from __future__ import annotations

import json
from typing import Any

from ..enums import ReportStatus
from ..models import Report, now_iso
from .base import BaseRepo, RecordNotFound


class ReportRepo(BaseRepo):
    # ── okuma ─────────────────────────────────────────────────────────────
    def get(self, report_id: str) -> Report | None:
        return self._one(Report, "SELECT * FROM reports WHERE report_id = ?;", [report_id])

    def get_or_raise(self, report_id: str) -> Report:
        report = self.get(report_id)
        if report is None:
            raise RecordNotFound(f"Rapor bulunamadi: {report_id}")
        return report

    def latest(self, app_id: str, stage_code: str, level: str = "Genel") -> Report | None:
        return self._one(
            Report,
            "SELECT * FROM reports WHERE app_id = ? AND UPPER(stage_code) = UPPER(?) "
            "AND level = ? ORDER BY version DESC LIMIT 1;",
            [app_id, stage_code, level],
        )

    def versions(self, app_id: str, stage_code: str, level: str = "Genel") -> list[Report]:
        return self._many(
            Report,
            "SELECT * FROM reports WHERE app_id = ? AND UPPER(stage_code) = UPPER(?) "
            "AND level = ? ORDER BY version DESC;",
            [app_id, stage_code, level],
        )

    def list_for_application(self, app_id: str) -> list[Report]:
        return self._many(
            Report,
            "SELECT * FROM reports WHERE app_id = ? ORDER BY created_at DESC;",
            [app_id],
        )

    def list_for_user(self, user_id: str) -> list[Report]:
        """GIZLILIK KAPISI — yalnizca kullanicinin takimlarinin raporlari."""
        return self._many(
            Report,
            "SELECT r.* FROM reports r "
            "JOIN applications a ON a.app_id = r.app_id "
            "JOIN team_members m ON m.team_id = a.team_id "
            "WHERE m.user_id = ? ORDER BY r.created_at DESC;",
            [user_id],
        )

    def list_for_admin(
        self,
        *,
        competition_id: str | None = None,
        stage_code: str | None = None,
        status: ReportStatus | None = None,
        unassigned_only: bool = False,
        search: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> list[Report]:
        sql = "SELECT r.* FROM reports r WHERE 1=1"
        params: list[Any] = []
        if competition_id:
            sql += " AND r.competition_id = ?"
            params.append(competition_id)
        if stage_code:
            sql += " AND UPPER(r.stage_code) = UPPER(?)"
            params.append(stage_code)
        if status:
            sql += " AND r.status = ?"
            params.append(status.value)
        if unassigned_only:
            sql += (" AND NOT EXISTS (SELECT 1 FROM report_assignments ra "
                    "WHERE ra.report_id = r.report_id AND ra.status != 'IPTAL')")
        if search:
            sql += " AND LOWER(r.file_name) LIKE ?"
            params.append(f"%{search.lower()}%")
        sql += " ORDER BY r.created_at DESC LIMIT ? OFFSET ?;"
        params += [limit, offset]
        return self._many(Report, sql, params)

    def corpus_for(self, report: Report, *, limit: int = 400) -> list[Report]:
        """Benzerlik korpusu: AYNI yarisma + AYNI asamadaki diger raporlar.

        Eski kodda `run_all_checks`'e korpus HIC gecilmiyordu; bu yuzden
        intihal orani her raporda sabit %8 gorunuyordu.
        """
        return self._many(
            Report,
            "SELECT * FROM reports WHERE competition_id = ? "
            "AND UPPER(stage_code) = UPPER(?) AND report_id != ? "
            "AND report_text IS NOT NULL AND LENGTH(report_text) > 200 "
            "ORDER BY created_at DESC LIMIT ?;",
            [report.competition_id, report.stage_code, report.report_id, limit],
        )

    def stats(self, competition_id: str | None = None) -> dict[str, int]:
        sql = "SELECT status, COUNT(*) AS n FROM reports"
        params: list[Any] = []
        if competition_id:
            sql += " WHERE competition_id = ?"
            params.append(competition_id)
        sql += " GROUP BY status;"
        rows = self.db.query(sql, params)
        out = {s.value: 0 for s in ReportStatus}
        for row in rows:
            out[str(row["status"])] = int(row["n"])
        out["TOPLAM"] = sum(v for k, v in out.items() if k != "TOPLAM")
        return out

    # ── yazma ─────────────────────────────────────────────────────────────
    def create(
        self,
        *,
        app_id: str,
        competition_id: str,
        stage_code: str,
        file_name: str,
        r2_key: str,
        level: str = "Genel",
        branch_code: str | None = None,
        page_count: int | None = None,
        report_text: str | None = None,
        uploaded_by: str | None = None,
    ) -> Report:
        previous = self.latest(app_id, stage_code, level)
        version = (previous.version + 1) if previous else 1

        report = Report(
            app_id=app_id,
            competition_id=competition_id,
            stage_code=stage_code.upper(),
            level=level,
            branch_code=branch_code,
            version=version,
            file_name=file_name,
            r2_key=r2_key,
            page_count=page_count,
            report_text=report_text,
            status=ReportStatus.BEKLEMEDE,
            uploaded_by=uploaded_by,
        )
        self._insert("reports", report)
        self.audit("report.upload", actor_user_id=uploaded_by,
                   entity_type="report", entity_id=report.report_id,
                   after={"file_name": file_name, "version": version, "r2_key": r2_key})
        return report

    def update(self, report_id: str, changes: dict[str, Any], *,
               actor: str | None = None) -> Report:
        self._update("reports", "report_id", report_id, changes)
        return self.get_or_raise(report_id)

    def set_status(self, report_id: str, status: ReportStatus, *,
                   actor: str | None = None) -> Report:
        before = self.get_or_raise(report_id)
        self._update("reports", "report_id", report_id, {"status": status.value})
        after = self.get_or_raise(report_id)
        self.audit("report.status", actor_user_id=actor,
                   entity_type="report", entity_id=report_id,
                   before={"status": before.status.value}, after={"status": after.status.value})
        return after

    def save_checks(self, report_id: str, checks: dict[str, Any], *,
                    actor: str | None = None) -> Report:
        """ADIM 3 (sartname/bicim on denetimi) ciktisini kaydeder."""
        return self.update(
            report_id,
            {"checks_json": json.dumps(checks, ensure_ascii=False, default=str)},
            actor=actor,
        )

    def save_ai_evaluation(
        self, report_id: str, evaluation: dict[str, Any], total_score: float | None, *,
        actor: str | None = None,
    ) -> Report:
        """ADIM 4 (rubrik puanlama) AI ciktisini kaydeder.

        Boylece her Streamlit rerun'unda LLM yeniden cagrilmaz.
        """
        return self.update(
            report_id,
            {
                "ai_data_json": json.dumps(evaluation, ensure_ascii=False, default=str),
                "ai_score": total_score,
            },
            actor=actor,
        )

    def save_security(self, report_id: str, security: dict[str, Any]) -> Report:
        return self.update(
            report_id, {"security_json": json.dumps(security, ensure_ascii=False, default=str)}
        )

    def load_checks(self, report_id: str) -> dict[str, Any] | None:
        report = self.get_or_raise(report_id)
        return _loads(report.checks_json)

    def load_ai_evaluation(self, report_id: str) -> dict[str, Any] | None:
        report = self.get_or_raise(report_id)
        return _loads(report.ai_data_json)

    def delete(self, report_id: str, *, actor: str | None = None) -> Report:
        before = self.get_or_raise(report_id)
        self._delete("reports", "report_id", report_id)
        self.audit("report.delete", actor_user_id=actor,
                   entity_type="report", entity_id=report_id, before=before)
        return before


def _loads(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


__all__ = ["ReportRepo"]
