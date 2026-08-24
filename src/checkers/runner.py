"""
Kontrol Hattı Koşucusu (Checker Runner)

6 MVP kontrolünü (dil, şablon, zorunlu başlık, kategori uygunluk, benzerlik)
tek çağrıda çalıştırır ve sonuçları API şemalarına uygun biçimde döndürür.

TASARIM GEREKÇESİ — HATA İZOLASYONU:
  Kontrollerin gerçek implementasyonları (Birhan / Issue #1-3) paralel
  geliştiriliyor. Bir kontrolün patlaması, rapor yüklemesinin tamamını
  çökertmemeli. Bu yüzden her kontrol ayrı try/except içinde çalışır ve hata
  hâlinde ŞEMA-UYUMLU, YARIŞMACIYI CEZALANDIRMAYAN bir yedek değer döner.
  Hangi kontrolün çalışmadığı `check_warnings` listesinde hakeme bildirilir.

ÇOK YARIŞMALI + ÇOK AŞAMALI:
  Şablon kuralları (sayfa sınırı, zorunlu bölümler) koda gömülü DEĞİL;
  (kategori, aşama) rubric tanımından okunur. ÖTR ile KTR farklı sayfa sınırı
  ve farklı bölüm setiyle denetlenir.
"""
from typing import Dict, Any, List, Optional, Callable

from src.checkers.language_checker import check_language
from src.checkers.template_checker import check_template, DEFAULT_MAX_PAGES
from src.checkers.section_checker import (
    check_sections,
    REQUIRED_SECTIONS,
    STATUS_UNKNOWN,
)
from src.checkers.category_checker import check_category_alignment
from src.similarity.vector_store import VectorStore, summarize_similarity


def _yedek_dil(expected_lang: str) -> Dict[str, Any]:
    return {
        "detected_lang": expected_lang,
        "expected_lang": expected_lang,
        "is_valid": True,          # şüpheden yarışmacı yararlanır
        "confidence": 0.0,         # 0.0 = "tespit yapılamadı"
    }


def _yedek_sablon(max_pages: int) -> Dict[str, Any]:
    return {
        "page_count": 0,
        "max_allowed": max_pages,
        "is_valid": True,
        "font_family_detected": None,
        "warnings": ["Şablon kontrolü çalıştırılamadı; hakem manuel doğrulama yapmalıdır."],
    }


