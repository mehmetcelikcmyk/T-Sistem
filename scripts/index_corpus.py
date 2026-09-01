"""Gerçek rapor havuzunu işler, indeksler ve bölüm uzunluk istatistiği çıkarır.

Klasör yapısı etiket taşıyor:
    <kök>/<yarışma>/raporlar/*.pdf|*.docx
Her yarışma kendi rapor şablonuyla eşleştirilir (FOLDER_MAP).

İki iş yapıyor:
  1. Tüm raporları Qdrant'a indeksler → benzerlik analizi ve kalibrasyonun temeli
  2. Her bölüm için gerçek kelime sayısı dağılımını çıkarır → min_words
     eşiklerini tahminden ölçüme çevirmek için (--calibrate-words)

KULLANIM
--------
    python scripts/index_corpus.py --dir docs/raporvesablon
    python scripts/index_corpus.py --dir docs/raporvesablon --calibrate-words
    python scripts/index_corpus.py --dir docs/raporvesablon --qdrant http://localhost:6333
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tsistem.embedding.encoder import get_encoder  # noqa: E402
from tsistem.service import ReportPipeline  # noqa: E402
from tsistem.vectorstore.qdrant_store import QdrantStore  # noqa: E402

#: Klasör -> (kategori kimliği, rapor şablonu)
FOLDER_MAP: dict[str, tuple[str, str]] = {
    "havacilikta-yapay-zeka": ("havacilikta_yapay_zeka", "havacilik_yz_otr_2026"),
    "insansiz-su-alti-sistemleri": ("insansiz_su_alti", "su_alti_ktr_2026"),
    "jet-motor-tasarim": ("jet_motor_tasarim", "jet_motor_dtr_2026"),
    "robotaksi-binek-otonom-arac": ("robotaksi_otonom_arac", "robotaksi_ozgun_ktr_2026"),
    "roket": ("roket", "roket_a1_ahr_2026"),
    "saglikta-yapay-zeka": ("saglikta_yapay_zeka", "saglik_yz_pdr_2026"),
    "sanayide-robotik-uygulamalar": ("sanayide_robotik", "sanayi_robotik_pdr_2026"),
    "savasan-iha": ("savasan_iha", "savasan_iha_ktr_2026"),
}

COMPETITION = "teknofest_2026"
ICON = {"ok": "🟢", "info": "🔵", "warn": "🟡", "error": "🔴"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "docs" / "raporvesablon"))
    ap.add_argument("--qdrant", default=":memory:")
    ap.add_argument("--calibrate-words", action="store_true",
                    help="Bölüm uzunluk dağılımını çıkar ve min_words önerisi yaz")
    ap.add_argument("--out", default=str(ROOT / "data" / "out" / "corpus_analiz.json"))
    args = ap.parse_args()

    enc = get_encoder()
    print(f"Encoder : {enc.name}  (semantik={enc.is_semantic})")
    if not enc.is_semantic:
        print("⚠  Yedek encoder — benzerlik sonuçları sözel düzeyde kalır.\n")

    store = QdrantStore(url=args.qdrant, dim=enc.dim)
    store.ensure_collection(recreate=True)
    pipeline = ReportPipeline(store=store, encoder=enc)

    base = Path(args.dir)
    # 1. TUR — hepsini indeksle (benzerlik için havuz kurulmalı)
    print("1. tur: indeksleme")
    indexed: list[tuple[str, str, str, Path]] = []
    for folder, (category, template_id) in FOLDER_MAP.items():
        files = sorted(
            f for f in (base / folder / "raporlar").glob("*")
            if f.suffix.lower() in (".pdf", ".docx", ".docm")
        )
        for f in files:
            report_id = f"{folder[:10]}-{f.stem[:8]}"
            try:
                pipeline.ingest(
                    f, report_id=report_id, competition_id=COMPETITION,
                    template_id=template_id, category_id=category,
                    team_id=f.stem[:8], run_similarity=False,
                    run_category_fit=False, index=True,
                )
                indexed.append((report_id, category, template_id, f))
                print(f"  ✓ {report_id}")
            except Exception as exc:
                print(f"  ✗ {report_id}: {type(exc).__name__}: {exc}")

    print(f"\n{len(indexed)} rapor indekslendi · {store.count()} chunk")

    # 2. TUR — tam analiz (artık her rapor diğerlerini görebiliyor)
    print("\n2. tur: analiz")
    analyses = []
    word_stats: dict[tuple[str, str], list[int]] = defaultdict(list)
    for report_id, category, template_id, f in indexed:
        try:
            a = pipeline.ingest(
                f, report_id=report_id, competition_id=COMPETITION,
                template_id=template_id, category_id=category,
                team_id=f.stem[:8], run_similarity=True,
                run_category_fit=True, index=True,
            )
        except Exception as exc:
            print(f"  ✗ {report_id}: {exc}")
            continue
        analyses.append(a)
        if a.template:
            for fi in a.template.findings:
                if fi.found and fi.word_count > 0:
                    word_stats[(template_id, fi.key)].append(fi.word_count)

    # ---- Özet tablo ----
    print("\n" + "=" * 104)
    print(f"{'RAPOR':<22}{'D':<3}{'DİL':<5}{'UYUM':>6}{'RİSK':>6}  "
          f"{'KATEGORİ TAHMİNİ':<24}{'EN YAKIN RAPOR'}")
    print("=" * 104)
    for a in sorted(analyses, key=lambda x: x.report_id):
        t, cat, sim = a.template, a.category_fit, a.similarity
        catxt = "-"
        if cat:
            mark = "✓" if cat.best_category_id == a.category_id else "✗"
            catxt = f"{mark} {(cat.best_category_id or '-')[:20]}"
        simtxt = "temiz"
        if sim and sim.matches:
            m = sim.matches[0]
            simtxt = f"{m.report_id[:18]} {m.aggregate_score:.2f} %{m.coverage*100:.0f}"
        print(f"{a.report_id:<22}{ICON[a.overall_severity.value]:<2} "
              f"{a.language.value:<5}{(t.compliance_score if t else 0):>5.0f}%"
              f"{(t.points_at_risk if t else 0):>6.1f}  {catxt:<24}{simtxt}")

    # ---- Kategori isabeti ----
    hits = sum(1 for a in analyses
               if a.category_fit and a.category_fit.best_category_id == a.category_id)
    if analyses:
        print(f"\nKategori isabeti: {hits}/{len(analyses)} "
              f"(%{100*hits/len(analyses):.0f})")

    # ---- Bölüm uzunluk kalibrasyonu ----
    if args.calibrate_words and word_stats:
        print("\n" + "=" * 88)
        print("BÖLÜM UZUNLUK DAĞILIMI  (gerçek raporlardan · min_words önerisi)")
        print("=" * 88)
        print(f"{'ŞABLON':<24}{'BÖLÜM':<28}{'N':>3}{'MİN':>6}{'ORT':>6}"
              f"{'MED':>6}{'ÖNERİ':>7}")
        print("-" * 88)
        suggestions: dict[str, dict[str, int]] = defaultdict(dict)
        for (tid, key), vals in sorted(word_stats.items()):
            if len(vals) < 2:
                continue
            vals.sort()
            # Öneri: 25. yüzdelik — "normal" bir raporun altına düşmeyeceği sınır.
            # Ortalama alsak yarı raporu "zayıf" işaretlerdik; minimum alsak
            # hiçbir raporu yakalamazdık.
            idx = max(int(len(vals) * 0.25) - 1, 0)
            sug = int(vals[idx] * 0.8 / 10) * 10 or 10
            suggestions[tid][key] = sug
            print(f"{tid[:23]:<24}{key[:27]:<28}{len(vals):>3}{min(vals):>6}"
                  f"{int(statistics.mean(vals)):>6}{int(statistics.median(vals)):>6}"
                  f"{sug:>7}")

        out = ROOT / "data" / "out" / "min_words_onerileri.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "_not": (
                "Öneriler gerçek rapor bölüm uzunluklarının 25. yüzdeliğinin "
                "%80'i (10'a yuvarlanmış). scripts/apply_min_words.py ile "
                "şablonlara uygulanabilir. N<2 olan bölümler atlandı."
            ),
            "suggestions": suggestions,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n✓ {out}")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps([json.loads(a.model_dump_json()) for a in analyses],
                   ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✓ {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
