"""Benzerlik eşiği kalibrasyonu.

NE YAPAR
--------
Elindeki raporların HEPSİNİ birbiriyle karşılaştırıp skor dağılımını çıkarır,
sonra `data/labels/similarity_labels.json` içindeki "bu ikisi gerçekten kopya"
etiketlerini kullanarak en iyi eşik ikilisini önerir.

NEDEN İKİ EŞİK
--------------
  flag (kırmızı) : "bu rapor incelenmeli" — bir takımı kopyayla suçlamak ağır,
                   burada YANLIŞ ALARM istemiyoruz. Yüksek kesinlik.
  warn (sarı)    : "göz atılsın" — burada kaçırmak istemiyoruz. Yüksek duyarlılık.

TEMEL FİKİR
-----------
Gerçek kopya çiftlerinin skorları bir aralıkta, bağımsız çiftlerin skorları
başka bir aralıkta toplanır. İki aralığın arasındaki boşluk = eşiğin yeri.
Boşluk genişse model işini yapıyor; boşluk yoksa/örtüşüyorsa ya model zayıf
ya da etiketler hatalı.

KULLANIM
--------
    python scripts/calibrate.py                      # gömülü Qdrant
    python scripts/calibrate.py --qdrant http://localhost:6333
    python scripts/calibrate.py --write-env          # önerileri .env'e yaz
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tsistem.analysis.similarity import decide_severity  # noqa: E402
from tsistem.embedding.encoder import get_encoder  # noqa: E402
from tsistem.models import Severity  # noqa: E402
from tsistem.pipeline.chunker import chunk_document  # noqa: E402
from tsistem.pipeline.extractor import extract_pdf  # noqa: E402
from tsistem.pipeline.section_parser import (  # noqa: E402
    build_sections,
    detect_headings,
)
from tsistem.pipeline.templates import load_template  # noqa: E402
from tsistem.pipeline.extractor import extract_document  # noqa: E402

#: Gerçek korpus: klasör -> (kategori, şablon). Kopya merdiveni ayrı klasörde.
CORPUS_MAP: dict[str, tuple[str, str]] = {
    "havacilikta-yapay-zeka": ("havacilikta_yapay_zeka", "havacilik_yz_otr_2026"),
    "insansiz-su-alti-sistemleri": ("insansiz_su_alti", "su_alti_ktr_2026"),
    "jet-motor-tasarim": ("jet_motor_tasarim", "jet_motor_dtr_2026"),
    "robotaksi-binek-otonom-arac": ("robotaksi_otonom_arac", "robotaksi_ozgun_ktr_2026"),
    "roket": ("roket", "roket_a1_ahr_2026"),
    "saglikta-yapay-zeka": ("saglikta_yapay_zeka", "saglik_yz_pdr_2026"),
    "sanayide-robotik-uygulamalar": ("sanayide_robotik", "sanayi_robotik_pdr_2026"),
    "savasan-iha": ("savasan_iha", "savasan_iha_ktr_2026"),
}


def load_corpus(
    corpus_dir: Path, copy_dir: Path | None
) -> dict[str, np.ndarray]:
    """Gerçek korpus + üretilen kopyaları vektörleştirir.

    report_id üretimi index_corpus.py ve make_copy_ladder.py ile AYNI olmak
    zorunda; etiket dosyasındaki kimlikler buna göre yazıldı.
    """
    encoder = get_encoder()
    out: dict[str, np.ndarray] = {}

    def add(path: Path, report_id: str, template_id: str) -> None:
        try:
            result = extract_document(path, ocr_if_scanned=False)
            headings = detect_headings(result)
            sections, _ = build_sections(result, load_template(template_id), headings)
            chunks = chunk_document(result, sections, report_id=report_id,
                                    competition_id="calib")
            if not chunks:
                return
            out[report_id] = encoder.encode([c.embed_text or c.text for c in chunks])
            print(f"  ✓ {report_id:<24} {len(chunks):>3} chunk")
        except Exception as exc:
            print(f"  ✗ {report_id}: {type(exc).__name__}: {exc}")

    for folder, (_cat, template_id) in CORPUS_MAP.items():
        for f in sorted((corpus_dir / folder / "raporlar").glob("*")):
            if f.suffix.lower() not in (".pdf", ".docx", ".docm"):
                continue
            add(f, f"{folder[:10]}-{f.stem[:8]}", template_id)

    if copy_dir and copy_dir.exists():
        for f in sorted(copy_dir.glob("*.pdf")):
            # Kopyalar kaynak şablonundan bağımsız; genel şablonla bölümlenir
            add(f, f.stem, "teknofest_pdr_2026")
    return out


DEFAULT_MANIFEST = {
    "saglik_ai_tam.pdf": {"report_id": "RPR-001", "category_id": "saglikta_yapay_zeka"},
    "nlp_chatbot_tam.pdf": {"report_id": "RPR-002", "category_id": "dogal_dil_isleme"},
    "saglik_ai_kopya.pdf": {"report_id": "RPR-003", "category_id": "saglikta_yapay_zeka"},
    "eksik_basliklar.pdf": {"report_id": "RPR-004", "category_id": "siber_guvenlik"},
    "yanlis_kategori.pdf": {"report_id": "RPR-005", "category_id": "saglikta_yapay_zeka"},
    "ingilizce_rapor.pdf": {"report_id": "RPR-006",
                            "category_id": "insansiz_hava_araclari"},
}


# --------------------------------------------------------------------------- #
#  1) Vektörleri hazırla
# --------------------------------------------------------------------------- #
def load_reports(pdf_dir: Path, template_id: str, manifest: dict) -> dict[str, np.ndarray]:
    """Her rapor için (chunk_sayısı, dim) vektör matrisi döner."""
    encoder = get_encoder()
    template = load_template(template_id)
    out: dict[str, np.ndarray] = {}

    for pdf in sorted(pdf_dir.glob("*.pdf")):
        info = manifest.get(pdf.name, {})
        rid = info.get("report_id", pdf.stem)
        result = extract_pdf(pdf, ocr_if_scanned=False)
        headings = detect_headings(result)
        sections, _ = build_sections(result, template, headings)
        chunks = chunk_document(
            result, sections,
            report_id=rid, competition_id="calib",
            category_id=info.get("category_id"),
        )
        if not chunks:
            print(f"  ! {pdf.name}: chunk üretilemedi, atlanıyor")
            continue
        vecs = encoder.encode([c.embed_text or c.text for c in chunks])
        out[rid] = vecs
        print(f"  ✓ {rid:<10} {pdf.name:<28} {len(chunks):>3} chunk")
    return out


# --------------------------------------------------------------------------- #
#  2) Çift bazında chunk-en-iyi-skor vektörü
# --------------------------------------------------------------------------- #
def pair_best_scores(va: np.ndarray, vb: np.ndarray) -> np.ndarray:
    """A'nın her chunk'ı için B'deki en yakın chunk skoru (nA,).

    Vektörler L2-normalize olduğu için iç çarpım = kosinüs benzerliği.
    """
    return (va @ vb.T).max(axis=1)


def metrics_at(best: np.ndarray, flag: float, warn: float) -> tuple[float, float, int, Severity]:
    """Verilen eşiklerde (aggregate, coverage, matched, severity) döner."""
    matched_mask = best >= warn
    matched = int(matched_mask.sum())
    if matched == 0:
        return 0.0, 0.0, 0, Severity.OK
    aggregate = float(best[matched_mask].mean())
    coverage = matched / len(best)
    sev = decide_severity(aggregate, coverage, matched, flag=flag, warn=warn)
    return aggregate, coverage, matched, sev


# --------------------------------------------------------------------------- #
#  3) Ana akış
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default=str(ROOT / "data" / "raw"))
    ap.add_argument("--corpus", help="Gerçek korpus klasörü (docs/raporvesablon)")
    ap.add_argument("--copies", default=str(ROOT / "data" / "raw_kopya"),
                    help="Kopya merdiveni klasörü")
    ap.add_argument("--labels", default=str(ROOT / "data" / "labels" / "similarity_labels.json"))
    ap.add_argument("--template", default="teknofest_pdr_2026")
    ap.add_argument("--write-env", action="store_true",
                    help="Önerilen eşikleri .env dosyasına yaz")
    args = ap.parse_args()

    enc = get_encoder()
    print(f"Encoder: {enc.name} (semantik={enc.is_semantic})")
    if not enc.is_semantic:
        print("\n⚠  UYARI: Yedek (sözel) encoder devrede. Kalibrasyon sonuçları")
        print("   GERÇEK DEĞİL — parafraz kopyalar yakalanmadığı için eşikler yanlış")
        print("   çıkar. Önce BGE-M3'ü kur, sonra bu scripti tekrar çalıştır.\n")

    print("\nRaporlar işleniyor...")
    if args.corpus:
        vectors = load_corpus(Path(args.corpus), Path(args.copies))
    else:
        vectors = load_reports(Path(args.pdf_dir), args.template, DEFAULT_MANIFEST)
    if len(vectors) < 2:
        print("En az 2 rapor gerekli.")
        return 1

    labels_raw = json.loads(Path(args.labels).read_text(encoding="utf-8"))
    label_map: dict[frozenset[str], bool] = {
        frozenset({p["report_a"], p["report_b"]}): bool(p["is_copy"])
        for p in labels_raw.get("pairs", [])
    }
    level_map: dict[frozenset[str], str] = {
        frozenset({p["report_a"], p["report_b"]}): p.get("seviye", "-")
        for p in labels_raw.get("pairs", [])
    }

    # ---- Tüm çiftler için ham skorlar ----
    rids = sorted(vectors)
    rows = []
    for i, a in enumerate(rids):
        for b in rids[i + 1:]:
            # Her iki yön: hangisi daha yüksekse üretimde o işaretlenir
            best_ab = pair_best_scores(vectors[a], vectors[b])
            best_ba = pair_best_scores(vectors[b], vectors[a])
            best = best_ab if best_ab.mean() >= best_ba.mean() else best_ba
            key = frozenset({a, b})
            rows.append({
                "a": a, "b": b, "best": best,
                "peak": float(best.max()),
                "mean": float(best.mean()),
                "is_copy": label_map.get(key),   # None = etiketsiz
                "seviye": level_map.get(key, "-"),
            })

    # ---- Skor dağılımı: en öğretici çıktı ----
    print("\n" + "=" * 78)
    print("SKOR DAĞILIMI  (peak = en benzer tek parça, mean = genel yakınlık)")
    print("=" * 78)
    print(f"{'ÇİFT':<50} {'peak':>7} {'mean':>7} {'SEV':>5}  ETİKET")
    print("-" * 88)
    labeled = [r for r in rows if r["is_copy"] is not None]
    unlabeled = [r for r in rows if r["is_copy"] is None]
    for r in sorted(labeled, key=lambda x: -x["peak"]):
        etiket = {True: "KOPYA", False: "bağımsız"}[r["is_copy"]]
        pair = f"{r['a'][:23]} ↔ {r['b'][:22]}"
        print(f"{pair:<50} {r['peak']:>7.4f} {r['mean']:>7.4f} "
              f"{r['seviye']:>5}  {etiket}")
    if unlabeled:
        top = sorted(unlabeled, key=lambda x: -x["peak"])[:5]
        print(f"\n  Etiketsiz çiftlerin en yükseği ({len(unlabeled)} çift içinden):")
        for r in top:
            print(f"    {r['a'][:23]} ↔ {r['b'][:22]:<24} {r['peak']:.4f}")

    copies = [r for r in rows if r["is_copy"] is True]
    clean = [r for r in rows if r["is_copy"] is False]

    if not copies:
        print("\n⚠  Etiketli KOPYA çifti yok — eşik önerilemez.")
        print("   data/labels/similarity_labels.json içine en az bir")
        print("   'is_copy: true' çifti ekle, sonra tekrar çalıştır.")
        return 1

    copy_lo = min(r["peak"] for r in copies)
    clean_hi = max((r["peak"] for r in clean), default=0.0)

    print("\n" + "=" * 78)
    print("AYRIM ANALİZİ")
    print("=" * 78)
    print(f"Kopya çiftlerinin EN DÜŞÜK peak skoru   : {copy_lo:.4f}")
    print(f"Bağımsız çiftlerin EN YÜKSEK peak skoru : {clean_hi:.4f}")
    gap = copy_lo - clean_hi
    print(f"Aradaki boşluk (ayrım gücü)             : {gap:+.4f}")

    if gap <= 0:
        print("\n✗ Boşluk yok — kopya ve bağımsız çiftler örtüşüyor.")
        print("  Olası nedenler:")
        print("   1) Yedek encoder kullanılıyor (semantik değil) → BGE-M3 kur")
        print("   2) Etiketlerden biri hatalı → labels dosyasını gözden geçir")
        print("   3) Çok az örnek var → daha fazla rapor ekle")
        print("  Bu durumda eşik önermek anlamsız; yukarıdaki üçünü çöz.")
        return 1

    # ---- Seviye bazlı özet: kopya şiddeti ile skor ilişkisi ----
    by_level: dict[str, list[float]] = {}
    for r in labeled:
        by_level.setdefault(r["seviye"], []).append(r["peak"])
    if len(by_level) > 1:
        print("\n" + "=" * 78)
        print("KOPYA ŞİDDETİ ↔ SKOR  (merdiven beklendiği gibi mi?)")
        print("=" * 78)
        for lvl in sorted(by_level):
            vals = sorted(by_level[lvl], reverse=True)
            print(f"  {lvl:<12} n={len(vals):<3} en yüksek={vals[0]:.4f}  "
                  f"en düşük={vals[-1]:.4f}  ortalama={sum(vals)/len(vals):.4f}")
        print("\n  Beklenti: L1 > L2 > L3 sırası korunmalı. L3 (ağır parafraz)")
        print("  skoru bağımsız çiftlerin üstünde kalmalı — eşiği o belirliyor.")

    # ---- Eşik taraması: kesinlik/duyarlılık tablosu ----
    print("\n" + "=" * 78)
    print("EŞİK TARAMASI  (flag = kırmızı eşiği)")
    print("=" * 78)
    print(f"{'flag':>6} {'warn':>6} {'yakalanan':>10} {'yanlış alarm':>13} "
          f"{'kesinlik':>9} {'duyarlılık':>11}")
    print("-" * 78)

    best_config = None
    scan = []
    # Tarama aralığı veriden türetilir — sabit 0.60-0.99 aralığı, encoder
    # değiştiğinde (ör. yedek encoder) gözlenen skorların tamamen dışında kalıyor.
    all_peaks = [r["peak"] for r in rows]
    scan_lo = max(0.10, round(min(all_peaks) - 0.05, 2))
    scan_hi = min(0.995, round(max(all_peaks) + 0.10, 2))
    print(f"(tarama aralığı verilerden türetildi: {scan_lo:.2f} – {scan_hi:.2f})")
    print("-" * 78)

    for flag in np.arange(scan_lo, scan_hi, 0.01):
        warn = round(max(flag - 0.08, scan_lo * 0.8), 2)
        tp = sum(1 for r in copies
                 if metrics_at(r["best"], flag, warn)[3] in (Severity.ERROR, Severity.WARN))
        fp = sum(1 for r in clean
                 if metrics_at(r["best"], flag, warn)[3] in (Severity.ERROR, Severity.WARN))
        fn = len(copies) - tp
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        scan.append((round(float(flag), 2), warn, tp, fp, precision, recall, f1))

    # Sadece anlamlı satırları bas (durum değişen noktalar)
    prev = None
    for flag, warn, tp, fp, p, r, f1 in scan:
        sig = (tp, fp)
        if sig != prev:
            print(f"{flag:>6.2f} {warn:>6.2f} {tp:>4}/{len(copies):<5} "
                  f"{fp:>6}/{len(clean):<6} {p:>9.2f} {r:>11.2f}")
            prev = sig

    # En iyi: önce kesinlik 1.0 olanlar, onlar arasında en yüksek duyarlılık
    perfect = [s for s in scan if s[4] >= 1.0 and s[2] > 0]
    if perfect:
        best_config = max(perfect, key=lambda s: (s[5], s[0]))
        gerekce = "yanlış alarm sıfır, duyarlılık en yüksek"
    else:
        best_config = max(scan, key=lambda s: s[6])
        gerekce = "kesinlik 1.0 sağlanamadı; en iyi F1"

    flag, warn = best_config[0], best_config[1]
    # Boşluğun ortası daha güvenli bir seçim olabilir — karşılaştır
    orta = round((copy_lo + clean_hi) / 2, 2)

    print("\n" + "=" * 78)
    print("ÖNERİ")
    print("=" * 78)
    print(f"TSISTEM_SIMILARITY_FLAG_THRESHOLD={flag:.2f}")
    print(f"TSISTEM_SIMILARITY_WARN_THRESHOLD={warn:.2f}")
    print(f"\nGerekçe: {gerekce}.")
    print(f"Yakalanan kopya: {best_config[2]}/{len(copies)}, "
          f"yanlış alarm: {best_config[3]}/{len(clean)}")
    print(f"\nReferans: iki dağılımın tam ortası {orta:.2f}. Önerilen flag bundan")
    print("çok uzaksa örnek sayın az demektir; daha fazla rapor toplayınca tekrar koş.")

    if len(copies) < 3 or len(clean) < 5:
        print(f"\n⚠  Örnek az (kopya={len(copies)}, bağımsız={len(clean)}).")
        print("   Bu eşikler başlangıç noktası; gerçek başvurular gelince")
        print("   en az 5 kopya + 20 bağımsız çift ile tekrar kalibre et.")

    if args.write_env:
        env_path = ROOT / ".env"
        lines = []
        if env_path.exists():
            lines = [
                ln for ln in env_path.read_text(encoding="utf-8").splitlines()
                if not ln.startswith(("TSISTEM_SIMILARITY_FLAG_THRESHOLD",
                                      "TSISTEM_SIMILARITY_WARN_THRESHOLD"))
            ]
        lines += [
            f"TSISTEM_SIMILARITY_FLAG_THRESHOLD={flag:.2f}",
            f"TSISTEM_SIMILARITY_WARN_THRESHOLD={warn:.2f}",
        ]
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\n✓ .env güncellendi: {env_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
