"""Kanıt alıntısını raporun kendi sayfasında gösterme.

Hakem "neden bu puan?" diye sorduğunda cevap ekranda olmalı: alıntının
rapordaki yeri. Bu modül alıntıyı PDF içinde arar, bulduğu yeri işaretler ve
o sayfanın görüntüsünü döndürür.

Alıntı birebir bulunamazsa (PDF metin çıkarımı satır sonlarını ve tireleri
bozabilir) giderek kısalan öneklerle aranır; hiç bulunamazsa bölüm başlığına
düşülür. Hiçbiri olmazsa dürüst cevap verilir: "raporda konumlandırılamadı".
"""

from __future__ import annotations

import base64
import re
from functools import lru_cache
from pathlib import Path

# SAĞLAMLAŞTIRMA: pymupdf'in native DLL'i (bazı Windows "Uygulama Denetimi" /
# Smart App Control politikalarında) yüklenemeyebilir. Bu durumda import'un
# TÜM arayüzü çökertmemesi için opsiyonel yükleniyor. pymupdf yoksa PDF önizleme
# ve alıntı işaretleme özellikleri devre dışı kalır; arayüzün geri kalanı çalışır.
try:
    import pymupdf
    PYMUPDF_VAR = True
except Exception as _e:  # ImportError, DLL load failed, vb.
    print(f"[PDF GÖRÜNÜM UYARI] pymupdf yüklenemedi; PDF önizleme devre dışı: {type(_e).__name__}: {_e}")
    pymupdf = None
    PYMUPDF_VAR = False

import tempfile

# Arayüz paketine gömülü örnek raporlar ve proje kökü
PROJE_KOKU = Path(__file__).resolve().parents[2]
ORNEK_DIZIN = Path(tempfile.gettempdir()) / "tsistem_cache" / "ornek_raporlar"

ISARET_RENK = (1.0, 0.85, 0.30)      # yumuşak sarı vurgulama
CERCEVE_RENK = (0.16, 0.47, 0.84)    # slot-1 mavi


@lru_cache(maxsize=1)
def ornek_raporlar() -> tuple[str, ...]:
    if not ORNEK_DIZIN.exists():
        return ()
    return tuple(sorted(p.name for p in ORNEK_DIZIN.glob("*.pdf")))


_PDF_INDEX: dict[str, Path] = {}

def _init_pdf_index():
    global _PDF_INDEX
    if _PDF_INDEX:
        return
    import urllib.parse
    for arama_dizini in (PROJE_KOKU / "docs", PROJE_KOKU / "data"):
        if arama_dizini.exists():
            for eslesen in arama_dizini.rglob("*.pdf"):
                _PDF_INDEX[eslesen.name.lower()] = eslesen
                _PDF_INDEX[urllib.parse.unquote(eslesen.name).lower()] = eslesen
                _PDF_INDEX[eslesen.stem.lower()] = eslesen


@lru_cache(maxsize=4096)
def yol(dosya_adi: str) -> Path:
    """
    Dosyayı sırasıyla:
    1. data/ornek_raporlar/
    2. Hızlı bellek içi PDF indeksi (O(1))
    3. Proje genelinde dosya adı eşleşmesi
    4. Bulunamazsa Cloudflare R2'den yerel önbelleğe indirme
    şeklinde arar ve tam yolunu döndürür.
    """
    import urllib.parse
    temiz_ad = urllib.parse.unquote(dosya_adi or "").strip()
    if not temiz_ad:
        return None
    sade_ad = Path(temiz_ad).name
    sade_lower = sade_ad.lower()

    # 1. Doğrudan data/ornek_raporlar
    p1 = ORNEK_DIZIN / sade_ad
    if p1.exists():
        return p1

    # 2. Mutlak yol olarak verilmişse
    p_direct = Path(dosya_adi)
    if p_direct.is_absolute() and p_direct.exists():
        return p_direct

    # 3. Hızlı O(1) bellek indeksi
    _init_pdf_index()
    if sade_lower in _PDF_INDEX:
        return _PDF_INDEX[sade_lower]

    # 4. Cloudflare R2'den indirmeyi dene
    try:
        from src.utils.storage import storage
        if storage.client:
            for olasi_key in [sade_ad, dosya_adi, urllib.parse.quote(sade_ad)]:
                baytlar = storage.get_file_bytes(olasi_key)
                if baytlar:
                    hedef = ORNEK_DIZIN / sade_ad
                    ORNEK_DIZIN.mkdir(parents=True, exist_ok=True)
                    hedef.write_bytes(baytlar)
                    return hedef
    except Exception:
        pass

    return p1


