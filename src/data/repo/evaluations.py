"""Atama, degerlendirme, kriter puanlari ve karne deposu.

DEGISIKLIKLER
-------------
* IZOLASYON: `list_for_referee` YALNIZCA `report_assignments` JOIN'i uzerinden
  calisir. Eski SQL filtresi `OR referee_id IS NULL OR referee_id = ''
  OR referee_id = 'usr_hakem_ef6def'` iceriyordu; bu, atanmamis her raporu
  her hakeme aciyordu.
* TEK YAZIM: Muhurleme tek noktadan yapilir. Eski kodda hem
  `db.update_referee_decision` hem `api_client.hakem_karari_gonder`
  cagriliyor, ikincisi gercek hakem kimligini `"HAKEM-EMRE-1"` ile eziyordu.
* KRITER KIRILIMI: Puanlar `evaluation_scores` tablosuna kriter kriter yazilir.
  Eski kod yalnizca toplam float sakliyordu; itiraz/denetim izi yoktu.
* KARNE: Muhurlemeyle birlikte `report_cards` uretilir ve BASVURUYA baglanir,
  boylece yarismaci puanini gercekten gorebilir.
"""

from __future__ import annotations

import json
from typing import Any

from ..enums import AssignmentStatus, Decision, ReportStatus
from ..models import (
    Assignment,
    CriterionScore,
    Evaluation,
    Notification,
    ReportCard,
    now_iso,
)
from .base import BaseRepo, DuplicateRecord, RecordNotFound
from .reports import ReportRepo


