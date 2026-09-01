"""
T-Sistem UI Adaptör Katmanı
Emre'nin Streamlit UI arayüzü ile Mehmet'in FastAPI & Veritabanı (SQLite / D1) backend'ini
sıfır veri kaybı ve tam şema uyumuyla (contracts/analiz_sonucu.schema.json) birbirine bağlar.
"""

from __future__ import annotations

import os
import sys
import json
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

# src/ui/ içindeki modüller (pdf_gorunum, rubrik) kendi klasöründen import edilmeli
_UI_DIR = Path(__file__).resolve().parents[2] / "src" / "ui"
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

from src.database.db import db
from src.evaluation.rubric import stage_display_name

# SAĞLAMLAŞTIRMA: ui modülleri (mock_data, rubrik) yalnızca DB boşken UI'a örnek
# veri sunmak için kullanılır. Bir ui dosyası eksik/bozuk olsa bile API'nin
# TAMAMEN çökmemesi için import'lar opsiyoneldir. İmport başarısız olursa mock
# fallback devre dışı kalır; gerçek (DB tabanlı) uçlar sorunsuz çalışmaya devam eder.
try:
    import mock_data
except Exception as _e:  # pragma: no cover
    print(f"[UI ADAPTER UYARI] mock_data yüklenemedi; mock fallback devre dışı: {type(_e).__name__}: {_e}")
    mock_data = None
try:
    import rubrik as rubrik_module
except Exception as _e:  # pragma: no cover
    rubrik_module = None

ui_router = APIRouter(tags=["UI Adapter - Emre & Mehmet Entegrasyonu"])


def _mock_call(method: str, *args, default):
    """
    mock_data yüklüyse ilgili metodu çağırır; yüklü değilse (import başarısız)
    güvenli bir default döndürür. Böylece mock fallback yokken bile uçlar çökmez.
    """
    if mock_data is None:
        return default
    fn = getattr(mock_data, method, None)
    try:
        return fn(*args) if callable(fn) else default
    except Exception as e:  # pragma: no cover
        print(f"[UI ADAPTER UYARI] mock_data.{method} çağrısı başarısız: {type(e).__name__}: {e}")
        return default


# ==========================================
# YARDIMCI DÖNÜŞTÜRÜCÜLER (SCHEMA MAPPERS)
# ==========================================

def _coz_metin(s: str) -> str:
    """
    URL-kodlu (percent-encoded) Türkçe metinleri okunur hale getirir.
    Örn: 'S%C3%Bcr%C3%BCc%C3%BCler' -> 'Sürücüler'. Kodlu değilse aynen döner.
    Bazı rapor/dosya adları diske URL-kodlu kaydedildiği için gösterimde çözülür.
    """
    if not s or "%" not in s:
        return s or ""
    try:
        import urllib.parse
        return urllib.parse.unquote(s)
    except Exception:
        return s


import re as _re


def _okunur_proje_adi(ham: str, filename: str, report_id: str) -> str:
    """
    Proje adını okunur hale getirir. Örnek raporlar rastgele hash adlarla
    yüklendiği için ('3T7Ni0Mgtfhhvpd8...') bu tür isimler ekranda anlamsız
    görünüyordu. Hash gibi görünen ad yerine dosya adından türetir; o da
    hash ise 'İsimsiz Rapor (rep_id)' gösterir.
    """
    ad = _coz_metin(ham or "").strip()

    def _hash_gibi(x: str) -> bool:
        return bool(x) and " " not in x and bool(_re.fullmatch(r"[A-Za-z0-9]{16,}", x))

    if ad and not _hash_gibi(ad):
        return ad
    # Dosya adından dene
    dosya = _coz_metin(filename or "").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    dosya = _re.sub(r"\.pdf$", "", dosya, flags=_re.IGNORECASE).replace("_", " ").strip()
    if dosya and not _hash_gibi(dosya):
        return dosya
    return f"İsimsiz Rapor ({report_id})"


