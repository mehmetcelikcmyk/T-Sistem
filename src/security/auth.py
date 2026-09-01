"""T-Sistem · FastAPI kimlik dogrulama ve rol bazli erisim kontrolu.

ONCEKI DURUM (KRITIK ACIK)
--------------------------
    x_user_role: Optional[str] = Header("ADMIN", alias="X-User-Role")

Kullanici kimligi istemcinin gonderdigi duz HTTP header'dan geliyordu ve
VARSAYILANI "ADMIN" idi. Yani header hic gondermeden butun admin uclarina
erisilebiliyordu:

    curl http://localhost:8000/api/admin/calibration    # ADMIN olarak gecerdi

YENI DURUM
----------
* Imzali, kisa omurlu JWT (HS256). Gizli anahtar `.env` icindeki
  TSISTEM_JWT_SECRET; tanimli degilse uygulama ACILISTA hata verir
  (sessiz zayif varsayilan yok).
* Token `sub` (user_id), `role`, `email`, `exp`, `iat` tasir.
* Rol dogrulamasi token claim'inden yapilir, header'dan degil.
* Rol adlari `src.data.enums.Role` ile ayni sozlugu kullanir
  (yarismaci / hakem / admin).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from enum import Enum as _Enum
from typing import Any, Callable, Iterable

from fastapi import Depends, Header, HTTPException, status
from pydantic import BaseModel

_ALGORITHM = "HS256"
_DEFAULT_TTL = 8 * 60 * 60  # 8 saat
_LEEWAY = 30


class TokenError(Exception):
    pass


# ── rol sozlugu (src.data.enums.Role ile birebir) ──────────────────────────
ROLE_YARISMACI = "yarismaci"
ROLE_HAKEM = "hakem"
ROLE_ADMIN = "admin"
ALL_ROLES = (ROLE_YARISMACI, ROLE_HAKEM, ROLE_ADMIN)

_LEGACY_ROLES = {
    "contestant": ROLE_YARISMACI,
    "uye": ROLE_YARISMACI,
    "field_referee": ROLE_HAKEM,
    "head_referee": ROLE_HAKEM,
    "referee": ROLE_HAKEM,
    "yonetici": ROLE_ADMIN,
}


class AuthUser(BaseModel):
    user_id: str
    email: str = ""
    name: str = ""
    role: str = ROLE_YARISMACI

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    @property
    def is_referee(self) -> bool:
        return self.role == ROLE_HAKEM


# ── gizli anahtar ──────────────────────────────────────────────────────────
def _secret() -> bytes:
    raw = os.getenv("TSISTEM_JWT_SECRET", "")
    if len(raw) < 32:
        raise RuntimeError(
            "TSISTEM_JWT_SECRET tanimli degil veya 32 karakterden kisa. "
            "Uretin: python -c \"import secrets;print(secrets.token_urlsafe(48))\""
        )
    return raw.encode("utf-8")


# ── JWT (harici bagimlilik olmadan, HS256) ─────────────────────────────────
def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def create_token(
    user_id: str,
    role: str,
    *,
    email: str = "",
    name: str = "",
    ttl_seconds: int = _DEFAULT_TTL,
) -> str:
    role = normalize_role(role)
    now = int(time.time())
    header = {"alg": _ALGORITHM, "typ": "JWT"}
    payload = {
        "sub": user_id,
        "role": role,
        "email": email,
        "name": name,
        "iat": now,
        "exp": now + ttl_seconds,
        "iss": "t-sistem",
    }
    segments = [
        _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    segments.append(_b64url_encode(signature))
    return ".".join(segments)


def decode_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("Token bicimi gecersiz.") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(_secret(), signing_input, hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64url_decode(signature_b64)):
        raise TokenError("Token imzasi dogrulanamadi.")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except (ValueError, json.JSONDecodeError) as exc:
        raise TokenError("Token icerigi okunamadi.") from exc

    if payload.get("iss") != "t-sistem":
        raise TokenError("Token kaynagi gecersiz.")
    exp = int(payload.get("exp", 0))
    if exp and exp + _LEEWAY < int(time.time()):
        raise TokenError("Oturum suresi doldu. Lutfen tekrar giris yapiniz.")
    return payload


def normalize_role(raw: str | None) -> str:
    value = (raw or "").strip().lower()
    value = _LEGACY_ROLES.get(value, value)
    return value if value in ALL_ROLES else ROLE_YARISMACI


# ── FastAPI bagimliliklari ─────────────────────────────────────────────────
def get_current_user(authorization: str | None = Header(None)) -> AuthUser:
    """Authorization: Bearer <token> basligindan kullaniciyi cozer.

    VARSAYILAN KULLANICI YOKTUR. Token gecersizse 401 doner.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Kimlik dogrulama gerekli. 'Authorization: Bearer <token>' basligi gonderiniz.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except TokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except RuntimeError as exc:  # gizli anahtar eksik
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)
        ) from exc

    return AuthUser(
        user_id=str(payload.get("sub", "")),
        email=str(payload.get("email", "")),
        name=str(payload.get("name", "")),
        role=normalize_role(payload.get("role")),
    )


def require_roles(allowed_roles: Iterable[str]) -> Callable[..., AuthUser]:
    allowed = {normalize_role(r) for r in allowed_roles}

    def _checker(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Bu islem icin gerekli rol: {', '.join(sorted(allowed))}. "
                    f"Mevcut rol: {user.role}."
                ),
            )
        return user

    return _checker


require_admin = require_roles([ROLE_ADMIN])
require_referee = require_roles([ROLE_HAKEM, ROLE_ADMIN])
require_any = require_roles(ALL_ROLES)


# ── geriye donuk uyumluluk ────────────────────────────────────────────────
# `api/routes.py` eski `UserRole` enum'unu import ediyor. Kirmadan gecis icin
# ince bir kabuk birakildi; yeni kod dogrudan ROLE_* sabitlerini kullanmalidir.
class UserRole(str, _Enum):
    ADMIN = ROLE_ADMIN
    HAKEM = ROLE_HAKEM
    CONTESTANT = ROLE_YARISMACI
    # eski adlar
    HEAD_REFEREE = ROLE_HAKEM
    FIELD_REFEREE = ROLE_HAKEM

    def __str__(self) -> str:  # pragma: no cover
        return self.value


__all__ = [
    "AuthUser", "TokenError", "UserRole",
    "create_token", "decode_token", "normalize_role",
    "get_current_user", "require_roles",
    "require_admin", "require_referee", "require_any",
    "ROLE_YARISMACI", "ROLE_HAKEM", "ROLE_ADMIN", "ALL_ROLES",
]
