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


import json
import os
from pathlib import Path

_AI_DIR = Path(__file__).resolve().parents[2] / "data" / "ai_rapor_analizi"


from functools import lru_cache

@lru_cache(maxsize=128)
def getir(yarisma_id: str, asama: str | None = None, seviye: str | None = None) -> dict:
    """Yarışma ve aşamaya ait resmî 0-100 puanlık rubrik kriterlerini döner."""
    clean_id = (yarisma_id or "").strip()
    target_stg = (asama or "OTR").upper().replace("Ö", "O").replace("Ü", "U").replace("İ", "I")

    # 1. Cloudflare D1 competition_rubrics Tablosundan Sorgula
    try:
        from src.database.db import db
        d1_rows = db.execute_d1(
            "SELECT criteria_json, total_score, stage_code, level FROM competition_rubrics WHERE competition_id = ? OR competition_id LIKE ?;",
            [clean_id, f"%{clean_id}%"]
        )
        if d1_rows:
            matched_row = None
            for r in d1_rows:
                r_stg = (r.get("stage_code") or "").upper().replace("Ö", "O").replace("Ü", "U").replace("İ", "I")
                if r_stg == target_stg or target_stg in r_stg:
                    matched_row = r
                    break
            if not matched_row and d1_rows:
                matched_row = d1_rows[0]

            if matched_row and matched_row.get("criteria_json"):
                criteria_raw = json.loads(matched_row["criteria_json"])
                c_list = []
                for c in criteria_raw:
                    c_list.append({
                        "id": c.get("id", "kriter"),
                        "ad": c.get("name") or c.get("title") or "Kriter",
                        "maks": float(c.get("max_score", 10.0)),
                        "bolum": c.get("name", "").split(".")[0] if "." in c.get("name", "") else "—",
                        "aciklama": c.get("description", "")
                    })
                if c_list:
                    return {
                        "yarisma_id": clean_id,
                        "ad": clean_id,
                        "rapor_turu": matched_row.get("stage_code", target_stg),
                        "toplam_puan": float(matched_row.get("total_score", 100.0)),
                        "kriterler": c_list,
                        "zorunlu_bolumler": []
                    }
    except Exception:
        pass

    # 2. data/ai_rapor_analizi/{slug}.json dosyasından oku
    json_candidates = list(_AI_DIR.glob(f"*{clean_id}*.json")) if _AI_DIR.exists() else []
    if json_candidates:
        try:
            with open(json_candidates[0], "r", encoding="utf-8") as f:
                c_data = json.load(f)
                
            stages_pool = []
            stg_val = c_data.get("stages") or c_data.get("rubrics")
            if isinstance(stg_val, list):
                stages_pool.extend(stg_val)
            elif isinstance(stg_val, dict):
                for lvl_name, stg_list in stg_val.items():
                    if isinstance(stg_list, list):
                        stages_pool.extend(stg_list)

            matched_stage = None
            for s in stages_pool:
                if isinstance(s, dict):
                    s_code = (s.get("stage") or "").upper().replace("Ö", "O").replace("Ü", "U").replace("İ", "I")
                    if s_code == target_stg or target_stg in s_code:
                        matched_stage = s
                        break
                        
            if not matched_stage and stages_pool:
                matched_stage = stages_pool[0]

            if matched_stage and "rubric" in matched_stage and isinstance(matched_stage["rubric"], dict):
                rub = matched_stage["rubric"]
                c_list = []
                for c in rub.get("criteria", []):
                    c_list.append({
                        "id": c.get("id", "kriter"),
                        "ad": c.get("name") or c.get("title") or "Kriter",
                        "maks": float(c.get("max_score", 10.0)),
                        "bolum": c.get("name", "").split(".")[0] if "." in c.get("name", "") else "—",
                        "aciklama": c.get("description", "")
                    })
                if c_list:
                    return {
                        "yarisma_id": clean_id,
                        "ad": c_data.get("name", clean_id),
                        "rapor_turu": matched_stage.get("stage_name", target_stg),
                        "toplam_puan": float(rub.get("total_score", 100.0)),
                        "kriterler": c_list,
                        "zorunlu_bolumler": matched_stage.get("sections", [])
                    }
        except Exception:
            pass

    # 2. Hardcoded fallback'ler
    for y in YARISMALAR:
        if y["yarisma_id"] == clean_id:
            return y
    return YARISMALAR[0]


def kriter_bul(yarisma: dict, kriter_id: str) -> dict | None:
    for k in yarisma.get("kriterler", []):
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
