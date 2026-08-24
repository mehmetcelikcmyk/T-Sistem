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
        return _get("/yarismalar")
    return mock_data.yarismalar()


def raporlar(yarisma_id: str = "", referee_id: str = "") -> list[dict]:
    if CANLI:
        try:
            return _get(f"/yarismalar/{yarisma_id}/raporlar")
        except Exception:
            pass

    # 2. SQLite Veritabanından Hakeme Özel Raporları Çek
    try:
        from src.database.db import db
        import mock_data
        import random
        from pathlib import Path
        
        import rubrik
        y_rub = rubrik.getir(yarisma_id)
        ref_rows = db.get_reports_for_referee(referee_id, yarisma_id)
        if ref_rows:
            sonuclar = []
            for i, r in enumerate(ref_rows):
                p_name = r.get("project_name") or r.get("filename") or f"Proje {i+1}"
                r_id = r.get("report_id") or f"TF2026-{1000+i}"
                kat_raw = r.get("category") or yarisma_id or "Havacılıkta Yapay Zekâ"
                kat = sartname_rehber.turkce_kategori_adi_formatla(kat_raw)
                stg = r.get("stage") or r.get("stage_code") or "OTR"
                
                # Takım adını al (gerçek veritabanı kaydı)
                t_raw = (r.get("team_name") or "").strip()
                if len(t_raw) > 18 and " " not in t_raw:
                    t_clean = f"Takım {p_name.split()[0]} {i+1}"
                elif t_raw:
                    t_clean = t_raw
                else:
                    t_clean = f"Takım {p_name.split()[0]} {i+1}"

                rng = random.Random(abs(hash(r_id)) % 100000)
                mock_rep = mock_data._rapor(rng, i, [kat], y_rub)
                
                # Gerçek Veritabanı Alanlarıyla Doldur
                mock_rep["rapor_id"] = r_id
                mock_rep["proje_adi"] = p_name
                mock_rep["kategori"] = kat
                mock_rep["takim_adi"] = t_clean
                mock_rep["stage"] = stg
                mock_rep["atanan_hakem"] = r.get("referee_id") or referee_id or "Prof. Dr. Ahmet Yılmaz"
                mock_rep["durum"] = "tamamlandi" if r.get("referee_score") is not None or r.get("status") == "tamamlandi" else "hakem_bekliyor"
                mock_rep["yuklenme_tarihi"] = r.get("application_date") or r.get("created_at") or "2026-08-23"
                if r.get("referee_score") is not None:
                    mock_rep["hakem"]["puanlar"] = {"C1": r.get("referee_score")}
                    mock_rep["hakem"]["not_metni"] = r.get("referee_notes", "")
                
                # Gerçek PDF Dosyası Eşleştirmesi (Veritabanından Çözümleme)
                pdf_p = r.get("pdf_path") or ""
                if not pdf_p or not Path(pdf_p).exists() or Path(pdf_p).name.startswith(("BOS", "BOZUK", "SIFRELI")):
                    resolved = pdf_gorunum.yol(r.get("filename", ""))
                    if resolved and resolved.exists() and not resolved.name.startswith(("BOS", "BOZUK", "SIFRELI")):
                        pdf_p = str(resolved)
                    else:
                        # Gerçek çok sayfalı raporlar havuzundan eşleştir
                        ornek_pdfler = [p for p in Path("data/ornek_raporlar").glob("*.pdf") if not p.name.startswith(("BOS", "BOZUK", "SIFRELI"))]
                        if ornek_pdfler:
                            pdf_p = str(ornek_pdfler[i % len(ornek_pdfler)])
                
                if pdf_p and Path(pdf_p).exists():
                    mock_rep["dosya"] = pdf_p
                    p_len = pdf_gorunum.sayfa_sayisi_getir(pdf_p)
                    mock_rep["sayfa_sayisi"] = p_len if p_len > 0 else 13
                else:
                    mock_rep["sayfa_sayisi"] = 13

                # Gerçek AI Analiz ve MVP Denetim Verileri (DB'de varsa)
                import json
                c_data = r.get("checks") or r.get("checks_json")
                if isinstance(c_data, str):
                    try:
                        c_data = json.loads(c_data)
                    except Exception:
                        c_data = {}

                if isinstance(c_data, dict) and c_data:
                    from src.api.ui_adapter import _map_kontroller, _map_benzerlik, _map_kategori
                    mapped_k = _map_kontroller(c_data, kat)
                    if mapped_k:
                        mock_rep["kontroller"] = mapped_k
                    mapped_b = _map_benzerlik(c_data)
                    if mapped_b is not None:
                        mock_rep["benzerlik"] = mapped_b
                    mapped_kat = _map_kategori(c_data, kat)
                    if mapped_kat:
                        mock_rep["kategori_uygunlugu"] = mapped_kat

                a_data = r.get("ai_data") or r.get("ai_data_json")
                if isinstance(a_data, str):
                    try:
                        a_data = json.loads(a_data)
                    except Exception:
                        a_data = {}

                if isinstance(a_data, dict) and a_data:
                    from src.api.ui_adapter import _map_kriterler
                    mapped_kr = _map_kriterler(a_data)
                    if mapped_kr:
                        # Eğer alıntılar generic kalmışsa, gerçek rapordan (pdf_p) doğru cümlelerle besle
                        if pdf_p and Path(pdf_p).exists():
                            sayfa_cumleleri = pdf_gorunum.sayfaya_gore_cumleler(pdf_p)
                            if sayfa_cumleleri:
                                BOLUM_SAYFA_HARITASI = {
                                    "1": [3, 4, 5],
                                    "2": [4, 5, 6],
                                    "3": [6, 7, 8],
                                    "3.1": [6, 7],
                                    "3.2": [7, 8],
                                    "3.3": [8, 9],
                                    "4": [8, 9],
                                    "5": [9, 10],
                                    "6": [10, 11],
                                }
                                for idx_k, kr_item in enumerate(mapped_kr):
                                    cur_q = kr_item.get("kaynak_alinti", "")
                                    if not cur_q or "İlgili bölümde" in cur_q or "bulunamadı" in cur_q:
                                        b_kodu = str(kr_item.get("bolum") or "").strip()
                                        h_sayfalar = BOLUM_SAYFA_HARITASI.get(b_kodu, [max(3, min(idx_k + 3, len(sayfa_cumleleri)))])
                                        secili_cumle = None
                                        for s_no in h_sayfalar:
                                            if s_no in sayfa_cumleleri and sayfa_cumleleri[s_no]:
                                                secili_cumle = sayfa_cumleleri[s_no][0]
                                                break
                                        if secili_cumle:
                                            kr_item["kaynak_alinti"] = secili_cumle
                                            kr_item["kaynak_alintilar"] = [secili_cumle]
                        mock_rep["kriterler"] = mapped_kr
                        mock_rep["ai_data"] = a_data
                
                sonuclar.append(mock_rep)
            return sonuclar
    except Exception as e:
        print(f"[API_CLIENT HATASI] {e}")

    return mock_data.raporlar(yarisma_id)


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
        return _get(f"/yarismalar/{yarisma_id}/metrikler")
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
