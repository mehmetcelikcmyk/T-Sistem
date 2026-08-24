"""
Yarışma Kategorisi Anlamsal Uygunluk Kontrolörü — GERÇEK ÖLÇÜM (bağımlılıksız)

SÖZLEŞME (bkz. docs/ENTEGRASYON_SOZLESMESI.md):
  check_category_alignment() çıktısı src/api/schemas.py -> CategoryCheckResult
  şemasına BİREBİR uymak zorundadır. Alan adları değiştirilemez.

Yöntem: Harici embedding/model olmadan, her yarışma alanı için tanımlı bir
anahtar-terim sözlüğü (_ALAN_SOZLUGU) ile raporun özet/gövde metni Türkçe-normalize
edilip terim örtüşmesi (kaç ayrı alan terimi geçiyor) ölçülür. Örtüşme oranı
0.40 taban + 0.60 ölçekle bir "anlamsal benzerlik" skoruna çevrilir. Böylece
embedding altyapısı gelene kadar gerçek, açıklanabilir bir sinyal üretilir.
"""
from typing import Dict, Any, List
import re
import unicodedata

# Bu eşiğin altındaki anlamsal benzerlik "kategori uyumsuz" sayılır (kalibrasyondan okunur)
CATEGORY_ALIGNMENT_THRESHOLD = 0.60

