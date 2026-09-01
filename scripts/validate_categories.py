"""Kategori uygunluğu doğruluğunu ölçer (MVP 4 doğrulaması).

NE YAPAR
--------
Klasör yapısı zaten "hangi rapor hangi yarışmadan" bilgisini taşıyor
(docs/raporvesablon/<yarışma>/raporlar/*.pdf). Yani ücretsiz etiketli veri.
Bu script her raporu işleyip "sistem doğru yarışmayı tahmin etti mi?" diye
ölçüyor ve karışıklık matrisi basıyor.

NEDEN ÖNEMLİ
------------
MVP 4 "kategori uygunluğu ve benzerlik analizi" maddesinin doğruluğunu
sayıyla gösteren tek yer bu. Hakeme "bu rapor yanlış kategoride" demek
iddialı bir çıkarım; önce kendi isabet oranımızı bilmemiz gerekiyor.

ENCODER UYARISI
---------------
Yedek (sözel) encoder ile koşarsa sonuç düşük çıkar — kategori eşleştirmesi
kavramsal bir iş, sözel benzerlik yetmez. Script encoder'ı başta bildiriyor.

KULLANIM
--------
    python scripts/validate_categories.py --dir docs/raporvesablon
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tsistem.analysis.category_fit import (  # noqa: E402
    CategoryRegistry,
    analyze_category_fit,
)
from tsistem.embedding.encoder import get_encoder  # noqa: E402
from tsistem.pipeline.chunker import chunk_document  # noqa: E402
from tsistem.pipeline.extractor import extract_pdf  # noqa: E402
from tsistem.pipeline.section_parser import build_sections, detect_headings  # noqa: E402
from tsistem.pipeline.templates import load_template  # noqa: E402

#: Klasör adı -> (kategori kimliği, o yarışmanın rapor şablonu)
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "docs" / "raporvesablon"))
    ap.add_argument("--competition", default="teknofest_2026")
    args = ap.parse_args()

    enc = get_encoder()
    print(f"Encoder    : {enc.name}")
    print(f"Semantik mi: {enc.is_semantic}")
    if not enc.is_semantic:
        print("\n⚠  Yedek (sözel) encoder devrede. Kategori eşleştirmesi kavramsal")
        print("   bir iş; sözel benzerlik düşük isabet verir. BGE-M3 ile tekrar koş.\n")

    reg = CategoryRegistry(args.competition)
    print(f"Kategori   : {len(reg.categories)}\n")

    base = Path(args.dir)
    rows: list[tuple[str, str, str, float, float]] = []
    confusion: dict[str, Counter] = defaultdict(Counter)

    for folder, (expected, template_id) in FOLDER_MAP.items():
        pdfs = sorted((base / folder / "raporlar").glob("*.pdf"))
        if not pdfs:
            continue
        template = load_template(template_id)
        for pdf in pdfs:
            result = extract_pdf(pdf, ocr_if_scanned=False)
            headings = detect_headings(result)
            sections, _ = build_sections(result, template, headings)
            chunks = chunk_document(
                result, sections,
                report_id=pdf.stem, competition_id=args.competition,
                category_id=expected,
            )
            if not chunks:
                print(f"  ! {pdf.name[:14]} chunk üretilemedi")
                continue
            vectors = enc.encode([c.embed_text or c.text for c in chunks])
            fit = analyze_category_fit(
                report_id=pdf.stem, chunks=chunks, vectors=vectors,
                registry=reg, encoder=enc, declared_category_id=expected,
            )
            rows.append((pdf.stem[:12], expected, fit.best_category_id or "-",
                         fit.declared_score, fit.best_score))
            confusion[expected][fit.best_category_id or "-"] += 1

    if not rows:
        print("Rapor bulunamadı. --dir yolunu kontrol et.")
        return 1

    print(f"{'RAPOR':<14}{'GERÇEK':<24}{'TAHMİN':<24}{'BEYAN':>7}{'EN İYİ':>8}  ")
    print("-" * 84)
    correct = 0
    for rid, exp, got, ds, bs in rows:
        ok = exp == got
        correct += ok
        print(f"{rid:<14}{exp:<24}{got:<24}{ds:>7.3f}{bs:>8.3f}  {'✓' if ok else '✗'}")

    total = len(rows)
    print(f"\nİSABET: {correct}/{total} = %{100 * correct / total:.0f}")

    print("\nKARIŞIKLIK (gerçek → tahmin)")
    print("-" * 60)
    for exp in sorted(confusion):
        items = ", ".join(f"{k}×{v}" for k, v in confusion[exp].most_common())
        n = sum(confusion[exp].values())
        hit = confusion[exp][exp]
        print(f"  {exp:<24} {hit}/{n}   {items}")

    print("\nNot: Bu ölçüm klasör adlarını gerçek etiket kabul ediyor.")
    print("Karıştırılan kategori çiftleri, kategori profil metinlerini")
    print("(data/categories/*.json) iyileştirmek için ilk bakılacak yer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