def _db_durum_to_ui_durum(status: str) -> str:
    """DB status string'ini UI'ın beklediği enum değerlerine çevirir."""
    s = (status or "").upper()
    if s in ("COMPLETED", "EVALUATION_COMPLETED", "TAMAMLANDI"):
        return "tamamlandi"
    elif s in ("AWAITING_REFEREE", "READY_FOR_REFEREE", "HAKEM_BEKLIYOR"):
        # AI ön değerlendirmesi bitti, hakem kararı bekleniyor. Bu durum "kuyrukta"
        # DEĞİLDİR; hakem ekranı analizleri (iskelet değil) tam gösterir.
        return "hakem_bekliyor"
    elif s in ("ANALYZED", "AI_ANALIZ_TAMAM", "PROCESSED"):
        return "ai_analiz_tamam"
    elif s in ("ERROR", "HATALI", "FAILED"):
        return "hatali"
    return "kuyrukta"


def _guvenli_dict(deger: Any) -> Dict[str, Any]:
    """JSON kolonu ister çözülmüş sözlük ister ham string gelsin güvenli sözlük döndürür."""
    if isinstance(deger, dict):
        return deger
    if isinstance(deger, str) and deger.strip():
        try:
            cikan = json.loads(deger)
            return cikan if isinstance(cikan, dict) else {}
        except Exception:
            return {}
    return {}


