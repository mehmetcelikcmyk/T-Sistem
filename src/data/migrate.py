"""T-Sistem · Sema uygulama ve dogrulama araci.

Onceki kod tabaninda D1 icin hicbir migration yolu yoktu; tablolar yalnizca
kazara (uygulama acilisinda gonderilen kirpilmis CREATE ifadeleriyle)
olusuyordu. Bu modul semayi tek kaynaktan hem D1'e hem yerel SQLite'a uygular
ve iki tarafin ayni oldugunu dogrular.

KULLANIM
--------
    python -m src.data.migrate --apply  --target sqlite
    python -m src.data.migrate --apply  --target d1
    python -m src.data.migrate --apply  --target both
    python -m src.data.migrate --verify --target both
    python -m src.data.migrate --seed
    python -m src.data.migrate --health
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .client import D1Client, DataError, NotConfigured
from .models import now_iso
from .r2 import get_r2

SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

EXPECTED_TABLES = [
    "applications",
    "audit_log",
    "auth_users",
    "calibration_settings",
    "competition_requirements",
    "competition_specs",
    "competition_stages",
    "competitions",
    "evaluation_scores",
    "evaluations",
    "notifications",
    "report_assignments",
    "report_cards",
    "report_embedding_vectors",
    "report_embeddings",
    "reports",
    "similarity_results",
    "stage_rubric_criteria",
    "team_members",
    "teams",
]

DEFAULT_CALIBRATION = [
    ("similarity_high_threshold", 0.70, "Yuksek intihal riski esigi (birlesik skor)"),
    ("similarity_medium_threshold", 0.40, "Orta intihal riski esigi"),
    ("semantic_high_threshold", 0.82, "Anlamsal benzerlik yuksek risk esigi"),
    ("literal_high_threshold", 0.35, "Birebir kopya yuksek risk esigi"),
    ("ai_score_offset", 0.0, "AI puanina uygulanan sabit kaydirma"),
    ("ai_score_slope", 1.0, "AI puanina uygulanan carpan"),
    ("referee_ai_warning_delta", 15.0, "Hakem-AI puan farki uyari esigi"),
    ("feedback_min_score_for_positive", 70.0, "Olumlu geri bildirim alt siniri"),
    ("accept_threshold", 75.0, "KABUL karari alt siniri"),
    ("revision_threshold", 60.0, "REVIZYON karari alt siniri"),
]


def load_schema() -> str:
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"Sema dosyasi bulunamadi: {SCHEMA_PATH}")
    return SCHEMA_PATH.read_text(encoding="utf-8")


def _client_for(target: str) -> D1Client:
    if target == "sqlite":
        return D1Client(backend="sqlite")
    return D1Client(backend="d1")


def apply_schema(target: str) -> dict[str, int]:
    """Semayi hedefe uygular. Tum ifadeler IF NOT EXISTS oldugu icin idempotenttir."""
    script = load_schema()
    results: dict[str, int] = {}
    for tgt in _targets(target):
        client = _client_for(tgt)
        count = client.execute_script(script)
        results[tgt] = count
        print(f"  [{tgt}] {count} ifade uygulandi · {len(client.table_names())} tablo mevcut")
    return results


def verify_schema(target: str) -> bool:
    """Beklenen tum tablolar var mi ve iki hedef ayni mi?"""
    ok = True
    snapshots: dict[str, dict[str, list[str]]] = {}

    for tgt in _targets(target):
        client = _client_for(tgt)
        tables = client.table_names()
        missing = [t for t in EXPECTED_TABLES if t not in tables]
        extra = [t for t in tables if t not in EXPECTED_TABLES]

        print(f"\n  [{tgt}] {len(tables)} tablo")
        if missing:
            ok = False
            print(f"    EKSIK ({len(missing)}): {', '.join(missing)}")
        if extra:
            print(f"    FAZLA/ESKI ({len(extra)}): {', '.join(extra)}")
        if not missing and not extra:
            print("    Tablo listesi beklenen ile birebir ayni.")

        snapshots[tgt] = {t: client.column_names(t) for t in tables if t in EXPECTED_TABLES}

    if len(snapshots) == 2:
        left, right = list(snapshots.keys())
        print(f"\n  Karsilastirma: {left} <-> {right}")
        diffs = 0
        for table in EXPECTED_TABLES:
            lcols = set(snapshots[left].get(table, []))
            rcols = set(snapshots[right].get(table, []))
            if lcols != rcols:
                diffs += 1
                ok = False
                only_l = sorted(lcols - rcols)
                only_r = sorted(rcols - lcols)
                print(f"    {table}: sadece {left}={only_l} · sadece {right}={only_r}")
        if diffs == 0:
            print("    Tum tablolarin kolonlari birebir ayni.")

    return ok


def seed_calibration(target: str) -> int:
    inserted = 0
    for tgt in _targets(target):
        client = _client_for(tgt)
        for key, value, desc in DEFAULT_CALIBRATION:
            existing = client.query(
                "SELECT key FROM calibration_settings WHERE key = ?;", [key]
            )
            if existing:
                continue
            client.execute(
                "INSERT INTO calibration_settings (key, value, description, updated_at) "
                "VALUES (?, ?, ?, ?);",
                [key, value, desc, now_iso()],
            )
            inserted += 1
        print(f"  [{tgt}] {inserted} kalibrasyon ayari eklendi")
    return inserted


def healthcheck(target: str) -> bool:
    ok = True
    for tgt in _targets(target):
        try:
            info = _client_for(tgt).healthcheck()
        except NotConfigured as exc:
            print(f"  [{tgt}] YAPILANDIRILMAMIS: {exc}")
            ok = False
            continue
        state = "OK " if info.get("ok") else "HATA"
        print(f"  [{tgt}] {state} · {info}")
        ok = ok and bool(info.get("ok"))

    r2_info = get_r2().healthcheck()
    print(f"  [r2]     {'OK ' if r2_info.get('ok') else 'HATA'} · {r2_info}")
    return ok and bool(r2_info.get("ok"))


# ═══════════════════════════════════════════════════════════════════════════
# ESKI TABLOLARI YENI SEMAYA YUKSELTME
# ═══════════════════════════════════════════════════════════════════════════
# `CREATE TABLE IF NOT EXISTS` var olan bir tabloyu DEGISTIRMEZ. Onceki
# surumde olusmus tablolar (or. `surname` kolonu olmayan `auth_users`,
# 7 kolonluk kirpilmis `reports`, eski semali `competition_rubrics`) bu yuzden
# oldugu gibi kalir ve yeni kod INSERT ederken "no such column" hatasi alir.
#
# Bu bolum iki strateji uygular:
#   1. Eksik kolonlarin HEPSI nullable ise -> ALTER TABLE ADD COLUMN (veri korunur)
#   2. Eksik kolonlar arasinda NOT NULL varsa -> eski tablo `<ad>_eski_<tarih>`
#      olarak yeniden adlandirilir, yeni tablo temiz olusturulur (veri kaybolmaz,
#      elle incelenebilir)

_RENAMEABLE = {"reports", "competition_rubrics", "users", "categories"}


def _parse_schema_columns() -> dict[str, list[tuple[str, str]]]:
    """schema.sql'den {tablo: [(kolon, tanim), ...]} cikarir."""
    import re

    text = load_schema()
    out: dict[str, list[tuple[str, str]]] = {}
    for match in re.finditer(
        r"CREATE TABLE IF NOT EXISTS\s+(\w+)\s*\((.*?)\n\);", text, re.DOTALL
    ):
        table, body = match.group(1), match.group(2)
        columns: list[tuple[str, str]] = []
        buffer: list[str] = []
        depth = 0
        for raw_line in body.split("\n"):
            line = raw_line.split("--")[0].rstrip()
            if not line.strip():
                continue
            buffer.append(line.strip())
            depth += line.count("(") - line.count(")")
            if depth <= 0 and line.rstrip().endswith(","):
                definition = " ".join(buffer).rstrip(",").strip()
                buffer = []
                head = definition.split()[0].upper()
                if head in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}:
                    continue
                columns.append((definition.split()[0], definition))
        if buffer:
            definition = " ".join(buffer).rstrip(",").strip()
            head = definition.split()[0].upper()
            if head not in {"PRIMARY", "FOREIGN", "UNIQUE", "CHECK", "CONSTRAINT"}:
                columns.append((definition.split()[0], definition))
        out[table] = columns
    return out


