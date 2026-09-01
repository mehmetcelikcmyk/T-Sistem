"""BGE-M3 kurulum doğrulaması.

İlk çalıştırmada modeli indirir (~2.2 GB) ve Türkçe parafraz testi yapar.
Bu script başarıyla geçmeden pipeline'ı gerçek veriyle çalıştırma —
yedek encoder'a düşmüş olursun ve parafrazlanmış kopyalar yakalanmaz.

Kullanım:  PYTHONPATH=src python scripts/check_model.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

# Aynı anlam, farklı kelimeler -> yüksek skor beklenir
PARAPHRASE = (
    "Akciğer tomografi görüntülerinde nodül tespiti yapan derin öğrenme "
    "tabanlı klinik karar destek sistemi geliştirilmektedir.",
    "Tomografi kesitleri üzerinde nodül saptayan derin öğrenme temelli "
    "klinik karar destek yazılımı hazırlanmaktadır.",
)
# Farklı konu -> düşük skor beklenir
UNRELATED = (
    PARAPHRASE[0],
    "Buğday tarlalarında pas hastalığını yaprak görüntülerinden tespit eden "
    "hassas tarım sistemi kurulmaktadır.",
)

MIN_PARAPHRASE = 0.80   # bu değerin altındaysa model/kurulum sorunlu
MAX_UNRELATED = 0.75    # bu değerin üstündeyse ayrım gücü yetersiz


def main() -> int:
    from tsistem.embedding.encoder import get_encoder, reset_encoder

    reset_encoder()
    t0 = time.time()
    enc = get_encoder()
    print(f"Encoder      : {enc.name}")
    print(f"Boyut        : {enc.dim}")
    print(f"Semantik mi  : {enc.is_semantic}")
    print(f"Yükleme      : {time.time() - t0:.1f} sn\n")

    if not enc.is_semantic:
        print("✗ BGE-M3 yüklenemedi, yedek encoder devrede.")
        print("  Kontrol et: pip install sentence-transformers torch")
        print("  ve huggingface.co erişimi (kurumsal ağda proxy gerekebilir).")
        return 1

    v = enc.encode([PARAPHRASE[0], PARAPHRASE[1], UNRELATED[1]])
    para = float(v[0] @ v[1])
    unrel = float(v[0] @ v[2])

    print(f"Parafraz benzerliği (yüksek olmalı) : {para:.4f}  "
          f"{'✓' if para >= MIN_PARAPHRASE else '✗ beklenen ≥ ' + str(MIN_PARAPHRASE)}")
    print(f"Alakasız benzerliği (düşük olmalı)  : {unrel:.4f}  "
          f"{'✓' if unrel <= MAX_UNRELATED else '✗ beklenen ≤ ' + str(MAX_UNRELATED)}")
    print(f"Ayrım gücü (fark)                   : {para - unrel:.4f}")

    ok = para >= MIN_PARAPHRASE and unrel <= MAX_UNRELATED
    print("\n" + ("✓ Model hazır — pipeline'ı çalıştırabilirsin."
                  if ok else "✗ Beklenen ayrım sağlanamadı; eşikleri kalibre et."))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