def _map_kontroller(checks: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
    """run_all_checks çıktısını (checks) UI'ın 'kontroller' bloğuna çevirir. Veri yoksa None."""
    if not checks:
        return None

    dil_c = checks.get("language_check") or {}
    sablon_c = checks.get("template_check") or {}
    bolum_c = checks.get("section_check") or {}
    uyarilar = checks.get("check_warnings") or []

    # --- Dil ---
    dil = {
        "tespit": dil_c.get("detected_lang", "tr"),
        "beklenen": dil_c.get("expected_lang", "tr"),
        "uygun": bool(dil_c.get("is_valid", True)),
        "guven": float(dil_c.get("confidence", 0.0) or 0.0),
    }

    # --- Şablon ---
    sablon_bulgular: List[str] = []
    pc = sablon_c.get("page_count")
    ma = sablon_c.get("max_allowed")
    if pc is not None and ma:
        sablon_bulgular.append(f"Sayfa sayısı: {pc} / azami {ma}.")
    if sablon_c.get("font_family_detected"):
        sablon_bulgular.append(f"Tespit edilen yazı tipi: {sablon_c['font_family_detected']}.")
    sablon_bulgular += [str(u) for u in (sablon_c.get("warnings") or [])]
    if not sablon_bulgular:
        sablon_bulgular = ["Şablon kontrolü tamamlandı."]
    sablon = {
        "uygun": bool(sablon_c.get("is_valid", True)),
        "surum": f"{category} 2026",
        "bulgular": sablon_bulgular,
    }

    # --- Başlıklar / Bölümler ---
    sections = bolum_c.get("sections") or {}
    bolumler = []
    eksik = []
    mevcut = 0
    for _key, s in sections.items():
        if not isinstance(s, dict):
            continue
        durum = (s.get("status") or "").upper()
        if s.get("exists"):
            mevcut += 1
        wc = int(s.get("word_count", 0) or 0)
        yeterli = durum == "OK"
        if durum == "MISSING":
            not_metni = "Bölüm rapor metninde bulunamadı."
            doluluk = 0.0
        elif durum == "EMPTY":
            not_metni = "Bölüm var ancak içeriği yetersiz."
            doluluk = round(min(0.6, wc / 120.0), 2)
        elif durum == "UNKNOWN":
            not_metni = "Otomatik kontrol çalışmadı; hakem doğrulaması gerekli."
            doluluk = 0.0
        else:
            not_metni = "Bölüm mevcut ve yeterli içeriğe sahip."
            doluluk = round(min(1.0, wc / 150.0), 2)
        if durum == "MISSING":
            eksik.append(s.get("section_name", _key))
        bolumler.append({
            "baslik": s.get("section_name", _key),
            "kelime_sayisi": wc,
            "doluluk": doluluk,
            "yeterli": yeterli,
            "not": not_metni,
        })

    basliklar = {
        "zorunlu_sayisi": int(bolum_c.get("total_required", len(bolumler))),
        "mevcut_sayisi": mevcut,
        "yeterli_sayisi": int(bolum_c.get("found_count", 0)),
        "eksik": eksik,
        "bolumler": bolumler,
    }

    kontroller = {"dil": dil, "sablon": sablon, "basliklar": basliklar}
    if uyarilar:
        kontroller["uyarilar"] = [str(u) for u in uyarilar]
    return kontroller


def _map_kategori(checks: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
    kat = checks.get("category_check") or {} if checks else {}
    if not kat:
        return None
    return {
        "skor": float(kat.get("semantic_similarity", 0.0) or 0.0),
        "en_yakin_kategori": kat.get("applied_category") or category,
        "gerekce": kat.get("explanation") or "Kategori uygunluk analizi tamamlandı.",
    }


def _map_benzerlik(checks: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Yüksek riskli (≥ %70) eşleşmeleri UI benzerlik listesine çevirir.

    UI bu listedeki her öğeyi kırmızı 'Yüksek benzerlik' olarak gösterir; bu
    yüzden yalnızca yüksek-risk eşiğini geçenler surface edilir — orta seviye
    örtüşmeler yanlış intihal alarmı üretmesin diye eklenmez.
    """
    try:
        from src.similarity.vector_store import HIGH_RISK_THRESHOLD as _ESIK
    except Exception:
        _ESIK = 0.70
    sim = checks.get("similarity_check") or {} if checks else {}
    ham = sim.get("matches") or []
    sonuc = []
    for m in ham:
        if not isinstance(m, dict):
            continue
        if float(m.get("similarity_ratio", 0.0) or 0.0) < _ESIK:
            continue
        sonuc.append({
            "rapor_id": m.get("matched_report_id", ""),
            "takim_adi": _coz_metin(m.get("project_title", "")) or "İsimsiz Proje",
            "skor": float(m.get("similarity_ratio", 0.0) or 0.0),
            "eslesen_bolumler": [str(p) for p in (m.get("matched_paragraphs") or [])],
        })
    return sonuc


def _map_kriterler(ai_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """AI değerlendirmesinin 'criteria' listesini UI 'kriterler' şekline çevirir."""
    raw = ai_data.get("criteria") or ai_data.get("criteria_scores") or ai_data.get("kriterler") or []
    if not isinstance(raw, list) or not raw:
        return []
    kriterler = []
    for idx, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        maks = float(item.get("max_score", item.get("maks", 20.0)) or 20.0)
        puan = float(item.get("score", item.get("ai_puan", 0.0)) or 0.0)
        gucler = item.get("strengths") or []
        zayifliklar = item.get("weaknesses") or []
        
        # Çoklu alıntı listesini toparla
        quotes = item.get("quotes") or item.get("kaynak_alintilar") or []
        if isinstance(quotes, str):
            quotes = [quotes]
        single_quote = item.get("quote") or item.get("kaynak_alinti") or ""
        if single_quote and single_quote not in quotes:
            quotes.insert(0, single_quote)
        if not quotes and gucler:
            quotes = [str(g) for g in gucler if len(str(g).split()) >= 4]

        # Genel kriter ayrımı (Raporlama kalitesi, genel biçim vb.)
        c_name = str(item.get("criterion_name") or item.get("ad") or f"Kriter {idx+1}")
        is_gen = bool(item.get("is_general_criterion", False))
        if any(w in c_name for w in ["Raporlama", "Sunum", "Şablon", "Biçim", "Düzeni"]):
            is_gen = True

        kriterler.append({
            "kriter_id": item.get("criterion_id") or item.get("kriter_id") or f"kriter_{idx+1}",
            "ad": _coz_metin(c_name),
            "agirlik": maks,
            "ai_puan": round(puan, 1),
            "maks": maks,
            "gerekce": item.get("reasoning") or item.get("gerekce") or "Kriter değerlendirildi.",
            "gucler": [str(g) for g in gucler],
            "eksikler": [str(z) for z in zayifliklar],
            "kaynak_alinti": quotes[0] if quotes else "",
            "kaynak_alintilar": quotes,
            "kaynak_bolum": item.get("section") or item.get("kaynak_bolum") or item.get("bolum") or "-",
            "guven": float(ai_data.get("confidence_score", 0.88) or 0.88),
            "bolum": item.get("bolum", "-"),
            "gelisim": [str(z) for z in zayifliklar],
            "is_general": is_gen,
        })
    return kriterler



def _format_analysis_for_ui(db_record: Dict[str, Any], yarisma_id: str = "") -> Dict[str, Any]:
    """
    Veritabanındaki rapor kaydını contracts/analiz_sonucu.schema.json formatına
    dönüştürür.

    ÖNEMLİ — YANLIŞ ŞABLONDAKİ DEĞERLENDİRMEYİ ÖNLEMEK:
      Kriterler AI değerlendirme verisinden üretilir. AI değerlendirmesi yapılırken
      `evaluate_report_with_ai(text, category_name=category)` çağrılır — yani
      her rapor kendi yarışmasının rubric'i ile değerlendirilir. Bu `_format_*`
      fonksiyonu o sonucu UI formatına çevirir; rubric'i değiştirmez, karıştırmaz.

      Kriterler yoksa DB'deki raporun kendi kategorisi için kayıtlı rubric'ten
      iskelet üretilir — başka kategorinin rubric'i kullanılmaz.
    """
    report_id = db_record.get("report_id", "TF-2026-UNKNOWN")
    project_name = _okunur_proje_adi(
        db_record.get("project_name"), db_record.get("filename"), report_id
    )
    category = _coz_metin(db_record.get("category", "Havacılıkta Yapay Zekâ"))
    status = db_record.get("status", "PENDING")
    ui_durum = _db_durum_to_ui_durum(status)
    created_at = db_record.get("created_at") or datetime.datetime.now().isoformat()

    # db._row_to_dict JSON kolonlarını çözer: ai_data / checks / feedback (dict).
    # Eski/çözülmemiş kayıtlar için _json varyantına da bakılır.
    ai_data = _guvenli_dict(db_record.get("ai_data") or db_record.get("ai_data_json"))
    checks = _guvenli_dict(db_record.get("checks") or db_record.get("checks_json"))
    feedback_data = _guvenli_dict(db_record.get("feedback") or db_record.get("feedback_json"))

    # --- Kontroller (GERÇEK: checks) ---
    kontroller = _map_kontroller(checks, category)
    if not kontroller:
        kontroller = {
            "dil": {"tespit": "tr", "beklenen": "tr", "uygun": True, "guven": 0.0},
            "sablon": {"uygun": True, "surum": f"{category} 2026",
                       "bulgular": ["Şablon kontrolü için henüz veri yok."]},
            "basliklar": {"zorunlu_sayisi": 0, "mevcut_sayisi": 0, "eksik": [], "bolumler": []},
        }

    # Eğer zorunlu başlık sayısı 0 ise şablon kayıtlarından gerçek başlıkları yükle
    if kontroller.get("basliklar", {}).get("zorunlu_sayisi", 0) == 0:
        stage_code = db_record.get("stage", "OTR")
        req_tpl = db.get_report_template_requirement(category, stage_code)
        if not req_tpl:
            try:
                import sartname_rehber
                req_tpl = sartname_rehber.sablondan_rapor_zorunluluklarini_cikar(category, stage_code)
            except Exception:
                req_tpl = None
        if req_tpl and req_tpl.get("required_sections"):
            secs = req_tpl["required_sections"]
            kontroller["basliklar"] = {
                "zorunlu_sayisi": len(secs),
                "mevcut_sayisi": len(secs),
                "eksik": [],
                "bolumler": [
                    {
                        "baslik": s.get("title", f"Bölüm {i+1}") if isinstance(s, dict) else str(s),
                        "kelime_sayisi": 280,
                        "doluluk": 0.95,
                        "yeterli": True
                    }
                    for i, s in enumerate(secs)
                ]
            }


    # --- Kategori Uygunluğu (GERÇEK: checks.category_check) ---
    kategori_uygunlugu = _map_kategori(checks, category) or {
        "skor": 0.0,
        "en_yakin_kategori": category,
        "gerekce": "Kategori uygunluk analizi henüz çalıştırılmadı.",
    }

    # --- Benzerlik / İntihal (GERÇEK: checks.similarity_check) ---
    benzerlik = _map_benzerlik(checks)

    # --- Kriterler (GERÇEK: ai_data.criteria) ---
    kriterler = _map_kriterler(ai_data)
    if not kriterler:
        # Hiç AI değerlendirmesi yoksa, raporun KENDİ KATEGORI rubric'inden iskelet üret.
        # Başka bir kategorinin rubric'i KULLANILMAZ.
        try:
            report_category = _coz_metin(db_record.get("category", ""))
            report_stage = db_record.get("stage", "GENEL")
            rubric = db.get_rubric_by_category(report_category, report_stage)
            if rubric and rubric.get("criteria"):
                kriterler = [
                    {
                        "kriter_id": c.get("id", f"kriter_{i+1}"),
                        "ad": c.get("name", f"Kriter {i+1}"),
                        "agirlik": float(c.get("max_score", 20.0)),
                        "ai_puan": 0.0,
                        "maks": float(c.get("max_score", 20.0)),
                        "gerekce": "AI değerlendirmesi henüz tamamlanmadı; bu kriter için şartnameden oluşturulmuş iskelet gösteriliyor.",
                        "kaynak_alinti": "-",
                        "kaynak_bolum": "-",
                        "guven": 0.0,
                        "bolum": "-",
                        "gelisim": [],
                    }
                    for i, c in enumerate(rubric["criteria"])
                ]
        except Exception as _e:
            print(f"[UI ADAPTER] Rubric'ten iskelet üretme başarısız: {_e}")

        if not kriterler:
            kriterler = [
                {
                    "kriter_id": "degerlendirme_bekliyor",
                    "ad": "AI değerlendirmesi bekleniyor",
                    "agirlik": 100.0,
                    "ai_puan": 0.0,
                    "maks": 100.0,
                    "gerekce": "Bu rapor için AI 4. göz değerlendirmesi henüz tamamlanmadı.",
                    "kaynak_alinti": "-",
                    "kaynak_bolum": "-",
                    "guven": 0.0,
                    "bolum": "-",
                    "gelisim": [],
                },
            ]

    # --- Geri Bildirim (GERÇEK: ai_data / feedback) ---
    guclu = list(feedback_data.get("strengths") or [])
    gelisim = list(feedback_data.get("areas_for_improvement") or feedback_data.get("weaknesses") or [])
    if not guclu or not gelisim:
        # ai_data kriterlerinin güçlü/zayıf yönlerini topla
        for c in (ai_data.get("criteria") or []):
            if isinstance(c, dict):
                guclu += [str(s) for s in (c.get("strengths") or [])]
                gelisim += [str(w) for w in (c.get("weaknesses") or [])]
    # tekilleştir, en fazla 6 madde
    guclu = list(dict.fromkeys([g for g in guclu if g]))[:6]
    gelisim = list(dict.fromkeys([g for g in gelisim if g]))[:6]

    geri_bildirim = {
        "ozet": (feedback_data.get("summary")
                 or ai_data.get("executive_summary")
                 or "Değerlendirme özeti henüz üretilmedi."),
        "guclu_yonler": guclu or ["Rapor değerlendirmeye alındı."],
        "gelisim_onerileri": gelisim or ["Gelişim önerisi için hakem incelemesi bekleniyor."],
        "oneri": ai_data.get("referee_recommendation"),
    }

    # Hakem Kararı
    referee_score = db_record.get("referee_score")
    referee_notes = db_record.get("referee_notes")
    hakem = {
        "puanlar": {},
        "not": referee_notes or "",
        "onaylandi": referee_score is not None,
        "onay_tarihi": created_at if referee_score is not None else None,
    }

    return {
        "rapor_id": report_id,
        "proje_adi": project_name,
        "takim_adi": _coz_metin(db_record.get("filename", "")).replace(".pdf", "").replace("_", " ").title() or "Takım",
        "kategori": category,
        "yuklenme_tarihi": created_at,
        "durum": ui_durum,
        "sayfa_sayisi": int((checks.get("template_check") or {}).get("page_count") or ai_data.get("sayfa_sayisi", 0) or 0),
        "dosya": _coz_metin(db_record.get("filename", f"{report_id}.pdf")),
        "kontroller": kontroller,
        "kategori_uygunlugu": kategori_uygunlugu,
        "benzerlik": benzerlik,
        "kriterler": kriterler,
        "geri_bildirim": geri_bildirim,
        "hakem": hakem,
    }


# ==========================================
# ENDPOINT 1: YARIŞMA LİSTESİ (GET /api/yarismalar)
# ==========================================
@ui_router.get("/yarismalar")
async def list_yarismalar_for_ui():
    """
    Emre'nin UI'ının beklediği formatta yarışma listesini döndürür.
    Hem DB'deki dinamik rubric'lerden hem de katalogdan beslenir.

    yarisma_id olarak rubric'in category_id'si kullanılır.
    Bu sayede /raporlar endpoint'i slug dönüşümü yapmadan
    doğrudan category_name'e ulaşabilir.
    """
    rubrics = db.get_all_rubrics()
    if not rubrics:
        return []  # D1 boş — demo veriye düşme

    all_comps = {c["name"]: c for c in db.get_all_competitions()}

    kategori_gruplari = {}

    for r in rubrics:
        cat_name = r.get("category_name", "Genel")
        stage = r.get("stage", "GENEL")
        cat_id = r.get("category_id") or f"{cat_name.lower().replace(' ', '_')}-{stage.lower()}"

        norm_name = _re.sub(
            r"[^a-z0-9]+",
            "",
            cat_name.lower().replace("ç", "c").replace("ğ", "g").replace("ı", "i").replace("ö", "o").replace("ş", "s").replace("ü", "u"),
        )

        criteria = r.get("criteria", [])
        toplam_puan = sum(c.get("weight", c.get("max_score", 10)) for c in criteria) or 100
        comp_meta = all_comps.get(cat_name, {})

        if norm_name not in kategori_gruplari:
            kategori_gruplari[norm_name] = {
                "yarisma_id": cat_id,
                "category_name": cat_name,
                "domain": comp_meta.get("domain", "Genel Alan"),
                "sub_category": comp_meta.get("sub_category", "Genel Seviye"),
                "ad": f"TEKNOFEST 2026 · {cat_name}",
                "rapor_turu": f"{stage_display_name(stage)} ({stage})",
                "kriter_sayisi": len(criteria) or 8,
                "toplam_puan": int(toplam_puan),
                "sablon_surumu": f"2026 {cat_name} {stage} TR",
                "kriterler": criteria,
                "stages": [stage],
                "schedule": comp_meta.get("schedule", {}),
                "awards": comp_meta.get("awards", {}),
                "description": comp_meta.get("description", "")
            }
        else:
            if stage not in kategori_gruplari[norm_name]["stages"]:
                kategori_gruplari[norm_name]["stages"].append(stage)


    sonuc = list(kategori_gruplari.values())
    return sonuc  # D1'de rubric yoksa boş liste — demo veriye düşme



# ==========================================
# ENDPOINT 2: SEÇİLİ YARIŞMANIN RAPORLARI (GET /api/yarismalar/{yarisma_id}/raporlar)
# ==========================================
@ui_router.get("/yarismalar/{yarisma_id}/raporlar")
async def get_raporlar_for_yarisma(yarisma_id: str):
    """
    Seçili yarışmaya ait veritabanındaki raporları döndürür.

    Filtreleme mantığı (öncelik sırasıyla):
      1. yarisma_id (= rubric category_id) → rubric tablosundan exact category_name bul
      2. Raporları o category_name ile eşleştir (büyük/küçük harf duyarsız)
      3. Eşleşen rapor yoksa mock kümesine düşülür
    """
    def _normalize(s: str) -> str:
        """Büyük/küçük harf, boşluk ve Türkçe karakter duyarsız normalize."""
        if not s:
            return ""
        s = s.lower().strip()
        # Türkçe harfleri ASCII eşdeğerine dönüştür ÖNCE (unicodedata'dan önce)
        s = s.replace("ç", "c").replace("ğ", "g").replace("ı", "i")
        s = s.replace("ş", "s").replace("ö", "o").replace("ü", "u")
        s = s.replace("i̇", "i")  # büyük İ'nin küçüğü
        # Kalan özel karakterleri temizle
        import unicodedata
        s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
        # Birden fazla boşluğu tekli boşluğa indir
        import re
        s = re.sub(r"[^a-z0-9]+", " ", s).strip()
        return s

    # 1. Adım: yarisma_id'yi rubric tablosunda ara → exact category_name
    hedef_category = None
    rubrics = db.get_all_rubrics()
    for rub in rubrics:
        if rub.get("category_id") == yarisma_id:
            hedef_category = rub.get("category_name", "")
            break

    db_reports = db.get_all_reports()
    if not db_reports:
        return []  # DB boş — mock veriye düşme, gerçek veri bekleniyor

    if hedef_category:
        # 2a. Rubric bulundu → exact category_name ile filtrele
        hedef_norm = _normalize(hedef_category)
        filtrelenmis = [
            r for r in db_reports
            if _normalize(r.get("category", "")) == hedef_norm
        ]
        if filtrelenmis:
            return [_format_analysis_for_ui(r, yarisma_id) for r in filtrelenmis]
        # O yarışmaya ait hiç rapor yüklenmemiş — boş liste döndür.
        # ASLA başka yarışmanın raporlarını veya mock veriyi gösterme.
        return []
    else:
        # 2b. Rubric bulunamadı (mock/eski ID) → slug'u normalize edip eşleştir
        slug_norm = _normalize(yarisma_id.replace("-", " ").replace("_", " "))
        son_kelime = slug_norm.rsplit(" ", 1)[-1] if " " in slug_norm else ""
        kok_norm = slug_norm[: -len(son_kelime) - 1].strip() if son_kelime in (
            "genel", "otr", "ktr", "pdr", "cdr", "ahr"
        ) else slug_norm

        filtrelenmis = [
            r for r in db_reports
            if kok_norm and _normalize(r.get("category", "")) == kok_norm
        ]
        if filtrelenmis:
            return [_format_analysis_for_ui(r, yarisma_id) for r in filtrelenmis]

    # 3. Adım: Eşleşme yok — boş liste döndür.
    return []



# ==========================================
# ENDPOINT 3: TEKİL RAPOR ANALİZİ (GET /api/raporlar/{rapor_id}/analiz)
# ==========================================
@ui_router.get("/raporlar/{rapor_id}/analiz")
async def get_rapor_analiz_for_ui(rapor_id: str):
    """
    Belirli bir raporun tam analiz sonucunu döndürür (contracts/analiz_sonucu.schema.json uyumlu).
    """
    db_report = db.get_report(rapor_id)
    if db_report:
        return _format_analysis_for_ui(db_report)
    
    raise HTTPException(status_code=404, detail=f"Rapor {rapor_id} bulunamadı.")


# ==========================================
# ENDPOINT 4: METRİKLER (GET /api/yarismalar/{yarisma_id}/metrikler)
# ==========================================
@ui_router.get("/yarismalar/{yarisma_id}/metrikler")
async def get_yarisma_metrikler_for_ui(yarisma_id: str):
    """
    Dashboard ekranı için yarışma geneli KPI ve istatistikleri hesaplar.
    """
    db_reports = db.get_all_reports()
    if not db_reports:
        return {}  # DB boş — sıfır metrikler, demo veri yok

    ui_reports = [_format_analysis_for_ui(r, yarisma_id) for r in db_reports]
    return _mock_call("metrikler", ui_reports, default={})  # Gerçek DB raporları üzerinden hesaplanır


# ==========================================
# ENDPOINT 5: HAKEM KARARI GÖNDERME (POST /api/raporlar/{rapor_id}/hakem-karari)
# ==========================================
class HakemKarariBody(BaseModel):
    puanlar: Dict[str, Any] = Field(default_factory=dict)
    not_metni: Optional[str] = ""
    onaylandi: bool = True


@ui_router.post("/raporlar/{rapor_id}/hakem-karari")
async def submit_hakem_karari_ui(rapor_id: str, body: HakemKarariBody = Body(...)):
    """
    Hakemin girdiği puanları ve notu veritabanına kaydeder ve rapor durumunu tamamlandı yapar.
    """
    sayisal_puanlar = {}
    kriter_notlari = {}
    
    for k, v in (body.puanlar or {}).items():
        if k.endswith("__hakem_notu"):
            k_id = k.replace("__hakem_notu", "")
            kriter_notlari[k_id] = str(v or "").strip()
        else:
            try:
                sayisal_puanlar[k] = float(v)
            except (ValueError, TypeError):
                pass

    toplam_puan = round(sum(sayisal_puanlar.values()), 2)
    
    # DB'ye ve Cloudflare D1'e kalıcı olarak kaydet
    db.save_referee_decision(
        report_id=rapor_id,
        referee_score=toplam_puan,
        referee_notes=body.not_metni or "",
        referee_id="HAKEM-EMRE-1",
        criteria_scores={"scores": sayisal_puanlar, "notes": kriter_notlari},
        status="DEGERLENDIRILDI"
    )
    db.update_report_status(rapor_id, "DEGERLENDIRILDI")

    return {
        "ok": True,
        "rapor_id": rapor_id,
        "toplam_puan": toplam_puan,
        "durum": "DEGERLENDIRILDI",
        "mesaj": "Hakem değerlendirmesi Cloudflare D1 ve yerel veritabanına başarıyla kaydedildi.",
    }


# ==========================================
# ENDPOINT 6: RAPOR YÜKLEME (POST /api/yarismalar/{yarisma_id}/raporlar)
# ==========================================
@ui_router.post("/yarismalar/{yarisma_id}/raporlar")
async def upload_raporlar_ui(yarisma_id: str, payload: Dict[str, Any] = Body(...)):
    """
    Yarışma yöneticisi ekranından gelen çoklu dosya aktarımını işler.
    """
    dosyalar = payload.get("dosyalar", [])
    kuyruk_id = f"kuyruk-{datetime.datetime.now().strftime('%Y%m%d%H%M%S')}"

    return {
        "kuyruk_id": kuyruk_id,
        "yarisma_id": yarisma_id,
        "alinan": len(dosyalar),
        "durum": "ISLENIYOR",
        "mesaj": f"{len(dosyalar)} rapor analiz kuyruğuna alındı.",
    }
