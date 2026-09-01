"""Demo modu — jüri sunumu için kurgulanmış gezinti.

Neden var: canlı sunumda iki şey demoyu öldürür — (1) API/internet patlaması,
(2) doğru ekranı ve doğru raporu ararken kaybedilen saniyeler. Demo modu ikisini
de kapatır: veri kaynağını mock'a sabitler ve adımları sırayla önüne koyar.

Adımlar rapor kimliği ile SABİTLENMEZ; her adım bir SEÇİM KURALI taşır. Veri
değişse bile adım "şablon uyumsuz + benzerlik uyarısı olan rapor"u bulmaya
devam eder.
"""

from __future__ import annotations

from typing import Callable


def _temiz_ve_kanitli(r: dict) -> bool:
    k = r["kontroller"]
    return (r["durum"] not in ("hatali", "kuyrukta")
            and k["sablon"]["uygun"] and not k["basliklar"]["eksik"]
            and r["kategori_uygunlugu"]["skor"] >= 0.80
            and bool(r["kriterler"]))


def _sorunlu_kontroller(r: dict) -> bool:
    k = r["kontroller"]
    return (r["durum"] not in ("hatali", "kuyrukta")
            and (not k["sablon"]["uygun"] or len(k["basliklar"]["eksik"]) >= 2)
            and bool(r["kriterler"]))


def _benzerlik_uyarisi(r: dict) -> bool:
    return (r["durum"] not in ("hatali", "kuyrukta")
            and len(r["benzerlik"]) >= 1 and bool(r["kriterler"]))


def _islenemeyen(r: dict) -> bool:
    return r["durum"] == "hatali" and bool(r.get("hata"))


def _kuyrukta(r: dict) -> bool:
    return r["durum"] == "kuyrukta"


def _tamamlanmis(r: dict) -> bool:
    return r["durum"] == "tamamlandi" and bool(r["kriterler"])


# (ekran, başlık, anlatım, rapor seçim kuralı | None)
ADIMLAR: list[tuple[str, str, str, Callable[[dict], bool] | None]] = [
    ("yonetici", "Yarışma tanımı şartnameden gelir",
     "Kriterler ve ağırlıklar koda gömülü değil. Yarışma seçilince rubrik "
     "değişiyor — sistem TEKNOFEST'in tüm yarışmalarında aynı motorla çalışıyor.",
     None),
    ("hakem", "Otomatik kontroller · temiz rapor",
     "Dil, şablon ve zorunlu başlık kontrolleri geçmiş bir rapor. Hakem hangi "
     "kontrolün neden geçtiğini görüyor.",
     _temiz_ve_kanitli),
    ("hakem", "Kanıta dayalı puanlama",
     "Her AI puanının altında rapordan alınmış cümle var. 'Kanıtı raporda gör' "
     "düğmesi PDF'in ilgili sayfasını işaretli olarak açıyor — 'neden bu puan?' "
     "sorusunun cevabı ekranda.",
     _temiz_ve_kanitli),
    ("hakem", "Şablon uyumsuzluğu ve eksik başlık",
     "Aynı ekran, sorunlu bir raporda. Bulgular tek tek listeleniyor; hakem "
     "puanı buna göre düzeltiyor ve fark anında hesaplanıyor.",
     _sorunlu_kontroller),
    ("hakem", "Benzerlik uyarısı",
     "Eşiği geçen benzerlik hakem incelemesi için işaretlenir. Bu bir intihal "
     "kararı değil — karar hakemde.",
     _benzerlik_uyarisi),
    ("hakem", "İşlenemeyen rapor · dürüst hata",
     "Taranmış, bozuk veya parola korumalı dosyada sistem puan uydurmuyor. "
     "Ne olduğunu, nedenini ve yapılacak işlemi söylüyor.",
     _islenemeyen),
    ("karsilastirma", "AI ↔ Hakem · gerçek vaka",
     "Gerçek bir TEKNOFEST başvurusu. Hakem 73 verdi; motor puanları görmeden "
     "62,5 verdi ve aynı zayıf noktayı buldu: sonuç bölümünde ölçülmüş çıktı yok.",
     None),
    ("yarismaci", "Yarışmacı karnesi",
     "Yarışmacı puanını, güçlü yönlerini ve somut gelişim önerilerini görüyor; "
     "karneyi PDF olarak indirebiliyor.",
     _tamamlanmis),
    ("dashboard", "Operasyon panosu",
     "Değerlendirme yöneticisi tamamlanma oranını, bekleyenleri, sorunlu "
     "dosyaları ve benzerlik uyarılarını tek ekranda izliyor.",
     None),
]


def adim_sayisi() -> int:
    return len(ADIMLAR)


def adim(no: int) -> dict:
    """1'den başlayan adım numarası için adım bilgisi."""
    no = max(1, min(no, len(ADIMLAR)))
    ekran, baslik, anlatim, kural = ADIMLAR[no - 1]
    return {"no": no, "ekran": ekran, "baslik": baslik,
            "anlatim": anlatim, "kural": kural}


def rapor_sec(kural, raporlar: list[dict]) -> str | None:
    """Adımın kuralına uyan ilk raporun kimliği."""
    if kural is None:
        return None
    for r in raporlar:
        try:
            if kural(r):
                return r["rapor_id"]
        except Exception:
            continue
    return None
