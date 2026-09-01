"""T-Sistem · Olu kod ve demo veri temizleyicisi (Faz 0).

Denetimde tespit edilen, HICBIR YERDEN import edilmeyen dosyalari ve
uygulamanin surekli yeniden urettigi demo veri dosyalarini kaldirir.

VARSAYILAN OLARAK YALNIZCA RAPORLAR. Silmek icin `--apply` gerekir; silinen
her sey once `_silinenler_<zaman>/` klasorune tasinir (geri alinabilir).

Kullanim:
    python scripts/cleanup_dead_code.py             # yalnizca listele
    python scripts/cleanup_dead_code.py --apply     # tasi (geri alinabilir)
    python scripts/cleanup_dead_code.py --apply --purge   # kalici sil
"""

from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Hicbir yerden import edilmeyen dosyalar (denetimde dogrulandi)
DEAD_FILES = [
    ("src/ui/demo.py", "113 satir. `grep -rn 'import demo'` -> sifir sonuc."),
    ("src/ui/views/yarismaci_paneli.py", "79 satir. Karne blogu %100 hardcoded "
                                         "('TF-2026-100004', '82.5 / 100')."),
    ("src/ui/views/hakem_paneli.py", "142 satir. Tum metrikler sabit (12/8/4/76.4); "
                                     "kaydet butonu hicbir yere yazmiyor."),
    ("src/ui/views/yonetici_paneli.py", "101 satir. '142 basvuru', '74.8 ortalama', "
                                        "sahte intihal matrisi."),
    ("src/ui/mock_data.py", "23 KB sahte veri ureteci. Yeni arayuz katmani "
                            "artik yalnizca repos() kullaniyor."),
    ("src/similarity/embeddings.py", "Tamami TODO stub; sabit sifir vektor donduruyordu. "
                                     "Yerine src/similarity/hybrid.py geldi."),
    ("src/utils/storage.py", "Ikinci R2 istemcisi (farkli bucket adi, erisilemez URL). "
                             "Yerine src/data/r2.py geldi."),
]

# Uygulamanin yeniden urettigi demo/gecici veri
DEMO_FILES = [
    ("data/takimlar.json", "Global takim dosyasi — ayni sunucudaki TUM kullanicilar "
                           "birbirinin takimlarini goruyordu. Takimlar artik D1'de."),
    ("data/.remembered_user.json", "Oturum artigi."),
    ("data/smoke.db", "Test veritabani."),
]

# Yalnizca UYARI: elle karar verilmeli
REVIEW_FILES = [
    ("src/database/db.py", "76 KB. Yeni `src/data/` katmani devraldi. FastAPI "
                           "rotalari hala kullaniyorsa once onlar tasinmali."),
    ("src/ui/api_client.py", "Mock harmanlamasi yapiyordu. Arayuz artik repos() "
                             "kullaniyor; FastAPI istemcisi olarak kalabilir."),
    ("src/ui/rubrik.py", "Sabit HYZ/IYT rubrikleri. Rubrikler artik D1'de."),
    ("src/ui/firebase_config.py", "clientSecret kaynak kodda. .env'e tasindiktan "
                                  "sonra silinmeli."),
]


def _scan(entries: list[tuple[str, str]]) -> list[tuple[Path, str, int]]:
    found: list[tuple[Path, str, int]] = []
    for rel, reason in entries:
        path = ROOT / rel
        if path.exists():
            found.append((path, reason, path.stat().st_size))
    return found


def _print_group(title: str, items: list[tuple[Path, str, int]]) -> int:
    print(f"\n{title}")
    print("-" * len(title))
    if not items:
        print("  (bulunamadi — zaten temiz)")
        return 0
    total = 0
    for path, reason, size in items:
        total += size
        print(f"  {path.relative_to(ROOT)}  ({size / 1024:.1f} KB)")
        print(f"      {reason}")
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T-Sistem olu kod temizleyicisi")
    parser.add_argument("--apply", action="store_true", help="Dosyalari tasi/sil")
    parser.add_argument("--purge", action="store_true",
                        help="--apply ile birlikte: yedeklemeden kalici sil")
    args = parser.parse_args(argv)

    dead = _scan(DEAD_FILES)
    demo = _scan(DEMO_FILES)
    review = _scan(REVIEW_FILES)

    total = 0
    total += _print_group("1 · OLU DOSYALAR (hicbir yerden import edilmiyor)", dead)
    total += _print_group("2 · DEMO / GECICI VERI", demo)
    _print_group("3 · ELLE KARAR VERILMELI (silinmeyecek)", review)

    targets = dead + demo
    print(f"\nToplam temizlenecek: {len(targets)} dosya · {total / 1024:.1f} KB")

    if not args.apply:
        print("\nBu bir ON IZLEME. Silmek icin: python scripts/cleanup_dead_code.py --apply")
        return 0
    if not targets:
        return 0

    if args.purge:
        for path, _, _ in targets:
            path.unlink()
            print(f"  silindi: {path.relative_to(ROOT)}")
        print(f"\n{len(targets)} dosya KALICI silindi.")
        return 0

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = ROOT / f"_silinenler_{stamp}"
    backup.mkdir(parents=True, exist_ok=True)
    for path, _, _ in targets:
        destination = backup / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        print(f"  tasindi: {path.relative_to(ROOT)} -> {destination.relative_to(ROOT)}")
    print(f"\n{len(targets)} dosya '{backup.name}' klasorune tasindi.")
    print("Uygulamayi test ettikten sonra bu klasoru elle silebilirsiniz.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
