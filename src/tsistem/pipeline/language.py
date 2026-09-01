"""Türkçe / İngilizce dil tespiti.

Neden hazır kütüphane değil:
  * langdetect kısa metinlerde kararsız ve C derleyici gerektiriyor.
  * Bizim ihtiyacımız iki dilli (TR/EN) ikili karar + güven skoru.
  * Teknik raporlarda İngilizce terim yoğunluğu yüksek olduğu için
    saf n-gram yaklaşımı yanılıyor; stopword + karakter sinyalini birleştiriyoruz.

Yöntem: ayırt edici stopword frekansı + Türkçeye özgü karakterler (ı, ğ, ş, ç, ö, ü)
ve Türkçe ekler (-ler/-lar/-dır/-tır) sinyallerinin ağırlıklı toplamı.
"""

from __future__ import annotations

import re
from collections import Counter

from ..models import Language

# Sadece tek dilde sık geçen, teknik metinde de bulunan kelimeler seçildi.
TR_STOPWORDS = {
    "ve", "ile", "bir", "bu", "için", "olarak", "daha", "veya", "gibi", "ancak",
    "ayrıca", "çok", "kadar", "sonra", "önce", "hem", "de", "da", "ki", "ise",
    "olan", "olduğu", "edilen", "yapılan", "üzerinde", "tarafından", "amacıyla",
    "böylece", "ayrıntılı", "çalışma", "sistem", "veri", "sonuç", "yöntem",
}
EN_STOPWORDS = {
    "the", "and", "of", "to", "in", "is", "are", "for", "with", "that", "this",
    "as", "be", "by", "on", "from", "it", "an", "which", "was", "were", "has",
    "have", "can", "will", "our", "we", "these", "their", "such", "been",
}

TR_CHARS = set("ıİğĞşŞçÇöÖüÜ")
TR_SUFFIX_RE = re.compile(
    r"\w+(ler|lar|dır|dir|dur|dür|tır|tir|tur|tür|mış|miş|muş|müş|"
    r"nın|nin|nun|nün|ının|inin|sının|larının|lerinin)\b",
    re.IGNORECASE,
)
WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def detect_language(text: str, sample_chars: int = 20_000) -> tuple[Language, float]:
    """Metnin dilini ve 0-1 arası güven skorunu döner.

    Güven skoru = kazanan dilin normalize edilmiş sinyal payı.
    Çok kısa veya alfabetik içerik barındırmayan metinlerde UNKNOWN döner.
    """
    sample = text[:sample_chars]
    words = [w.lower() for w in WORD_RE.findall(sample)]
    if len(words) < 20:
        return Language.UNKNOWN, 0.0

    counts = Counter(words)
    total = len(words)

    tr_stop = sum(counts[w] for w in TR_STOPWORDS)
    en_stop = sum(counts[w] for w in EN_STOPWORDS)

    tr_char_hits = sum(1 for ch in sample if ch in TR_CHARS)
    tr_char_ratio = tr_char_hits / max(len(sample), 1)

    suffix_hits = len(TR_SUFFIX_RE.findall(sample))
    suffix_ratio = suffix_hits / total

    # Sinyalleri karşılaştırılabilir ölçeğe getir.
    tr_signal = (
        (tr_stop / total) * 1.0
        + min(tr_char_ratio * 12.0, 0.45)     # ~%3.5 TR karakter -> tavan
        + min(suffix_ratio * 1.5, 0.35)
    )
    en_signal = (en_stop / total) * 1.0

    # Türkçe karakter hiç yoksa TR ihtimalini bastır (İngilizce rapor sinyali).
    if tr_char_hits == 0:
        tr_signal *= 0.35

    denom = tr_signal + en_signal
    if denom <= 1e-9:
        return Language.UNKNOWN, 0.0

    if tr_signal >= en_signal:
        return Language.TR, round(tr_signal / denom, 4)
    return Language.EN, round(en_signal / denom, 4)
