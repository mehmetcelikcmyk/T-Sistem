"""
Zorunlu Başlık ve Bölüm İçerik Kontrolörü — GERÇEK TESPİT

SÖZLEŞME (bkz. docs/ENTEGRASYON_SOZLESMESI.md):
  check_sections() çıktısı src/api/schemas.py -> SectionCheckResult şemasına
  BİREBİR uymak zorundadır.

Yöntem (bağımlılıksız): rapor metninde her zorunlu başlığın adı (ve anahtar
kelimeleri) Türkçe-normalize edilmiş biçimde aranır; bulunan başlıklar konuma
göre sıralanıp aralarındaki metin o bölümün içeriği sayılır ve kelime sayısı
hesaplanır. Doluluk eşiği kalibrasyondan (min_section_words) okunur.
"""
from typing import Dict, Any, Optional, List, Tuple
import re
import unicodedata

REQUIRED_SECTIONS: Dict[str, str] = {
    "ozet": "Özet",
    "problem": "Problem Tanımı",
    "yontem": "Yöntem ve Çözüm Yaklaşımı",
    "ozgunluk": "Yenilikçi / Özgün Yön",
    "uygulanabilirlik": "Uygulanabilirlik ve Sürdürülebilirlik",
    "kaynaklar": "Kaynaklar",
}

STATUS_OK = "OK"
STATUS_EMPTY = "EMPTY"
STATUS_MISSING = "MISSING"
STATUS_UNKNOWN = "UNKNOWN"
ALLOWED_STATUSES = (STATUS_OK, STATUS_EMPTY, STATUS_MISSING, STATUS_UNKNOWN)

MIN_WORDS_PER_SECTION = 50

# Yaygın başlık eş anlamlıları (anahtar -> ek arama terimleri)
_ESANLAM: Dict[str, List[str]] = {
    "ozet": ["ozet", "yonetici ozeti", "abstract", "summary"],
    "problem": ["problem", "problem tanimi", "ihtiyac", "amac", "giris"],
    "yontem": ["yontem", "cozum", "sistem mimarisi", "mimari", "algoritma", "metot", "metodoloji"],
    "ozgunluk": ["ozgun", "ozgunluk", "yenilik", "yenilikci", "farklilik"],
    "uygulanabilirlik": ["uygulanabilirlik", "surdurulebilirlik", "butce", "maliyet", "fizibilite", "risk"],
    "kaynaklar": ["kaynak", "kaynakca", "referans", "kaynaklar"],
    "sonuc": ["sonuc", "bulgu", "test", "deney", "sonuclar"],
    "prototip": ["prototip", "test", "dogrulama"],
    "guvenlik": ["guvenlik", "emniyet"],
    "kurtarma": ["kurtarma"],
}


def _norm(s: str) -> str:
    """Türkçe karakterleri sadeleştirir, küçük harfe indirir."""
    if not s:
        return ""
    eslem = str.maketrans({"ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g",
                           "Ğ": "g", "ç": "c", "Ç": "c", "ö": "o", "Ö": "o",
                           "ü": "u", "Ü": "u"})
    s = s.translate(eslem)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def classify_section(exists: bool, word_count: int) -> str:
    """Durum etiketi; 'dolu' eşiği kalibrasyondan (min_section_words) okunur."""
    try:
        from src.utils.calibration import get_threshold
        min_kelime = int(get_threshold("min_section_words", MIN_WORDS_PER_SECTION))
    except Exception:
        min_kelime = MIN_WORDS_PER_SECTION
    if not exists:
        return STATUS_MISSING
    if word_count < min_kelime:
        return STATUS_EMPTY
    return STATUS_OK


def _arama_terimleri(key: str, display_name: str) -> List[str]:
    terimler = [_norm(display_name)]
    # Görünen addaki anlamlı kelimeler
    for kelime in _norm(display_name).replace("/", " ").split():
        if len(kelime) >= 4:
            terimler.append(kelime)
    terimler += _ESANLAM.get(key, [])
    # tekilleştir, boşları at
    return [t for t in dict.fromkeys(terimler) if t]


def _ilk_konum(norm_text: str, terimler: List[str]) -> int:
    """Terimlerden herhangi birinin metindeki en erken konumu; yoksa -1."""
    en_erken = -1
    for t in terimler:
        idx = norm_text.find(t)
        if idx != -1 and (en_erken == -1 or idx < en_erken):
            en_erken = idx
    return en_erken


def check_sections(
    text: str,
    required_sections: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Raporun zorunlu başlıklarını ve içerik doluluğunu GERÇEKTEN tespit eder.

    `required_sections` verilirse (kategori/aşamaya özel set) o kullanılır.

    Returns: SectionCheckResult şemasına uygun sözlük.
    """
    hedef = required_sections if required_sections else REQUIRED_SECTIONS
    norm_text = _norm(text or "")
    kelimeler_toplam = len((text or "").split())

    # 1) Her bölüm için ilk konum
    konumlar: List[Tuple[str, int]] = []
    bulunan_pos: Dict[str, int] = {}
    for key, ad in hedef.items():
        pos = _ilk_konum(norm_text, _arama_terimleri(key, ad)) if norm_text else -1
        bulunan_pos[key] = pos
        if pos != -1:
            konumlar.append((key, pos))

    # 2) Bulunan başlıkları konuma göre sırala; aralardaki metni o bölüme say
    konumlar.sort(key=lambda x: x[1])
    span_kelime: Dict[str, int] = {}
    for i, (key, pos) in enumerate(konumlar):
        bitis = konumlar[i + 1][1] if i + 1 < len(konumlar) else len(norm_text)
        span = norm_text[pos:bitis]
        span_kelime[key] = len(span.split())

    # 3) Bölümleri kur
    sections: Dict[str, Dict[str, Any]] = {}
    for key, ad in hedef.items():
        pos = bulunan_pos[key]
        exists = pos != -1
        wc = span_kelime.get(key, 0)
        sections[key] = {
            "section_name": ad,
            "exists": exists,
            "word_count": wc,
            "status": classify_section(exists, wc),
        }

    found_count = sum(1 for s in sections.values() if s["status"] == STATUS_OK)
    return {
        "total_required": len(hedef),
        "found_count": found_count,
        "is_complete": found_count == len(hedef),
        "sections": sections,
    }