class EvaluationRepo(BaseRepo):
    def __init__(self, client=None) -> None:  # noqa: ANN001
        super().__init__(client)
        self.reports = ReportRepo(self.db)

    # ── atama ─────────────────────────────────────────────────────────────
    def assign(
        self, report_id: str, referee_user_id: str, *, assigned_by: str
    ) -> Assignment:
        existing = self._one(
            Assignment,
            "SELECT * FROM report_assignments WHERE report_id = ? AND referee_user_id = ?;",
            [report_id, referee_user_id],
        )
        if existing and existing.status != AssignmentStatus.IPTAL:
            raise DuplicateRecord("Bu rapor bu hakeme zaten atanmis.")

        assignment = Assignment(
            report_id=report_id, referee_user_id=referee_user_id, assigned_by=assigned_by
        )
        self._insert("report_assignments", assignment, replace=bool(existing))
        self.reports.set_status(report_id, ReportStatus.HAKEME_ATANDI, actor=assigned_by)
        self.notify(
            referee_user_id,
            kind="rapor_atandi",
            title="Yeni rapor atandi",
            body="Degerlendirme istasyonunuzda inceleme bekleyen yeni bir rapor var.",
        )
        self.audit("assignment.create", actor_user_id=assigned_by,
                   entity_type="assignment", entity_id=assignment.assignment_id, after=assignment)
        return assignment

    def unassign(self, assignment_id: str, *, actor: str) -> None:
        assignment = self.get_assignment_or_raise(assignment_id)
        if assignment.status == AssignmentStatus.TAMAMLANDI:
            raise ValueError("Tamamlanmis bir degerlendirmenin atamasi geri alinamaz.")
        self._update(
            "report_assignments", "assignment_id", assignment_id,
            {"status": AssignmentStatus.IPTAL.value},
        )
        remaining = self._count(
            "SELECT COUNT(*) FROM report_assignments WHERE report_id = ? AND status != ?;",
            [assignment.report_id, AssignmentStatus.IPTAL.value],
        )
        if remaining == 0:
            self.reports.set_status(assignment.report_id, ReportStatus.BEKLEMEDE, actor=actor)
        self.audit("assignment.cancel", actor_user_id=actor,
                   entity_type="assignment", entity_id=assignment_id, before=assignment)

    def get_assignment(self, assignment_id: str) -> Assignment | None:
        return self._one(
            Assignment, "SELECT * FROM report_assignments WHERE assignment_id = ?;",
            [assignment_id],
        )

    def get_assignment_or_raise(self, assignment_id: str) -> Assignment:
        assignment = self.get_assignment(assignment_id)
        if assignment is None:
            raise RecordNotFound(f"Atama bulunamadi: {assignment_id}")
        return assignment

    def find_assignment(self, report_id: str, referee_user_id: str) -> Assignment | None:
        return self._one(
            Assignment,
            "SELECT * FROM report_assignments WHERE report_id = ? AND referee_user_id = ? "
            "AND status != ?;",
            [report_id, referee_user_id, AssignmentStatus.IPTAL.value],
        )

    def assignments_of_report(self, report_id: str) -> list[Assignment]:
        return self._many(
            Assignment,
            "SELECT * FROM report_assignments WHERE report_id = ? ORDER BY assigned_at;",
            [report_id],
        )

    def list_for_referee(
        self, referee_user_id: str, *, only_open: bool = False
    ) -> list[dict[str, Any]]:
        """KATI IZOLASYON — yalnizca bu hakeme atanmis raporlar."""
        sql = (
            "SELECT r.*, ra.assignment_id, ra.status AS assignment_status, "
            "       ra.assigned_at, c.name AS competition_name, c.slug AS competition_slug, "
            "       t.name AS team_name, t.level AS team_level "
            "FROM report_assignments ra "
            "JOIN reports r      ON r.report_id = ra.report_id "
            "JOIN applications a ON a.app_id = r.app_id "
            "JOIN teams t        ON t.team_id = a.team_id "
            "LEFT JOIN competitions c ON c.competition_id = r.competition_id "
            "WHERE ra.referee_user_id = ? AND ra.status != ?"
        )
        params: list[Any] = [referee_user_id, AssignmentStatus.IPTAL.value]
        if only_open:
            sql += " AND ra.status != ? AND (r.status != 'DEGERLENDIRILDI' AND r.referee_score IS NULL)"
            params.append(AssignmentStatus.TAMAMLANDI.value)
        sql += " ORDER BY ra.assigned_at DESC;"
        return self.db.query(sql, params)

    def referee_workload(self) -> list[dict[str, Any]]:
        # auth_users tablosunda 'surname' ve 'specialty' kolonu yok;
        # 'name' tam adı, 'department' uzmanlık alanını tutar.
        rows = self.db.query(
            "SELECT u.user_id, u.name, '' AS surname, u.email, "
            "       COALESCE(u.department, u.institution, '') AS specialty, "
            "       SUM(CASE WHEN ra.status = 'TAMAMLANDI' THEN 1 ELSE 0 END) AS tamamlanan, "
            "       SUM(CASE WHEN ra.status IN ('ATANDI','INCELENIYOR') THEN 1 ELSE 0 END) AS bekleyen, "
            "       COUNT(ra.assignment_id) AS toplam "
            "FROM auth_users u "
            "LEFT JOIN report_assignments ra "
            "       ON ra.referee_user_id = u.user_id AND ra.status != 'IPTAL' "
            "WHERE LOWER(u.role) IN ('hakem', 'referee') AND u.status = 'aktif' "
            "GROUP BY u.user_id ORDER BY bekleyen DESC, u.name;"
        )
        # "name" alanını "hakem" key olarak da ekle (yonetici.py dataframe uyumu)
        for r in (rows or []):
            if "hakem" not in r:
                r["hakem"] = r.get("name", "")
        return rows or []

    def auto_distribute(self, report_ids: list[str], *, assigned_by: str) -> dict[str, str]:
        """Bekleyen raporlari en az yuklu hakemlere dengeli dagitir."""
        workload = self.referee_workload()
        if not workload:
            raise RecordNotFound("Sistemde aktif hakem yok.")
        pool = [(int(w["bekleyen"] or 0), w["user_id"]) for w in workload]
        result: dict[str, str] = {}
        for report_id in report_ids:
            pool.sort()
            load, referee_id = pool[0]
            self.assign(report_id, referee_id, assigned_by=assigned_by)
            result[report_id] = referee_id
            pool[0] = (load + 1, referee_id)
        return result

    # ── degerlendirme ─────────────────────────────────────────────────────
    def get_evaluation(self, evaluation_id: str) -> Evaluation | None:
        return self._one(
            Evaluation, "SELECT * FROM evaluations WHERE evaluation_id = ?;", [evaluation_id]
        )

    def evaluation_of_assignment(self, assignment_id: str) -> Evaluation | None:
        return self._one(
            Evaluation, "SELECT * FROM evaluations WHERE assignment_id = ?;", [assignment_id]
        )

    def evaluation_of_report(self, report_id: str) -> Evaluation | None:
        return self._one(
            Evaluation,
            "SELECT * FROM evaluations WHERE report_id = ? ORDER BY created_at DESC LIMIT 1;",
            [report_id],
        )

    def scores(self, evaluation_id: str) -> list[CriterionScore]:
        return self._many(
            CriterionScore,
            "SELECT * FROM evaluation_scores WHERE evaluation_id = ? ORDER BY order_index;",
            [evaluation_id],
        )

    def seal(
        self,
        *,
        assignment_id: str,
        referee_user_id: str,
        criterion_scores: list[CriterionScore],
        decision: Decision,
        referee_notes: str | None = None,
        ai_total_score: float | None = None,
        spec_compliance: dict[str, Any] | None = None,
        max_total_score: float | None = None,
    ) -> Evaluation:
        """Degerlendirmeyi TEK yazimda muhurler ve karneyi uretir."""
        assignment = self.get_assignment_or_raise(assignment_id)
        if assignment.referee_user_id != referee_user_id:
            raise ValueError("Bu degerlendirme baska bir hakeme ait.")

        top_level = [s for s in criterion_scores if True]
        total = round(sum(s.referee_score for s in top_level), 2)
        ceiling = max_total_score or round(sum(s.max_score for s in top_level), 2) or 100.0

        for score in top_level:
            if score.referee_score < 0 or score.referee_score > score.max_score:
                raise ValueError(
                    f"'{score.criterion_name}' icin puan 0 ile {score.max_score} arasinda olmalidir "
                    f"(girilen: {score.referee_score})."
                )

        existing = self.evaluation_of_assignment(assignment_id)
        evaluation = Evaluation(
            evaluation_id=existing.evaluation_id if existing else Evaluation.model_fields["evaluation_id"].default_factory(),
            assignment_id=assignment_id,
            report_id=assignment.report_id,
            referee_user_id=referee_user_id,
            total_score=total,
            ai_total_score=ai_total_score,
            max_total_score=ceiling,
            decision=decision,
            referee_notes=referee_notes,
            spec_compliance_json=(
                json.dumps(spec_compliance, ensure_ascii=False, default=str)
                if spec_compliance else None
            ),
            sealed_at=now_iso(),
        )
        self._insert("evaluations", evaluation, replace=True)

        self.db.execute(
            "DELETE FROM evaluation_scores WHERE evaluation_id = ?;", [evaluation.evaluation_id]
        )
        for idx, score in enumerate(criterion_scores):
            score.evaluation_id = evaluation.evaluation_id
            score.order_index = idx
            self._insert("evaluation_scores", score)

        self._update(
            "report_assignments", "assignment_id", assignment_id,
            {"status": AssignmentStatus.TAMAMLANDI.value, "completed_at": now_iso()},
        )
        new_status = {
            Decision.KABUL: ReportStatus.DEGERLENDIRILDI,
            Decision.REVIZYON: ReportStatus.REVIZYON_ISTENDI,
            Decision.RET: ReportStatus.REDDEDILDI,
        }[decision]
        self.reports.set_status(assignment.report_id, new_status, actor=referee_user_id)

        self.audit("evaluation.seal", actor_user_id=referee_user_id,
                   entity_type="evaluation", entity_id=evaluation.evaluation_id,
                   after={"total": total, "decision": decision.value})
        return evaluation

    # ── karne ─────────────────────────────────────────────────────────────
    def publish_card(
        self,
        evaluation_id: str,
        *,
        strengths: list[str] | None = None,
        improvements: list[str] | None = None,
        roadmap: list[str] | None = None,
        pedagogical_note: str | None = None,
        pdf_r2_key: str | None = None,
        actor: str | None = None,
    ) -> ReportCard:
        evaluation = self.get_evaluation(evaluation_id)
        if evaluation is None:
            raise RecordNotFound(f"Degerlendirme bulunamadi: {evaluation_id}")
        report = self.reports.get_or_raise(evaluation.report_id)

        existing = self._one(
            ReportCard, "SELECT * FROM report_cards WHERE evaluation_id = ?;", [evaluation_id]
        )
        card = ReportCard(
            card_id=existing.card_id if existing else ReportCard.model_fields["card_id"].default_factory(),
            app_id=report.app_id,
            report_id=report.report_id,
            evaluation_id=evaluation_id,
            total_score=evaluation.total_score,
            max_total_score=evaluation.max_total_score,
            strengths_json=_dump(strengths),
            improvements_json=_dump(improvements),
            roadmap_json=_dump(roadmap),
            pedagogical_note=pedagogical_note,
            pdf_r2_key=pdf_r2_key,
            published_at=now_iso(),
        )
        self._insert("report_cards", card, replace=True)

        for row in self.db.query(
            "SELECT m.user_id FROM team_members m "
            "JOIN applications a ON a.team_id = m.team_id WHERE a.app_id = ?;",
            [report.app_id],
        ):
            self.notify(
                row["user_id"],
                kind="karne_yayinlandi",
                title="Degerlendirme karneniz hazir",
                body=f"{report.stage_code} asamasi icin puaniniz: "
                     f"{evaluation.total_score:.1f} / {evaluation.max_total_score:.0f}",
            )

        self.audit("card.publish", actor_user_id=actor,
                   entity_type="report_card", entity_id=card.card_id, after=card)
        return card

    def card_for_report(self, report_id: str) -> ReportCard | None:
        return self._one(
            ReportCard,
            "SELECT * FROM report_cards WHERE report_id = ? ORDER BY created_at DESC LIMIT 1;",
            [report_id],
        )

    def cards_for_application(self, app_id: str) -> list[ReportCard]:
        return self._many(
            ReportCard,
            "SELECT * FROM report_cards WHERE app_id = ? ORDER BY created_at DESC;",
            [app_id],
        )

    def card_detail(self, card: ReportCard) -> dict[str, Any]:
        """Yarismaci karnesi icin kriter kirilimi + hakem notu."""
        evaluation = self.get_evaluation(card.evaluation_id)
        return {
            "card": card,
            "evaluation": evaluation,
            "scores": self.scores(card.evaluation_id),
            "strengths": _load(card.strengths_json),
            "improvements": _load(card.improvements_json),
            "roadmap": _load(card.roadmap_json),
        }

    # ── bildirim ──────────────────────────────────────────────────────────
    def notify(self, user_id: str, *, kind: str, title: str,
               body: str | None = None, link: str | None = None) -> Notification:
        notification = Notification(
            user_id=user_id, kind=kind, title=title, body=body, link=link
        )
        self._insert("notifications", notification)
        return notification

    def unread(self, user_id: str) -> list[Notification]:
        return self._many(
            Notification,
            "SELECT * FROM notifications WHERE user_id = ? AND is_read = 0 "
            "ORDER BY created_at DESC LIMIT 50;",
            [user_id],
        )

    def mark_read(self, user_id: str) -> int:
        return self.db.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0;", [user_id]
        )


def _dump(value: Any) -> str | None:
    return json.dumps(value, ensure_ascii=False, default=str) if value else None


def _load(raw: str | None) -> list[Any]:
    if not raw:
        return []
    try:
        value = json.loads(raw)
        return value if isinstance(value, list) else []
    except json.JSONDecodeError:
        return []


__all__ = ["EvaluationRepo"]