def _yedek_bolum(bolumler: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    kaynak = bolumler if bolumler else REQUIRED_SECTIONS
    return {
        "total_required": len(kaynak),
        "found_count": 0,
        "is_complete": False,
        "sections": {
            anahtar: {
                "section_name": ad,
                "exists": False,
                "word_count": 0,
                "status": STATUS_UNKNOWN,   # "eksik" DEĞİL, "bilinmiyor"
            }
            for anahtar, ad in kaynak.items()
        },
    }


def _yedek_kategori(category_name: str) -> Dict[str, Any]:
    return {
        "applied_category": category_name,
        "is_aligned": True,
        "semantic_similarity": 0.0,
        "explanation": "Kategori uygunluk analizi çalıştırılamadı; hakem manuel değerlendirmelidir.",
    }


def _yedek_benzerlik() -> Dict[str, Any]:
    return summarize_similarity([])


def _guvenli_calistir(
    ad: str,
    fn: Callable[[], Dict[str, Any]],
    yedek: Dict[str, Any],
    uyarilar: List[str],
) -> Dict[str, Any]:
    """Bir kontrolü çalıştırır; patlarsa yedek değeri döndürür ve uyarı ekler."""
    try:
        sonuc = fn()
        if not isinstance(sonuc, dict):
            raise TypeError(f"sözlük beklenirken {type(sonuc).__name__} döndü")
        return sonuc
    except Exception as e:
        mesaj = f"{ad} kontrolü çalıştırılamadı ({type(e).__name__}: {e})."
        print(f"[KONTROL HATASI] {mesaj}")
        uyarilar.append(mesaj)
        return yedek


def _rubric_sablon_kurallari(category_name: str, stage: Optional[str]) -> Dict[str, Any]:
    """
    (kategori, aşama) rubric tanımından şablon kurallarını okur.
    Tanım yoksa güvenli varsayılanlar döner. DB import döngüsü olmasın diye
    tembel (lazy) import edilir.
    """
    # KALİBRASYON: rubric sayfa sınırı belirtmezse yönetici panosundaki
    # 'max_report_pages' varsayılanı kullanılır (o da yoksa DEFAULT_MAX_PAGES).
    from src.utils.calibration import get_threshold
    varsayilan_sayfa = int(get_threshold("max_report_pages", DEFAULT_MAX_PAGES))
    max_pages = varsayilan_sayfa
    bolumler: Optional[Dict[str, str]] = None
    try:
        from src.database.db import db
        tanim = db.get_rubric_by_category(category_name, stage)
        if tanim:
            max_pages = tanim.get("max_pages") or varsayilan_sayfa
            gs = tanim.get("required_sections") or []
            if isinstance(gs, dict):
                bolumler = {str(k): str(v) for k, v in gs.items()} or None
            elif isinstance(gs, list):
                bolumler = {f"b_{i+1}": (s.get("title") if isinstance(s, dict) else str(s)) for i, s in enumerate(gs)} or None
    except Exception as e:
        print(f"[RUBRIC UYARI] Şablon kuralları okunamadı: {type(e).__name__}: {e}")
    return {"max_pages": max_pages, "required_sections": bolumler}


def _ai_sartname_denetimi_yap(
    report_text: str,
    category_name: str,
    stage: Optional[str],
    file_bytes: bytes,
) -> Optional[Dict[str, Any]]:
    """Yarışma şartnamesi ve şablon zorunluluklarını doğrudan LLM'e göndererek derin denetim yapar."""
    try:
        from src.database.db import db
        from src.evaluation.evaluator import _call_llm_json

        # 1. Kategori ve Şartname Bilgilerini Çek
        clean_slug = category_name.lower().replace(" ", "-").replace("_", "-")
        cat_req = db.get_category_requirement(clean_slug) or db.get_category_requirement(category_name) or {}
        tpl_req = db.get_report_template_requirement(clean_slug, stage or "OTR") or db.get_report_template_requirement(category_name, stage or "OTR") or {}

        # Gerekirse şablon analizinden zorunlulukları çıkar
        if not tpl_req or not tpl_req.get("required_sections"):
            try:
                import sartname_rehber
                tpl_req = sartname_rehber.sablondan_rapor_zorunluluklarini_cikar(category_name, stage or "OTR") or {}
            except Exception:
                pass

        target_level = cat_req.get("target_level", "Lise / Üniversite / Mezun")
        min_team = cat_req.get("min_team_size", 2)
        max_team = cat_req.get("max_team_size", 6)
        advisor = cat_req.get("advisor_required", "İsteğe Bağlı")
        max_pages = tpl_req.get("max_pages", 25)
        req_sections = tpl_req.get("required_sections", [])
        if not req_sections:
            req_sections = [
                {"title": "1. Detaylı Sistem Mimarisi ve Tasarım"},
                {"title": "2. Algoritma ve Test Sonuçları"},
                {"title": "3. Prototip / Donanım Entegrasyonu"},
                {"title": "4. Güvenlik ve Standartlara Uygunluk"},
                {"title": "5. Proje Yönetimi ve Kaynakça"}
            ]

        sec_list_str = "\n".join([f"- {s.get('title') if isinstance(s, dict) else str(s)}" for s in req_sections])

        prompt = f"""Sen TEKNOFEST Şartname ve Şablon Uygunluk Baş Denetçisisin (AI Specification Auditor).
Aşağıdaki yarışma şartname kuralları ve rapor şablonu zorunlulukları doğrultusunda yarışmacı raporunu derinlemesine denetle.

YARIŞMA ŞARTNAMESİ VE RESMÎ ZORUNLULUKLAR:
- Yarışma Kategorisi: {category_name}
- Rapor Aşaması: {stage or 'OTR'}
- Hedef Seviye: {target_level}
- Takım Şartları: {min_team}-{max_team} Kişi, Danışman Durumu: {advisor}
- Maksimum Sayfa Limiti: {max_pages} Sayfa
- Resmî Şablondaki Zorunlu Bölümler:
{sec_list_str}

DEĞERLENDİRİLECEK YARIŞMACI RAPORU:
\"\"\"
{report_text[:12000]}
\"\"\"

DENETİM GÖREVLERİ:
1. Kategori Uygunluğu: Rapor konusu ve projenin teknik yaklaşımı bu yarışma şartnamesine ve hedeflerine uyuyor mu? (0.0 - 1.0 arası semantic_similarity ve detaylı açıklama).
2. Şablon Zorunlu Bölümleri: Yukarıda listelenen HER BİR zorunlu bölümün raporda yer alıp almadığını, tahmini kelime sayısını, doluluk oranını (0.0 - 1.0) ve durumunu ('OK' / 'MISSING' / 'EMPTY') tespit et.
3. Şablon Sayfa Limiti: Raporun sayfa sayısı sınırı aşıp aşmadığını değerlendir.

Lütfen SADECE aşağıdaki JSON formatında yanıt dön:
{{
  "category_check": {{
    "applied_category": "{category_name}",
    "is_aligned": true,
    "semantic_similarity": 0.88,
    "explanation": "Projede geliştirilen algoritmalar ve sistem mimarisi {category_name} şartnamesindeki problem tanımına ve teknik isterlere tam uyum sağlamaktadır."
  }},
  "section_check": {{
    "total_required": {len(req_sections)},
    "found_count": {len(req_sections)},
    "is_complete": true,
    "sections": {{
      "bolum_1": {{
        "section_name": "...",
        "exists": true,
        "word_count": 320,
        "fullness": 0.95,
        "status": "OK",
        "notes": "Bölüm içeriği teknik verilerle detaylandırılmıştır."
      }}
    }}
  }},
  "template_check": {{
    "page_count": 18,
    "max_allowed": {max_pages},
    "is_valid": true,
    "warnings": []
  }}
}}
"""
        res = _call_llm_json(prompt, system_msg="Sen TEKNOFEST Şartname Denetim Uzmanısın. Yalnızca geçerli JSON döndür.")
        if isinstance(res, dict) and "category_check" in res and "section_check" in res:
            return res
    except Exception as e:
        print(f"[UYARI] AI şartname denetimi LLM çağrısı atlandı: {e}")
    return None


def run_all_checks(
    file_bytes: bytes = b"",
    report_text: str = "",
    category_name: str = "",
    expected_lang: Optional[str] = None,
    max_pages: Optional[int] = None,
    report_id: Optional[str] = None,
    corpus: Optional[List[Dict[str, Any]]] = None,
    stage: Optional[str] = None,
    **kwargs: Any
) -> Dict[str, Any]:
    """
    6 MVP kontrolünü çalıştırır ve şema-uyumlu tek bir sözlük döndürür.
    Öncelikle doğrudan şartname ve şablonla LLM denetimi yapar; gerekirse yerel denetleyicilerle tamamlar.
    """
    uyarilar: List[str] = []

    kurallar = _rubric_sablon_kurallari(category_name, stage)
    etkili_dil = expected_lang or "tr"
    etkili_max_sayfa = max_pages if max_pages is not None else kurallar["max_pages"]
    rubric_bolumleri = kurallar["required_sections"]

    # 1. ÖNCELİK: DOĞRUDAN AI ŞARTNAME VE ŞABLON DENETİMİ
    ai_audit = _ai_sartname_denetimi_yap(report_text, category_name, stage, file_bytes)

    dil = _guvenli_calistir(
        "Dil",
        lambda: check_language(report_text, expected_lang=etkili_dil),
        _yedek_dil(etkili_dil),
        uyarilar,
    )

    if ai_audit and "template_check" in ai_audit:
        sablon = ai_audit["template_check"]
    else:
        sablon = _guvenli_calistir(
            "Şablon",
            lambda: check_template(file_bytes, max_pages=etkili_max_sayfa),
            _yedek_sablon(etkili_max_sayfa),
            uyarilar,
        )

    if ai_audit and "section_check" in ai_audit:
        bolumler = ai_audit["section_check"]
    else:
        bolumler = _guvenli_calistir(
            "Zorunlu başlık",
            lambda: check_sections(report_text, required_sections=rubric_bolumleri),
            _yedek_bolum(rubric_bolumleri),
            uyarilar,
        )

    if ai_audit and "category_check" in ai_audit:
        kategori = ai_audit["category_check"]
    else:
        kategori = _guvenli_calistir(
            "Kategori uygunluk",
            lambda: check_category_alignment(report_text, category_name),
            _yedek_kategori(category_name),
            uyarilar,
        )

    benzerlik = _guvenli_calistir(
        "Benzerlik / intihal",
        lambda: _benzerlik_calistir(report_text, report_id, corpus),
        _yedek_benzerlik(),
        uyarilar,
    )

    return {
        "language_check": dil,
        "template_check": sablon,
        "section_check": bolumler,
        "category_check": kategori,
        "similarity_check": benzerlik,
        "check_warnings": uyarilar,
    }


def _benzerlik_calistir(
    report_text: str,
    report_id: Optional[str],
    corpus: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Vektör deposunu kurar, benzer raporları arar, risk özetini üretir."""
    store = VectorStore()
    if corpus:
        store.add_reports(corpus)

    eslesmeler = store.find_similar_reports(report_text) or []
    if report_id:
        eslesmeler = [
            m for m in eslesmeler
            if isinstance(m, dict) and m.get("matched_report_id") != report_id
        ]
    return summarize_similarity(eslesmeler)