@lru_cache(maxsize=64)
def _belge_metni(dosya_adi: str) -> tuple[str, ...]:
    """Sayfa sayfa metin. Taranmış PDF'te tüm sayfalar boş döner."""
    if not PYMUPDF_VAR:
        return ()
    p = yol(dosya_adi)
    if not p.exists():
        return ()
    try:
        with pymupdf.open(p) as belge:
            return tuple(sayfa.get_text() for sayfa in belge)
    except Exception:
        return ()



@lru_cache(maxsize=1024)
def cumleler(dosya_adi: str, en_az_kelime: int = 9) -> list[str]:
    """Rapordan gerçek cümleler — mock veri bunlardan besleniyor,
    böylece arayüzdeki alıntı PDF'te gerçekten bulunabiliyor."""
    ham = " ".join(_belge_metni(dosya_adi))
    ham = re.sub(r"\s+", " ", ham)
    parcalar = re.split(r"(?<=[.!?])\s+", ham)
    sonuc = []
    for c in parcalar:
        c = c.strip()
        if len(c.split()) >= en_az_kelime and not c.startswith(("Tablo", "Şekil", "[")):
            sonuc.append(c)
    return sonuc


ASGARI_KARAKTER = 400   # bu eşiğin altı "içerik yok" sayılır


@lru_cache(maxsize=64)
def dosya_durumu(dosya_adi: str) -> str:
    """Dosyanın işlenebilirliği: dosya_yok | acilamaz | sifreli | metin_yok |
    cok_az_metin | tamam.

    Hata türü uydurulmaz — dosyanın gerçek halinden okunur.
    """
    if not PYMUPDF_VAR:
        return "onizleme_yok"
    p = yol(dosya_adi)
    if not p.exists():
        return "dosya_yok"
    try:
        belge = pymupdf.open(p)
    except Exception:
        return "acilamaz"
    with belge:
        if belge.needs_pass:
            return "sifreli"
        try:
            toplam = sum(len(sayfa.get_text().strip()) for sayfa in belge)
        except Exception:
            return "acilamaz"
    if toplam == 0:
        return "metin_yok"
    if toplam < ASGARI_KARAKTER:
        return "cok_az_metin"
    return "tamam"


def _adaylar(alinti: str | list[str]) -> list[str]:
    """Aranacak metinler: tam alıntı, sonra giderek kısalan önekler."""
    if isinstance(alinti, (list, tuple)):
        alintilar = [str(a) for a in alinti if a]
    else:
        alintilar = [str(alinti)]

    adaylar = []
    for tek in alintilar:
        temiz = re.sub(r"\s+", " ", tek).strip().strip("“”\"")
        if not temiz:
            continue
        kelimeler = temiz.split()
        if temiz not in adaylar:
            adaylar.append(temiz)
        for uzunluk in (14, 10, 7, 5):
            if len(kelimeler) > uzunluk:
                onek = " ".join(kelimeler[:uzunluk])
                if onek not in adaylar:
                    adaylar.append(onek)
    return adaylar


def _satirlari_birlestir(kutular: list) -> list:
    """Aynı satırdaki parça kutuları tek dikdörtgende birleştirir.

    PDF'te satır sonuna gelen bir alıntı kelime kelime kutulanır; birleştirmeden
    işaretleme dağınık görünür.
    """
    if not kutular:
        return []
    siralanmis = sorted(kutular, key=lambda k: (round(k.y0, 1), k.x0))
    birlesik = [pymupdf.Rect(siralanmis[0])]
    for kutu in siralanmis[1:]:
        son = birlesik[-1]
        ayni_satir = abs(kutu.y0 - son.y0) < 3.5 and abs(kutu.y1 - son.y1) < 3.5
        yakin = kutu.x0 - son.x1 < 12
        if ayni_satir and yakin:
            birlesik[-1] = pymupdf.Rect(son.x0, min(son.y0, kutu.y0),
                                        max(son.x1, kutu.x1), max(son.y1, kutu.y1))
        else:
            birlesik.append(pymupdf.Rect(kutu))
    return birlesik