# Yarışma alanı -> o alana özgü teknik terimler (normalize edilmiş biçimde eşleşir)
_ALAN_SOZLUGU: Dict[str, List[str]] = {
    "roket": ["roket", "irtifa", "motor", "itki", "yakit", "govde", "burun", "kanatcik",
              "paralel", "kurtarma", "paraşut", "parasut", "aviyonik", "faydali yuk",
              "ateşleme", "atesleme", "balistik", "apoje", "mach"],
    "iha": ["iha", "insansiz", "hava araci", "kanat", "otonom", "gorev", "ucus",
            "sabit kanat", "döner kanat", "doner kanat", "pilot", "kamera", "telemetri",
            "yer istasyonu", "irtifa", "manevra"],
    "uydu": ["uydu", "model uydu", "gorev yuku", "telemetri", "sensor", "basinc",
             "gps", "ivme", "jiroskop", "yer istasyonu", "inis", "kurtarma",
             "veri", "haberleşme", "haberlesme", "yörünge", "yorunge"],
    "otonom": ["otonom", "arac", "gorüntü işleme", "goruntu isleme", "lidar", "sensor",
               "yol", "serit", "trafik", "engel", "navigasyon", "ros", "kontrol"],
    "yapay zeka": ["yapay zeka", "model", "veri seti", "veri kümesi", "veri kumesi",
                   "egitim", "eğitim", "sinir agi", "sinir ağı", "derin ogrenme",
                   "derin öğrenme", "siniflandirma", "sınıflandırma", "dogruluk",
                   "doğruluk", "algoritma", "etiket", "tahmin"],
    "saglik": ["saglik", "sağlık", "hasta", "teşhis", "teshis", "tıbbi", "tibbi",
               "klinik", "goruntuleme", "görüntüleme", "biyomedikal", "tedavi"],
    "tarim": ["tarim", "tarım", "sulama", "toprak", "urun", "ürün", "sera", "hasat",
              "gubre", "gübre", "verim", "sensor", "drone"],
    "enerji": ["enerji", "verim", "gunes", "güneş", "panel", "batarya", "sarj", "şarj",
               "yenilenebilir", "elektrik", "guc", "güç", "tuketim", "tüketim"],
    "egitim": ["egitim", "eğitim", "ogrenci", "öğrenci", "ogretim", "öğretim", "ders",
               "mufredat", "müfredat", "pedagoji", "oyunlaştirma", "oyunlastirma"],
    "savunma": ["savunma", "güvenlik", "guvenlik", "tespit", "radar", "hedef",
                "sistem", "tehdit", "izleme", "şifreleme", "sifreleme"],
    "haberlesme": ["haberlesme", "haberleşme", "sinyal", "anten", "frekans", "modülasyon",
                   "modulasyon", "protokol", "ag", "ağ", "veri iletimi", "bant"],
    "cevre": ["cevre", "çevre", "atik", "atık", "geri donusum", "geri dönüşüm",
              "kirlilik", "surdurulebilir", "sürdürülebilir", "karbon", "su", "hava kalitesi"],
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


def _kategori_terimleri(category_name: str) -> List[str]:
    """Kategori adına en iyi uyan alan sözlüğünü seçip terimlerini döndürür."""
    norm_ad = _norm(category_name)
    # Kategori adında geçen alan anahtarlarına göre terim topla
    terimler: List[str] = []
    for alan, kelimeler in _ALAN_SOZLUGU.items():
        if _norm(alan) in norm_ad or any(_norm(k) in norm_ad for k in kelimeler[:3]):
            terimler += [_norm(k) for k in kelimeler]
    # Hiç eşleşme yoksa: kategori adının kendi anlamlı kelimeleri terim olur
    if not terimler:
        for kelime in norm_ad.replace("/", " ").replace("-", " ").split():
            if len(kelime) >= 4:
                terimler.append(kelime)
    # tekilleştir
    return [t for t in dict.fromkeys(terimler) if t]


def _esik() -> float:
    try:
        from src.utils.calibration import get_threshold
        return float(get_threshold("category_alignment_threshold", CATEGORY_ALIGNMENT_THRESHOLD))
    except Exception:
        return CATEGORY_ALIGNMENT_THRESHOLD


def check_category_alignment(report_summary: str, category_name: str) -> Dict[str, Any]:
    """
    Raporun başvurduğu kategoriyle anlamsal uygunluk derecesini GERÇEKTEN ölçer.

    Yöntem: kategoriye özgü terim kümesinin rapor metninde ne oranda geçtiği.
    Embedding altyapısı geldiğinde (Birhan) bu fonksiyonun içi kosinüs
    benzerliğiyle değiştirilebilir; DÖNÜŞ YAPISI aynı kalır.

    Returns:
        {applied_category, is_aligned, semantic_similarity, explanation}
    """
    esik = _esik()
    terimler = _kategori_terimleri(category_name)
    norm_metin = _norm(report_summary or "")

    if not terimler or not norm_metin:
        # Ölçüm yapılamıyor: yarışmacı aleyhine karar verme, nötr-yüksek dön ama düşük güvenle.
        semantic_similarity = 0.60
        is_aligned = semantic_similarity >= esik
        return {
            "applied_category": category_name,
            "is_aligned": is_aligned,
            "semantic_similarity": round(semantic_similarity, 2),
            "explanation": (
                f"'{category_name}' kategorisi için otomatik anlamsal ölçüm yapılamadı "
                f"(yetersiz metin veya tanımlı terim yok); hakem değerlendirmesi önerilir."
            ),
        }

    eslesen = sum(1 for t in terimler if t in norm_metin)
    oran = eslesen / len(terimler)

    # 0.40 taban + 0.60 ölçek: hiç terim geçmese bile mutlak 0 vermeyip
    # "büyük olasılıkla uyumsuz" bölgesinde tutar; tam örtüşmede ~1.0'a yaklaşır.
    semantic_similarity = min(0.99, 0.40 + 0.60 * oran)
    is_aligned = semantic_similarity >= esik

    return {
        "applied_category": category_name,
        "is_aligned": is_aligned,
        "semantic_similarity": round(float(semantic_similarity), 2),
        "explanation": (
            f"Rapor metninde '{category_name}' kategorisine ait {len(terimler)} teknik "
            f"terimden {eslesen} tanesi tespit edildi (%{oran * 100:.0f} örtüşme); "
            f"anlamsal uyum %{semantic_similarity * 100:.0f}."
            + ("" if is_aligned else " Eşik altında; kategori uygunluğu hakemce gözden geçirilmelidir.")
        ),
    }
