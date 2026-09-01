"""Repository tabani.

SOZLESME
--------
1. Her metot Pydantic modeli alir / dondurur — cikis olarak dict yoktur.
2. Hata FIRLATIR. `except Exception: pass` yasaktir.
3. `bool` dondurmez; olusturulan veya guncellenen nesneyi dondurur.
4. Tum kimlikler `uuid4` — `hash()` yasaktir.
5. Tum enum degerleri `src.data.enums`'tan gelir — string literal yasaktir.
"""

from __future__ import annotations

import json
from typing import Any, Sequence, TypeVar

from ..client import D1Client, QueryFailed, get_client
from ..models import AuditEntry, Base, now_iso

T = TypeVar("T", bound=Base)

# (client_id, table) -> kolon adlari. Sema calisma aninda degismedigi icin guvenli.
_COLUMN_CACHE: dict[tuple[int, str], set[str]] = {}


class RecordNotFound(QueryFailed):
    """Beklenen kayit bulunamadi."""


class DuplicateRecord(QueryFailed):
    """Benzersizlik kisiti ihlali."""


class BaseRepo:
    def __init__(self, client: D1Client | None = None) -> None:
        self.db = client or get_client()

    # ── dusuk seviye yardimcilar ──────────────────────────────────────────
    def _insert(self, table: str, model: Base, *, replace: bool = False) -> None:
        row = model.to_row()
        cols = list(row.keys())
        verb = "INSERT OR REPLACE INTO" if replace else "INSERT INTO"
        sql = (
            f"{verb} {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)});"
        )
        try:
            self.db.execute(sql, [row[c] for c in cols])
        except QueryFailed as exc:
            if "UNIQUE" in str(exc).upper():
                raise DuplicateRecord(f"{table}: benzersizlik ihlali — {exc}") from exc
            raise

    def _upsert(self, table: str, model: Base, conflict_cols: Sequence[str]) -> None:
        row = model.to_row()
        if self._has_column(table, "updated_at"):
            row["updated_at"] = now_iso()
        cols = list(row.keys())
        updatable = [c for c in cols if c not in conflict_cols and c != "created_at"]
        sql = (
            f"INSERT INTO {table} ({', '.join(cols)}) "
            f"VALUES ({', '.join('?' for _ in cols)}) "
            f"ON CONFLICT({', '.join(conflict_cols)}) DO UPDATE SET "
            + ", ".join(f"{c}=excluded.{c}" for c in updatable)
            + ";"
        )
        self.db.execute(sql, [row[c] for c in cols])

    def _has_column(self, table: str, column: str) -> bool:
        key = (id(self.db), table)
        cached = _COLUMN_CACHE.get(key)
        if cached is None:
            cached = set(self.db.column_names(table))
            _COLUMN_CACHE[key] = cached
        return column in cached

    def _update(self, table: str, pk_col: str, pk_val: str, changes: dict[str, Any]) -> int:
        if not changes:
            return 0
        payload = dict(changes)
        # `updated_at` yalnizca tabloda varsa eklenir (or. report_assignments'ta yok).
        if "updated_at" not in payload and self._has_column(table, "updated_at"):
            payload["updated_at"] = now_iso()
        sets = ", ".join(f"{c} = ?" for c in payload)
        params = [_scalar(v) for v in payload.values()] + [pk_val]
        return self.db.execute(f"UPDATE {table} SET {sets} WHERE {pk_col} = ?;", params)

    def _delete(self, table: str, pk_col: str, pk_val: str) -> int:
        return self.db.execute(f"DELETE FROM {table} WHERE {pk_col} = ?;", [pk_val])

    def _one(self, model_cls: type[T], sql: str, params: Sequence[Any] | None = None) -> T | None:
        rows = self.db.query(sql, params)
        return model_cls(**rows[0]) if rows else None

    def _many(self, model_cls: type[T], sql: str, params: Sequence[Any] | None = None) -> list[T]:
        return [model_cls(**r) for r in self.db.query(sql, params)]

    def _count(self, sql: str, params: Sequence[Any] | None = None) -> int:
        rows = self.db.query(sql, params)
        if not rows:
            return 0
        return int(list(rows[0].values())[0] or 0)

    # ── denetim izi ───────────────────────────────────────────────────────
    def audit(
        self,
        action: str,
        *,
        actor_user_id: str | None = None,
        actor_email: str | None = None,
        entity_type: str | None = None,
        entity_id: str | None = None,
        before: Any = None,
        after: Any = None,
    ) -> None:
        entry = AuditEntry(
            actor_user_id=actor_user_id,
            actor_email=actor_email,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before_json=_dumps(before),
            after_json=_dumps(after),
        )
        self._insert("audit_log", entry)


def _scalar(value: Any) -> Any:
    if isinstance(value, bool):
        return 1 if value else 0
    if hasattr(value, "value"):
        return value.value
    return value


def _dumps(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Base):
        return json.dumps(value.to_row(), ensure_ascii=False, default=str)
    return json.dumps(value, ensure_ascii=False, default=str)


__all__ = ["BaseRepo", "RecordNotFound", "DuplicateRecord"]