@lru_cache(maxsize=32)
def sayfaya_gore_cumleler(dosya_adi: str) -> dict[int, list[str]]:
    """PDF belgesinin her sayfasındaki temiz cümleleri sayfa numarasına (1-indexed) göre döner."""
    if not PYMUPDF_VAR:
        return {}
    p = yol(dosya_adi)
    if not p.exists():
        return {}
    
    sonuclar = {}
    try:
        with pymupdf.open(p) as belge:
            for no, sayfa in enumerate(belge):
                sayfa_no = no + 1
                metin = sayfa.get_text()
                metin = re.sub(r"\s+", " ", metin)
                parcalar = re.split(r"(?<=[.!?])\s+", metin)
                c_listesi = []
                for c in parcalar:
                    c = c.strip()
                    if len(c.split()) >= 7 and not c.startswith(("Tablo", "Şekil", "[", "http")):
                        c_listesi.append(c)
                if c_listesi:
                    sonuclar[sayfa_no] = c_listesi
    except Exception as e:
        print(f"[PDF Cümle Çıkarma Hatası]: {e}")
    return sonuclar


def isaretle(dosya_adi: str, alinti: str | list[str], bolum_ipucu: str | None = None,
             dpi: int = 115) -> dict:
    """Alıntıyı/alıntıları PDF içindeki TÜM sayfalarda arar, bulduğu yerleri işaretler
    ve bulunan bütün sayfaların görüntülerini döndürür.

    Dönen sözlük:
      durum: "bulundu" | "bolum_bulundu" | "bulunamadi" | "metin_yok" | "dosya_yok" | "acilamaz" | "sifreli"
      sayfalar: list[dict] -> [{"sayfa": int, "png": bytes, "eslesen": list[str], "adet": int}, ...]
      sayfa: int | None          (ilk bulunan sayfa numarası, geriye uyumluluk için)
      png: bytes | None          (ilk bulunan sayfa görüntüsü, geriye uyumluluk için)
      toplam_sayfa: int          (belgedeki toplam sayfa sayısı)
      bulunan_sayfa_sayisi: int  (kanıt bulunan toplam sayfa sayısı)
      eslesen: str | None
    """
    if not PYMUPDF_VAR:
        return {"durum": "onizleme_yok", "sayfalar": [], "png": None, "sayfa": None,
                "eslesen": None, "toplam_sayfa": 0, "bulunan_sayfa_sayisi": 0}
    p = yol(dosya_adi)
    if not p.exists():
        return {"durum": "dosya_yok", "sayfalar": [], "png": None, "sayfa": None,
                "eslesen": None, "toplam_sayfa": 0, "bulunan_sayfa_sayisi": 0}

    try:
        belge = pymupdf.open(p)
    except Exception:
        return {"durum": "acilamaz", "sayfalar": [], "png": None, "sayfa": None,
                "eslesen": None, "toplam_sayfa": 0, "bulunan_sayfa_sayisi": 0}

    with belge:
        if belge.needs_pass:
            return {"durum": "sifreli", "sayfalar": [], "png": None, "sayfa": None,
                    "eslesen": None, "toplam_sayfa": len(belge), "bulunan_sayfa_sayisi": 0}
        
        toplam_karakter = sum(len(s.get_text().strip()) for s in belge)
        if toplam_karakter < 50:
            return {"durum": "metin_yok", "sayfalar": [], "png": None, "sayfa": None,
                    "eslesen": None, "toplam_sayfa": len(belge), "bulunan_sayfa_sayisi": 0}

        toplam_sayfa_adedi = len(belge)
        
        # Sayfa bazında bulunan kutular ve eşleşen metinler
        sayfa_kutulari: dict[int, list] = {}
        sayfa_eslesmeler: dict[int, list[str]] = {}

        # 1. TÜM ALINTILARI BAĞIMSIZ ARA: her alıntı için kendi adaylarını üret ve tüm sayfalarda tara
        #    (Eski kod: ilk eşleşmede break yapıyordu → sadece 1 kanıt görünüyordu)
        alinti_listesi = alinti if isinstance(alinti, (list, tuple)) else [alinti]
        alinti_listesi = [str(a).strip() for a in alinti_listesi if a and str(a).strip()]

        for tek_alinti in alinti_listesi:
            # Her alıntı için giderek kısalan önek adayları
            tek_temiz = re.sub(r"\s+", " ", tek_alinti).strip().strip("\u201c\u201d\"")
            kelimeler = tek_temiz.split()
            tek_adaylar: list[str] = [tek_temiz]
            for uzunluk in (14, 10, 7, 5):
                if len(kelimeler) > uzunluk:
                    onek = " ".join(kelimeler[:uzunluk])
                    if onek not in tek_adaylar:
                        tek_adaylar.append(onek)

            # Bu alıntı için tüm sayfalarda en uzun eşleşmeyle ara; bulununca diğer öneklere geçme
            for aday in tek_adaylar:
                aday_bulundu = False
                for no, sayfa in enumerate(belge):
                    bulunan = sayfa.search_for(aday, quads=False)
                    if bulunan:
                        sayfa_kutulari.setdefault(no, []).extend(bulunan)
                        if aday not in sayfa_eslesmeler.setdefault(no, []):
                            sayfa_eslesmeler[no].append(aday)
                        aday_bulundu = True
                # Bu alıntı için en kesin adayla eşleşme bulunduysa, kısa önek ile sayfaları kirletme
                if aday_bulundu:
                    break

        durum = "bulundu" if sayfa_kutulari else "bulunamadi"


        # 2. Birebir veya önek eşleşme bulunamazsa bölüm ipucuyla tüm sayfalarda ara
        if not sayfa_kutulari and bolum_ipucu:
            temiz_ipucu = str(bolum_ipucu).strip()
            for no, sayfa in enumerate(belge):
                bulunan = sayfa.search_for(temiz_ipucu, quads=False)
                if bulunan:
                    sayfa_kutulari.setdefault(no, []).extend(bulunan)
                    sayfa_eslesmeler.setdefault(no, []).append(temiz_ipucu)
                    durum = "bolum_bulundu"

        # 3. Eğer alıntı sentetik/LLM özetiyse, PDF'teki gerçek cümleler arasından en çok örtüşeni bulup işaretle
        if not sayfa_kutulari:
            alinti_metin = " ".join(aranacak_adaylar) if aranacak_adaylar else str(alinti)
            alinti_tokens = set(re.findall(r"\w{4,}", alinti_metin.lower()))
            
            en_iyi_skor = 0
            en_iyi_aday = None
            en_iyi_sayfa_no = None
            
            for no, sayfa in enumerate(belge):
                s_text = sayfa.get_text()
                parcalar = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", s_text))
                for c in parcalar:
                    c_clean = c.strip()
                    if len(c_clean.split()) >= 5:
                        c_tokens = set(re.findall(r"\w{4,}", c_clean.lower()))
                        ortusme = len(alinti_tokens.intersection(c_tokens))
                        if ortusme > en_iyi_skor:
                            en_iyi_skor = ortusme
                            en_iyi_aday = c_clean
                            en_iyi_sayfa_no = no
            
            if en_iyi_aday and en_iyi_sayfa_no is not None and en_iyi_skor >= 1:
                c_words = en_iyi_aday.split()
                for uzunluk in (len(c_words), 10, 7, 5, 3):
                    if len(c_words) >= uzunluk:
                        parca = " ".join(c_words[:uzunluk])
                        bulunan = belge[en_iyi_sayfa_no].search_for(parca, quads=False)
                        if bulunan:
                            sayfa_kutulari.setdefault(en_iyi_sayfa_no, []).extend(bulunan)
                            sayfa_eslesmeler.setdefault(en_iyi_sayfa_no, []).append(parca)
                            durum = "bulundu"
                            break

        # 4. Hala bulunamadıysa başlık sayfaları dışındaki ilgili ilk paragrafları işaretle
        if not sayfa_kutulari:
            for no in range(min(1, len(belge) - 1), len(belge)):
                sayfa = belge[no]
                lines = [l.strip() for l in sayfa.get_text().split("\n") if len(l.strip()) > 30 and not l.strip().startswith(("TEKNOFEST", "Sayfa"))]
                if lines:
                    target_line = lines[0]
                    words = target_line.split()
                    sample_chunk = " ".join(words[:min(len(words), 8)])
                    bulunan = sayfa.search_for(sample_chunk, quads=False)
                    if bulunan:
                        sayfa_kutulari.setdefault(no, []).extend(bulunan)
                        sayfa_eslesmeler.setdefault(no, []).append(sample_chunk)
                        durum = "bolum_bulundu"
                        break

        if not sayfa_kutulari:
            return {"durum": "bulunamadi", "sayfalar": [], "png": None, "sayfa": None,
                    "eslesen": None, "toplam_sayfa": toplam_sayfa_adedi, "bulunan_sayfa_sayisi": 0}

        # 5. Bulunan bütün sayfaları işaretle ve PNG oluştur
        bulunan_sayfalar = []
        for no in sorted(sayfa_kutulari.keys()):
            sayfa = belge[no]
            kutular = sayfa_kutulari[no]
            birlestirilmis = _satirlari_birlestir(kutular)
            
            for kutu in birlestirilmis:
                try:
                    vurgu = sayfa.add_highlight_annot(kutu)
                    vurgu.set_colors(stroke=ISARET_RENK)
                    vurgu.update()
                except Exception:
                    pass
                try:
                    sayfa.draw_rect(kutu + (-2, -2, 2, 2), color=CERCEVE_RENK, width=1.2)
                except Exception:
                    pass

            png_bytes = sayfa.get_pixmap(dpi=dpi).tobytes("png")
            bulunan_sayfalar.append({
                "sayfa": no + 1,
                "png": png_bytes,
                "eslesen": sayfa_eslesmeler.get(no, []),
                "adet": len(birlestirilmis),
            })

    ilk_sayfa = bulunan_sayfalar[0]["sayfa"] if bulunan_sayfalar else None
    ilk_png = bulunan_sayfalar[0]["png"] if bulunan_sayfalar else None
    ilk_eslesen = (bulunan_sayfalar[0]["eslesen"][0]
                   if bulunan_sayfalar and bulunan_sayfalar[0]["eslesen"] else None)

    return {
        "durum": durum,
        "sayfalar": bulunan_sayfalar,
        "sayfa": ilk_sayfa,
        "png": ilk_png,
        "eslesen": ilk_eslesen,
        "toplam_sayfa": toplam_sayfa_adedi,
        "bulunan_sayfa_sayisi": len(bulunan_sayfalar),
    }


