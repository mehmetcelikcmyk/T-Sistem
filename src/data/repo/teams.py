"""Takim ve takim uyesi deposu.

DEGISIKLIKLER
-------------
* Takimlar artik `data/takimlar.json` yerine D1'de. Eski dosya GLOBAL'di —
  ayni sunucudaki tum kullanicilar birbirinin takimlarini goruyordu.
* Davet kodu `abs(hash(ad))` yerine KARARLI, benzersiz 6 haneli kod.
  Eski kodda PYTHONHASHSEED yuzunden uygulama her yeniden baslatildiginda
  ayni takim adi farkli kod uretiyordu.
* Takima katilma artik kodu GERCEKTEN dogruluyor; eski kod herhangi bir
  sayiyi kabul edip "Katilinan Takim 999999" adiyla sahte kayit aciyordu.
* KARAR: Takimlar bir yarismaya baglanmaz — bag `applications` tablosundadir.
"""

from __future__ import annotations

import secrets
import string
from typing import Any

from ..enums import TeamRole, TeamStatus
from ..models import Team, TeamMember, User
from .base import BaseRepo, DuplicateRecord, RecordNotFound

_CODE_ALPHABET = string.digits + "ABCDEFGHJKLMNPQRSTUVWXYZ"  # I, O, 0 karisikligi yok
_CODE_LEN = 6


