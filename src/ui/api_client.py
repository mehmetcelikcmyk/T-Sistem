"""Veri kaynağı katmanı — arayüz ile backend arasındaki TEK temas noktası.

`T_SISTEM_API` ortam değişkeni tanımlıysa gerçek backend'e HTTP ile gider,
tanımlı değilse mock veriyle çalışır. Ekranlar hangi modda olduğunu bilmez.

Backend hazır olduğunda yapılacak tek şey:
    export T_SISTEM_API="http://localhost:8000"
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

# mock_data aynı dizinde; src/ui/app.py'nin sys.path bootstrap'ından bağımsız
# olarak import edebilmek için klasörü yola ekle
_UI_DIR = Path(__file__).resolve().parent
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

import mock_data  # noqa: E402
import pdf_gorunum  # noqa: E402
import sartname_rehber  # noqa: E402

API_BASE = os.environ.get("T_SISTEM_API", "").rstrip("/")
CANLI = bool(API_BASE)


def _get(yol: str) -> Any:
    import requests  # yalnızca canlı modda gerekir
    cevap = requests.get(f"{API_BASE}{yol}", timeout=10)
    cevap.raise_for_status()
    return cevap.json()


def _post(yol: str, govde: dict) -> Any:
    import requests
    cevap = requests.post(f"{API_BASE}{yol}", json=govde, timeout=10)
    cevap.raise_for_status()
    return cevap.json()


# --- Okuma ---------------------------------------------------------------

def yarismalar() -> list[dict]:
    if CANLI:
        try:
            return _get("/yarismalar")
        except Exception as e:
            print(f"[API_CLIENT] /yarismalar hatası: {e}")
            return []
    # Demo mod: mock veriye düşme — boş döndür
    return []


def raporlar(yarisma_id: str = "", referee_id: str = "", only_open: bool = True) -> list[dict]:
    """Seçili yarışmaya veya hakeme atanmış gerçek yarışmacı raporlarını döndürür."""
    try:
        import json
        from pathlib import Path
        from src.database.db import db
        import rubrik
        from src.data import repos

        # Hakem ID kontrolü
        ref_id_clean = (referee_id or "").strip()
        
        # 1. Eğer hakem girişi varsa, YALNIZCA D1'de bu hakeme atanmış raporları çek
        assigned_reports = []
        if ref_id_clean and ref_id_clean != "admin":
            try:
                # only_open=True ise mühürlenmiş/tamamlanmış raporlar hakemin değerlendirme listesine GELMEZ
                assigned_reports = repos().evaluations.list_for_referee(ref_id_clean, only_open=only_open)
            except Exception as e:
                print(f"[API_CLIENT] list_for_referee hatası: {e}")
                assigned_reports = []

            sonuclar = []
            for row in assigned_reports:
                cat_slug = row.get("competition_slug") or row.get("competition_id") or "genel"
                stg = (row.get("stage_code") or row.get("stage") or "OTR").upper()
                r_id = row.get("report_id") or ""
                p_name = row.get("file_name") or row.get("project_name") or "Yarışmacı Raporu"
                t_name = row.get("team_name") or "Takım"
                
                # Rubrik ve kriterler
                y_rub = rubrik.getir(cat_slug, stg)
                kriter_listesi = []
                
                # Cloudflare D1 JSON sütunlarını parse et
                raw_ai = row.get("ai_data_json") or row.get("ai_data") or {}
                if isinstance(raw_ai, str):
                    try:
                        raw_ai = json.loads(raw_ai)
                    except Exception:
                        raw_ai = {}

                raw_checks = row.get("checks_json") or row.get("checks") or {}
                if isinstance(raw_checks, str):
                    try:
                        raw_checks = json.loads(raw_checks)
                    except Exception:
                        raw_checks = {}

                raw_feedback = row.get("feedback_json") or row.get("feedback") or {}
                if isinstance(raw_feedback, str):
                    try:
                        raw_feedback = json.loads(raw_feedback)
                    except Exception:
                        raw_feedback = {}

                # Rubrik ve kriterler: Eğer raporda kaydedilmiş AI kriterleri varsa doğrudan oradan yükle
                ai_krits = raw_ai.get("criteria", []) or raw_ai.get("kriterler", []) if isinstance(raw_ai, dict) else []
                
                if ai_krits:
                    for kr_idx, ak in enumerate(ai_krits):
                        kid = str(ak.get("criterion_id") or ak.get("id") or ak.get("kriter_id") or f"kr_{kr_idx+1}")
                        kmaks = float(ak.get("max_score") or ak.get("maks") or 20.0)
                        kad = str(ak.get("criterion_name") or ak.get("ad") or ak.get("name") or f"Kriter {kr_idx+1}")
                        ai_score = ak.get("score") if ak.get("score") is not None else ak.get("ai_puan")
                        
                        saved_h_score = None
                        saved_h_note = ""
                        if isinstance(raw_feedback, dict):
                            saved_h_score = raw_feedback.get(kid)
                            saved_h_note = raw_feedback.get(f"{kid}__hakem_notu", "")

                        kriter_listesi.append({
                            "kriter_id": kid,
                            "ad": kad,
                            "maks": kmaks,
                            "ai_puan": float(ai_score) if ai_score is not None else round(kmaks * 0.75, 1),
                            "hakem_puan": float(saved_h_score) if saved_h_score is not None else (float(ai_score) if ai_score is not None else round(kmaks * 0.75, 1)),
                            "hakem_notu": saved_h_note,
                            "gerekce": ak.get("reasoning") or ak.get("explanation") or ak.get("gerekce") or ak.get("aciklama", ""),
                            "aciklama": ak.get("reasoning") or ak.get("explanation") or ak.get("gerekce") or ak.get("aciklama", ""),
                            "kanitlar": ak.get("quotes", []) or ak.get("evidence_quotes", []) or ak.get("kanitlar", []) or ak.get("kanit_alintilar", []),
                            "kaynak_alintilar": ak.get("quotes", []) or ak.get("evidence_quotes", []) or ak.get("kanitlar", []) or ak.get("kanit_alintilar", []),
                            "gucler": ak.get("strengths", []),
                            "eksikler": ak.get("weaknesses", []) or ak.get("improvements", [])
                        })
                else:
                    y_rub = rubrik.getir(cat_slug, stg)
                    for kr_idx, kr in enumerate(y_rub.get("kriterler", [])):
                        kid = str(kr.get("kriter_id") or kr.get("id") or f"kr_{kr_idx+1}")
                        kmaks = float(kr.get("puan") or kr.get("max_puan") or 20.0)
                        kad = str(kr.get("ad") or kr.get("kriter_adi") or kr.get("tanim") or f"Kriter {kr_idx+1}")
                        
                        saved_h_score = None
                        saved_h_note = ""
                        if isinstance(raw_feedback, dict):
                            saved_h_score = raw_feedback.get(kid)
                            saved_h_note = raw_feedback.get(f"{kid}__hakem_notu", "")

                        kriter_listesi.append({
                            "kriter_id": kid,
                            "ad": kad,
                            "maks": kmaks,
                            "ai_puan": round(kmaks * 0.75, 1),
                            "hakem_puan": float(saved_h_score) if saved_h_score is not None else round(kmaks * 0.75, 1),
                            "hakem_notu": saved_h_note,
                            "aciklama": kr.get("aciklama", ""),
                            "kanitlar": [],
                            "kaynak_alintilar": []
                        })

                asgn_st = str(row.get("assignment_status") or "").upper()
                rep_st = str(row.get("status") or "").upper()
                has_score = (row.get("referee_score") is not None)
                durum = "tamamlandi" if (asgn_st in ("TAMAMLANDI", "COMPLETED") or rep_st in ("DEGERLENDIRILDI", "TAMAMLANDI", "COMPLETED") or has_score) else "hakem_bekliyor"

                sonuclar.append({
                    "rapor_id": r_id,
                    "proje_adi": p_name,
                    "takim_adi": t_name,
                    "kategori": cat_slug,
                    "yarisma_adi": row.get("competition_name") or cat_slug,
                    "stage": stg,
                    "stage_code": stg,
                    "atanan_hakem": ref_id_clean,
                    "durum": durum,
                    "assignment_id": row.get("assignment_id"),
                    "puan": row.get("referee_score") or row.get("ai_score") or 75.0,
                    "ai_puan": row.get("ai_score") or 75.0,
                    "hakem_puan": row.get("referee_score"),
                    "referee_notes": row.get("referee_notes") or "",
                    "feedback": raw_feedback,
                    "yuklenme_tarihi": str(row.get("created_at") or "2026-08-26")[:10],
                    "dosya": row.get("r2_key") or row.get("file_name") or f"{r_id}.pdf",
                    "sayfa_sayisi": row.get("page_count") or 15,
                    "kriterler": kriter_listesi,
                    "benzerlik": [],
                    "checks": raw_checks,
                    "ai_data": raw_ai,
                })

            if yarisma_id and yarisma_id != "tumu":
                sonuclar = [s for s in sonuclar if yarisma_id.lower() in s["kategori"].lower() or s["kategori"].lower() in yarisma_id.lower()]
            return sonuclar

        # 2. Yönetici (Admin) veya genel sorgu: D1'deki tüm raporları döndür
        db_reps = db.get_all_reports() or []
        sonuclar = []
        for row in db_reps:
            cat = row.get("category") or "genel"
            stg = row.get("stage", "OTR")
            r_id = row.get("report_id") or ""
            
            y_rub = rubrik.getir(cat, stg)
            kriter_listesi = []
            ai_data = row.get("ai_data") or {}
            if isinstance(ai_data, str):
                try:
                    ai_data = json.loads(ai_data)
                except Exception:
                    ai_data = {}
            ai_krits = ai_data.get("kriterler", []) if isinstance(ai_data, dict) else []
            ai_kr_map = {k.get("kriter_id"): k for k in ai_krits if isinstance(k, dict)}

            for kr_idx, kr in enumerate(y_rub.get("kriterler", [])):
                kid = str(kr.get("kriter_id") or kr.get("id") or f"kr_{kr_idx+1}")
                kmaks = float(kr.get("puan") or kr.get("max_puan") or 20.0)
                kad = str(kr.get("ad") or kr.get("kriter_adi") or kr.get("tanim") or f"Kriter {kr_idx+1}")
                ak = ai_kr_map.get(kid, {})
                kriter_listesi.append({
                    "kriter_id": kid,
                    "ad": kad,
                    "maks": kmaks,
                    "ai_puan": ak.get("ai_puan", round(kmaks * 0.75, 1)),
                    "hakem_puan": row.get("referee_score"),
                    "aciklama": ak.get("aciklama", kr.get("aciklama", "")),
                    "kanitlar": ak.get("kanitlar", [])
                })

            st_raw = str(row.get("status") or "").upper()
            durum = "tamamlandi" if st_raw in ("TAMAMLANDI", "DEGERLENDIRILDI", "COMPLETED") else "hakem_bekliyor"

            sonuclar.append({
                "rapor_id": r_id,
                "proje_adi": row.get("project_name") or "Yarışmacı Projesi",
                "takim_adi": row.get("team_name") or row.get("project_name") or "Takım",
                "kategori": cat,
                "stage": stg,
                "stage_code": stg,
                "atanan_hakem": row.get("referee_id") or "",
                "durum": durum,
                "puan": row.get("referee_score") or row.get("ai_score") or 75.0,
                "ai_puan": row.get("ai_score") or 75.0,
                "hakem_puan": row.get("referee_score"),
                "yuklenme_tarihi": str(row.get("created_at") or "2026-08-26")[:10],
                "dosya": row.get("r2_key") or row.get("filename") or f"{r_id}.pdf",
                "sayfa_sayisi": row.get("page_count") or 15,
                "kriterler": kriter_listesi,
                "benzerlik": [],
                "checks": row.get("checks"),
                "ai_data": row.get("ai_data"),
            })

        if yarisma_id and yarisma_id != "tumu":
            sonuclar = [s for s in sonuclar if yarisma_id.lower() in s["kategori"].lower() or s["kategori"].lower() in yarisma_id.lower()]

        return sonuclar
    except Exception as e:
        print(f"[API_CLIENT] Veritabanı rapor okuma hatası: {e}")
        return []
        try:
            return _get(f"/yarismalar/{yarisma_id}/raporlar")
        except Exception:
            pass

    return mock_data.raporlar(yarisma_id)  # Yalnızca demo mod (CANLI=False)


def analiz(rapor_id: str, yarisma_id: str = "hyz-otr-2026") -> dict | None:
    if CANLI:
        return _get(f"/raporlar/{rapor_id}/analiz")
    # 1. Seçili yarışma kategorisindeki raporlar arasında ara
    for r in raporlar(yarisma_id):
        if r.get("rapor_id") == rapor_id:
            return r
    # 2. Genel veritabanından doğrudan eşleşen raporu bul
    try:
        from src.database.db import db
        db_rep = db.get_report(rapor_id)
        if db_rep:
            cat = db_rep.get("category") or yarisma_id
            for r in raporlar(cat):
                if r.get("rapor_id") == rapor_id:
                    return r
    except Exception:
        pass
    return None


def metrikler(yarisma_id: str) -> dict:
    if CANLI:
        try:
            return _get(f"/yarismalar/{yarisma_id}/metrikler")
        except Exception as e:
            print(f"[API_CLIENT] /metrikler hatası: {e}")
            return mock_data.metrikler([])  # Boş metrikler — sıfır değerler
    return mock_data.metrikler(mock_data.raporlar(yarisma_id))


# --- Yazma ---------------------------------------------------------------

def hakem_karari_gonder(rapor_id: str, puanlar: dict, not_metni: str) -> dict:
    # Backend endpoint'i "not_metni" alanı bekler ("not" Python keyword'ü çakışmasını önler)
    govde = {"puanlar": puanlar, "not_metni": not_metni, "onaylandi": True}
    if CANLI:
        return _post(f"/raporlar/{rapor_id}/hakem-karari", govde)
    return {"ok": True, "mod": "mock", "gonderilen": govde}


def rapor_yukle(yarisma_id: str, dosya_adlari: list[str]) -> dict:
    if CANLI:
        return _post(f"/yarismalar/{yarisma_id}/raporlar", {"dosyalar": dosya_adlari})
    return {"kuyruk_id": "mock-kuyruk-1", "alinan": len(dosya_adlari), "mod": "mock"}
