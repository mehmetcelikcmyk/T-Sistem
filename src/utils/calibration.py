"""
Kalibrasyon Eşiği Okuyucu (tek nokta)

Karar mantığı (AI puan kalibrasyonu, intihal risk eşikleri, sayfa sınırı, karne
bandı, hakem uyarısı) eşik değerlerini KODA GÖMÜLÜ SABİTLERDEN değil, buradan —
yani veritabanındaki `calibration_settings` tablosundan — okur. Yönetici
`/api/admin/calibration` panosundan değeri değiştirdiğinde sistem anında ona göre
davranır.

DB erişilemezse (test, göç, vb.) güvenli `default` değere düşülür; böylece
kalibrasyon katmanı hiçbir zaman akışı çökertmez.
"""
from typing import Optional


def get_threshold(key: str, default: float) -> float:
    """Bir kalibrasyon eşiğini okur; DB yoksa/erişilemezse default döner."""
    try:
        from src.database.db import db
        return float(db.get_calibration_value(key, default))
    except Exception as e:
        print(f"[KALİBRASYON UYARI] '{key}' okunamadı, varsayılan kullanılıyor: {type(e).__name__}: {e}")
        return default


def calibrate_score(raw_score: float) -> float:
    """
    Ham AI puanına kalibre sapma (offset) ve eğim (slope) düzeltmesi uygular:
        kalibre = raw * slope + offset
    Sonuç 0-100 aralığına sıkıştırılır.
    """
    slope = get_threshold("ai_score_slope", 1.0)
    offset = get_threshold("ai_score_offset", 0.0)
    try:
        deger = float(raw_score) * slope + offset
    except (TypeError, ValueError):
        deger = float(raw_score)
    return round(min(100.0, max(0.0, deger)), 1)
