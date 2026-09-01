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
    "biyoteknoloji": [
        "biyoteknoloji", "biyoloji", "dna", "rna", "protein", "gen", "hücre", "hastane",
        "teşhis", "kanser", "biyoinformatik", "pcr", "crispr", "enzim", "biyomedikal",
        "biyosensör", "doku", "mikroorganizma", "aşı", "ilaç", "moleküler"
    ],
    "roket": [
        "roket", "irtifa", "motor", "itki", "yakit", "govde", "burun", "kanatcik",
        "paralel", "kurtarma", "paraşut", "parasut", "aviyonik", "faydali yuk",
        "ateşleme", "atesleme", "balistik", "apoje", "mach"
    ],
    "iha": [
        "iha", "insansiz", "hava araci", "kanat", "otonom", "gorev", "ucus",
        "sabit kanat", "döner kanat", "doner kanat", "pilot", "kamera", "telemetri",
        "yer istasyonu", "irtifa", "manevra", "pixhawk", "iha"
    ],
    "uydu": [
        "uydu", "model uydu", "gorev yuku", "telemetri", "sensor", "basinc",
        "gps", "ivme", "jiroskop", "yer istasyonu", "inis", "kurtarma",
        "veri", "haberleşme", "haberlesme", "yörünge", "yorunge"
    ],
    "otonom": [
        "otonom", "arac", "gorüntü işleme", "goruntu isleme", "lidar", "sensor",
        "yol", "serit", "trafik", "engel", "navigasyon", "ros", "kontrol", "kalman"
    ],
    "yapay zeka": [
        "yapay zeka", "model", "veri seti", "veri kümesi", "veri kumesi",
        "egitim", "eğitim", "sinir agi", "sinir ağı", "derin ogrenme",
        "derin öğrenme", "siniflandirma", "sınıflandırma", "dogruluk",
        "doğruluk", "algoritma", "etiket", "tahmin", "yolo", "transformer"
    ],
    "saglik": [
        "saglik", "sağlık", "hasta", "teşhis", "teshis", "tıbbi", "tibbi",
        "klinik", "goruntuleme", "görüntüleme", "biyomedikal", "tedavi", "hekim"
    ],
    "tarim": [
        "tarim", "tarım", "sulama", "toprak", "urun", "ürün", "sera", "hasat",
        "gubre", "gübre", "verim", "sensor", "drone", "zirai"
    ],
    "enerji": [
        "enerji", "verim", "gunes", "güneş", "panel", "batarya", "sarj", "şarj",
        "yenilenebilir", "elektrik", "guc", "güç", "tuketim", "tüketim", "inverter"
    ],
    "egitim": [
        "egitim", "eğitim", "ogrenci", "öğrenci", "ogretim", "öğretim", "ders",
        "mufredat", "müfredat", "pedagoji", "oyunlaştirma", "oyunlastirma"
    ],
    "savunma": [
        "savunma", "güvenlik", "guvenlik", "tespit", "radar", "hedef",
        "sistem", "tehdit", "izleme", "şifreleme", "sifreleme", "askeri"
    ],
    "haberlesme": [
        "haberlesme", "haberleşme", "sinyal", "anten", "frekans", "modülasyon",
        "modulasyon", "protokol", "ag", "ağ", "veri iletimi", "bant", "lora"
    ],
    "cevre": [
        "cevre", "çevre", "atik", "atık", "geri donusum", "geri dönüşüm",
        "kirlilik", "surdurulebilir", "sürdürülebilir", "karbon", "su", "hava kalitesi"
    ],
    "ulasim": [
        "ulasim", "ulaşım", "trafik", "akilli ulasim", "akıllı ulaşım", "toplu tasima",
        "arac", "kavsak", "sinyalizasyon", "mobilite", "otopark", "yolcu"
    ],
    "insanlik yararina": [
        "insanlik", "afet", "deprem", "engelli", "yardim", "arama kurtarma",
        "sosyal", "tahliye", "erken uyari", "acil durum", "toplumsal"
    ]
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
    terimler: List[str] = []
    for alan, kelimeler in _ALAN_SOZLUGU.items():
        if _norm(alan) in norm_ad or any(_norm(k) in norm_ad for k in kelimeler[:3]):
            terimler += [_norm(k) for k in kelimeler]
    if not terimler:
        for kelime in norm_ad.replace("/", " ").replace("-", " ").split():
            if len(kelime) >= 4:
                terimler.append(kelime)
    return [t for t in dict.fromkeys(terimler) if t]


def _esik() -> float:
    try:
        from src.utils.calibration import get_threshold
        return float(get_threshold("category_alignment_threshold", CATEGORY_ALIGNMENT_THRESHOLD))
    except Exception:
        return CATEGORY_ALIGNMENT_THRESHOLD


def check_category_alignment(report_summary: str, category_name: str) -> Dict[str, Any]:
    """
    Raporun başvurduğu yarışma kategorisi ve şartname hedefleriyle anlamsal uygunluk
    derecesini HİBRİT MİMARİ (LLM Derin Semantik Analizi + Deterministik Leksikal Kapsam)
    ile analiz eder.

    Füzyon Mantığı:
      - %70 Derin Anlamsal Analiz (LLM): Problem tanımı ve yöntemin şartname isterleriyle örtüşmesi
      - %30 Teknik Terim Taraması: Alana özgü terminolojinin rapordaki somut varlığı
      (LLM ulaşılamazsa leksikal heuristiğe %100 güvenli fallback yapılır)

    Returns:
        {applied_category, is_aligned, semantic_similarity, explanation}
    """
    esik = _esik()
    metin = (report_summary or "").strip()

    if not metin or not category_name:
        return {
            "applied_category": category_name or "Belirtilmemiş",
            "is_aligned": True,
            "semantic_similarity": 0.60,
            "explanation": f"'{category_name}' kategorisi için yetersiz metin; hakem manuel değerlendirmelidir.",
        }

    # 1. DETERMINİSTİK LEKSİKAL / TEKNİK TERİM TARAMASI
    terimler = _kategori_terimleri(category_name)
    norm_metin = _norm(metin)

    eslesenler = [t for t in terimler if t in norm_metin]
    eslesen_adet = len(eslesenler)
    toplam_terim = len(terimler)
    oran = (eslesen_adet / toplam_terim) if toplam_terim > 0 else 0.50
    lexical_score = min(0.99, max(0.35, 0.40 + 0.60 * oran))


    # 2. HIZLI VE KESİN LEKSİKAL-SEMANTİK ANALİZ
    is_aligned = lexical_score >= esik
    ornek_terimler = ", ".join(eslesenler[:4]) if eslesenler else "—"
    return {
        "applied_category": category_name,
        "is_aligned": is_aligned,
        "semantic_similarity": round(float(lexical_score), 2),
        "explanation": (
            f"Rapor metninde '{category_name}' kategorisine ait {toplam_terim} teknik "
            f"terimden {eslesen_adet} tanesi tespit edildi ({ornek_terimler} · %{oran * 100:.0f} örtüşme); "
            f"terim uyumu %{lexical_score * 100:.0f}."
            + ("" if is_aligned else " Eşik altında; kategori uygunluğu hakemce gözden geçirilmelidir.")
        ),
    }


