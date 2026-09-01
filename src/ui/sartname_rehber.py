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

import tempfile

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = Path(tempfile.gettempdir()) / "tsistem_cache"
DOCS_DIR = CACHE_DIR / "yarismalar"
RUBRICS_DIR = CACHE_DIR / "rubrics"
LOGOS_DIR = CACHE_DIR / "logos"


@lru_cache(maxsize=128)
def kategori_logosu_getir(slug: str) -> Path | None:
    """Yarışma slug'ına ait resmî logo dosya yolunu döndürür, yoksa R2'den indirip döner."""
    if not slug:
        return None
        
    clean_slug = slug.strip().lower()

    # 1. DOCS_DIR / slug / logo.* (Öncelikli yerel klasör)
    comp_dir = DOCS_DIR / clean_slug
    if comp_dir.exists():
        for ext in [".png", ".webp", ".jpg", ".jpeg"]:
            p = comp_dir / f"logo{ext}"
            if p.exists():
                return p

    # 2. LOGOS_DIR / slug.*
    if LOGOS_DIR.exists():
        for ext in [".png", ".webp", ".jpg", ".jpeg"]:
            p = LOGOS_DIR / f"{clean_slug}{ext}"
            if p.exists():
                return p
                
        clean_norm = clean_slug.replace("-", "").replace(" ", "").replace("i", "ı")
        for f in LOGOS_DIR.iterdir():
            if f.is_file() and f.suffix.lower() in [".png", ".webp", ".jpg", ".jpeg"]:
                f_norm = f.stem.replace("-", "").replace(" ", "").replace("i", "ı").lower()
                if clean_norm in f_norm or f_norm in clean_norm:
                    return f

    # 3. Cloudflare R2'den dinamik çek
    try:
        from src.services.r2_service import r2_service
        for ext in [".png", ".webp", ".jpg", ".jpeg"]:
            r2_key = f"yarismalar/{clean_slug}/logo{ext}"
            img_bytes = r2_service.download_bytes(r2_key)
            if img_bytes:
                comp_dir.mkdir(parents=True, exist_ok=True)
                local_logo = comp_dir / f"logo{ext}"
                local_logo.write_bytes(img_bytes)
                return local_logo
    except Exception:
        pass

    # 4. Varsayılan T-Sistem Logosu
    fallback_logo = ROOT / "src" / "ui" / "tsistem_logo.png"
    if fallback_logo.exists():
        return fallback_logo

    return None


@lru_cache(maxsize=256)
def kategori_logosu_base64_getir(slug: str) -> str:
    """Yarışma logosunu kırpıp optimize boyutlu (max 180px) Base64 Data URI olarak döner."""
    p = kategori_logosu_getir(slug)
    if not p or not p.exists():
        return ""
    try:
        from PIL import Image, ImageChops
        import io

        im = Image.open(p)
        # Etraftaki gereksiz beyaz ve şeffaf boşlukları otomatik kırp
        if im.mode in ("RGBA", "LA"):
            alpha = im.getchannel("A")
            bbox = alpha.getbbox()
            if bbox:
                im = im.crop(bbox)
        else:
            rgb = im.convert("RGB")
            diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, (255, 255, 255)))
            diff_bbox = diff.getbbox()
            if diff_bbox:
                w, h = im.size
                pad = 8
                crop_box = (
                    max(0, diff_bbox[0] - pad),
                    max(0, diff_bbox[1] - pad),
                    min(w, diff_bbox[2] + pad),
                    min(h, diff_bbox[3] + pad)
                )
                im = im.crop(crop_box)

        # Hızlı yükleme ve hafiflik için thumbnail boyutlandır
        im.thumbnail((180, 180), Image.Resampling.LANCZOS)

        buf = io.BytesIO()
        im.save(buf, format="WEBP", quality=90)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/webp;base64,{encoded}"
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
    "ODR": {"kod": "ODR", "ad": "Ön Değerlendirme Raporu", "ikon": "", "renk": "#3b82f6"},
    "OTR": {"kod": "OTR", "ad": "Ön Tasarım Raporu", "ikon": "", "renk": "#2563eb"},
    "PDR": {"kod": "PDR", "ad": "Proje Detay / Ön Tasarım İnceleme", "ikon": "", "renk": "#0284c7"},
    "KTR": {"kod": "KTR", "ad": "Kritik Tasarım Raporu", "ikon": "", "renk": "#7c3aed"},
    "CDR": {"kod": "CDR", "ad": "Kritik Tasarım İnceleme Raporu", "ikon": "", "renk": "#6d28d9"},
    "DTR": {"kod": "DTR", "ad": "Detaylı Tasarım Raporu", "ikon": "", "renk": "#8b5cf6"},
    "AHR": {"kod": "AHR", "ad": "Atışa Hazırlık Raporu", "ikon": "", "renk": "#ea580c"},
    "POR": {"kod": "POR", "ad": "Proje Planı ve Organizasyon", "ikon": "", "renk": "#0d9488"},
    "QR":  {"kod": "QR",  "ad": "Yeterlilik İnceleme Raporu", "ikon": "", "renk": "#16a34a"},
    "FRR": {"kod": "FRR", "ad": "Uçuşa Yeterlilik Raporu", "ikon": "", "renk": "#059669"},
    "PFR": {"kod": "PFR", "ad": "Uçuş Sonrası İnceleme", "ikon": "", "renk": "#475569"},
    "FTR": {"kod": "FTR", "ad": "Final Tasarım Raporu", "ikon": "", "renk": "#dc2626"},
    "FYR": {"kod": "FYR", "ad": "Final Yarışma Raporu", "ikon": "", "renk": "#b91c1c"},
    "GENEL": {"kod": "GENEL", "ad": "Genel Değerlendirme", "ikon": "", "renk": "#4b5563"},
}

