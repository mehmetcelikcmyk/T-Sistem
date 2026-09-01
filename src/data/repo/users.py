"""Kullanici deposu ve parola politikasi.

DEGISIKLIKLER
-------------
* Eski `users` tablosu kaldirildi; `auth_users` tek kaynak (KARAR #3).
* Parola hash'i saltsiz SHA-256 yerine Argon2id / PBKDF2-SHA256.
  Eski SHA-256 hash'leri taninir ve ilk basarili giriste sessizce yukseltilir.
* Seed hesaplar yalnizca `TSISTEM_BOOTSTRAP=1` iken ve parolalar `.env`'den
  okunarak olusturulur; her aciliste D1'e geri yazilmaz.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from typing import Any

from ..enums import Role, UserStatus
from ..models import User, now_iso
from .base import BaseRepo, DuplicateRecord, RecordNotFound

_PBKDF2_ROUNDS = 240_000
_LEGACY_SHA256_LEN = 64


# ── parola ─────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    """Argon2id varsa onu, yoksa PBKDF2-SHA256 kullanir."""
    if not password:
        raise ValueError("Parola bos olamaz.")
    try:
        from argon2 import PasswordHasher  # type: ignore

        return PasswordHasher().hash(password)
    except ImportError:
        salt = secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), _PBKDF2_ROUNDS
        ).hex()
        return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt}${digest}"


def verify_password(password: str, stored: str | None) -> tuple[bool, bool]:
    """(dogru_mu, yukseltilmeli_mi) dondurur."""
    if not stored or not password:
        return False, False

    if stored.startswith("$argon2"):
        try:
            from argon2 import PasswordHasher  # type: ignore
            from argon2.exceptions import VerifyMismatchError  # type: ignore

            try:
                PasswordHasher().verify(stored, password)
                return True, False
            except VerifyMismatchError:
                return False, False
        except ImportError:
            return False, False

    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, rounds_s, salt, digest = stored.split("$", 3)
            candidate = hashlib.pbkdf2_hmac(
                "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds_s)
            ).hex()
            return hmac.compare_digest(candidate, digest), False
        except (ValueError, TypeError):
            return False, False

    # Eski saltsiz SHA-256 — dogruysa yukseltilmesi gerektigi bildirilir.
    if len(stored) == _LEGACY_SHA256_LEN:
        legacy = hashlib.sha256(password.encode("utf-8")).hexdigest()
        if hmac.compare_digest(legacy, stored):
            return True, True
    return False, False


class UserRepo(BaseRepo):
    # ── okuma ─────────────────────────────────────────────────────────────
    def get(self, user_id: str) -> User | None:
        return self._one(User, "SELECT * FROM auth_users WHERE user_id = ?;", [user_id])

    def get_by_email(self, email: str) -> User | None:
        return self._one(
            User, "SELECT * FROM auth_users WHERE LOWER(email) = LOWER(?) LIMIT 1;", [email]
        )

    def get_or_raise(self, user_id: str) -> User:
        user = self.get(user_id)
        if user is None:
            raise RecordNotFound(f"Kullanici bulunamadi: {user_id}")
        return user

    def list(
        self,
        *,
        role: Role | None = None,
        status: UserStatus | None = None,
        search: str = "",
        limit: int = 500,
        offset: int = 0,
    ) -> list[User]:
        sql = "SELECT * FROM auth_users WHERE 1=1"
        params: list[Any] = []
        if role:
            sql += " AND role = ?"
            params.append(role.value)
        if status:
            sql += " AND status = ?"
            params.append(status.value)
        if search:
            sql += " AND (LOWER(name) LIKE ? OR LOWER(email) LIKE ? OR LOWER(institution) LIKE ?)"
            needle = f"%{search.lower()}%"
            params += [needle, needle, needle]
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?;"
        params += [limit, offset]
        return self._many(User, sql, params)

    def referees(self) -> list[User]:
        """Hakem havuzu. Eski sorgu var olmayan `surname` kolonunu istedigi
        icin her zaman bos donuyordu; sema artik bu kolonu iceriyor."""
        return self.list(role=Role.HAKEM, status=UserStatus.AKTIF)

    def counts_by_role(self) -> dict[str, int]:
        rows = self.db.query("SELECT role, COUNT(*) AS n FROM auth_users GROUP BY role;")
        return {r["role"]: int(r["n"]) for r in rows}

    # ── yazma ─────────────────────────────────────────────────────────────
    def create(self, user: User, password: str | None = None, *,
               actor: str | None = None) -> User:
        if self.get_by_email(user.email):
            raise DuplicateRecord(f"Bu e-posta zaten kayitli: {user.email}")
        if password:
            user.password_hash = hash_password(password)
        self._insert("auth_users", user)
        self.audit("user.create", actor_user_id=actor,
                   entity_type="user", entity_id=user.user_id,
                   after={"email": user.email, "role": user.role.value})
        return user

    def update(self, user_id: str, changes: dict[str, Any], *,
               actor: str | None = None) -> User:
        before = self.get_or_raise(user_id)
        payload = dict(changes)
        if "password" in payload:
            payload["password_hash"] = hash_password(payload.pop("password"))
        if "email" in payload:
            existing = self.get_by_email(payload["email"])
            if existing and existing.user_id != user_id:
                raise DuplicateRecord(f"Bu e-posta baska kullanicida: {payload['email']}")
        self._update("auth_users", "user_id", user_id, payload)
        after = self.get_or_raise(user_id)
        self.audit("user.update", actor_user_id=actor,
                   entity_type="user", entity_id=user_id,
                   before={"role": before.role.value, "status": before.status.value},
                   after={"role": after.role.value, "status": after.status.value})
        return after

    def delete(self, user_id: str, *, actor: str | None = None) -> None:
        before = self.get_or_raise(user_id)
        self._guard_last_admin(before, deleting=True)
        self._delete("auth_users", "user_id", user_id)
        self.audit("user.delete", actor_user_id=actor,
                   entity_type="user", entity_id=user_id, before={"email": before.email})

    def set_role(self, user_id: str, role: Role, *, actor: str | None = None) -> User:
        target = self.get_or_raise(user_id)
        if target.role == Role.ADMIN and role != Role.ADMIN:
            self._guard_last_admin(target, deleting=True)
        return self.update(user_id, {"role": role.value}, actor=actor)

    def set_status(self, user_id: str, status: UserStatus, *,
                   actor: str | None = None) -> User:
        target = self.get_or_raise(user_id)
        if target.role == Role.ADMIN and status == UserStatus.PASIF:
            self._guard_last_admin(target, deleting=True)
        return self.update(user_id, {"status": status.value}, actor=actor)

    # ── kimlik dogrulama ──────────────────────────────────────────────────
    def authenticate(self, email: str, password: str) -> User:
        user = self.get_by_email(email)
        if user is None:
            raise RecordNotFound("E-posta veya parola hatali.")
        if user.status != UserStatus.AKTIF:
            raise RecordNotFound("Hesabiniz pasif durumda. Yonetici ile iletisime geciniz.")
        ok, needs_upgrade = verify_password(password, user.password_hash)
        if not ok:
            raise RecordNotFound("E-posta veya parola hatali.")
        if needs_upgrade:
            self._update(
                "auth_users", "user_id", user.user_id,
                {"password_hash": hash_password(password)},
            )
        return user

    def set_password(self, user_id: str, password: str) -> None:
        if len(password) < 8:
            raise ValueError("Parola en az 8 karakter olmalidir.")
        self._update("auth_users", "user_id", user_id, {"password_hash": hash_password(password)})

    # ── bootstrap ─────────────────────────────────────────────────────────
    def bootstrap_admin(self) -> User | None:
        """Yalnizca TSISTEM_BOOTSTRAP=1 iken ve hic admin yokken calisir.

        Eski kod `admin123` / `hakem123` hesaplarini HER ACILISTA hem yerele
        hem canli D1'e yaziyordu; bu, prod'da degistirilen parolayi geri
        dondurebiliyordu.
        """
        if os.getenv("TSISTEM_BOOTSTRAP", "") != "1":
            return None
        if self.list(role=Role.ADMIN, limit=1):
            return None

        email = os.getenv("TSISTEM_ADMIN_EMAIL", "").strip().lower()
        password = os.getenv("TSISTEM_ADMIN_PASSWORD", "")
        if not email or len(password) < 12:
            raise ValueError(
                "Bootstrap icin TSISTEM_ADMIN_EMAIL ve en az 12 karakterlik "
                "TSISTEM_ADMIN_PASSWORD tanimlanmalidir."
            )
        admin = User(
            name=os.getenv("TSISTEM_ADMIN_NAME", "Sistem"),
            surname=os.getenv("TSISTEM_ADMIN_SURNAME", "Yoneticisi"),
            email=email,
            role=Role.ADMIN,
            profile_completed=True,
            created_at=now_iso(),
        )
        return self.create(admin, password=password)

    # ── ic kontrol ────────────────────────────────────────────────────────
    def _guard_last_admin(self, user: User, *, deleting: bool) -> None:
        if user.role != Role.ADMIN or not deleting:
            return
        active_admins = self._count(
            "SELECT COUNT(*) FROM auth_users WHERE role = ? AND status = ?;",
            [Role.ADMIN.value, UserStatus.AKTIF.value],
        )
        if active_admins <= 1:
            raise ValueError(
                "Sistemdeki son aktif yonetici silinemez, rolu dusurulemez veya pasife alinamaz."
            )


__all__ = ["UserRepo", "hash_password", "verify_password"]