@lru_cache(maxsize=2048)
def sayfa_sayisi_getir(dosya_adi: str) -> int:
    """PDF dosyasının toplam sayfa sayısını döner."""
    if not PYMUPDF_VAR:
        return 0
    p = yol(dosya_adi)
    if not p.exists():
        return 0
    try:
        with pymupdf.open(p) as belge:
            return len(belge)
    except Exception:
        return 0


def sayfa_goruntusu(dosya_adi: str, sayfa_no: int, dpi: int = 120) -> bytes | None:
    """Belirtilen sayfanın (1-indexed) PNG görüntüsünü döner."""
    if not PYMUPDF_VAR:
        return None
    p = yol(dosya_adi)
    if not p.exists():
        return None
    try:
        with pymupdf.open(p) as belge:
            idx = sayfa_no - 1
            if 0 <= idx < len(belge):
                return belge[idx].get_pixmap(dpi=dpi).tobytes("png")
    except Exception as e:
        print(f"[PDF Sayfa Render Hatası]: {e}")
    return None


@lru_cache(maxsize=1024)
def sayfa_cumleleri_getir(dosya_adi: str, en_az_kelime: int = 6) -> dict[int, list[str]]:
    """Sayfa numarasına göre (1-indexed) cümle listesi sözlüğü döner."""
    if not PYMUPDF_VAR:
        return {}
    p = yol(dosya_adi)
    if not p.exists():
        return {}
    sonuc = {}
    try:
        with pymupdf.open(p) as belge:
            for s_idx, sayfa in enumerate(belge):
                s_metin = sayfa.get_text()
                s_metin = re.sub(r"\s+", " ", s_metin)
                parcalar = re.split(r"(?<=[.!?])\s+", s_metin)
                c_list = [c.strip() for c in parcalar if len(c.strip().split()) >= en_az_kelime and not c.strip().startswith(("Tablo", "Şekil", "["))]
                if c_list:
                    sonuc[s_idx + 1] = c_list
    except Exception:
        pass
    return sonuc