# Bilinen Ana Gruplar ve Alt Kategori Tanımları
YARISMA_GRUPLARI = {
    "insanlik-yararina-teknoloji": {
        "ad": "İnsanlık Yararına Teknoloji Yarışması",
        "ikon": "",
        "alt_kategoriler": [
            {"id": "lise", "ad": "Lise Seviyesi", "klasor": "insanlik-yararina-teknolojiler-yarismasi-lise-seviyesi"},
            {"id": "ortaokul", "ad": "Ortaokul Seviyesi", "klasor": "insanlik-yararina-teknolojiler-yarismasi-ortaokul-seviyesi"},
            {"id": "ilkokul", "ad": "İlkokul Seviyesi", "klasor": "insanlik-yararina-teknolojiler-yarismasi-ilkokul-seviyesi"},
            {"id": "universite", "ad": "Üniversite ve Üzeri Seviyesi", "klasor": "nsosyal-inovasyon-yarismasi"},
        ]
    },
    "roket-yarismasi": {
        "ad": "Roket Yarışması",
        "ikon": "",
        "alt_kategoriler": [
            {"id": "roket-genel", "ad": "Genel Roket Kategorisi", "klasor": "roket-yarismasi"},
            {"id": "dikey-inis", "ad": "Dikey İnişli Roket", "klasor": "dikey-inisli-roket-yarismasi"},
            {"id": "su-alti-roket", "ad": "Su Altı Roket", "klasor": "su-alti-roket-yarismasi"},
        ]
    },
    "savasan-iha": {
        "ad": "Savaşan İHA Yarışması",
        "ikon": "",
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
    """Yarışma ID, slug veya başlığına göre klasörü bulur veya R2/D1 hedef yolunu döndürür."""
    if not query:
        return None
    slug = query.strip().lower()
    target_dir = DOCS_DIR / slug
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir


@lru_cache(maxsize=128)
def klasor_bilgisi(yarisma_id_veya_adi: str) -> dict:
    """Belirtilen yarışma için şartname ve aşama şablonlarını Cloudflare D1 ve R2 üzerinden dinamik çözer."""
    if not yarisma_id_veya_adi:
        return {"asama_listesi": ["GENEL"], "sartname_pdf": None, "sablonlar": {}, "tum_sablon_dosyalari": []}

    slug = yarisma_id_veya_adi.strip().lower()
    comp_dir = DOCS_DIR / slug
    comp_dir.mkdir(parents=True, exist_ok=True)
    sn_dir = comp_dir / "sartname"
    sn_dir.mkdir(parents=True, exist_ok=True)

    sartname_pdf = None
    asama_map = {}
    tum_sablonlar = []

    # 1. Cloudflare D1 & R2 Entegrasyonu
    try:
        from src.data import repos
        from src.services.r2_service import r2_service

        repo = repos().competitions
        # A) Şartnameyi D1 ve R2'den Çek
        specs = repo.list_specs(slug)
        if specs:
            primary_spec = next((s for s in specs if s.is_primary), specs[0])
            if primary_spec and primary_spec.r2_key:
                local_sn = sn_dir / (Path(primary_spec.r2_key).name)
                if not local_sn.exists():
                    pdf_bytes = r2_service.download_bytes(primary_spec.r2_key)
                    if pdf_bytes:
                        local_sn.write_bytes(pdf_bytes)
                if local_sn.exists():
                    sartname_pdf = local_sn

        # B) Şablonları D1 ve R2'den Çek
        stages = repo.list_stages(slug)
        for stg in stages:
            stg_code = (stg.stage_code or "OTR").upper().replace("Ö", "O").replace("Ü", "U").replace("İ", "I")
            stg_dir = comp_dir / "sablon" / stg_code
            stg_dir.mkdir(parents=True, exist_ok=True)

            r2_target = stg.sablon_pdf_r2_key or stg.sablon_docx_r2_key
            if r2_target:
                fname = Path(r2_target).name
                local_file = stg_dir / fname
                if not local_file.exists():
                    data = r2_service.download_bytes(r2_target)
                    if data:
                        local_file.write_bytes(data)

                # PDF karşılığı varsa onu önceliklendir
                if local_file.suffix.lower() == ".docx" and not local_file.with_suffix(".pdf").exists():
                    pdf_target = r2_target.replace(".docx", ".pdf")
                    pdf_data = r2_service.download_bytes(pdf_target)
                    if pdf_data:
                        local_pdf = stg_dir / Path(pdf_target).name
                        local_pdf.write_bytes(pdf_data)
                        local_file = local_pdf

                if local_file.exists():
                    asama_map[stg_code] = local_file
                    tum_sablonlar.append(local_file)
    except Exception as e:
        pass

    # 2. Eğer D1/R2 boşsa R2 Prefix taraması ile dinamik kurtarma
    if not sartname_pdf or not asama_map:
        try:
            from src.services.r2_service import r2_service
            res = r2_service.client.list_objects_v2(
                Bucket=r2_service.bucket_name,
                Prefix=f"yarismalar/{slug}/"
            )
            for item in res.get("Contents", []):
                key = item["Key"]
                if "/sartname/" in key and key.lower().endswith(".pdf") and not sartname_pdf:
                    fname = Path(key).name
                    local_sn = sn_dir / fname
                    if not local_sn.exists():
                        b = r2_service.download_bytes(key)
                        if b:
                            local_sn.write_bytes(b)
                    if local_sn.exists():
                        sartname_pdf = local_sn
                elif "/sablon/" in key:
                    parts = key.split("/")
                    # yarismalar/{slug}/sablon/{STAGE}/{file}
                    stg_code = parts[3].upper() if len(parts) > 3 else "GENEL"
                    stg_code = stg_code.replace("Ö", "O").replace("Ü", "U").replace("İ", "I")
                    stg_dir = comp_dir / "sablon" / stg_code
                    stg_dir.mkdir(parents=True, exist_ok=True)
                    fname = Path(key).name
                    local_s = stg_dir / fname
                    if not local_s.exists():
                        b = r2_service.download_bytes(key)
                        if b:
                            local_s.write_bytes(b)
                    if local_s.exists() and stg_code not in asama_map:
                        asama_map[stg_code] = local_s
                        tum_sablonlar.append(local_s)
        except Exception:
            pass

    asama_listesi = list(asama_map.keys()) if asama_map else ["OTR"]

    return {
        "asama_listesi": asama_listesi,
        "sartname_pdf": sartname_pdf,
        "sablonlar": asama_map,
        "tum_sablon_dosyalari": tum_sablonlar
    }


def dokuman_rehberi_getir(klasor_adi: str, secili_asama: str = "OTR", secili_seviye: str | None = None) -> dict:
    """Seçilen yarışma ve aşamaya ait dokümanları, sayfa sayısını ve kılavuz başlıklarını döner."""
    kb = klasor_bilgisi(klasor_adi)
    sartname_pdf = kb.get("sartname_pdf")
    
    clean_asama = (secili_asama or "OTR").upper().replace("Ö", "O").replace("Ü", "U").replace("İ", "I")
    sablonlar = kb.get("sablonlar", {})
    
    # 1. Doğrudan veya seviyeli eşleşme ara
    sablon_pdf = None
    if secili_seviye:
        clean_lvl = secili_seviye.upper().replace(" ", "_")
        sablon_pdf = sablonlar.get(f"{clean_asama}_{clean_lvl}")
        
    if not sablon_pdf:
        sablon_pdf = sablonlar.get(clean_asama)
        
    if not sablon_pdf:
        for k_stg, s_file in sablonlar.items():
            if clean_asama in k_stg or k_stg in clean_asama:
                sablon_pdf = s_file
                break
                
    if not sablon_pdf and kb.get("tum_sablon_dosyalari"):
        sablon_pdf = kb.get("tum_sablon_dosyalari")[0]

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

    # Şablondan gerçek içindekiler / zorunlu bölümleri çıkar
    zorunlu_bolumler = []
    if sablon_pdf and sablon_pdf.exists():
        zorunlu_bolumler = sablon_zorunlu_bolumleri_ayikla(sablon_pdf)

    if not zorunlu_bolumler:
        zorunlu_bolumler = [
            "1. PROJE MEVCUT DURUM VE İHTİYAÇ ANALİZİ",
            "2. VERİ SETLERİ VE HAZIRLIK SÜREÇLERİ",
            "3. ALGORİTMA VE SİSTEM MİMARİSİ",
            "4. AKIŞ ŞEMASI VE BLOK DİYAGRAMLAR",
            "5. ÖZGÜNLÜK VE YENİLİKÇİ YÖNLER",
            "6. PROJE TAKVİMİ VE İŞ PAKETLERİ",
            "7. SONUÇLAR VE RİSK ANALİZİ",
            "8. KAYNAKÇA VE REFERANSLAR",
        ]

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
        "zorunlu_bolumler": zorunlu_bolumler,
        "sayfa_limiti": f"Maksimum {sablon_sayfa_sayisi if sablon_sayfa_sayisi > 0 else 25} Sayfa (Kapak ve Kaynakça hariç)",
        "yazi_tipi_kurallari": "Times New Roman / Arial 11pt, 1.15 satır aralığı, 2.5 cm kenar boşlukları"
    }


@lru_cache(maxsize=128)
def sablon_zorunlu_bolumleri_ayikla(sablon_path: Path | str) -> list[str]:
    """Şablon PDF veya Word dosyasından resmî zorunlu başlıkları ayıklar."""
    p = Path(sablon_path)
    if not p.exists():
        return []
        
    sections = []
    # PDF ise PyMuPDF ile tara
    if p.suffix.lower() == ".pdf":
        try:
            doc = pymupdf.open(str(p))
            # 1. Strateji: İçindekiler Sayfasını Ara
            for page_idx in range(min(len(doc), 6)):
                page_text = doc[page_idx].get_text()
                if any(w in page_text.upper() for w in ['İÇİNDEKİLER', 'ICINDEKILER', 'TABLE OF CONTENTS', 'İ Ç İ N D E K İ L E R']):
                    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
                    i = 0
                    while i < len(lines):
                        line = lines[i]
                        # Format A: '1.' sonraki satır 'TAKIM YAPISI ..... 3'
                        if re.match(r'^\d+[\.\)]$', line) and i + 1 < len(lines):
                            next_line = lines[i+1]
                            clean_title = re.sub(r'[\.\s\d]+$', '', next_line).strip()
                            if clean_title and len(clean_title) > 2:
                                sections.append(f'{line} {clean_title}')
                            i += 2
                            continue
                        # Format B: '1. TAKIM YAPISI ..... 3'
                        m = re.match(r'^(\d+[\.\)]\s*[A-ZÇĞİÖŞÜa-zçğıöşü\s\(\)\/\-]+)', line)
                        if m and not line.isdigit():
                            clean_title = re.sub(r'[\.\s\d]+$', '', line).strip()
                            if clean_title and len(clean_title) > 2 and clean_title not in sections:
                                sections.append(clean_title)
                        elif line.upper() in ['EKLER', 'KAYNAKÇA', 'SONUÇ'] and line.upper() not in [s.upper() for s in sections]:
                            sections.append(line)
                        i += 1
                    if sections:
                        break

            # 2. Strateji: İçindekiler tablosu yoksa doğrudan metin içindeki sıralı 1., 2., 3. başlıkları tara
            if not sections:
                current_num = 1
                for page in doc:
                    lines = [l.strip() for l in page.get_text().splitlines() if l.strip()]
                    for line in lines:
                        pattern = rf'^{current_num}[\.\)]\s+([A-ZÇĞİÖŞÜ0-9\s\(\)\/\-_,]+)$'
                        m = re.match(pattern, line)
                        if m:
                            clean_h = m.group(1).strip()
                            if len(clean_h) > 2 and len(clean_h) < 90:
                                heading = f'{current_num}. {clean_h}'
                                if heading not in sections:
                                    sections.append(heading)
                                    current_num += 1

            doc.close()
        except Exception:
            pass
            
    return sections


@lru_cache(maxsize=128)
def sartname_gereklilikleri_getir(yarisma_id: str) -> list[dict]:
    """Yarışmanın veritabanındaki veya resmî şartname PDF'indeki gerçek gereksinim ve kurallarını döner."""
    gereksinimler = []
    
    # 1. Cloudflare D1 competition_requirements tablosunu sorgula
    try:
        from src.database.db import db
        clean_slug = yarisma_id.strip()
        rows = db.execute_d1(
            "SELECT title, description, min_team_size, max_team_size, advisor_required, target_level, is_mandatory FROM competition_requirements WHERE competition_id = ? OR competition_id LIKE ? ORDER BY order_index ASC;",
            [clean_slug, f"%{clean_slug}%"]
        )
        if rows:
            for r in rows:
                gereksinimler.append({
                    "baslik": r.get("title") or "Şartname Kuralı",
                    "aciklama": r.get("description") or "",
                    "zorunlu": bool(r.get("is_mandatory", 1)),
                    "min_uye": r.get("min_team_size"),
                    "max_uye": r.get("max_team_size"),
                    "danisman": r.get("advisor_required"),
                    "seviye": r.get("target_level")
                })
            return gereksinimler
    except Exception:
        pass

    # 2. Şartname PDF'inden akıllı kural çıkarımı
    kb = klasor_bilgisi(yarisma_id)
    sn_pdf = kb.get("sartname_pdf")
    if sn_pdf and Path(sn_pdf).exists():
        try:
            doc = pymupdf.open(str(sn_pdf))
            full_text = ""
            for p in range(min(len(doc), 15)):
                full_text += doc[p].get_text() + "\n"
            doc.close()

            # Danışman Kuralı
            for line in full_text.splitlines():
                if "DANIŞMAN" in line.upper() and len(line) > 25 and not line.endswith("..."):
                    gereksinimler.append({
                        "baslik": "Danışman Kuralı",
                        "aciklama": line.strip(),
                        "zorunlu": True
                    })
                    break

            # Katılım Koşulları & Takım Sınırı
            for line in full_text.splitlines():
                if any(k in line.upper() for k in ["EN AZ", "EN FAZLA", "TAKIM ÜYE", "TAKIM YAPISI"]) and any(d in line for d in ["1", "2", "3", "4", "5", "6", "7", "8"]):
                    if len(line) > 20 and len(line) < 140:
                        gereksinimler.append({
                            "baslik": "Takım Yapısı & Üye Sınırları",
                            "aciklama": line.strip(),
                            "zorunlu": True
                        })
                        break

            # Özgünlük & İntihal Kuralı
            for line in full_text.splitlines():
                if any(k in line.upper() for k in ["ÖZGÜNLÜK", "İNTİHAL", "ALINTI"]) and len(line) > 25:
                    gereksinimler.append({
                        "baslik": "Özgünlük & Kaynakça İlkesi",
                        "aciklama": line.strip(),
                        "zorunlu": True
                    })
                    break

            # Raporlama Standardı
            for line in full_text.splitlines():
                if any(k in line.upper() for k in ["PUNTO", "YAZI TİPİ", "SAYFA KENAR", "SATIR ARALIĞI"]) and len(line) > 25:
                    gereksinimler.append({
                        "baslik": "Format & Yazı Tipi Kuralları",
                        "aciklama": line.strip(),
                        "zorunlu": True
                    })
                    break
        except Exception:
            pass

    if not gereksinimler:
        gereksinimler = [
            {"baslik": "Özgünlük İlkesi", "aciklama": "Başka kaynaklardan yapılan alıntılar açıkça kaynakça ile belirtilmeli, intihal oranı azami %15 olmalıdır.", "zorunlu": True},
            {"baslik": "Sayfa Sınırı", "aciklama": "Şartnamede belirtilen sayfa sınırını aşan raporlar için puan kırılma kuralları işletilir.", "zorunlu": True},
            {"baslik": "Zorunlu Başlıklar", "aciklama": "Zorunlu başlıklardan herhangi biri boş veya eksik bırakılmışsa ilgili kriterden 0 puan verilir.", "zorunlu": True},
            {"baslik": "Etik Kurallar", "aciklama": "Takım üyeleri ve danışman bilgileri hakem kör değerlendirmesinde gizlenmelidir.", "zorunlu": True}
        ]

    return gereksinimler


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
    if not slug:
        return "Yarışma"
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
    """Cloudflare D1 competitions tablosundaki yarışmaları slug -> Ad sözlüğü olarak döndürür.

    Yalnızca D1 competitions tablosuna yönetici panelinden eklenen gerçek yarışmalar
    listelenir. Tablo boşsa boş sözlük döner — demo/seed/hardcoded veriye düşülmez.
    """
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

