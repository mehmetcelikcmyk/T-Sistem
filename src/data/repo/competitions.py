"""Yarisma, sartname, asama, kural ve rubrik deposu.

KARAR (#1): Cok sartnameli yarismalarda birlestirme YAPILMAZ.
Her sartname `competition_specs` icinde ayri satirdir ve `branch_code` ile
izole edilir. Kural cikarimi dal bazinda calisir; yarismaci basvururken dalini
secer; hakem yalnizca o dalin kural ve rubrigini gorur.

KARAR (#2): Asamasi olmayan yarismalara varsayilan `OTR` asamasi eklenir
(`is_auto_generated=1`). Kendi asamasi olan yarismalarin asama kodlarina
DOKUNULMAZ (Robolig ODR, IHA PSR vb. orijinal kalir).
"""

from __future__ import annotations

import json
from typing import Any

from ..enums import PublishStatus, RubricStatus, SpecStatus
from ..models import (
    Competition,
    CompetitionSpec,
    Requirement,
    RubricCriterion,
    Stage,
    now_iso,
)
from .base import BaseRepo, RecordNotFound

DEFAULT_STAGE_CODE = "OTR"
DEFAULT_STAGE_NAME = "On Tasarim Raporu"


class CompetitionRepo(BaseRepo):
    # ── yarisma ───────────────────────────────────────────────────────────
    def create(self, comp: Competition, *, actor: str | None = None) -> Competition:
        self._insert("competitions", comp)
        self.audit("competition.create", actor_user_id=actor,
                   entity_type="competition", entity_id=comp.competition_id, after=comp)
        return comp

    def upsert(self, comp: Competition, *, actor: str | None = None) -> Competition:
        before = self.get(comp.competition_id)
        self._upsert("competitions", comp, ["slug"])
        self.audit("competition.upsert", actor_user_id=actor,
                   entity_type="competition", entity_id=comp.competition_id,
                   before=before, after=comp)
        return self.get_or_raise(comp.competition_id)

    def update(self, competition_id: str, changes: dict[str, Any], *,
               actor: str | None = None) -> Competition:
        """KISMI guncelleme — gonderilmeyen alanlar EZILMEZ.

        Eski kodda sartname yukleme, `domain`/`levels`/`description` alanlarini
        varsayilana dondurup veri kaybettiriyordu.
        """
        before = self.get_or_raise(competition_id)
        self._update("competitions", "competition_id", competition_id, changes)
        after = self.get_or_raise(competition_id)
        self.audit("competition.update", actor_user_id=actor,
                   entity_type="competition", entity_id=competition_id,
                   before=before, after=after)
        return after

    def get(self, competition_id: str) -> Competition | None:
        return self._one(
            Competition,
            "SELECT * FROM competitions WHERE competition_id = ? OR slug = ? LIMIT 1;",
            [competition_id, competition_id],
        )

    def get_or_raise(self, competition_id: str) -> Competition:
        comp = self.get(competition_id)
        if comp is None:
            raise RecordNotFound(f"Yarisma bulunamadi: {competition_id}")
        return comp

    def list(
        self,
        *,
        search: str = "",
        domain: str | None = None,
        level: str | None = None,
        publish_status: PublishStatus | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[Competition]:
        sql = "SELECT * FROM competitions WHERE 1=1"
        params: list[Any] = []
        if search:
            sql += " AND (name LIKE ? OR slug LIKE ? OR description LIKE ? OR domain LIKE ? OR LOWER(name) LIKE ? OR name LIKE ?)"
            s_clean = search.strip()
            s_tr_lower = s_clean.replace('İ', 'i').replace('I', 'ı').lower()
            s_tr_upper = s_clean.replace('i', 'İ').replace('ı', 'I').upper()
            params += [f"%{s_clean}%", f"%{s_clean.lower()}%", f"%{s_clean}%", f"%{s_clean}%", f"%{s_tr_lower}%", f"%{s_tr_upper}%"]
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        if level:
            sql += " AND levels LIKE ?"
            params.append(f"%{level}%")
        if publish_status:
            sql += " AND publish_status = ?"
            params.append(publish_status.value)
        sql += " ORDER BY name COLLATE NOCASE LIMIT ? OFFSET ?;"
        params += [limit, offset]
        return self._many(Competition, sql, params)

    def count(self, publish_status: PublishStatus | None = None) -> int:
        if publish_status:
            return self._count(
                "SELECT COUNT(*) FROM competitions WHERE publish_status = ?;",
                [publish_status.value],
            )
        return self._count("SELECT COUNT(*) FROM competitions;")

    def domains(self) -> list[str]:
        rows = self.db.query(
            "SELECT DISTINCT domain FROM competitions WHERE domain IS NOT NULL "
            "ORDER BY domain COLLATE NOCASE;"
        )
        return [r["domain"] for r in rows]

    def levels(self) -> list[str]:
        seen: list[str] = []
        for row in self.db.query("SELECT levels FROM competitions WHERE levels IS NOT NULL;"):
            for part in (row["levels"] or "").split(","):
                value = part.strip()
                if value and value not in seen:
                    seen.append(value)
        return sorted(seen)

    def delete(self, competition_id: str, *, actor: str | None = None) -> None:
        before = self.get_or_raise(competition_id)
        # FK ON DELETE CASCADE spec/stage/requirement/rubric'i temizler;
        # rubrik tablosunda FK yok, elle silinir.
        self.db.execute(
            "DELETE FROM stage_rubric_criteria WHERE competition_id = ?;", [competition_id]
        )
        self._delete("competitions", "competition_id", competition_id)
        self.audit("competition.delete", actor_user_id=actor,
                   entity_type="competition", entity_id=competition_id, before=before)

    def set_schedule(self, competition_id: str, schedule: dict[str, str], *,
                     actor: str | None = None) -> Competition:
        """Takvimi KISMI gunceller — mevcut anahtarlar korunur.

        Eski kodda her guncelleme `schedule_json`'i tamamen eziyordu ve
        `sonuc_tarihi` her seferinde siliniyordu.
        """
        comp = self.get_or_raise(competition_id)
        current: dict[str, str] = {}
        if comp.schedule_json:
            try:
                current = json.loads(comp.schedule_json)
            except json.JSONDecodeError:
                current = {}
        current.update({k: v for k, v in schedule.items() if v})
        return self.update(
            competition_id,
            {"schedule_json": json.dumps(current, ensure_ascii=False)},
            actor=actor,
        )

    # ── sartname (spec) ───────────────────────────────────────────────────
    def add_spec(self, spec: CompetitionSpec, *, actor: str | None = None) -> CompetitionSpec:
        self._upsert("competition_specs", spec, ["competition_id", "branch_code"])
        self.update(spec.competition_id, {"spec_status": SpecStatus.YUKLENDI.value}, actor=actor)
        self.audit("spec.upload", actor_user_id=actor,
                   entity_type="competition_spec", entity_id=spec.spec_id, after=spec)
        return spec

    def list_specs(self, competition_id: str) -> list[CompetitionSpec]:
        return self._many(
            CompetitionSpec,
            "SELECT * FROM competition_specs WHERE competition_id = ? "
            "ORDER BY is_primary DESC, branch_name COLLATE NOCASE;",
            [competition_id],
        )

    def get_spec(self, spec_id: str) -> CompetitionSpec | None:
        return self._one(
            CompetitionSpec, "SELECT * FROM competition_specs WHERE spec_id = ?;", [spec_id]
        )

    def delete_spec(self, spec_id: str, *, actor: str | None = None) -> None:
        before = self.get_spec(spec_id)
        self._delete("competition_specs", "spec_id", spec_id)
        self.audit("spec.delete", actor_user_id=actor,
                   entity_type="competition_spec", entity_id=spec_id, before=before)

    def branches(self, competition_id: str) -> list[tuple[str, str]]:
        """(branch_code, branch_name) listesi — cok dalli yarismalar icin."""
        return [
            (s.branch_code, s.branch_name or s.title)
            for s in self.list_specs(competition_id)
            if s.branch_code
        ]

    # ── asama ─────────────────────────────────────────────────────────────
    def add_stage(self, stage: Stage, *, actor: str | None = None) -> Stage:
        self._upsert(
            "competition_stages", stage,
            ["competition_id", "stage_code", "level", "branch_code"],
        )
        self.audit("stage.upsert", actor_user_id=actor,
                   entity_type="competition_stage", entity_id=stage.stage_id, after=stage)
        return stage

    def update_stage(self, stage_id: str, changes: dict[str, Any], *,
                     actor: str | None = None) -> Stage:
        before = self.get_stage(stage_id)
        self._update("competition_stages", "stage_id", stage_id, changes)
        after = self.get_stage(stage_id)
        if after is None:
            raise RecordNotFound(f"Asama bulunamadi: {stage_id}")
        self.audit("stage.update", actor_user_id=actor,
                   entity_type="competition_stage", entity_id=stage_id,
                   before=before, after=after)
        return after

    def get_stage(self, stage_id: str) -> Stage | None:
        return self._one(Stage, "SELECT * FROM competition_stages WHERE stage_id = ?;", [stage_id])

    def find_stage(
        self, competition_id: str, stage_code: str, level: str = "Genel",
        branch_code: str | None = None,
    ) -> Stage | None:
        # 1. Tam eslesme
        sql = (
            "SELECT * FROM competition_stages "
            "WHERE competition_id = ? AND UPPER(stage_code) = UPPER(?) "
            "ORDER BY CASE WHEN level = ? THEN 0 ELSE 1 END, "
            "         CASE WHEN branch_code IS ? THEN 0 ELSE 1 END LIMIT 1;"
        )
        res = self._one(Stage, sql, [competition_id, stage_code, level, branch_code])
        if res:
            return res
            
        # 2. On-ek / Seviye eslesmesi (or. PDR -> PDR_UNIVERSITE_SEVIYESI)
        clean_lvl = (level or "").split()[0].upper()
        patt = f"{stage_code}%"
        lvl_patt = f"%{clean_lvl}%" if clean_lvl else "%"
        sql_prefix = (
            "SELECT * FROM competition_stages "
            "WHERE competition_id = ? AND (UPPER(stage_code) LIKE UPPER(?) OR UPPER(stage_name) LIKE UPPER(?)) "
            "ORDER BY CASE WHEN UPPER(stage_code) LIKE ? THEN 0 ELSE 1 END LIMIT 1;"
        )
        return self._one(Stage, sql_prefix, [competition_id, patt, patt, lvl_patt])

    def list_stages(self, competition_id: str, branch_code: str | None = None) -> list[Stage]:
        sql = "SELECT * FROM competition_stages WHERE competition_id = ?"
        params: list[Any] = [competition_id]
        if branch_code:
            sql += " AND (branch_code = ? OR branch_code IS NULL)"
            params.append(branch_code)
        sql += " ORDER BY order_index, stage_code;"
        return self._many(Stage, sql, params)

    def delete_stage(self, stage_id: str, *, actor: str | None = None) -> None:
        before = self.get_stage(stage_id)
        if before:
            self.db.execute(
                "DELETE FROM stage_rubric_criteria WHERE competition_id = ? AND stage_code = ?;",
                [before.competition_id, before.stage_code],
            )
        self._delete("competition_stages", "stage_id", stage_id)
        self.audit("stage.delete", actor_user_id=actor,
                   entity_type="competition_stage", entity_id=stage_id, before=before)

    def ensure_default_stage(self, competition_id: str, *, actor: str | None = None) -> Stage | None:
        """KARAR #2: Hic asamasi olmayan yarismaya varsayilan OTR ekler.

        Kendi asamasi olan yarismalara DOKUNMAZ.
        """
        if self.list_stages(competition_id):
            return None
        stage = Stage(
            competition_id=competition_id,
            stage_code=DEFAULT_STAGE_CODE,
            stage_name=DEFAULT_STAGE_NAME,
            level="Genel",
            is_auto_generated=True,
            order_index=0,
        )
        self.add_stage(stage, actor=actor)
        return stage

    # ── sartname kurallari ────────────────────────────────────────────────
    def replace_requirements(
        self,
        competition_id: str,
        requirements: list[Requirement],
        *,
        branch_code: str | None = None,
        actor: str | None = None,
    ) -> list[Requirement]:
        """Belirtilen dalin kurallarini toplu degistirir (admin 'Kaydet' akisi)."""
        before = self.list_requirements(competition_id, branch_code)
        if branch_code:
            self.db.execute(
                "DELETE FROM competition_requirements WHERE competition_id = ? AND branch_code = ?;",
                [competition_id, branch_code],
            )
        else:
            self.db.execute(
                "DELETE FROM competition_requirements "
                "WHERE competition_id = ? AND branch_code IS NULL;",
                [competition_id],
            )
        for idx, req in enumerate(requirements):
            req.competition_id = competition_id
            req.branch_code = branch_code
            req.order_index = idx
            self._insert("competition_requirements", req)
        self.audit("requirements.replace", actor_user_id=actor,
                   entity_type="competition", entity_id=competition_id,
                   before=[r.to_row() for r in before],
                   after=[r.to_row() for r in requirements])
        return requirements

    def list_requirements(
        self, competition_id: str, branch_code: str | None = None
    ) -> list[Requirement]:
        sql = "SELECT * FROM competition_requirements WHERE competition_id = ?"
        params: list[Any] = [competition_id]
        if branch_code:
            sql += " AND (branch_code = ? OR branch_code IS NULL)"
            params.append(branch_code)
        sql += " ORDER BY order_index, rule_type;"
        return self._many(Requirement, sql, params)

    def approve_requirements(self, competition_id: str, *, actor: str | None = None) -> int:
        changed = self.db.execute(
            "UPDATE competition_requirements SET approved_by_admin = 1, updated_at = ? "
            "WHERE competition_id = ?;",
            [now_iso(), competition_id],
        )
        self.update(competition_id, {"spec_status": SpecStatus.ONAYLANDI.value}, actor=actor)
        return changed

    def eligibility(self, competition_id: str, branch_code: str | None = None) -> dict[str, Any]:
        """Basvuru uygunluk kontrolu icin ozet kural seti."""
        rules = self.list_requirements(competition_id, branch_code)
        summary: dict[str, Any] = {
            "min_team_size": None,
            "max_team_size": None,
            "advisor_required": False,
            "target_levels": [],
        }
        for rule in rules:
            if rule.min_team_size is not None:
                summary["min_team_size"] = rule.min_team_size
            if rule.max_team_size is not None:
                summary["max_team_size"] = rule.max_team_size
            if rule.advisor_required:
                summary["advisor_required"] = True
            if rule.target_level:
                for lvl in rule.target_level.split(","):
                    lvl = lvl.strip()
                    if lvl and lvl not in summary["target_levels"]:
                        summary["target_levels"].append(lvl)
        return summary

    # ── rubrik kriterleri ─────────────────────────────────────────────────
    def replace_rubric(
        self,
        competition_id: str,
        stage_code: str,
        criteria: list[RubricCriterion],
        *,
        level: str = "Genel",
        branch_code: str | None = None,
        actor: str | None = None,
    ) -> list[RubricCriterion]:
        before = self.list_rubric(competition_id, stage_code, level, branch_code)
        self.db.execute(
            "DELETE FROM stage_rubric_criteria WHERE competition_id = ? "
            "AND UPPER(stage_code) = UPPER(?) AND level = ?;",
            [competition_id, stage_code, level],
        )
        for idx, crit in enumerate(criteria):
            crit.competition_id = competition_id
            crit.stage_code = stage_code.upper()
            crit.level = level
            crit.branch_code = branch_code
            crit.order_index = idx
            self._insert("stage_rubric_criteria", crit)

        stage = self.find_stage(competition_id, stage_code, level, branch_code)
        if stage:
            self.update_stage(
                stage.stage_id,
                {
                    "rubric_status": RubricStatus.CIKARILDI.value,
                    "max_score": sum(c.max_score for c in criteria if not c.parent_code) or 100.0,
                },
                actor=actor,
            )
        self.audit("rubric.replace", actor_user_id=actor,
                   entity_type="stage", entity_id=f"{competition_id}:{stage_code}",
                   before=[c.to_row() for c in before],
                   after=[c.to_row() for c in criteria])
        return criteria

    def list_rubric(
        self,
        competition_id: str,
        stage_code: str,
        level: str = "Genel",
        branch_code: str | None = None,
    ) -> list[RubricCriterion]:
        """Rubrik cozumleme — HER ZAMAN dogru yarismanin kriterleri.

        Eski `rubrik.getir()` eslesme bulamayinca sessizce ilk yarismaya
        (HYZ OTR) dusuyordu; bu metot bulamazsa BOS liste doner ve cagiran
        taraf kullaniciya acik uyari gosterir.
        """
        sql = (
            "SELECT * FROM stage_rubric_criteria "
            "WHERE competition_id = ? AND UPPER(stage_code) = UPPER(?)"
        )
        params: list[Any] = [competition_id, stage_code]
        rows = self._many(
            RubricCriterion, sql + " AND level = ? ORDER BY order_index;", params + [level]
        )
        if rows:
            return rows
        return self._many(RubricCriterion, sql + " ORDER BY order_index;", params)

    def approve_rubric(
        self, competition_id: str, stage_code: str, *, actor: str | None = None
    ) -> int:
        changed = self.db.execute(
            "UPDATE stage_rubric_criteria SET approved_by_admin = 1, updated_at = ? "
            "WHERE competition_id = ? AND UPPER(stage_code) = UPPER(?);",
            [now_iso(), competition_id, stage_code],
        )
        stage = self.find_stage(competition_id, stage_code)
        if stage:
            self.update_stage(
                stage.stage_id, {"rubric_status": RubricStatus.ONAYLANDI.value}, actor=actor
            )
        return changed

    def rubric_total(self, competition_id: str, stage_code: str, level: str = "Genel") -> float:
        criteria = self.list_rubric(competition_id, stage_code, level)
        return sum(c.max_score for c in criteria if not c.parent_code)


__all__ = ["CompetitionRepo", "DEFAULT_STAGE_CODE", "DEFAULT_STAGE_NAME"]
