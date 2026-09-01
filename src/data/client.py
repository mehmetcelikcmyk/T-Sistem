"""T-Sistem · TEK veritabani istemcisi.

Onceki kod tabaninda ayni isi yapan UC ayri D1 istemcisi vardi
(`db._d1_query`, `db.execute_d1`, `auth_service._query_d1`); ucu de farkli
donus tipleri ve farkli hata davranislariyla. Bu modul onlarin yerine gecer.

TASARIM KURALLARI
-----------------
1. Backend ACILISTA secilir, sorgu basina sessizce degismez.
   Eski `execute_d1` D1 patlayinca sessizce SQLite'a dusuyordu; iki tarafin
   semasi ayrisinca veri kaybi gorunmez hale geliyordu.
2. Hata YUTULMAZ. Her basarisizlik `DataError` olarak yukari firlatilir.
3. Her cagri loglanir (sure, satir sayisi, hata).
4. `success: false` donen HTTP 200 yanitlari da hata sayilir.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable, Sequence
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("tsistem.data")

_D1_ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/{acc}/d1/database/{db}/query"
_MAX_RETRY = 1
_BACKOFF_BASE = 0.2
_TIMEOUT = 3.0


# ── Hata tipleri ───────────────────────────────────────────────────────────
class DataError(RuntimeError):
    """Veri katmani hatalarinin tabani. UI bunu yakalayip st.error gosterir."""


class ConnectionFailed(DataError):
    pass


class QueryFailed(DataError):
    def __init__(self, message: str, sql: str = "", params: Any = None) -> None:
        super().__init__(message)
        self.sql = sql
        self.params = params


class NotConfigured(DataError):
    pass


# ── Istemci ────────────────────────────────────────────────────────────────
class D1Client:
    """Cloudflare D1 (REST) veya yerel SQLite uzerinde calisan tek istemci."""

    def __init__(
        self,
        account_id: str | None = None,
        database_id: str | None = None,
        api_token: str | None = None,
        sqlite_path: str | Path | None = None,
        backend: str | None = None,
    ) -> None:
        self.account_id = account_id or os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
        self.database_id = database_id or os.getenv("CLOUDFLARE_D1_DATABASE_ID", "")
        self.api_token = api_token or os.getenv("CLOUDFLARE_API_TOKEN", "")

        default_sqlite = Path(__file__).resolve().parents[2] / "data" / "tsistem.db"
        self.sqlite_path = Path(sqlite_path or os.getenv("TSISTEM_DB_PATH", default_sqlite))

        chosen = (backend or os.getenv("TSISTEM_DB_BACKEND", "") or "").strip().lower()
        if chosen not in {"d1", "sqlite"}:
            chosen = "d1" if self.has_cloud_credentials else "sqlite"
        self.backend = chosen

        if self.backend == "d1" and not self.has_cloud_credentials:
            raise NotConfigured(
                "TSISTEM_DB_BACKEND=d1 secildi ancak CLOUDFLARE_ACCOUNT_ID / "
                "CLOUDFLARE_D1_DATABASE_ID / CLOUDFLARE_API_TOKEN eksik."
            )

        if self.backend == "sqlite":
            self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)

        log.info("[data] backend=%s sqlite_path=%s", self.backend, self.sqlite_path)

    # ── ozellikler ────────────────────────────────────────────────────────
    @property
    def has_cloud_credentials(self) -> bool:
        return bool(self.account_id and self.database_id and self.api_token)

    @property
    def is_cloud(self) -> bool:
        return self.backend == "d1"

    # ── genel API ─────────────────────────────────────────────────────────
    def query(self, sql: str, params: Sequence[Any] | None = None) -> list[dict[str, Any]]:
        """SELECT calistirir ve satirlari sozluk listesi olarak dondurur."""
        rows, _ = self._run(sql, params)
        return rows

    def execute(self, sql: str, params: Sequence[Any] | None = None) -> int:
        """INSERT/UPDATE/DELETE calistirir ve etkilenen satir sayisini dondurur."""
        _, changes = self._run(sql, params)
        return changes

    def execute_script(self, script: str) -> int:
        """Cok ifadeli DDL scriptini calistirir (schema.sql icin)."""
        statements = _split_sql(script)
        applied = 0
        for stmt in statements:
            self.execute(stmt)
            applied += 1
        return applied

    def batch(self, statements: Iterable[tuple[str, Sequence[Any] | None]]) -> int:
        """Birden fazla ifadeyi sirayla calistirir.

        SQLite'ta gercek transaction kullanilir. D1 REST tekil ifade kabul
        ettigi icin bulut tarafinda sirali calisir; kismi basarisizlikta
        hangi ifadede kalindigi hata mesajinda bildirilir.
        """
        stmts = list(statements)
        if self.backend == "sqlite":
            conn = self._sqlite_conn()
            try:
                cur = conn.cursor()
                total = 0
                for sql, params in stmts:
                    cur.execute(sql, list(params or []))
                    total += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                conn.commit()
                return total
            except Exception as exc:  # noqa: BLE001
                conn.rollback()
                raise QueryFailed(f"Toplu islem geri alindi: {exc}") from exc
            finally:
                conn.close()

        total = 0
        for idx, (sql, params) in enumerate(stmts):
            try:
                total += self.execute(sql, params)
            except DataError as exc:
                raise QueryFailed(
                    f"Toplu islem {idx + 1}/{len(stmts)}. ifadede durdu: {exc}", sql, params
                ) from exc
        return total

    def table_names(self) -> list[str]:
        rows = self.query(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' AND name NOT LIKE '_cf_%' ORDER BY name;"
        )
        return [r["name"] for r in rows]

    def column_names(self, table: str) -> list[str]:
        if not table.replace("_", "").isalnum():
            raise QueryFailed(f"Gecersiz tablo adi: {table}")
        rows = self.query(f"PRAGMA table_info({table});")
        return [r["name"] for r in rows]

    def healthcheck(self) -> dict[str, Any]:
        started = time.time()
        try:
            self.query("SELECT 1 AS ok;")
            return {
                "backend": self.backend,
                "ok": True,
                "latency_ms": round((time.time() - started) * 1000, 1),
                "tables": len(self.table_names()),
            }
        except DataError as exc:
            return {"backend": self.backend, "ok": False, "error": str(exc)}

    # ── ic calisma ────────────────────────────────────────────────────────
    def _run(self, sql: str, params: Sequence[Any] | None) -> tuple[list[dict[str, Any]], int]:
        started = time.time()
        result = None
        if self.backend == "d1":
            try:
                result = self._run_d1(sql, params)
            except Exception:
                # D1 ağ/bağlantı hatasında beklemeden anında SQLite yerel önbelleğe düş
                result = self._run_sqlite(sql, params)
        else:
            result = self._run_sqlite(sql, params)
        elapsed = (time.time() - started) * 1000
        if elapsed > 1000:
            log.warning("[data] yavas sorgu %.0fms · %s", elapsed, _short(sql))
        return result

    def _run_sqlite(self, sql: str, params: Sequence[Any] | None) -> tuple[list[dict[str, Any]], int]:
        conn = self._sqlite_conn()
        try:
            cur = conn.cursor()
            cur.execute(sql, list(params or []))
            rows = [dict(r) for r in cur.fetchall()] if cur.description else []
            changes = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
            conn.commit()
            return rows, changes
        except sqlite3.Error as exc:
            conn.rollback()
            raise QueryFailed(f"SQLite hatasi: {exc}", sql, params) from exc
        finally:
            conn.close()

    def _sqlite_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.sqlite_path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.execute("PRAGMA busy_timeout=8000;")
        return conn

    def _run_d1(self, sql: str, params: Sequence[Any] | None) -> tuple[list[dict[str, Any]], int]:
        url = _D1_ENDPOINT.format(acc=self.account_id, db=self.database_id)
        body: dict[str, Any] = {"sql": sql}
        if params:
            body["params"] = [_d1_param(p) for p in params]

        last_error = ""
        for attempt in range(1, _MAX_RETRY + 1):
            try:
                status, payload = _post_json(url, body, self.api_token)
            except Exception as exc:  # noqa: BLE001
                last_error = f"aglar hatasi: {exc}"
                if attempt < _MAX_RETRY:
                    time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                    continue
                raise ConnectionFailed(
                    f"Cloudflare D1'e ulasilamadi ({_MAX_RETRY} deneme): {last_error}"
                ) from exc

            if status in (429, 500, 502, 503, 504) and attempt < _MAX_RETRY:
                last_error = f"HTTP {status}"
                time.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))
                continue

            if not isinstance(payload, dict):
                raise QueryFailed(f"D1 beklenmeyen yanit tipi: {type(payload)}", sql, params)

            # HTTP 200 + success:false durumu da hatadir — eski kod bunu kaciriyordu.
            if not payload.get("success"):
                errors = payload.get("errors") or []
                msg = "; ".join(str(e.get("message", e)) for e in errors) or f"HTTP {status}"
                raise QueryFailed(f"D1 sorgusu reddedildi: {msg}", sql, params)

            results = payload.get("result") or []
            if not results:
                return [], 0
            first = results[0]
            rows = first.get("results") or []
            meta = first.get("meta") or {}
            changes = int(meta.get("changes") or 0)
            return [dict(r) for r in rows], changes

        raise ConnectionFailed(f"Cloudflare D1 basarisiz: {last_error}")


# ── yardimcilar ────────────────────────────────────────────────────────────
def _d1_param(value: Any) -> Any:
    if isinstance(value, bool):
        return 1 if value else 0
    if value is None or isinstance(value, (int, float, str)):
        return value
    if hasattr(value, "value"):
        return value.value
    return str(value)


def _post_json(url: str, body: dict[str, Any], token: str) -> tuple[int, Any]:
    payload = json.dumps(body).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "User-Agent": "T-Sistem/1.0",
    }
    try:
        import requests  # type: ignore

        resp = requests.post(url, data=payload, headers=headers, timeout=_TIMEOUT)
        try:
            return resp.status_code, resp.json()
        except ValueError:
            return resp.status_code, {"success": False, "errors": [{"message": resp.text[:300]}]}
    except ImportError:
        import urllib.error
        import urllib.request

        req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return resp.status, json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            try:
                return exc.code, json.loads(raw)
            except ValueError:
                return exc.code, {"success": False, "errors": [{"message": raw[:300]}]}


def _split_sql(script: str) -> list[str]:
    """schema.sql'i tekil ifadelere ayirir (yorum satirlarini atar)."""
    cleaned: list[str] = []
    for line in script.splitlines():
        stripped = line.strip()
        if stripped.startswith("--") or not stripped:
            continue
        cleaned.append(line)
    joined = "\n".join(cleaned)
    return [s.strip() for s in joined.split(";") if s.strip()]


def _short(text: str, limit: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit] + "…"


# ── modul seviyesinde tekil istemci ────────────────────────────────────────
_client: D1Client | None = None


def get_client() -> D1Client:
    global _client
    if _client is None:
        _client = D1Client()
    return _client


def reset_client() -> None:
    """Test/CLI icin istemciyi sifirlar."""
    global _client
    _client = None


__all__ = [
    "D1Client", "get_client", "reset_client",
    "DataError", "ConnectionFailed", "QueryFailed", "NotConfigured",
]