class TeamRepo(BaseRepo):
    # ── davet kodu ────────────────────────────────────────────────────────
    def _generate_code(self) -> str:
        for _ in range(40):
            code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))
            if not self.get_by_code(code):
                return code
        raise RuntimeError("Benzersiz takim kodu uretilemedi.")

    # ── okuma ─────────────────────────────────────────────────────────────
    def get(self, team_id: str) -> Team | None:
        return self._one(Team, "SELECT * FROM teams WHERE team_id = ?;", [team_id])

    def get_or_raise(self, team_id: str) -> Team:
        team = self.get(team_id)
        if team is None:
            raise RecordNotFound(f"Takim bulunamadi: {team_id}")
        return team

    def get_by_code(self, team_code: str) -> Team | None:
        return self._one(
            Team, "SELECT * FROM teams WHERE UPPER(team_code) = UPPER(?);", [team_code]
        )

    def list_all(self, *, include_disbanded: bool = False) -> list[Team]:
        """Sistemdeki TÜM takımları döner (admin kullanımı için).

        D1 ve SQLite'ı soyutlayan self.db.query üzerinden çalışır;
        aktif backend hangisiyse oradan okur.
        """
        if include_disbanded:
            return self._many(Team, "SELECT * FROM teams ORDER BY created_at DESC;")
        return self._many(
            Team,
            "SELECT * FROM teams WHERE status != ? ORDER BY created_at DESC;",
            [TeamStatus.DAGITILDI.value],
        )

    def list_for_user(self, user_id: str) -> list[Team]:
        """Kullanicinin uyesi oldugu TUM takimlar.

        Bir takimdaki herkesin ayni takimi gormesi kullanicinin #273'teki
        isteridir; eski yerel JSON bunu saglayamiyordu.
        """
        return self._many(
            Team,
            "SELECT t.* FROM teams t "
            "JOIN team_members m ON m.team_id = t.team_id "
            "WHERE m.user_id = ? AND t.status != ? "
            "ORDER BY t.created_at DESC;",
            [user_id, TeamStatus.DAGITILDI.value],
        )

    def members(self, team_id: str) -> list[tuple[TeamMember, User | None]]:
        rows = self.db.query(
            "SELECT m.team_id, m.user_id, m.role_in_team, m.joined_at, "
            "       u.name, u.surname, u.email, u.institution, u.education_level "
            "FROM team_members m LEFT JOIN auth_users u ON u.user_id = m.user_id "
            "WHERE m.team_id = ? ORDER BY "
            "  CASE m.role_in_team WHEN 'kaptan' THEN 0 WHEN 'danisman' THEN 2 ELSE 1 END, "
            "  m.joined_at;",
            [team_id],
        )
        out: list[tuple[TeamMember, User | None]] = []
        for row in rows:
            member = TeamMember(
                team_id=row["team_id"],
                user_id=row["user_id"],
                role_in_team=row["role_in_team"],
                joined_at=row["joined_at"],
            )
            user = None
            if row.get("email"):
                user = User(
                    user_id=row["user_id"],
                    name=row.get("name") or "",
                    surname=row.get("surname"),
                    email=row["email"],
                    institution=row.get("institution"),
                    education_level=row.get("education_level"),
                )
            out.append((member, user))
        return out

    def member_count(self, team_id: str, *, include_advisor: bool = False) -> int:
        sql = "SELECT COUNT(*) FROM team_members WHERE team_id = ?"
        params: list[Any] = [team_id]
        if not include_advisor:
            sql += " AND role_in_team != ?"
            params.append(TeamRole.DANISMAN.value)
        return self._count(sql + ";", params)

    def is_captain(self, team_id: str, user_id: str) -> bool:
        team = self.get(team_id)
        return bool(team and team.captain_user_id == user_id)

    # ── yazma ─────────────────────────────────────────────────────────────
    def create(
        self,
        *,
        name: str,
        captain_user_id: str,
        level: str | None = None,
        institution: str | None = None,
        advisor_name: str | None = None,
        advisor_email: str | None = None,
        advisor_title: str | None = None,
    ) -> Team:
        if not name.strip():
            raise ValueError("Takim adi bos olamaz.")
        existing = self._one(
            Team, "SELECT * FROM teams WHERE LOWER(name) = LOWER(?) LIMIT 1;", [name.strip()]
        )
        if existing:
            raise DuplicateRecord(f"'{name}' adinda bir takim zaten var.")

        team = Team(
            team_code=self._generate_code(),
            name=name.strip(),
            level=level,
            institution=institution,
            captain_user_id=captain_user_id,
            advisor_name=advisor_name,
            advisor_email=advisor_email,
            advisor_title=advisor_title,
        )
        self._insert("teams", team)
        self._insert(
            "team_members",
            TeamMember(team_id=team.team_id, user_id=captain_user_id, role_in_team=TeamRole.KAPTAN),
        )
        self.audit("team.create", actor_user_id=captain_user_id,
                   entity_type="team", entity_id=team.team_id, after=team)
        return team

    def update(self, team_id: str, changes: dict[str, Any], *,
               actor: str | None = None) -> Team:
        before = self.get_or_raise(team_id)
        self._update("teams", "team_id", team_id, changes)
        after = self.get_or_raise(team_id)
        self.audit("team.update", actor_user_id=actor,
                   entity_type="team", entity_id=team_id, before=before, after=after)
        return after

    def join_by_code(self, team_code: str, user_id: str) -> Team:
        """Davet koduyla katilma — kod GERCEKTEN dogrulanir."""
        team = self.get_by_code(team_code.strip())
        if team is None:
            raise RecordNotFound(
                "Bu koda sahip bir takim bulunamadi. Kodu takim kaptanindan tekrar aliniz."
            )
        if team.status != TeamStatus.AKTIF:
            raise ValueError("Bu takim aktif degil.")
        already = self._count(
            "SELECT COUNT(*) FROM team_members WHERE team_id = ? AND user_id = ?;",
            [team.team_id, user_id],
        )
        if already:
            raise DuplicateRecord("Zaten bu takimin uyesisiniz.")

        # Kullanıcı e-postası takımın danışman e-postasıyla eşleşiyor mu?
        user_row = self.db.query(
            "SELECT email FROM auth_users WHERE user_id = ? LIMIT 1;", [user_id]
        )
        user_email = (user_row[0].get("email") or "").strip().lower() if user_row else ""
        team_adv_email = (team.advisor_email or "").strip().lower()

        assigned_role = TeamRole.DANISMAN if (user_email and team_adv_email and user_email == team_adv_email) else TeamRole.UYE

        self._insert(
            "team_members",
            TeamMember(team_id=team.team_id, user_id=user_id, role_in_team=assigned_role),
        )
        self.audit("team.join", actor_user_id=user_id,
                   entity_type="team", entity_id=team.team_id, after={"user_id": user_id, "role": assigned_role.value})
        return team

    def add_member(self, team_id: str, user_id: str,
                   role_in_team: TeamRole = TeamRole.UYE) -> TeamMember:
        member = TeamMember(team_id=team_id, user_id=user_id, role_in_team=role_in_team)
        self._insert("team_members", member)
        return member

    def remove_member(self, team_id: str, user_id: str, *, actor: str | None = None) -> None:
        team = self.get_or_raise(team_id)
        if team.captain_user_id == user_id:
            raise ValueError(
                "Kaptan takimdan cikarilamaz. Once kaptanligi baska bir uyeye devrediniz."
            )
        self.db.execute(
            "DELETE FROM team_members WHERE team_id = ? AND user_id = ?;", [team_id, user_id]
        )
        self.audit("team.member_remove", actor_user_id=actor,
                   entity_type="team", entity_id=team_id, before={"user_id": user_id})

    def transfer_captain(self, team_id: str, new_captain_user_id: str, *,
                         actor: str | None = None) -> Team:
        member_exists = self._count(
            "SELECT COUNT(*) FROM team_members WHERE team_id = ? AND user_id = ?;",
            [team_id, new_captain_user_id],
        )
        if not member_exists:
            raise RecordNotFound("Yeni kaptan once takim uyesi olmalidir.")
        old = self.get_or_raise(team_id)
        self.db.execute(
            "UPDATE team_members SET role_in_team = ? WHERE team_id = ? AND user_id = ?;",
            [TeamRole.UYE.value, team_id, old.captain_user_id],
        )
        self.db.execute(
            "UPDATE team_members SET role_in_team = ? WHERE team_id = ? AND user_id = ?;",
            [TeamRole.KAPTAN.value, team_id, new_captain_user_id],
        )
        return self.update(team_id, {"captain_user_id": new_captain_user_id}, actor=actor)

    def delete(self, team_id: str, *, actor: str | None = None) -> None:
        before = self.get_or_raise(team_id)
        active_apps = self._count(
            "SELECT COUNT(*) FROM applications WHERE team_id = ? AND status = 'aktif';", [team_id]
        )
        if active_apps:
            raise ValueError(
                f"Bu takimin {active_apps} aktif basvurusu var. Once basvurulari geri cekiniz."
            )
        self._delete("teams", "team_id", team_id)
        self.audit("team.delete", actor_user_id=actor,
                   entity_type="team", entity_id=team_id, before=before)


__all__ = ["TeamRepo"]
