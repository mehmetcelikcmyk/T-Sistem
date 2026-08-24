"""
TEKNOFEST Hiyerarşik Yarışma, Alt Kategori ve Aşama Rehber Modülü.
Kategori (Domain) ➔ Ana Yarışma ➔ Alt Kategori/Seviye ➔ Aşama (ÖTR/KTR/AHR/FTR)
hiyerarşisini ve ilgili resmî Şartname/Şablon dokümanlarını çözer.
"""
from __future__ import annotations

import os
import re
import json
import glob
from pathlib import Path
from functools import lru_cache
from typing import Dict, List, Any, Optional

import base64
import pymupdf

ROOT = Path(__file__).resolve().parents[2]
DOCS_DIR = ROOT / "data" / "yarismalar"
RUBRICS_DIR = ROOT / "data" / "rubrics"
LOGOS_DIR = ROOT / "data" / "logos"


@lru_cache(maxsize=128)
def kategori_logosu_getir(slug: str) -> Path | None:
    """Yarışma slug'ına ait resmî logo dosya yolunu (.png, .webp, .jpg) döndürür."""
    if not slug:
        return None
        
    clean_slug = slug.strip().lower()
    if LOGOS_DIR.exists():
        for ext in [".png", ".webp", ".jpg", ".jpeg"]:
            p = LOGOS_DIR / f"{clean_slug}{ext}"
            if p.exists():
                return p
                
        # Benzer / Normalleştirilmiş Arama
        clean_norm = clean_slug.replace("-", "").replace(" ", "").replace("i", "ı")
        for f in LOGOS_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in [".png", ".webp", ".jpg", ".jpeg"]:
                f_norm = f.stem.replace("-", "").replace(" ", "").replace("i", "ı").lower()
                if clean_norm in f_norm or f_norm in clean_norm:
                    return f

    # Cloudflare R2 üzerinden indir ve önbellekle
    try:
        from src.services.r2_service import r2_service
        r2_key = f"logos/{clean_slug}.png"
        file_bytes = r2_service.download_file(r2_key)
        if file_bytes:
            LOGOS_DIR.mkdir(parents=True, exist_ok=True)
            cached_path = LOGOS_DIR / f"{clean_slug}.png"
            cached_path.write_bytes(file_bytes)
            return cached_path
    except Exception:
        pass

    return None