def _addable(definition: str) -> bool:
    """Bu kolon var olan tabloya ALTER ile eklenebilir mi?"""
    upper = definition.upper()
    if "PRIMARY KEY" in upper:
        return False
    if "NOT NULL" in upper and "DEFAULT" not in upper:
        return False
    return True


def upgrade_legacy(target: str, *, dry_run: bool = True) -> dict[str, list[str]]:
    """Var olan eski tablolari yeni semaya tasir."""
    from datetime import datetime, timezone

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    schema = _parse_schema_columns()
    actions: dict[str, list[str]] = {}

    for tgt in _targets(target):
        client = _client_for(tgt)
        existing = set(client.table_names())
        steps: list[str] = []

        for table, columns in schema.items():
            if table not in existing:
                steps.append(f"CREATE  {table} (yeni tablo, --apply ile olusur)")
                continue

            current = set(client.column_names(table))
            missing = [(name, definition) for name, definition in columns
                       if name not in current]
            if not missing:
                continue

            blockers = [name for name, definition in missing if not _addable(definition)]
            if blockers and table in _RENAMEABLE:
                legacy_name = f"{table}_eski_{stamp}"
                steps.append(
                    f"RENAME  {table} -> {legacy_name} (eksik NOT NULL kolon: "
                    f"{', '.join(blockers)}); ardindan temiz tablo olusturulur"
                )
                if not dry_run:
                    client.execute(f"ALTER TABLE {table} RENAME TO {legacy_name};")
                continue
            if blockers:
                steps.append(
                    f"UYARI   {table}: {', '.join(blockers)} kolonlari ALTER ile "
                    f"eklenemez ve bu tablo yeniden adlandirilamaz. Elle mudahale gerekli."
                )
                continue

            for name, definition in missing:
                steps.append(f"ADD     {table}.{name}")
                if not dry_run:
                    client.execute(f"ALTER TABLE {table} ADD COLUMN {definition};")

        # Artik kullanilmayan eski tablolar
        for obsolete in ("users", "categories", "category_requirements",
                         "report_template_requirements", "competition_rubrics",
                         "competition_rubrics_old"):
            if obsolete in existing and obsolete not in schema:
                steps.append(f"ESKI    {obsolete} (artik kullanilmiyor, silinmedi)")

        actions[tgt] = steps
        label = "ON IZLEME" if dry_run else "UYGULANDI"
        print(f"\n  [{tgt}] {label} · {len(steps)} islem")
        for step in steps:
            print(f"    {step}")
        if not steps:
            print("    Tablolar zaten guncel.")

    return actions