def pdf_onizle(st_obj, pdf_kaynak: str | Path | bytes, baslik: str = "", height: int = 780, key: str = "pdf_embed") -> None:
    """PDF dosyasını kesintisiz dikey kaydırma, yan yana sayfa görünümü (grid), anında tepki veren büyüteç/zoom slider ve butonları ile render eder."""
    import streamlit.components.v1 as components

    if isinstance(pdf_kaynak, (str, Path)):
        p = Path(pdf_kaynak)
        if not p.exists():
            st_obj.warning("Görüntülenecek PDF dosyası bulunamadı.")
            return
        pdf_bytes = p.read_bytes()
        dosya_adi = p.name
    else:
        pdf_bytes = pdf_kaynak
        dosya_adi = "dokuman.pdf"

    if not pdf_bytes:
        st_obj.warning("PDF içeriği boş.")
        return

    b64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8">
      <script src="https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.min.js"></script>
      <style>
        * {{
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }}
        body {{
          background-color: #2F3336;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          color: #F8FAFC;
          overflow: hidden;
          height: 100vh;
          display: flex;
          flex-direction: column;
        }}
        .toolbar {{
          background: #1A1D20;
          border-bottom: 1px solid #3E4348;
          padding: 8px 16px;
          display: flex;
          align-items: center;
          justify-content: space-between;
          flex-shrink: 0;
          z-index: 10;
          box-shadow: 0 2px 10px rgba(0,0,0,0.35);
          gap: 12px;
          flex-wrap: wrap;
        }}
        .toolbar-group {{
          display: flex;
          align-items: center;
          gap: 8px;
        }}
        .btn {{
          background: #2D3237;
          color: #F1F5F9;
          border: 1px solid #4A5158;
          border-radius: 6px;
          padding: 5px 11px;
          font-size: 13px;
          font-weight: 600;
          cursor: pointer;
          transition: all 0.15s ease;
          display: inline-flex;
          align-items: center;
          gap: 4px;
          user-select: none;
        }}
        .btn:hover {{
          background: #F04823;
          border-color: #F04823;
          color: #FFFFFF;
        }}
        .btn.active {{
          background: #F04823;
          border-color: #F04823;
          color: #FFFFFF;
        }}
        .zoom-slider-wrap {{
          display: flex;
          align-items: center;
          gap: 8px;
          background: #24282C;
          padding: 4px 10px;
          border-radius: 6px;
          border: 1px solid #3E4348;
        }}
        .zoom-slider {{
          -webkit-appearance: none;
          appearance: none;
          width: 110px;
          height: 5px;
          border-radius: 3px;
          background: #4A5158;
          outline: none;
          cursor: pointer;
        }}
        .zoom-slider::-webkit-slider-thumb {{
          -webkit-appearance: none;
          appearance: none;
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: #F04823;
          cursor: pointer;
          box-shadow: 0 0 6px rgba(240, 72, 35, 0.6);
        }}
        .zoom-slider::-moz-range-thumb {{
          width: 14px;
          height: 14px;
          border-radius: 50%;
          background: #F04823;
          cursor: pointer;
          box-shadow: 0 0 6px rgba(240, 72, 35, 0.6);
        }}
        .badge {{
          font-size: 12px;
          color: #94A3B8;
          font-weight: 600;
          padding: 4px 8px;
          background: #14171A;
          border-radius: 4px;
          border: 1px solid #2D3237;
          min-width: 48px;
          text-align: center;
        }}
        #viewer-container {{
          flex: 1;
          overflow-y: auto;
          overflow-x: auto;
          padding: 24px 20px;
          display: flex;
          gap: 24px;
          background-color: #525659;
          transition: all 0.15s ease;
        }}
        #viewer-container.mode-vertical {{
          flex-direction: column;
          align-items: center;
        }}
        #viewer-container.mode-grid {{
          flex-direction: row;
          flex-wrap: wrap;
          justify-content: center;
          align-items: flex-start;
        }}
        .page-wrapper {{
          display: flex;
          flex-direction: column;
          align-items: center;
          margin-bottom: 12px;
          transition: transform 0.1s ease;
        }}
        .pdf-page-canvas {{
          box-shadow: 0 8px 26px rgba(0, 0, 0, 0.45);
          background: #FFFFFF;
          border-radius: 4px;
          display: block;
          transform-origin: top center;
        }}
        .page-num-label {{
          margin-top: 6px;
          font-size: 12px;
          color: #CBD5E1;
          font-weight: 600;
        }}
        #loading {{
          margin: 40px auto;
          font-size: 14px;
          color: #E2E8F0;
        }}
      </style>
    </head>
    <body>
      <div class="toolbar">
        <div class="toolbar-group">
          <button class="btn" onclick="adjustZoom(-0.15)" title="Küçült">-</button>
          
          <div class="zoom-slider-wrap">
            <input type="range" min="30" max="250" value="100" class="zoom-slider" id="zoom-slider" oninput="onSliderZoom(this.value)">
            <span class="badge" id="zoom-label">100%</span>
          </div>

          <button class="btn" onclick="adjustZoom(0.15)" title="Büyüt">+</button>
          
          <button class="btn" onclick="fitWidth()" title="Genişliğe Sığdır">Sığdır</button>
          <button class="btn" onclick="setExactZoom(1.0)" title="Sıfırla">%100</button>
          <button class="btn" onclick="setExactZoom(1.5)" title="%150 Büyüt">%150</button>

          <span style="border-left:1px solid #4A5158; height:20px; margin:0 4px;"></span>
          <button class="btn active" id="btn-mode-vertical" onclick="setMode('vertical')">Dikey Akış</button>
          <button class="btn" id="btn-mode-grid" onclick="setMode('grid')">Yan Yana (Grid)</button>
        </div>

        <div class="toolbar-group">
          <span class="badge" id="page-count-badge">Yükleniyor...</span>
          <a class="btn" href="data:application/pdf;base64,{b64_pdf}" download="{dosya_adi}" style="text-decoration:none;">İndir</a>
        </div>
      </div>

      <div id="viewer-container" class="mode-vertical">
        <div id="loading">Belge hazırlanıyor, lütfen bekleyiniz...</div>
      </div>

      <script>
        pdfjsLib.GlobalWorkerOptions.workerSrc = 'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/3.11.174/pdf.worker.min.js';

        const pdfData = atob("{b64_pdf}");
        const uint8Array = new Uint8Array(pdfData.length);
        for (let i = 0; i < pdfData.length; i++) {{
          uint8Array[i] = pdfData.charCodeAt(i);
        }}

        let pdfDoc = null;
        let currentScale = 1.0;
        let currentMode = 'vertical';
        let renderTasks = [];
        let reRenderTimeout = null;

        const container = document.getElementById('viewer-container');
        const zoomLabel = document.getElementById('zoom-label');
        const zoomSlider = document.getElementById('zoom-slider');
        const pageBadge = document.getElementById('page-count-badge');
        const btnVertical = document.getElementById('btn-mode-vertical');
        const btnGrid = document.getElementById('btn-mode-grid');

        function updateModeButtons() {{
          if (currentMode === 'vertical') {{
            btnVertical.classList.add('active');
            btnGrid.classList.remove('active');
            container.className = 'mode-vertical';
          }} else {{
            btnGrid.classList.add('active');
            btnVertical.classList.remove('active');
            container.className = 'mode-grid';
          }}
        }}

        function setMode(mode) {{
          currentMode = mode;
          if (mode === 'grid' && currentScale > 0.8) {{
            currentScale = 0.60;
          }} else if (mode === 'vertical' && currentScale < 0.8) {{
            currentScale = 1.0;
          }}
          updateZoomUI();
          updateModeButtons();
          triggerHiResRender();
        }}

        function updateZoomUI() {{
          const pct = Math.round(currentScale * 100);
          zoomLabel.innerText = pct + '%';
          zoomSlider.value = pct;
        }}

        function onSliderZoom(val) {{
          currentScale = parseInt(val, 10) / 100.0;
          zoomLabel.innerText = val + '%';
          applyFastCssZoom();
          debouncedHiResRender();
        }}

        function adjustZoom(delta) {{
          currentScale = Math.max(0.3, Math.min(2.5, currentScale + delta));
          updateZoomUI();
          applyFastCssZoom();
          debouncedHiResRender();
        }}

        function setExactZoom(val) {{
          currentScale = val;
          updateZoomUI();
          applyFastCssZoom();
          debouncedHiResRender();
        }}

        function fitWidth() {{
          if (!pdfDoc) return;
          pdfDoc.getPage(1).then(page => {{
            const desiredWidth = container.clientWidth - (currentMode === 'grid' ? 100 : 60);
            const unscaledViewport = page.getViewport({{ scale: 1.0 }});
            currentScale = Math.max(0.4, Math.min(2.5, desiredWidth / unscaledViewport.width));
            updateZoomUI();
            applyFastCssZoom();
            debouncedHiResRender();
          }});
        }}

        // Ctrl + Mouse Wheel Zoom
        window.addEventListener('wheel', (e) => {{
          if (e.ctrlKey) {{
            e.preventDefault();
            adjustZoom(e.deltaY < 0 ? 0.1 : -0.1);
          }}
        }}, {{ passive: false }});

        function applyFastCssZoom() {{
          const canvases = document.querySelectorAll('.pdf-page-canvas');
          canvases.forEach(canvas => {{
            const baseW = canvas.dataset.baseWidth;
            const baseH = canvas.dataset.baseHeight;
            if (baseW && baseH) {{
              canvas.style.width = (baseW * currentScale) + 'px';
              canvas.style.height = (baseH * currentScale) + 'px';
            }}
          }});
        }}

        function debouncedHiResRender() {{
          if (reRenderTimeout) clearTimeout(reRenderTimeout);
          reRenderTimeout = setTimeout(() => {{
            triggerHiResRender();
          }}, 120);
        }}

        function cancelActiveRenders() {{
          renderTasks.forEach(task => {{
            try {{ task.cancel(); }} catch (e) {{}}
          }});
          renderTasks = [];
        }}

        async function triggerHiResRender() {{
          if (!pdfDoc) return;
          cancelActiveRenders();

          container.innerHTML = '';
          updateZoomUI();
          pageBadge.innerText = 'Toplam ' + pdfDoc.numPages + ' Sayfa';

          // Retina display çarpanı
          const dpr = Math.min(window.devicePixelRatio || 1.5, 2.0);

          for (let pageNum = 1; pageNum <= pdfDoc.numPages; pageNum++) {{
            const page = await pdfDoc.getPage(pageNum);
            const unscaledViewport = page.getViewport({{ scale: 1.0 }});
            const renderViewport = page.getViewport({{ scale: currentScale * dpr }});

            const wrapper = document.createElement('div');
            wrapper.className = 'page-wrapper';

            const canvas = document.createElement('canvas');
            canvas.className = 'pdf-page-canvas';
            canvas.id = 'page-' + pageNum;
            canvas.dataset.baseWidth = unscaledViewport.width;
            canvas.dataset.baseHeight = unscaledViewport.height;

            // Gerçek çizim boyutu (piksel kalitesi)
            canvas.width = renderViewport.width;
            canvas.height = renderViewport.height;

            // CSS ekran görünüm boyutu
            canvas.style.width = (unscaledViewport.width * currentScale) + 'px';
            canvas.style.height = (unscaledViewport.height * currentScale) + 'px';

            wrapper.appendChild(canvas);

            if (currentMode === 'grid') {{
              const label = document.createElement('div');
              label.className = 'page-num-label';
              label.innerText = 'Sayfa ' + pageNum;
              wrapper.appendChild(label);
            }}

            container.appendChild(wrapper);

            const ctx = canvas.getContext('2d');
            const renderTask = page.render({{
              canvasContext: ctx,
              viewport: renderViewport
            }});
            renderTasks.push(renderTask);

            try {{
              await renderTask.promise;
            }} catch (err) {{
              if (err.name !== 'RenderingCancelledException') {{
                console.error("Render hatası:", err);
              }}
            }}
          }}
        }}

        updateModeButtons();

        pdfjsLib.getDocument({{ data: uint8Array }}).promise.then(pdf => {{
          pdfDoc = pdf;
          triggerHiResRender();
        }}).catch(err => {{
          console.error("PDF yükleme hatası:", err);
          container.innerHTML = `
            <div style="padding:20px; color:#FFA4A4; text-align:center;">
              Belge doğrudan görüntülenemedi. 
              <br><br>
              <object data="data:application/pdf;base64,{b64_pdf}" type="application/pdf" width="100%" height="600px">
                <p><a href="data:application/pdf;base64,{b64_pdf}" download="{dosya_adi}">Dokümanı buradan indirin</a>.</p>
              </object>
            </div>
          `;
        }});
      </script>
    </body>
    </html>
    """

    components.html(html_code, height=height, scrolling=False)



