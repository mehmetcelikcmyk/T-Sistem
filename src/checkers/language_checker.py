"""
Rapor Dili Tespit Modülü — GERÇEK TESPİT (bağımlılıksız)

SÖZLEŞME: check_language() çıktısı LanguageCheckResult şemasına birebir uyar.

Yöntem: harici bir kütüphaneye (langdetect vb.) bağlanmadan, Türkçe'ye özgü
karakterler (ç, ğ, ı, İ, ö, ş, ü) ve iki dilin sık kelimeleri (stopword) üzerinden
skorlama. Böylece Windows DLL politikası veya kurulum eksikliği sorun çıkarmaz.
"""
from typing import Dict, Any
import re

SUPPORTED_LANGUAGES = ("tr", "en")

_TR_STOP = {
    "ve", "bir", "bu", "için", "ile", "olarak", "da", "de", "çok", "daha",
    "ancak", "ya", "veya", "gibi", "kadar", "sonra", "önce", "ise", "değil",
    "olan", "tarafından", "üzerine", "ayrıca", " hem", "yani",
}
_EN_STOP = {
    "the", "and", "of", "to", "in", "is", "for", "on", "with", "as", "by",
    "that", "this", "are", "be", "an", "or", "from", "at", "was", "which",
}
_TR_CHARS = set("çğıİöşü")


def check_language(text: str, expected_lang: str = "tr") -> Dict[str, Any]:
    """
    Rapor metninin dilini tespit eder ve şartnameye uygunluğunu doğrular.

    Returns:
        {detected_lang, expected_lang, is_valid, confidence}
    """
    ham = (text or "").strip()
    if len(ham) < 20:
        # Yeterli metin yok: şüpheden yarışmacı yararlanır, güven düşük.
        return {
            "detected_lang": expected_lang,
            "expected_lang": expected_lang,
            "is_valid": True,
            "confidence": 0.0,
        }

    dusuk = ham.lower()
    kelimeler = re.findall(r"[a-zçğıiöşü]+", dusuk)
    toplam = len(kelimeler) or 1

    tr_stop = sum(1 for k in kelimeler if k in _TR_STOP)
    en_stop = sum(1 for k in kelimeler if k in _EN_STOP)
    tr_char_orani = sum(1 for ch in dusuk if ch in _TR_CHARS) / max(len(dusuk), 1)

    # Puanlama: Türkçe karakter yoğunluğu güçlü sinyal; stopword oranları destekler.
    tr_skor = (tr_stop / toplam) * 1.0 + tr_char_orani * 8.0
    en_skor = (en_stop / toplam) * 1.0

    if tr_skor >= en_skor:
        detected = "tr"
        guven = min(0.99, 0.55 + tr_char_orani * 6 + (tr_stop / toplam) * 2)
    else:
        detected = "en"
        guven = min(0.99, 0.55 + (en_stop / toplam) * 3)

    return {
        "detected_lang": detected,
        "expected_lang": expected_lang,
        "is_valid": detected == expected_lang,
        "confidence": round(float(guven), 2),
    }