def _targets(target: str) -> list[str]:
    if target == "both":
        return ["sqlite", "d1"]
    return [target]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T-Sistem sema araci")
    parser.add_argument("--apply", action="store_true", help="Semayi uygula")
    parser.add_argument("--verify", action="store_true", help="Semayi dogrula")
    parser.add_argument("--seed", action="store_true", help="Kalibrasyon varsayilanlarini ekle")
    parser.add_argument("--health", action="store_true", help="D1 ve R2 baglanti testi")
    parser.add_argument("--upgrade", action="store_true",
                        help="Var olan ESKI tablolari yeni semaya tasi (once on izleme)")
    parser.add_argument(
        "--target", choices=["sqlite", "d1", "both"], default="both", help="Hedef backend"
    )
    args = parser.parse_args(argv)

    if not any([args.apply, args.verify, args.seed, args.health, args.upgrade]):
        parser.print_help()
        return 1

    try:
        if args.health:
            print("\nSAGLIK KONTROLU")
            if not healthcheck(args.target):
                return 2

        if args.upgrade:
            print("\nESKI TABLOLARI YUKSELTME")
            if args.apply:
                upgrade_legacy(args.target, dry_run=False)
            else:
                upgrade_legacy(args.target, dry_run=True)
                print("\n  Bu bir ON IZLEME. Uygulamak icin: --upgrade --apply")

        if args.apply:
            print("\nSEMA UYGULANIYOR")
            apply_schema(args.target)

        if args.seed:
            print("\nKALIBRASYON SEED")
            seed_calibration(args.target)

        if args.verify:
            print("\nSEMA DOGRULAMA")
            if not verify_schema(args.target):
                print("\nSONUC: SEMA UYUSMAZLIGI VAR")
                return 3
            print("\nSONUC: SEMA TUTARLI")

    except DataError as exc:
        print(f"\nVERI KATMANI HATASI: {exc}", file=sys.stderr)
        return 4
    except Exception as exc:  # noqa: BLE001
        print(f"\nBEKLENMEYEN HATA: {exc}", file=sys.stderr)
        return 5

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
