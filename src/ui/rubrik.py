"""Yarışma tanımları — rubrik KOD DEĞİL, VERİDİR.

Sistem "9 kriter" bilmez; seçilen yarışmanın tanımını okur ve ekranı ona göre
çizer. Yeni yarışma eklemek için buraya (ileride: backend'den gelen JSON'a)
bir kayıt eklemek yeterlidir — arayüzde tek satır değişmez.

Kriter puanı doğrudan ağırlıktır: "Sonuçlar ve İnceleme" 30 puan üzerinden
değerlendirilir, "Akış Şeması" 5 puan üzerinden. Toplam 100.
"""

from __future__ import annotations

# Gerçek kaynak: TEKNOFEST 2026 Havacılıkta Yapay Zekâ Yarışması,
# Ön Tasarım Raporu resmî değerlendirme formu.
HYZ_OTR_2026 = {
    "yarisma_id": "hyz-otr-2026",
    "ad": "TEKNOFEST 2026 · Havacılıkta Yapay Zekâ",
    "rapor_turu": "Ön Tasarım Raporu (ÖTR)",
    "sablon_surumu": "2026 HYZ ÖTR TR",
    "toplam_puan": 100,
    "kriterler": [
        {"id": "mevcut_durum", "ad": "Proje Mevcut Durum Değerlendirmesi",
         "maks": 10, "bolum": "2"},
        {"id": "veri_setleri", "ad": "Veri Setleri", "maks": 10, "bolum": "3.1"},
        {"id": "algoritmalar", "ad": "Algoritmalar", "maks": 15, "bolum": "3.2"},
        {"id": "akis_semasi", "ad": "Akış Şeması", "maks": 5, "bolum": "3.3"},
        {"id": "ozgunluk", "ad": "Özgünlük", "maks": 10, "bolum": "4"},
        {"id": "proje_takvimi", "ad": "Proje Takvimi", "maks": 10, "bolum": "5"},
        {"id": "sonuclar", "ad": "Sonuçlar ve İnceleme", "maks": 30, "bolum": "6"},
        {"id": "referanslar", "ad": "Referanslar (Kaynakça)", "maks": 5, "bolum": "7"},
        {"id": "rapor_duzeni", "ad": "Genel Rapor Düzeni", "maks": 5, "bolum": None},
    ],
    "zorunlu_bolumler": [
        "TAKIM ŞEMASI", "PROJE MEVCUT DURUM DEĞERLENDİRMESİ",
        "ALGORİTMALAR VE SİSTEM MİMARİSİ", "ÖZGÜNLÜK", "PROJE TAKVİMİ",
        "SONUÇLAR VE İNCELEME", "KAYNAKÇA",
    ],
}

# İkinci yarışma: farklı kriter sayısı ve farklı ağırlıklar — arayüzün
# gerçekten dinamik olduğunu göstermek için. (Örnek tanım; şartname
# geldiğinde değerler güncellenecek.)
IYT_OTR_2026 = {
    "yarisma_id": "iyt-otr-2026",
    "ad": "TEKNOFEST 2026 · İnsanlık Yararına Teknoloji",
    "rapor_turu": "Ön Tasarım Raporu (ÖTR)",
    "sablon_surumu": "2026 İYT ÖTR TR",
    "toplam_puan": 100,
    "kriterler": [
        {"id": "problem_tanimi", "ad": "Problem Tanımı ve İhtiyaç Analizi",
         "maks": 15, "bolum": "2"},
        {"id": "cozum", "ad": "Çözüm Yaklaşımı ve Yöntem", "maks": 25, "bolum": "3"},
        {"id": "ozgunluk", "ad": "Özgünlük", "maks": 15, "bolum": "4"},
        {"id": "toplumsal_etki", "ad": "Toplumsal Etki ve Yaygınlaştırma",
         "maks": 20, "bolum": "5"},
        {"id": "uygulanabilirlik", "ad": "Uygulanabilirlik ve Takvim",
         "maks": 15, "bolum": "6"},
        {"id": "rapor_duzeni", "ad": "Genel Rapor Düzeni", "maks": 10, "bolum": None},
    ],
    "zorunlu_bolumler": [
        "TAKIM ŞEMASI", "PROBLEM TANIMI", "ÇÖZÜM YAKLAŞIMI", "ÖZGÜNLÜK",
        "TOPLUMSAL ETKİ", "UYGULAMA PLANI", "KAYNAKÇA",
    ],
}

YARISMALAR = [HYZ_OTR_2026, IYT_OTR_2026]


def getir(yarisma_id: str) -> dict:
    for y in YARISMALAR:
        if y["yarisma_id"] == yarisma_id:
            return y
    return YARISMALAR[0]


def kriter_bul(yarisma: dict, kriter_id: str) -> dict | None:
    for k in yarisma["kriterler"]:
        if k["id"] == kriter_id:
            return k
    return None


# --- Gerçek referans vaka (gold set) ------------------------------------
# TEKNOFEST 2026 HYZ ÖTR — gerçek başvuru, gerçek hakem puanları.
# AI puanları: T-Sistem motorunun kör testi (hakem puanlarını görmeden).
GERCEK_VAKA = {
    "rapor_id": "GERCEK-001",
    "yarisma_id": "hyz-otr-2026",
    "proje_adi": "SafeLanding AI — Otonom Hava Araçları İçin Çevresel Algı ve İniş Güvenliği",
    "takim_adi": "Aero Intelligence",
    "hakem_toplam": 73.0,
    "kriterler": {
        "mevcut_durum": {"hakem": 8.5, "ai": 7.0,
                         "ai_notu": "Mevcut durum iyi analiz edilmiş; proje henüz planlama safhasında."},
        "veri_setleri": {"hakem": 9.0, "ai": 8.5,
                         "ai_notu": "VisDrone + sentetik veri ile dört katmanlı veri stratejisi güçlü."},
        "algoritmalar": {"hakem": 13.0, "ai": 12.0,
                         "ai_notu": "YOLOv8s, piramidal Lucas-Kanade ve hibrit SIFT/ORB mimarisi teknik olarak uygun."},
        "akis_semasi": {"hakem": 5.0, "ai": 4.0,
                        "ai_notu": "Sistem mimarisi ve blok diyagramlar anlaşılır."},
        "ozgunluk": {"hakem": 8.0, "ai": 9.0,
                     "ai_notu": "İrtifa uyarlamalı SIFT/ORB ve sentetik veri hattı özgün."},
        "proje_takvimi": {"hakem": 9.5, "ai": 8.0,
                          "ai_notu": "İş paketleri ve zaman planı tutarlı kurgulanmış."},
        "sonuclar": {"hakem": 11.5, "ai": 5.0,
                     "ai_notu": "Raporun en kritik eksiği: deneysel test çıktıları, mAP/FPS metrikleri ve karşılaştırmalı grafikler yok."},
        "referanslar": {"hakem": 5.0, "ai": 5.0,
                        "ai_notu": "IEEE biçiminde, yeterli sayıda ve konuyla ilgili kaynak."},
        "rapor_duzeni": {"hakem": 3.5, "ai": 4.0,
                         "ai_notu": "Şekil/tablo listesi ve dil düzgün; son bölümlerin zayıflığı düzeni olumsuz etkiliyor."},
    },
    "hakem_geri_bildirimi": [
        "Algoritma sonuçlarının paylaşılması ile rapor olgunlaşacaktır.",
        "Sonuç kısmında tüm görevlere dair çıktılar gözlemlenememiştir.",
    ],
}
