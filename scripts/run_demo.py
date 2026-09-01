"""Uçtan uca demo: data/raw altındaki tüm raporları işler ve özet tablo basar.

Kullanım:
    PYTHONPATH=src python scripts/run_demo.py                # gömülü Qdrant
    PYTHONPATH=src python scripts/run_demo.py --qdrant http://localhost:6333
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from tsistem.embedding.encoder import get_encoder  # noqa: E402
from tsistem.service import ReportPipeline  # noqa: E402
from tsistem.vectorstore.qdrant_store import QdrantStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

COMPETITION = "sentetik_test"
TEMPLATE = "teknofest_pdr_2026"

MANIFEST = {
    "saglik_ai_tam.pdf": {
        "report_id": "RPR-001", "team_id": "TKM-A",
        "category_id": "saglikta_yapay_zeka",
    },
    "nlp_chatbot_tam.pdf": {
        "report_id": "RPR-002", "team_id": "TKM-B",
        "category_id": "dogal_dil_isleme",
    },
    "saglik_ai_kopya.pdf": {
        "report_id": "RPR-003", "team_id": "TKM-C",
        "category_id": "saglikta_yapay_zeka",
    },
    "eksik_basliklar.pdf": {
        "report_id": "RPR-004", "team_id": "TKM-D",
        "category_id": "dogal_dil_isleme",
    },
    "yanlis_kategori.pdf": {
        "report_id": "RPR-005", "team_id": "TKM-E",
        "category_id": "saglikta_yapay_zeka",  # BEYAN sağlık, İÇERİK tarım
    },
    "ingilizce_rapor.pdf": {
        "report_id": "RPR-006", "team_id": "TKM-F",
        "category_id": "insansiz_hava_araclari",
    },
}

ICON = {"ok": "🟢", "info": "🔵", "warn": "🟡", "error": "🔴"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--qdrant", default=":memory:",
                    help="Qdrant URL ya da ':memory:' (gömülü mod)")
    ap.add_argument("--fallback-encoder", action="store_true",
                    help="BGE-M3 yerine yedek encoder'ı zorla")
    ap.add_argument("--out", default=str(ROOT / "data" / "out" / "analiz_sonuclari.json"))
    args = ap.parse_args()

    encoder = get_encoder(force_fallback=args.fallback_encoder)
    print(f"Encoder : {encoder.name} (dim={encoder.dim})")
    print(f"Qdrant  : {args.qdrant}\n")

    store = QdrantStore(url=args.qdrant, dim=encoder.dim)
    store.ensure_collection(recreate=True)
    pipeline = ReportPipeline(store=store, encoder=encoder)

    analyses = pipeline.reindex_competition(
        ROOT / "data" / "raw",
        competition_id=COMPETITION,
        template_id=TEMPLATE,
        manifest=MANIFEST,
    )

    print("=" * 100)
    print(f"{'RAPOR':<9} {'DURUM':<6} {'DİL':<5} {'ŞABLON':<8} {'BÖLÜM':<7} "
          f"{'KATEGORİ UYUM':<15} {'BENZERLİK'}")
    print("=" * 100)

    for a in analyses:
        t = a.template
        sim = a.similarity
        cat = a.category_fit
        lang = f"{a.language.value}{'✓' if t and t.language_ok else '✗'}"
        found = sum(1 for f in t.findings if f.found) if t else 0
        total = len(t.findings) if t else 0
        cat_txt = (
            f"{cat.declared_score:.2f}{'⚠' if cat.is_mismatch else ' '}"
            if cat else "-"
        )
        sim_txt = (
            f"{sim.matches[0].report_id} {sim.matches[0].aggregate_score:.2f} "
            f"(%{sim.matches[0].coverage * 100:.0f})"
            if sim and sim.matches else "temiz"
        )
        print(
            f"{a.report_id:<9} {ICON[a.overall_severity.value]:<5} {lang:<5} "
            f"{(t.compliance_score if t else 0):>5.0f}%   {found}/{total:<5} "
            f"{cat_txt:<15} {sim_txt}"
        )

    print("=" * 100)

    # Detaylı bulgular
    for a in analyses:
        lines: list[str] = []
        if a.template and a.template.severity.value != "ok":
            lines.append(f"  ŞABLON : {a.template.summary}")
        if a.category_fit and a.category_fit.severity.value in ("warn", "error"):
            lines.append(f"  KATEGORİ: {a.category_fit.message}")
        if a.similarity and a.similarity.matches:
            lines.append(f"  BENZERLİK: {a.similarity.summary}")
            top = a.similarity.matches[0]
            if top.passages:
                p = top.passages[0]
                lines.append(
                    f"    ↳ kanıt (skor {p.score:.2f}) "
                    f"[bu rapor s.{p.source_page} · {p.source_section}]"
                )
                lines.append(f"      « {p.source_excerpt[:150]}… »")
                lines.append(
                    f"    ↳ eşleşen  [{top.report_id} s.{p.target_page} · "
                    f"{p.target_section}]"
                )
                lines.append(f"      « {p.target_excerpt[:150]}… »")
        for w in a.warnings:
            lines.append(f"  UYARI  : {w}")
        if lines:
            print(f"\n▸ {a.report_id} ({a.document.file_name})")
            print("\n".join(lines))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([json.loads(a.model_dump_json()) for a in analyses],
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nJSON çıktı: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
