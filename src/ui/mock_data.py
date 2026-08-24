"""Mock veri üreteci.

Backend hazır olmadan arayüzün tamamını geliştirmek ve demo yapmak için.
Üretilen yapı `contracts/analiz_sonucu.schema.json` ile birebir aynıdır —
gerçek API geldiğinde arayüzde tek satır değişmez.

Tohum (seed) sabit: her çalıştırmada aynı veri gelir, demo tekrarlanabilir olur.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta

import pdf_gorunum
import rubrik

SEED = 20260819

KATEGORILER = [
    "İnsanlık Yararına Teknoloji",
    "Sağlıkta Yapay Zekâ",
    "Akıllı Ulaşım",
    "Tarım Teknolojileri",
    "Savunma Sanayii Dijital Teknolojiler",
]

# Kriterler artık burada tanımlı DEĞİL — seçilen yarışmanın rubriğinden gelir.
# Bkz. rubrik.py

# Gerçek "2026 HYZ ÖTR TR" şablonundan
ZORUNLU_BASLIKLAR = [
    "TAKIM ŞEMASI", "PROJE MEVCUT DURUM DEĞERLENDİRMESİ",
    "ALGORİTMALAR VE SİSTEM MİMARİSİ", "Veri Setleri", "Algoritmalar",
    "Akış Şeması", "ÖZGÜNLÜK", "PROJE TAKVİMİ", "SONUÇLAR VE İNCELEME",
    "KAYNAKÇA",
]

PROJE_ADLARI = [
    "Otonom Sera İklim Yönetimi", "Erken Uyarı Sismik Ağ", "Görü Destekli İHA Seyrüsefer",
    "Yapay Zekâ Destekli Tarımsal Zararlı Tespiti", "Akıllı Kavşak Optimizasyonu",
    "Taşınabilir Kan Analiz Cihazı", "Enerji Verimli Bina Otomasyonu",
    "Dil Öğrenme Asistanı", "Atık Ayrıştırma Robotu", "Kıyı Kirliliği İzleme Sistemi",
    "Deniz Altı Haritalama Aracı", "Yangın Yayılım Tahmin Modeli",
    "Depo İçi Otonom Taşıyıcı", "İşitme Engelliler İçin Çeviri Eldiveni",
    "Hassas Tarım Sulama Kontrolü", "Sanal Kombin Öneri Motoru",
    "Rüzgâr Türbini Arıza Kestirimi", "Trafik Yoğunluğu Tahmin Ağı",
    "Uzaktan Hasta Takip Platformu", "Mikroplastik Tespit Sensörü",
    "Şehir İçi Kargo Drone Ağı", "Sera Gazı Ölçüm İstasyonu",
    "Otonom Hassas İniş Sistemi", "Arı Kovanı Sağlık İzleme",
]

GEREKCELER_KULLANILMIYOR = {
    "ozgunluk": [
        "Literatürdeki benzer çalışmalardan ayrışan bir yöntem tanımlanmış; ancak farkın niceliksel karşılaştırması sunulmamış.",
        "Problem tanımı özgün, çözüm yaklaşımı büyük ölçüde mevcut açık kaynak yöntemlerin birleşimi.",
        "Yaklaşım hem problem seçimi hem yöntem kurgusu açısından özgün; karşılaştırmalı tablo ile desteklenmiş.",
    ],
    "teknik_derinlik": [
        "Mimari şeması ve algoritma akışı verilmiş, doğrulama testleri ve metrikler eksik.",
        "Yöntem matematiksel olarak tanımlanmış, hata analizi ve sınır koşulları tartışılmış.",
        "Teknik anlatım yüzeysel; kullanılan modellerin seçim gerekçesi belirtilmemiş.",
    ],
    "uygulanabilirlik": [
        "Donanım listesi ve maliyet tablosu gerçekçi; takvim iyimser ancak kabul edilebilir.",
        "Uygulama planı takvimlendirilmiş fakat kritik bağımlılıklar ve risk planı tanımsız.",
        "Prototip seviyesi net, saha koşullarında doğrulama adımı planlanmamış.",
    ],
    "etki": [
        "Hedef kitle ve ölçülebilir fayda tanımlı; yaygınlaştırma senaryosu zayıf.",
        "Toplumsal etki nitel olarak anlatılmış, sayısal bir hedef verilmemiş.",
        "Etki alanı geniş ve sayısallaştırılmış; sürdürülebilirlik modeli açıklanmış.",
    ],
    "sunum": [
        "Rapor akıcı; görsel ve tablolar metinle ilişkilendirilmiş.",
        "Anlatım yer yer tekrara düşüyor, şekil numaralandırmaları tutarsız.",
        "Dil ve biçim kurallarına uyum yüksek, kaynak gösterimi standarda uygun.",
    ],
}

# Kalite seviyesine göre gerekçe kalıpları — her kriterde kullanılabilir.
GEREKCE_KALIPLARI = {
    "yuksek": [
        "Bölüm somut çıktılarla desteklenmiş; ölçülmüş değerler ve karşılaştırma tablosu sunulmuş.",
        "Yöntem gerekçelendirilmiş, seçim kriterleri sayısal olarak karşılaştırılmış.",
        "Anlatım eksiksiz; iddialar kaynak ve ölçümle birlikte verilmiş.",
    ],
    "orta": [
        "Yaklaşım doğru kurgulanmış ancak başarımı gösteren niceliksel sonuç paylaşılmamış.",
        "Bölüm gerekli içeriği barındırıyor; derinlik ve doğrulama kısmı zayıf kalmış.",
        "Planlama tutarlı fakat kritik bağımlılıklar ve riskler açıkça tanımlanmamış.",
    ],
    "dusuk": [
        "Bölüm genel geçer ifadelerle sınırlı; ölçülebilir bir çıktı ya da veri yok.",
        "Beklenen içerik büyük ölçüde eksik; iddialar dayanaksız bırakılmış.",
        "Bölüm yüzeysel; yöntem, sonuç ve gerekçe ilişkisi kurulmamış.",
    ],
}

ALINTILAR = [
    "Önerilen yöntem, GPS sinyalinin bulunmadığı ortamlarda tek kameralı görüntü akışından konum kestirimi yapmaktadır.",
    "Sistem, saha testlerinde ortalama 12 cm konum hatası ile çalışmıştır.",
    "Maliyet analizi kapsamında toplam donanım bütçesi 48.500 TL olarak hesaplanmıştır.",
    "Proje kapsamında geliştirilen model, mevcut yaklaşımlara göre %18 daha az işlem gücü tüketmektedir.",
    "Hedef kullanıcı grubu, yıllık yaklaşık 40.000 küçük ölçekli üreticiyi kapsamaktadır.",
    "Prototip, 6 haftalık bir geliştirme takvimi sonunda laboratuvar ortamında doğrulanmıştır.",
]

GUCLU_YONLER = [
    "Problem tanımı sahadan veriyle desteklenmiş, gerçek bir ihtiyaca dayanıyor.",
    "Yöntem bölümünde algoritma akışı adım adım ve tekrarlanabilir biçimde anlatılmış.",
    "Maliyet tablosu kalem kalem verilmiş; bütçe gerçekçi.",
    "Ekip yetkinlikleri ile projenin teknik gereksinimleri örtüşüyor.",
    "Görsel ve tablolar metinle doğru ilişkilendirilmiş, okunabilirlik yüksek.",
]

GELISIM_ONERILERI = [
    "Yöntemin başarımını gösteren niceliksel bir doğrulama tablosu ekleyin (metrik, veri kümesi, sonuç).",
    "Benzer çalışmalarla karşılaştırma bölümü ekleyip özgün değeri sayısallaştırın.",
    "Risk analizi ve B planı bölümü ekleyin; kritik bağımlılıkları belirtin.",
    "Kaynakça gösterimini şablondaki referans stiline uyarlayın.",
    "Sonuç bölümünde ölçülebilir hedefler tanımlayın (ör. hata oranı, kullanıcı sayısı).",
    "Şekil ve tablo numaralandırmalarını metin içi atıflarla eşleştirin.",
]

# Gerçekte karşılaşılan işlenemezlik nedenleri. Her biri arayüzde farklı
# davranış gerektirir: kimi yeniden yükleme, kimi OCR, kimi elle inceleme.
HATA_TURLERI = {
    "taranmis": {
        "baslik": "Rapor taranmış görüntü — metin katmanı yok",
        "aciklama": "PDF içinde seçilebilir metin bulunmuyor; sayfalar görüntü olarak "
                    "kaydedilmiş. Bu haliyle dil, şablon, başlık ve kriter analizi yapılamaz.",
        "cozum": "OCR ile metin katmanı üretilmeli veya yarışmacıdan metin tabanlı PDF istenmeli.",
        "hakem_karar": False,
    },
    "bozuk_pdf": {
        "baslik": "Dosya açılamadı — PDF yapısı bozuk",
        "aciklama": "Dosya eksik ya da hatalı aktarılmış; PDF okuyucu belgeyi açamıyor.",
        "cozum": "Yarışmacıdan dosyanın yeniden yüklenmesi istenmeli.",
        "hakem_karar": False,
    },
    "sifreli": {
        "baslik": "Dosya parola korumalı",
        "aciklama": "PDF şifreli; içeriğe erişilemiyor.",
        "cozum": "Yarışmacıdan korumasız sürüm istenmeli.",
        "hakem_karar": False,
    },
    "bos": {
        "baslik": "Rapor içeriği yok denecek kadar az",
        "aciklama": "Belgede anlamlı metin bulunmuyor (yanlış dosya yüklenmiş olabilir).",
        "cozum": "Yarışmacıdan doğru dosyanın yüklenmesi istenmeli.",
        "hakem_karar": False,
    },
}

# Hakem havuzu — yük dağılımı ve uyum trendi bunlar üzerinden hesaplanır.
HAKEMLER = [
    "Dr. A. Yılmaz", "Doç. Dr. S. Demir", "Dr. M. Kaya",
    "Prof. Dr. E. Aydın", "Dr. B. Şahin",
]

SABLON_BULGULARI = [
    "Kapak sayfasındaki yarışma kategorisi alanı boş bırakılmış.",
    "Sayfa numaralandırması 3. sayfadan başlıyor, şablon 1'den istiyor.",
    "Kaynakça biçimi şablondaki referans stiliyle uyuşmuyor.",
    "Başlık hiyerarşisi şablondaki 3 seviyeli yapıya uymuyor.",
]


# Sorunlu dosyalar demoda bilinçli olarak azdır: her hata türünden bir örnek
# yeter, kalan raporlar sağlam dosyalara bağlanır.
SORUNLU_SIRALAR = (3, 9, 16, 21)


def _ornek_dosya(i: int) -> str | None:
    dosyalar = pdf_gorunum.ornek_raporlar()
    if not dosyalar:
        return None
    saglam = [d for d in dosyalar if pdf_gorunum.dosya_durumu(d) == "tamam"]
    sorunlu = [d for d in dosyalar if pdf_gorunum.dosya_durumu(d) != "tamam"]

    if sorunlu and i in SORUNLU_SIRALAR:
        return sorunlu[SORUNLU_SIRALAR.index(i) % len(sorunlu)]
    havuz = saglam or list(dosyalar)
    return havuz[i % len(havuz)]


def _rapor(rng: random.Random, i: int, yarisma_kategorileri: list[str],
           yarisma: dict) -> dict:
    # Rapora gerçek bir örnek PDF bağlanır; kanıt alıntıları o PDF'ten
    # seçilir. Böylece "kanıtı raporda gör" gerçekten çalışır.
    dosya = _ornek_dosya(i)
    havuz = pdf_gorunum.cumleler(dosya) if dosya else []
    sayfa_cumleleri = pdf_gorunum.sayfa_cumleleri_getir(dosya) if dosya else {}
    toplam_sayfa = pdf_gorunum.sayfa_sayisi_getir(dosya) if dosya else 15

    # Hata türü dosyanın GERÇEK halinden okunur; rastgele atanmaz.
    dosya_hali = pdf_gorunum.dosya_durumu(dosya) if dosya else "dosya_yok"
    kategori = rng.choice(yarisma_kategorileri)
    durum = rng.choices(
        ["tamamlandi", "hakem_bekliyor", "ai_analiz_tamam", "kuyrukta", "hatali"],
        weights=[46, 22, 16, 10, 6],
    )[0]

    eksik_sayisi = rng.choices([0, 0, 0, 1, 2, 3], weights=[40, 15, 10, 18, 12, 5])[0]
    eksik = rng.sample(ZORUNLU_BASLIKLAR[3:], eksik_sayisi) if eksik_sayisi else []

    bolumler = []
    for baslik in ZORUNLU_BASLIKLAR:
        if baslik in eksik:
            continue
        kelime = rng.randint(60, 900)
        doluluk = min(1.0, round(kelime / 600, 2))
        bolumler.append({
            "baslik": baslik,
            "kelime_sayisi": kelime,
            "doluluk": doluluk,
            "yeterli": kelime >= 150,
            "not": "" if kelime >= 150 else "Bölüm beklenen içeriğe göre zayıf.",
        })

    dil_uygun = rng.random() > 0.08
    sablon_uygun = rng.random() > 0.30

    kriterler = []
    # Bölümlere göre sayfa eşleşme tablosu (ÖTR şablon yapısı)
    BOLUM_SAYFA_HARITASI = {
        "1": [3],
        "2": [3, 4],
        "3.1": [4, 5],
        "3.2": [5],
        "3.3": [5, 6],
        "4": [6],
        "5": [7],
        "6": [7, 8],
        "7": [9],
    }

    for idx, kr in enumerate(yarisma["kriterler"]):
        # Oran olarak puan üret, sonra kriterin kendi tavanına ölçekle.
        oran = rng.choices([0.30, 0.55, 0.70, 0.85, 0.95],
                           weights=[8, 18, 30, 30, 14])[0]
        puan = round(kr["maks"] * oran * 2) / 2      # 0.5 adımlarına yuvarla
        seviye = "yuksek" if oran >= 0.85 else ("orta" if oran >= 0.55 else "dusuk")
        
        # Bu kritere uygun kanıt cümlelerini ilgili sayfalardan çek
        bolum_kodu = str(kr.get("bolum") or "").strip()
        hedef_sayfalar = BOLUM_SAYFA_HARITASI.get(bolum_kodu, [])
        if not hedef_sayfalar:
            # Genel kriterler için oransal dağıt
            hedef_sayfa_no = min(toplam_sayfa, max(3, int(3 + (idx / len(yarisma["kriterler"])) * (toplam_sayfa - 3))))
            hedef_sayfalar = [hedef_sayfa_no]
        
        secilen_alintilar = []
        for s_no in hedef_sayfalar:
            gercek_sayfa_no = min(s_no, toplam_sayfa)
            if gercek_sayfa_no in sayfa_cumleleri and sayfa_cumleleri[gercek_sayfa_no]:
                secilen_alintilar.append(rng.choice(sayfa_cumleleri[gercek_sayfa_no]))
        
        if not secilen_alintilar:
            if havuz:
                secilen_alintilar = [rng.choice(havuz)]
            else:
                secilen_alintilar = [rng.choice(ALINTILAR)]

        ana_alinti = secilen_alintilar[0]
        
        kriterler.append({
            "kriter_id": kr["id"],
            "ad": kr["ad"],
            "maks": kr["maks"],
            "ai_puan": puan,
            "bolum": kr["bolum"],
            "gerekce": rng.choice(GEREKCE_KALIPLARI[seviye]),
            "kaynak_alinti": ana_alinti,
            "kaynak_alintilar": secilen_alintilar,
            "kaynak_bolum": kr["bolum"] or "Genel",
            "guven": round(rng.uniform(0.58, 0.95), 2),
        })

    # Hata bilgisi: metin çıkmayan dosya kesin hatalı; ayrıca rastgele bir kısmı
    # başka nedenlerle hatalı işaretlenir.
    HALDEN_HATAYA = {
        "metin_yok": "taranmis",
        "acilamaz": "bozuk_pdf",
        "sifreli": "sifreli",
        "cok_az_metin": "bos",
        "dosya_yok": "bozuk_pdf",
    }
    hata = None
    if dosya_hali in HALDEN_HATAYA:
        durum = "hatali"
        tur = HALDEN_HATAYA[dosya_hali]
        hata = {"tur": tur, **HATA_TURLERI[tur]}
    elif durum == "hatali":
        # Dosya sağlamsa "hatalı" etiketi tutarsız olur — düzelt.
        durum = "hakem_bekliyor"

    # --- Hakem ataması ve (tamamlanmışsa) hakem puanları -----------------
    atanan_hakem = HAKEMLER[i % len(HAKEMLER)] if durum != "kuyrukta" else None

    hakem_puanlari: dict[str, float] = {}
    onay_tarihi = None
    if durum == "tamamlandi" and kriterler:
        # Hakem, AI'dan bağımsız puan verir: rastgele sapma + en ağır kriterde
        # sistematik fark. (Gerçek vakada AI, "Sonuçlar" kriterinde hakemden
        # belirgin biçimde daha sertti; mock bu deseni taklit eder.)
        en_agir = max(k["maks"] for k in kriterler)
        for k in kriterler:
            sapma = rng.gauss(0, 0.06) * k["maks"]
            if k["maks"] == en_agir:
                sapma += rng.uniform(0.10, 0.28) * k["maks"]   # hakem daha cömert
            puan = min(k["maks"], max(0.0, k["ai_puan"] + sapma))
            hakem_puanlari[k["kriter_id"]] = round(puan * 2) / 2
        # Onaylar 8 günlük pencereye yayılır: günlük trend anlamlı olsun
        onay_tarihi = (datetime(2026, 8, 11)
                       + timedelta(days=rng.randint(0, 7),
                                   hours=rng.randint(8, 19))).isoformat(timespec="minutes")

    benzerlik = []
    if rng.random() < 0.22:
        for _ in range(rng.randint(1, 2)):
            benzerlik.append({
                "rapor_id": f"TF-2026-{rng.randint(100, 999):06d}",
                "takim_adi": f"Takım {rng.randint(10, 99)}",
                "skor": round(rng.uniform(0.78, 0.96), 2),
                "eslesen_bolumler": rng.sample(["Yöntem", "Problem Tanımı", "Çözüm Yaklaşımı", "Özet"], 2),
            })

    return {
        "rapor_id": f"TF-2026-{100000 + i:06d}",
        "dosya": dosya,
        "proje_adi": PROJE_ADLARI[i % len(PROJE_ADLARI)],
        "takim_adi": f"{rng.choice(['Anadolu', 'Ege', 'Marmara', 'Toros', 'Fırat', 'Meriç', 'Sakarya'])} "
                     f"{rng.choice(['Teknoloji', 'Robotik', 'Yapay Zekâ', 'Mühendislik'])} Takımı",
        "kategori": kategori,
        "yuklenme_tarihi": (datetime(2026, 8, 10) + timedelta(hours=rng.randint(0, 210))).isoformat(timespec="minutes"),
        "durum": durum,
        "sayfa_sayisi": toplam_sayfa,
        "kontroller": {
            "dil": {
                "tespit": "tr" if dil_uygun else "en",
                "beklenen": "tr",
                "uygun": dil_uygun,
                "guven": round(rng.uniform(0.9, 0.99), 2),
            },
            "sablon": {
                "uygun": sablon_uygun,
                "surum": "2026 v3",
                "bulgular": [] if sablon_uygun else rng.sample(SABLON_BULGULARI, rng.randint(1, 2)),
            },
            "basliklar": {
                "zorunlu_sayisi": len(ZORUNLU_BASLIKLAR),
                "mevcut_sayisi": len(ZORUNLU_BASLIKLAR) - eksik_sayisi,
                "eksik": eksik,
                "bolumler": bolumler,
            },
        },
        "kategori_uygunlugu": {
            "skor": round(rng.uniform(0.42, 0.97), 2),
            "en_yakin_kategori": rng.choice(KATEGORILER),
            "gerekce": "Proje metnindeki teknik terimler ve uygulama alanı, başvurulan kategorinin "
                       "tanımıyla karşılaştırıldı; anlamsal örtüşme skoru buna göre hesaplandı.",
        },
        "benzerlik": benzerlik,
        "kriterler": [] if durum in ("kuyrukta", "hatali") else kriterler,
        "hata": hata,
        "atanan_hakem": atanan_hakem,
        "geri_bildirim": {
            "ozet": "Proje, tanımlanan problemi net biçimde ortaya koyuyor ve teknik yaklaşımı "
                    "izlenebilir. En büyük gelişim alanı, iddiaların ölçülebilir sonuçlarla "
                    "desteklenmesi.",
            "guclu_yonler": rng.sample(GUCLU_YONLER, 3),
            "gelisim_onerileri": rng.sample(GELISIM_ONERILERI, 3),
        },
        "hakem": {
            "ad": atanan_hakem,
            "puanlar": hakem_puanlari,
            "not": "",
            "onaylandi": durum == "tamamlandi",
            "onay_tarihi": onay_tarihi,
        },
    }


def yarismalar() -> list[dict]:
    """Rubrik dosyasından gelir — arayüz yarışma listesini kendi uydurmaz."""
    return [
        {
            "yarisma_id": y["yarisma_id"],
            "ad": y["ad"],
            "rapor_turu": y["rapor_turu"],
            "kriter_sayisi": len(y["kriterler"]),
            "toplam_puan": y["toplam_puan"],
            "rapor_sayisi": 24,
        }
        for y in rubrik.YARISMALAR
    ]


def raporlar(yarisma_id: str = "hyz-otr-2026", n: int = 48) -> list[dict]:
    yarisma = rubrik.getir(yarisma_id)
    # Tohum yarışmaya göre değişir: her yarışmanın verisi kendine özgü ama sabit
    rng = random.Random(SEED + len(yarisma_id))
    return [_rapor(rng, i, KATEGORILER, yarisma) for i in range(n)]


def metrikler(rapor_listesi: list[dict]) -> dict:
    rng = random.Random(SEED + 1)
    toplam = len(rapor_listesi)
    tamamlanan = sum(1 for r in rapor_listesi if r["durum"] == "tamamlandi")
    hatali = sum(1 for r in rapor_listesi if r["durum"] == "hatali")
    bekleyen = toplam - tamamlanan - hatali

    # Kriter listesi verinin kendisinden çıkar — sabit liste yok.
    kriter_tanimlari = []
    for r in rapor_listesi:
        for k in r["kriterler"]:
            if not any(t["kriter_id"] == k["kriter_id"] for t in kriter_tanimlari):
                kriter_tanimlari.append({"kriter_id": k["kriter_id"], "ad": k["ad"],
                                         "maks": k["maks"]})

    kriter_ort = []
    for t in kriter_tanimlari:
        puanlar = [k["ai_puan"] for r in rapor_listesi for k in r["kriterler"]
                   if k["kriter_id"] == t["kriter_id"]]
        ort = sum(puanlar) / len(puanlar) if puanlar else 0.0
        kriter_ort.append({
            "kriter_id": t["kriter_id"],
            "ad": t["ad"],
            "maks": t["maks"],
            "ortalama": round(ort, 2),
            "oran": round(ort / t["maks"], 3) if t["maks"] else 0.0,
        })

    gunluk = []
    for gun in range(10, 19):
        gunluk.append({
            "tarih": f"2026-08-{gun:02d}",
            "analiz_edilen": rng.randint(4, 22),
        })

    agirlikli = []
    for r in rapor_listesi:
        if not r["kriterler"]:
            continue
        # Kriter puanları zaten ağırlıklı (toplamı 100 üzerinden)
        agirlikli.append(sum(k["ai_puan"] for k in r["kriterler"]))

    # --- Hakem yükü ------------------------------------------------------
    hakem_yuku = []
    for ad in HAKEMLER:
        atanan = [r for r in rapor_listesi if r.get("atanan_hakem") == ad]
        if not atanan:
            continue
        tamam = sum(1 for r in atanan if r["durum"] == "tamamlandi")
        hakem_yuku.append({
            "hakem": ad,
            "atanan": len(atanan),
            "tamamlanan": tamam,
            "bekleyen": len(atanan) - tamam,
        })
    hakem_yuku.sort(key=lambda h: -h["atanan"])

    # --- AI ↔ hakem uyumu (yalnızca hakem puanı girilmiş raporlar) --------
    eslesenler = [r for r in rapor_listesi
                  if r["durum"] == "tamamlandi" and r["hakem"].get("puanlar")]

    kriter_sapmalari = []
    for t in kriter_tanimlari:
        farklar = []
        for r in eslesenler:
            for k in r["kriterler"]:
                if k["kriter_id"] != t["kriter_id"]:
                    continue
                hp = r["hakem"]["puanlar"].get(k["kriter_id"])
                if hp is not None:
                    farklar.append(k["ai_puan"] - hp)
        if farklar:
            kriter_sapmalari.append({
                "ad": t["ad"],
                "maks": t["maks"],
                "ortalama_fark": round(sum(farklar) / len(farklar), 2),
                "mutlak_fark": round(sum(abs(f) for f in farklar) / len(farklar), 2),
                "adet": len(farklar),
            })

    def _rapor_mae(r: dict) -> float | None:
        farklar = [abs(k["ai_puan"] - r["hakem"]["puanlar"][k["kriter_id"]])
                   for k in r["kriterler"]
                   if k["kriter_id"] in r["hakem"]["puanlar"]]
        return sum(farklar) / len(farklar) if farklar else None

    gunluk_uyum: dict[str, list[float]] = {}
    for r in eslesenler:
        tarih = (r["hakem"].get("onay_tarihi") or r["yuklenme_tarihi"])[:10]
        mae = _rapor_mae(r)
        if mae is not None:
            gunluk_uyum.setdefault(tarih, []).append(mae)

    uyum_trendi = [
        {"tarih": t, "mae": round(sum(v) / len(v), 2), "rapor": len(v)}
        for t, v in sorted(gunluk_uyum.items())
    ]

    tum_mae = [m for v in gunluk_uyum.values() for m in v]
    ortalama_mae = round(sum(tum_mae) / len(tum_mae), 2) if tum_mae else 0.0

    return {
        "hakem_yuku": hakem_yuku,
        "uyum_trendi": uyum_trendi,
        "kriter_sapmalari": kriter_sapmalari,
        "ortalama_mae": ortalama_mae,
        "uyum_rapor_sayisi": len(eslesenler),
        "toplam": toplam,
        "tamamlanan": tamamlanan,
        "bekleyen": bekleyen,
        "hatali": hatali,
        "ortalama_puan": round(sum(agirlikli) / len(agirlikli), 1) if agirlikli else 0.0,
        "kriter_ortalamalari": kriter_ort,
        "gunluk_hacim": gunluk,
        "benzerlik_uyarilari": sum(1 for r in rapor_listesi if r["benzerlik"]),
        "sablon_uyumsuz": sum(1 for r in rapor_listesi if not r["kontroller"]["sablon"]["uygun"]),
        "dil_uyumsuz": sum(1 for r in rapor_listesi if not r["kontroller"]["dil"]["uygun"]),
    }