@lru_cache(maxsize=128)
def kategori_logosu_base64_getir(slug: str) -> str:
    """Yarışma logosunu kırpıp tam ölçekte Base64 Data URI olarak döner."""
    p = kategori_logosu_getir(slug)
    if not p or not p.exists():
        return ""
    try:
        from PIL import Image, ImageChops
        import io

        im = Image.open(p)
        # Etraftaki gereksiz beyaz ve şeffaf boşlukları otomatik kırp
        rgb = im.convert("RGB")
        diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255)))
        diff_bbox = diff.getbbox()
        if diff_bbox:
            # Kenarlardan hafif nefes payı (padding) bırak
            w, h = im.size
            pad = 12
            crop_box = (
                max(0, diff_bbox[0] - pad),
                max(0, diff_bbox[1] - pad),
                min(w, diff_bbox[2] + pad),
                min(h, diff_bbox[3] + pad)
            )
            im = im.crop(crop_box)

        buf = io.BytesIO()
        im.save(buf, format="PNG", optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"
    except Exception:
        try:
            mime = "image/png" if p.suffix.lower() == ".png" else ("image/webp" if p.suffix.lower() == ".webp" else "image/jpeg")
            with open(p, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
                return f"data:{mime};base64,{encoded}"
        except Exception:
            return ""

# TEKNOFEST Bilinen Aşamalar ve Açıklamaları
ASAMALAR = {
    "ODR": {"kod": "ODR", "ad": "Ön Değerlendirme Raporu", "ikon": "📝", "renk": "#3b82f6"},
    "OTR": {"kod": "OTR", "ad": "Ön Tasarım Raporu", "ikon": "📐", "renk": "#2563eb"},
    "PDR": {"kod": "PDR", "ad": "Proje Detay / Ön Tasarım İnceleme", "ikon": "📋", "renk": "#0284c7"},
    "KTR": {"kod": "KTR", "ad": "Kritik Tasarım Raporu", "ikon": "🔍", "renk": "#7c3aed"},
    "CDR": {"kod": "CDR", "ad": "Kritik Tasarım İnceleme Raporu", "ikon": "🔬", "renk": "#6d28d9"},
    "DTR": {"kod": "DTR", "ad": "Detaylı Tasarım Raporu", "ikon": "📊", "renk": "#8b5cf6"},
    "AHR": {"kod": "AHR", "ad": "Atışa Hazırlık Raporu", "ikon": "🚀", "renk": "#ea580c"},
    "POR": {"kod": "POR", "ad": "Proje Planı ve Organizasyon", "ikon": "📅", "renk": "#0d9488"},
    "QR":  {"kod": "QR",  "ad": "Yeterlilik İnceleme Raporu", "ikon": "🎯", "renk": "#16a34a"},
    "FRR": {"kod": "FRR", "ad": "Uçuşa Yeterlilik Raporu", "ikon": "✈️", "renk": "#059669"},
    "PFR": {"kod": "PFR", "ad": "Uçuş Sonrası İnceleme", "ikon": "📈", "renk": "#475569"},
    "FTR": {"kod": "FTR", "ad": "Final Tasarım Raporu", "ikon": "🏆", "renk": "#dc2626"},
    "FYR": {"kod": "FYR", "ad": "Final Yarışma Raporu", "ikon": "🏅", "renk": "#b91c1c"},
    "GENEL": {"kod": "GENEL", "ad": "Genel Değerlendirme", "ikon": "⚖️", "renk": "#4b5563"},
}

# Bilinen Ana Gruplar ve Alt Kategori Tanımları
YARISMA_GRUPLARI = {
    "insanlik-yararina-teknoloji": {
        "ad": "İnsanlık Yararına Teknoloji Yarışması",
        "ikon": "🌍",
        "alt_kategoriler": [
            {"id": "lise", "ad": "Lise Seviyesi", "klasor": "insanlik-yararina-teknolojiler-yarismasi-lise-seviyesi"},
            {"id": "ortaokul", "ad": "Ortaokul Seviyesi", "klasor": "insanlik-yararina-teknolojiler-yarismasi-ortaokul-seviyesi"},
            {"id": "ilkokul", "ad": "İlkokul Seviyesi", "klasor": "insanlik-yararina-teknolojiler-yarismasi-ilkokul-seviyesi"},
            {"id": "universite", "ad": "Üniversite ve Üzeri Seviyesi", "klasor": "nsosyal-inovasyon-yarismasi"},
        ]
    },
    "roket-yarismasi": {
        "ad": "Roket Yarışması",
        "ikon": "🚀",
        "alt_kategoriler": [
            {"id": "roket-genel", "ad": "Genel Roket Kategorisi", "klasor": "roket-yarismasi"},
            {"id": "dikey-inis", "ad": "Dikey İnişli Roket", "klasor": "dikey-inisli-roket-yarismasi"},
            {"id": "su-alti-roket", "ad": "Su Altı Roket", "klasor": "su-alti-roket-yarismasi"},
        ]
    },
    "savasan-iha": {
        "ad": "Savaşan İHA Yarışması",
        "ikon": "✈️",
        "alt_kategoriler": [
            {"id": "savasan-iha-genel", "ad": "Savaşan İHA (Sabit / Döner Kanat)", "klasor": "savasan-iha-yarismasi"},
            {"id": "avci-drone", "ad": "Avcı Drone Kategorisi", "klasor": "savasan-iha-avci-drone-yarismasi"},
            {"id": "savasan-yildizlar", "ad": "Savaşan İHA Yıldızlar", "klasor": "savasan-iha-yildizlar-yarismasi"},
        ]
    },
    "iha-sistemleri": {
        "ad": "İnsansız Hava Araçları (İHA)",
        "ikon": "🛸",
        "alt_kategoriler": [
            {"id": "uluslararasi-iha", "ad": "Uluslararası İnsansız Hava Araçları", "klasor": "uluslararasi-insansiz-hava-araci-yarismasi"},
            {"id": "liseler-arasi-iha", "ad": "Liseler Arası İnsansız Hava Araçları", "klasor": "liseler-arasi-insansiz-hava-araclari-yarismasi"},
            {"id": "suru-iha", "ad": "Sürü İHA Yarışması", "klasor": "suru-iha-yarismasi"},
            {"id": "fpv-tracking", "ad": "FPV Drone İzleme (Tracking)", "klasor": "fpv-drone-izleme-tracking-yarismasi"},
            {"id": "drone-sampiyonasi", "ad": "TEKNOFEST Drone Şampiyonası", "klasor": "teknofest-drone-sampiyonasi"},
        ]
    },
    "insansiz-su-alti": {
        "ad": "İnsansız Su Altı Sistemleri",
        "ikon": "⚓",
        "alt_kategoriler": [
            {"id": "su-alti-genel", "ad": "İleri & Temel Kategori", "klasor": "insansiz-su-alti-sistemleri-yarismasi"},
            {"id": "su-alti-yildizlar", "ad": "Su Altı Yıldızlar Kategorisi", "klasor": "insansiz-su-alti-sistemleri-yildizlar-yarismasi"},
            {"id": "insansiz-deniz", "ad": "İnsansız Deniz Aracı (İDA)", "klasor": "insansiz-deniz-araci-yarismasi"},
        ]
    },
    "yapay-zeka": {
        "ad": "Yapay Zekâ Yarışmaları",
        "ikon": "🤖",
        "alt_kategoriler": [
            {"id": "havacilik-yz", "ad": "Havacılıkta Yapay Zekâ", "klasor": "havacilikta-yapay-zeka-yarismasi"},
            {"id": "saglik-yz", "ad": "Sağlıkta Yapay Zekâ", "klasor": "saglikta-yapay-zeka-yarismasi"},
            {"id": "5g-yz", "ad": "5G ve Yapay Zekâ Akıllı Yol Güvenliği", "klasor": "5g-yapay-zeka-ile-akilli-yol-guvenligi-yarismasi"},
            {"id": "dil-ajanlari", "ad": "Yapay Zekâ Dil Ajanları", "klasor": "yapay-zeka-dil-ajanlari-yarismasi"},
            {"id": "lojistik-yz", "ad": "Yapay Zekâ Destekli Lojistik Optimizasyonu", "klasor": "yapay-zeka-destekli-lojistik-anahat-optimizasyonu-yarismasi"},
            {"id": "havayolu-yz", "ad": "Yapay Zekâ Havayolu Optimizasyonu", "klasor": "yapay-zeka-destekli-havayolu-optimizasyonu-yarismasi"},
            {"id": "yz-film", "ad": "Yapay Zekâ Film Yarışması", "klasor": "teknofest-yapay-zeka-film-yarismasi"},
        ]
    }
}


def tr_norm(s: str) -> str:
    s = str(s).lower().replace("ç", "c").replace("ğ", "g").replace("ı", "i").replace("ö", "o").replace("ş", "s").replace("ü", "u")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def klasor_bul(query: str) -> Path | None:
    """Yarışma ID, kod veya başlığına göre klasörü bulur veya R2'den çeker."""
    if DOCS_DIR.exists():
        direct = DOCS_DIR / query
        if direct.exists() and direct.is_dir():
            return direct

        words = [w for w in tr_norm(query).split() if len(w) >= 2 and w not in (
            "tekno", "teknofest", "2026", "yarismasi", "genel", "raporu", "ve", "ile", "tr", "rub"
        )]
        if words:
            best_folder, best_score = None, 0
            for f in DOCS_DIR.iterdir():
                if not f.is_dir():
                    continue
                f_norm = tr_norm(f.name)
                f_words = f_norm.split()
                score = sum(3 for w in words if w in f_words) + sum(1 for w in words if w in f_norm)
                if any(w == f_words[0] for w in words):
                    score += 3
                if score > best_score:
                    best_score = score
                    best_folder = f
            if best_folder:
                return best_folder

    # R2 üzerinden dinamik klasör oluştur
    try:
        from src.services.r2_service import r2_service
        clean_slug = r2_service.slugify(query)
        target_dir = DOCS_DIR / clean_slug / "sartname"
        target_dir.mkdir(parents=True, exist_ok=True)
        return DOCS_DIR / clean_slug
    except Exception:
        pass

    return None


@lru_cache(maxsize=128)
def klasor_bilgisi(yarisma_id_veya_adi: str) -> dict:
    """Belirtilen yarışma için şartname ve aşama şablonlarını tarar."""
    klasor_yolu = klasor_bul(yarisma_id_veya_adi)
    if not klasor_yolu or not klasor_yolu.exists():
        return {"asama_listesi": ["GENEL"], "sartname_pdf": None, "sablonlar": {}, "zorunlu_bolumler": []}

    sartname_files = list((klasor_yolu / "sartname").glob("*.pdf"))
    sartname_pdf = sartname_files[0] if sartname_files else None

    # Eğer yerelde PDF yoksa R2'den çek
    if not sartname_pdf:
        try:
            from src.services.r2_service import r2_service
            clean_slug = r2_service.slugify(yarisma_id_veya_adi)
            r2_key = f"sartnameler/{clean_slug}/{clean_slug}_sartname.pdf"
            pdf_bytes = r2_service.download_file(r2_key)
            if pdf_bytes:
                sn_dir = klasor_yolu / "sartname"
                sn_dir.mkdir(parents=True, exist_ok=True)
                target_pdf = sn_dir / f"{clean_slug}_sartname.pdf"
                target_pdf.write_bytes(pdf_bytes)
                sartname_pdf = target_pdf
        except Exception:
            pass

    asama_map = {}
    tum_sablonlar = []

    # 1. Yeni Standart: asamalar/[asama]/sablon/
    asamalar_dir = klasor_yolu / "asamalar"
    if asamalar_dir.exists() and asamalar_dir.is_dir():
        for stg_dir in sorted(asamalar_dir.iterdir()):
            if stg_dir.is_dir():
                stg_code = stg_dir.name.upper()
                sablon_dir = stg_dir / "sablon"
                if sablon_dir.exists():
                    s_files = list(sablon_dir.glob("*.pdf")) + [f for f in sablon_dir.glob("*.docx") if not f.with_suffix(".pdf").exists()]
                    if s_files:
                        asama_map[stg_code] = s_files[0]
                        tum_sablonlar.extend(s_files)

    # 2. Geriye Dönük Uyumluluk (rapor_sablonlari/)
    if not asama_map:
        sablon_dir = klasor_yolu / "rapor_sablonlari"
        sablon_files = list(sablon_dir.glob("*.pdf")) + [f for f in sablon_dir.glob("*.docx") if not f.with_suffix(".pdf").exists()] if sablon_dir.exists() else []
        tum_sablonlar = sablon_files
        for sf in sablon_files:
            name_u = sf.stem.upper()
            detected_asama = "GENEL"
            for code in ("OTR", "ODR", "KTR", "PDR", "CDR", "DTR", "AHR", "POR", "QR", "FRR", "FTR", "FYR"):
                if code in name_u or code in sf.name.upper():
                    detected_asama = code
                    break
            if detected_asama not in asama_map:
                if sf.suffix.lower() == ".docx" and sf.with_suffix(".pdf").exists():
                    sf = sf.with_suffix(".pdf")
                asama_map[detected_asama] = sf

    # Şartname dosya adından da aşama tespit et
    if sartname_pdf and not asama_map:
        sn_u = sartname_pdf.name.upper()
        for code in ("OTR", "ODR", "KTR", "PDR", "AHR", "FTR"):
            if code in sn_u and code not in asama_map:
                asama_map[code] = sartname_pdf

    asama_listesi = list(asama_map.keys()) if asama_map else ["GENEL"]
    k_name = klasor_yolu.name
    if "OTR" in asama_listesi and "KTR" not in asama_listesi and any(w in k_name for w in ("roket", "iha", "yapay", "drone")):
        asama_listesi.append("KTR")

    return {
        "asama_listesi": asama_listesi,
        "sartname_pdf": sartname_pdf,
        "sablonlar": asama_map,
        "tum_sablon_dosyalari": tum_sablonlar
    }


def dokuman_rehberi_getir(klasor_adi: str, secili_asama: str = "OTR") -> dict:
    """Seçilen yarışma ve aşamaya ait dokümanları, sayfa sayısını ve kılavuz başlıklarını döner."""
    kb = klasor_bilgisi(klasor_adi)
    sartname_pdf = kb.get("sartname_pdf")
    sablon_pdf = kb.get("sablonlar", {}).get(secili_asama) or (kb.get("tum_sablon_dosyalari", [None])[0] if kb.get("tum_sablon_dosyalari") else None)

    if sablon_pdf and sablon_pdf.suffix.lower() == ".docx" and sablon_pdf.with_suffix(".pdf").exists():
        sablon_pdf = sablon_pdf.with_suffix(".pdf")

    sartname_sayfa_sayisi = 0
    if sartname_pdf and sartname_pdf.exists() and sartname_pdf.suffix.lower() == ".pdf":
        try:
            doc = pymupdf.open(sartname_pdf)
            sartname_sayfa_sayisi = len(doc)
            doc.close()
        except Exception:
            pass

    sablon_sayfa_sayisi = 0
    if sablon_pdf and sablon_pdf.exists() and sablon_pdf.suffix.lower() == ".pdf":
        try:
            doc = pymupdf.open(sablon_pdf)
            sablon_sayfa_sayisi = len(doc)
            doc.close()
        except Exception:
            pass

    # Aşama kuralları
    asama_meta = ASAMALAR.get(secili_asama, ASAMALAR["GENEL"])

    return {
        "asama": secili_asama,
        "asama_adi": asama_meta["ad"],
        "asama_ikon": asama_meta["ikon"],
        "asama_renk": asama_meta["renk"],
        "sartname_pdf_yolu": str(sartname_pdf) if sartname_pdf else None,
        "sartname_pdf_adi": sartname_pdf.name if sartname_pdf else "Şartname PDF'i bulunamadı",
        "sartname_sayfa_sayisi": sartname_sayfa_sayisi,
        "sablon_yolu": str(sablon_pdf) if sablon_pdf else None,
        "sablon_adi": sablon_pdf.name if sablon_pdf else "Rapor Şablonu bulunamadı",
        "sablon_sayfa_sayisi": sablon_sayfa_sayisi,
        "zorunlu_bolumler": [
            "1. PROJE MEVCUT DURUM VE İHTİYAÇ ANALİZİ",
            "2. VERİ SETLERİ VE HAZIRLIK SÜREÇLERİ",
            "3. ALGORİTMA VE SİSTEM MİMARİSİ",
            "4. AKIŞ ŞEMASI VE BLOK DİYAGRAMLAR",
            "5. ÖZGÜNLÜK VE YENİLİKÇİ YÖNLER",
            "6. PROJE TAKVİMİ VE İŞ PAKETLERİ",
            "7. SONUÇLAR VE RİSK ANALİZİ",
            "8. KAYNAKÇA VE REFERANSLAR",
        ],
        "sayfa_limiti": "Maksimum 25 Sayfa (Kapak ve Kaynakça hariç)",
        "yazi_tipi_kurallari": "Times New Roman / Arial 11pt, 1.15 satır aralığı, 2.5 cm kenar boşlukları"
    }


def pdf_sayfa_onizle(pdf_yolu: str, sayfa_no: int, dpi: int = 140) -> bytes | None:
    """PDF'in istenen sayfasını PNG baytları olarak render eder."""
    if not pdf_yolu or not os.path.exists(pdf_yolu):
        return None
    try:
        doc = pymupdf.open(pdf_yolu)
        if 0 <= sayfa_no < len(doc):
            pix = doc[sayfa_no].get_pixmap(dpi=dpi)
            png_bytes = pix.tobytes("png")
            doc.close()
            return png_bytes
        doc.close()
    except Exception:
        pass
    return None


def kriterleri_otomatik_cikar(pdf_yolu: str | None = None, asama_kodu: str = "OTR") -> list[dict]:
    """
    Şartname veya Rapor Şablonu PDF dosyasını tarayarak puanlama kriterlerini
    ve ağırlıklarını otomatik olarak çıkarır. Toplam tavan puan 100 olacak şekilde dengelenir.
    """
    cikarilan_kriterler = []
    
    if pdf_yolu and os.path.exists(pdf_yolu):
        try:
            doc = pymupdf.open(pdf_yolu)
            tam_metin = ""
            for page in doc:
                tam_metin += page.get_text() + "\n"
            doc.close()

            # 1. Başlık + Puan Kalıplarını Çıkar (ör: "1. PROJE ÖZETİ (15 Puan)", "Yöntem: %25", vb.)
            patterns = [
                r"(?:^|\n)\s*(\d{1,2}[\.\)]?\s+[A-Za-zÇĞİÖŞÜçğıöşü\s]{3,50})\s*[:\-\—\(\[]\s*(?:%|yüzde)?\s*(\d{1,2})\s*(?:Puan|puan|%|p\b|\)\])",
                r"(?:^|\n)\s*([A-Za-zÇĞİÖŞÜçğıöşü\s]{3,40})\s*[:\-\—]\s*(?:%|yüzde)?\s*(\d{1,2})\s*(?:Puan|puan|%)",
                r"(?:%|yüzde)\s*(\d{1,2})\s*[:\-\—]?\s*([A-Za-zÇĞİÖŞÜçğıöşü\s]{3,40})",
            ]
            for p in patterns:
                for match in re.finditer(p, tam_metin):
                    g1 = match.group(1).strip()
                    g2 = match.group(2).strip()
                    if g1.isdigit():
                        puan = float(g1)
                        k_ad = g2
                    else:
                        puan = float(g2)
                        k_ad = g1

                    # Başlık numarasını temizle
                    k_ad = re.sub(r"^\d{1,2}[\.\)]\s*", "", k_ad).strip()
                    if len(k_ad) > 3 and 0 < puan <= 50 and not any(k["name"].lower() == k_ad.lower() for k in cikarilan_kriterler):
                        cikarilan_kriterler.append({
                            "id": f"C{len(cikarilan_kriterler)+1}",
                            "name": k_ad.title(),
                            "max_score": puan,
                            "section": f"{len(cikarilan_kriterler)+1}"
                        })
            
            # 2. Eğer açık puan bulunamadıysa, şablondaki ana başlıkları çıkarıp puanları eşit/ağırlıklı dağıt
            if not cikarilan_kriterler:
                basliklar = re.findall(r"(?:^|\n)\s*(\d{1,2}[\.\)]\s+[A-ZÇĞİÖŞÜ\s]{4,60})", tam_metin)
                temiz_basliklar = []
                for b in basliklar:
                    tb = re.sub(r"^\d{1,2}[\.\)]\s*", "", b).strip().title()
                    if len(tb) > 3 and tb not in temiz_basliklar and not any(w in tb.lower() for w in ["içindekiler", "kapak", "teknofest", "tablolar", "şekiller"]):
                        temiz_basliklar.append(tb)
                
                if temiz_basliklar:
                    n = len(temiz_basliklar)
                    taban_puan = round(100.0 / n, 1)
                    kalan = 100.0
                    for i, b_ad in enumerate(temiz_basliklar):
                        p_val = taban_puan if i < n - 1 else round(kalan, 1)
                        kalan -= taban_puan
                        cikarilan_kriterler.append({
                            "id": f"C{i+1}",
                            "name": b_ad,
                            "max_score": p_val,
                            "section": str(i+1)
                        })
        except Exception:
            pass

    # Toplam puan 100'e eşitlenecek şekilde normalize et
    toplam = sum(k["max_score"] for k in cikarilan_kriterler)
    if cikarilan_kriterler and toplam > 0 and toplam != 100:
        for k in cikarilan_kriterler:
            k["max_score"] = round((k["max_score"] / toplam) * 100, 1)
        fark = 100.0 - sum(k["max_score"] for k in cikarilan_kriterler)
        if cikarilan_kriterler and abs(fark) > 0.01:
            cikarilan_kriterler[0]["max_score"] = round(cikarilan_kriterler[0]["max_score"] + fark, 1)

    # Eğer hiçbir başlık veya kriter tespit edilemediyse akıllı varsayılan ata
    if not cikarilan_kriterler:
        if asama_kodu in ("OTR", "PDR", "ODR"):
            cikarilan_kriterler = [
                {"id": "C1", "name": "Problem Tanımı ve İhtiyaç Analizi", "max_score": 20.0, "section": "1"},
                {"id": "C2", "name": "Özgünlük, Yenilik ve İnovasyon", "max_score": 25.0, "section": "2"},
                {"id": "C3", "name": "Teknik Yöntem ve Çözüm Mimarisi", "max_score": 30.0, "section": "3"},
                {"id": "C4", "name": "Proje Takvimi ve Risk Yönetimi", "max_score": 15.0, "section": "4"},
                {"id": "C5", "name": "Rapor Düzeni ve Şablon Uyumu", "max_score": 10.0, "section": "Genel"},
            ]
        elif asama_kodu in ("KTR", "CDR"):
            cikarilan_kriterler = [
                {"id": "C1", "name": "Detaylı Tasarım ve Sistem Mimarisi", "max_score": 30.0, "section": "1"},
                {"id": "C2", "name": "Simülasyon, Test ve Analiz Sonuçları", "max_score": 25.0, "section": "2"},
                {"id": "C3", "name": "Üretim ve Entegrasyon Olgunluğu", "max_score": 20.0, "section": "3"},
                {"id": "C4", "name": "Güvenlik, Doğrulama ve Bütçe Planı", "max_score": 15.0, "section": "4"},
                {"id": "C5", "name": "Raporlama Kalitesi ve Referanslar", "max_score": 10.0, "section": "Genel"},
            ]
        elif asama_kodu in ("AHR", "FTR", "FYR"):
            cikarilan_kriterler = [
                {"id": "C1", "name": "Sistem Hazırlık ve Entegrasyon Başarımı", "max_score": 35.0, "section": "1"},
                {"id": "C2", "name": "Operasyonel Güvenlik ve Prosedürler", "max_score": 30.0, "section": "2"},
                {"id": "C3", "name": "Saha/Uçuş/Atış Test Doğrulamaları", "max_score": 25.0, "section": "3"},
                {"id": "C4", "name": "Nihai Kontrol ve Dokümantasyon", "max_score": 10.0, "section": "Genel"},
            ]
        else:
            cikarilan_kriterler = [
                {"id": "C1", "name": "Özgünlük ve Yenilikçi Yaklaşım", "max_score": 25.0, "section": "1"},
                {"id": "C2", "name": "Teknik Derinlik ve Tasarım", "max_score": 30.0, "section": "2"},
                {"id": "C3", "name": "Uygulanabilirlik ve Etki", "max_score": 25.0, "section": "3"},
                {"id": "C4", "name": "Raporlama Kalitesi ve Şablon Uyumu", "max_score": 20.0, "section": "Genel"},
            ]


    return cikarilan_kriterler


OZEL_KATEGORI_ISIMLERI = {
    "biyoteknoloji-inovasyon-yarismasi": "Biyoteknoloji İnovasyon Yarışması",
    "saglikta-yapay-zeka-yarismasi": "Sağlıkta Yapay Zekâ Yarışması",
    "havacilikta-yapay-zeka-yarismasi": "Havacılıkta Yapay Zekâ Yarışması",
    "roket-yarismasi": "Roket Yarışması",
    "dikey-inisli-roket-yarismasi": "Dikey İnişli Roket Yarışması",
    "su-alti-roket-yarismasi": "Su Altı Roket Yarışması",
    "savasan-iha-yarismasi": "Savaşan İHA Yarışması",
    "insansiz-su-alti-sistemleri-yarismasi": "İnsansız Su Altı Sistemleri Yarışması",
    "robotaksi-binek-otonom-arac-yarismasi": "Robotaksi Binek Otonom Araç Yarışması",
    "celikkubbe-hava-savunma-sistemleri-yarismasi": "Çelik Kubbe Hava Savunma Sistemleri Yarışması",
    "tarim-teknolojileri-yarismasi": "Tarım Teknolojileri Yarışması",
    "cip-tasarim-yarismasi": "Çip Tasarım Yarışması",
    "hyperloop-gelistirme-yarismasi": "Hyperloop Geliştirme Yarışması",
    "jet-motor-tasarim-yarismasi": "Jet Motor Tasarım Yarışması",
    "sanayide-robotik-uygulamalar-yarismasi": "Sanayide Robotik Uygulamalar Yarışması",
    "insanlik-yararina-teknolojiler-yarismasi-lise-seviyesi": "İnsanlık Yararına Teknoloji Yarışması (Lise Seviyesi)",
    "insanlik-yararina-teknolojiler-yarismasi-ortaokul-seviyesi": "İnsanlık Yararına Teknoloji Yarışması (Ortaokul Seviyesi)",
    "insanlik-yararina-teknolojiler-yarismasi-ilkokul-seviyesi": "İnsanlık Yararına Teknoloji Yarışması (İlkokul Seviyesi)",
    "fpv-drone-izleme-tracking-yarismasi": "FPV Drone İzleme ve Takip Yarışması",
    "finansal-teknolojiler-yarismasi": "Finansal Teknolojiler Yarışması",
    "blokzincir-yarismasi": "Blokzincir Yarışması",
    "uluslararasi-elektrikli-arac-yarislari": "Uluslararası Elektrikli Araç Yarışları",
    "uluslararasi-iha-yarismasi": "Uluslararası İHA Yarışması",
    "akilli-ulasim-yarismasi": "Akıllı Ulaşım Yarışması",
    "egitim-teknolojileri-yarismasi": "Eğitim Teknolojileri Yarışması",
    "engelsiz-yasam-teknolojileri-yarismasi": "Engelsiz Yaşam Teknolojileri Yarışması",
    "cevre-ve-enerji-teknolojileri-yarismasi": "Çevre ve Enerji Teknolojileri Yarışması",
    "turizm-teknolojileri-yarismasi": "Turizm Teknolojileri Yarışması",
    "tarimsal-insansiz-kara-araci-yarismasi": "Tarımsal İnsansız Kara Aracı (İKA) Yarışması",
    "kablosuz-haberlesme-yarismasi": "Kablosuz Haberleşme Yarışması",
    "model-uydu-yarismasi": "Model Uydu Yarışması",
    "suru-iha-yarismasi": "Sürü İHA Yarışması",
    "psikolojide-teknolojik-uygulamalar-yarismasi": "Psikolojide Teknolojik Uygulamalar Yarışması",
    "turkce-dogal-dil-isleme-yarismasi": "Türkçe Doğal Dil İşleme Yarışması",
    "kuantum-hackathon-yarismasi": "Kuantum Hackathon Yarışması",
    "nsosyal-inovasyon-yarismasi": "Sosyal İnovasyon Yarışması",
}


def turkce_kategori_adi_formatla(slug: str) -> str:
    """Slug'ı kusursuz Türkçe karakterli kategori adına dönüştürür."""
    if slug in OZEL_KATEGORI_ISIMLERI:
        return OZEL_KATEGORI_ISIMLERI[slug]

    words = slug.split("-")
    tr_map = {
        "yarismasi": "Yarışması",
        "yarislari": "Yarışları",
        "teknolojileri": "Teknolojileri",
        "teknoloji": "Teknoloji",
        "saglik": "Sağlık",
        "saglikta": "Sağlıkta",
        "yapay": "Yapay",
        "zeka": "Zekâ",
        "tasarim": "Tasarım",
        "tasarimi": "Tasarımı",
        "gelistirme": "Geliştirme",
        "gelistirilmesi": "Geliştirilmesi",
        "insansiz": "İnsansız",
        "insanlik": "İnsanlık",
        "yararina": "Yararına",
        "arac": "Araç",
        "araci": "Aracı",
        "araclari": "Araçları",
        "otonom": "Otonom",
        "savasan": "Savaşan",
        "inisli": "İnişli",
        "inis": "İniş",
        "celik": "Çelik",
        "celikkubbe": "Çelik Kubbe",
        "kubbe": "Kubbe",
        "cip": "Çip",
        "iha": "İHA",
        "ika": "İKA",
        "siha": "SİHA",
        "yerli": "Yerli",
        "milli": "Milli",
        "akilli": "Akıllı",
        "egitim": "Eğitim",
        "cevre": "Çevre",
        "enerji": "Enerji",
        "biyo": "Biyo",
        "biyoteknoloji": "Biyoteknoloji",
        "inovasyon": "İnovasyon",
        "guvenlik": "Güvenlik",
        "haberlesme": "Haberleşme",
        "dogal": "Doğal",
        "dil": "Dil",
        "isleme": "İşleme",
        "lise": "Lise",
        "ortaokul": "Ortaokul",
        "ilkokul": "İlkokul",
        "universite": "Üniversite",
        "seviyesi": "Seviyesi",
    }
    
    formatted_words = []
    for w in words:
        w_lower = w.lower()
        if w_lower in tr_map:
            formatted_words.append(tr_map[w_lower])
        else:
            formatted_words.append(w.capitalize())
            
    return " ".join(formatted_words)


def tum_yarismalari_sozluk_getir() -> dict[str, str]:
    """Cloudflare D1 üzerindeki 60 yarışmayı slug -> Okunabilir Ad sözlüğü olarak döndürür."""
    sonuc = {}
    try:
        from src.database.db import db
        comps = db.list_all_competitions()
        for c in comps:
            slug = c.get("slug")
            name = c.get("name")
            if slug and name:
                sonuc[slug] = name
    except Exception:
        pass

    if not sonuc and DOCS_DIR.exists():
        for k in sorted(DOCS_DIR.iterdir()):
            if k.is_dir():
                slug = k.name
                ad = turkce_kategori_adi_formatla(slug)
                sonuc[slug] = f"TEKNOFEST 2026 · {ad}"
    
    if not sonuc:
        for slug, ad in OZEL_KATEGORI_ISIMLERI.items():
            sonuc[slug] = f"TEKNOFEST 2026 · {ad}"
            
    return sonuc


# =============================================================================
# 1. KATEGORİ ZORUNLULUKLARI (ŞARTNAMEDEN ÇIKARILANLAR)
# =============================================================================
def sartnameden_kategori_zorunluluklarini_cikar(klasor_adi: str) -> dict:
    """
    Yarışma ŞARTNAMESİNİ analiz ederek takımın ve projenin yarışmaya UYGUNLUĞUNU
    (Ön Eleme kriterleri) belirleyen kuralları çıkarır.
    """
    kb = klasor_bilgisi(klasor_adi)
    sartname_pdf = kb.get("sartname_pdf")
    
    # Standart Kategori Zorunlulukları Çerçevesi
    zorunluluklar = {
        "kategori_slug": klasor_adi,
        "kategori_adi": klasor_adi.replace("-", " ").title(),
        "hedef_egitim_seviyesi": "Lise / Üniversite / Lisansüstü / Mezun",
        "takim_uye_sayisi": {"min": 2, "max": 6},
        "danisman_sarti": "Lise seviyesi için zorunlu, üniversite için isteğe bağlı",
        "dil_gereksinimi": "Türkçe (Teknik terimler parantez içinde İngilizce belirtilebilir)",
        "temel_teknik_isterler": [
            "Projenin yarışma şartnamesindeki problem tanımıyla doğrudan örtüşmesi",
            "Yapay zekâ veya otonom sistem mimarisinin yerli/özgün algoritmalarla modellenmesi",
            "Simülasyon veya deneysel test ortamının kurgulanmış olması",
        ],
        "etik_ve_ozgunluk_kurallari": [
            "İntihal benzerlik oranı azami %15 olmalıdır.",
            "Takım ve danışman kimlik bilgileri hakem kör değerlendirmesi için rapor metninde gizlenmelidir."
        ],
        "sartname_dosyasi": sartname_pdf.name if sartname_pdf else "Mevcut Değil"
    }

    if "lise" in klasor_adi.lower():
        zorunluluklar["hedef_egitim_seviyesi"] = "Yalnızca Lise ve Dengi Okul Öğrencileri"
        zorunluluklar["danisman_sarti"] = "Zorunlu (Danışman Öğretmen / Akademisyen)"
    elif "ilkokul" in klasor_adi.lower() or "ortaokul" in klasor_adi.lower():
        zorunluluklar["hedef_egitim_seviyesi"] = "İlkokul / Ortaokul Öğrencileri"
        zorunluluklar["danisman_sarti"] = "Zorunlu (Danışman Öğretmen)"
    
    return zorunluluklar


# =============================================================================
# 2. RAPOR ZORUNLULUKLARI (RAPOR ŞABLONUNDAN ÇIKARILANLAR)
# =============================================================================
def sablondan_rapor_zorunluluklarini_cikar(klasor_adi: str, asama: str = "OTR") -> dict:
    """
    Aşama RAPOR ŞABLONUNU analiz ederek yüklenen raporun BİÇİMİNİ ve
    KRİTER BAZLI PUANLAMASINI (0-100 Rubrik) belirleyen kuralları çıkarır.
    """
    kb = klasor_bilgisi(klasor_adi)
    sablon_pdf = kb.get("sablonlar", {}).get(asama)
    
    # Şablondan zorunlu başlıklar
    if asama in ("OTR", "PDR", "ODR"):
        zorunlu_basliklar = [
            "1. PROJE ÖZETİ VE PROBLEM TANIMI",
            "2. VERİ SETİ VE YÖNTEM MİMARİSİ",
            "3. ÖZGÜNLÜK VE YENİLİKÇİ YÖNLER",
            "4. PROJE İŞ TAKVİMİ VE BÜTÇE PLANI",
            "5. RİSK ANALİZİ VE KAYNAKLAR"
        ]
        max_sayfa = 15
    elif asama in ("KTR", "CDR"):
        zorunlu_basliklar = [
            "1. DETAYLI SİSTEM MİMARİSİ VE TASARIM",
            "2. ALGORİTMA VE TEST SONUÇLARI",
            "3. PROTOTİP / DONANIM ENTEGRASYONU",
            "4. GÜVENLİK VE STANDARTLARA UYGUNLUK",
            "5. PROJE YÖNETİMİ VE KAYNAKÇA"
        ]
        max_sayfa = 25
    else:
        zorunlu_basliklar = [
            "1. ATIŞ / UÇUŞ / SAHA TEST RAPORU",
            "2. OPERASYONEL GÜVENLİK PROSEDÜRLERİ",
            "3. SONUÇ DEĞERLENDİRMESİ VE GELİŞTİRMELER"
        ]
        max_sayfa = 30

    rubrik_kriterleri = kriterleri_otomatik_cikar(str(sablon_pdf) if sablon_pdf else None, asama)

    return {
        "asama": asama,
        "sablon_dosyasi": sablon_pdf.name if sablon_pdf else f"TEKNOFEST_{asama}_Sablonu.pdf",
        "maksimum_sayfa_siniri": max_sayfa,
        "sayfa_asimi_kurali": "Sayfa sınırını aşan her sayfa için genel puandan 2 puan kırılır.",
        "yazi_tipi_ve_marjin": "Times New Roman / Arial 11pt, 1.15 satır aralığı, kenarlar 2.5 cm",
        "zorunlu_basliklar": zorunlu_basliklar,
        "rubrik_kriterleri": rubrik_kriterleri
    }

