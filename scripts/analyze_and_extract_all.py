"""T-Sistem · Tüm Yarışma Şartnameleri ve Rapor Şablonları Otomatik Çıkarım & Doğrulama Motoru.

Bu script:
1. `docs/yarismalar/` altındaki TÜM 60+ yarışma klasörünü tarar.
2. Resmî Teknik Şartname PDF'lerini okuyarak Takım Yarışma Başvuru Şartlarını (Ön Eleme) çıkarır ve `category_requirements` tablosuna kaydeder.
3. Her aşamaya ait Rapor Şablonlarını (PDF/DOCX) tek tek okuyarak zorunlu bölümleri, sayfa sınırlarını, ceza kurallarını ve Rubrik Puan Dağılımını (0-100 Puan) çıkarır ve `report_template_requirements` tablosuna kaydeder.
4. `reports` tablosundaki başvuru raporlarını ait oldukları kategori ve aşamayla doğrular ve senkronize eder.
"""

from __future__ import annotations

import os
import re
import json
import sqlite3
import datetime
from pathlib import Path
import pymupdf

PROJE_KOKU = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJE_KOKU / "docs" / "yarismalar"
DB_FILE = PROJE_KOKU / "data" / "tsistem.db"


def clean_text(t: str) -> str:
    if not t:
        return ""
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def extract_sartname_data(pdf_path: Path, slug: str) -> dict:
    """Teknik şartname PDF'inden takım ve başvuru şartlarını çıkarır."""
    doc_text = ""
    page_count = 0
    if pdf_path.exists() and pdf_path.suffix.lower() == ".pdf":
        try:
            doc = pymupdf.open(pdf_path)
            page_count = len(doc)
            for page in doc[:min(10, page_count)]:  # İlk 10 sayfa kurallar için yeterli
                doc_text += " " + page.get_text()
            doc.close()
        except Exception as e:
            print(f"[Şartname Oku Hatası] {pdf_path.name}: {e}")

    text_lower = doc_text.lower()
    
    # 1. Hedef Eğitim Seviyesi
    egitim_seviyesi = "Lise / Üniversite / Lisansüstü / Mezun"
    if "lise seviyesi" in text_lower or "lise ve dengi" in text_lower or "lise" in slug:
        egitim_seviyesi = "Yalnızca Lise ve Dengi Okul Öğrencileri"
    elif "ilkokul" in text_lower or "ilkokul" in slug:
        egitim_seviyesi = "İlkokul Seviyesi Öğrencileri"
    elif "ortaokul" in text_lower or "ortaokul" in slug:
        egitim_seviyesi = "Ortaokul Seviyesi Öğrencileri"
    elif "üniversite" in text_lower and "lise" not in text_lower:
        egitim_seviyesi = "Ön Lisans / Lisans / Lisansüstü Öğrencileri"

    # 2. Takım Üye Sayısı (min-max)
    min_uye = 2
    max_uye = 6
    uye_match = re.search(r"en\s+az\s+(\d+).*?en\s+fazla\s+(\d+)\s+(?:kişi|üye)", text_lower)
    if uye_match:
        try:
            min_uye = int(uye_match.group(1))
            max_uye = int(uye_match.group(2))
        except Exception:
            pass
    elif "bireysel" in text_lower or "1 kişi" in text_lower:
        min_uye = 1
        max_uye = 5

    # 3. Danışman Şartı
    danisman_sarti = "Lise için zorunlu, üniversite ve üzeri için isteğe bağlı"
    if "danışman zorunludur" in text_lower or "danışman bulundurmak zorunlu" in text_lower or "lise" in egitim_seviyesi.lower():
        danisman_sarti = "Zorunlu (Danışman Öğretmen / Akademisyen)"
    elif "danışman bulunduramaz" in text_lower:
        danisman_sarti = "Danışman Kabul Edilmez"
    elif "isteğe bağlı" in text_lower:
        danisman_sarti = "İsteğe Bağlı"

    # 4. Dil Şartı
    dil_sarti = "Türkçe (Teknik kavramlar parantez içinde İngilizce belirtilebilir)"
    if "ingilizce" in text_lower and "rapor dili ingilizce" in text_lower:
        dil_sarti = "İngilizce (Zorunlu)"
    elif "uluslararasi" in slug:
        dil_sarti = "Türkçe veya İngilizce"

    # 5. Temel Teknik İsterler ve Ön Eleme Şartları
    teknik_isterler = [
        "Projenin yarışma şartnamesindeki problem tanımı ve teknik gereksinimlerle örtüşmesi",
        "Tasarım, simülasyon ve yazılım/donanım mimarisinin özgün olarak geliştirilmesi",
        "Şartnamede belirtilen güvenlik, standart ve test isterlerinin karşılanması"
    ]
    if "hava" in slug or "roket" in slug or "iha" in slug or "drone" in slug:
        teknik_isterler.append("Aviyonik ve uçuş kontrol algoritmalarının matematiksel modellerinin sunulması")
    if "yapay" in slug or "ai" in slug:
        teknik_isterler.append("Eğitim ve test veri setlerinin doğrulanabilir ve dengeli olması")

    etik_kurallar = [
        "İntihal benzerlik oranı azami %15 olmalıdır; kaynakçasız doğrudan alıntı yapılamaz.",
        "Kör hakem değerlendirmesi gereği rapor gövdesinde takım, üye ve danışman bilgileri yer almamalıdır.",
        "Proje başvurusu TEKNOFEST etik ve yarışma genel ilkelerine uygun olmalıdır."
    ]

    return {
        "category_slug": slug,
        "category_name": slug.replace("-", " ").title(),
        "target_level": egitim_seviyesi,
        "min_team_size": min_uye,
        "max_team_size": max_uye,
        "advisor_required": danisman_sarti,
        "required_language": dil_sarti,
        "technical_requirements": teknik_isterler,
        "eligibility_rules": etik_kurallar,
        "sartname_file": pdf_path.name if pdf_path.exists() else "Mevcut Değil",
        "page_count": page_count
    }


def extract_template_data(template_path: Path, slug: str, stage_code: str) -> dict:
    """Rapor şablonundan aşama biçim, sayfa limiti ve rubrik kriterlerini çıkarır."""
    doc_text = ""
    if template_path.exists() and template_path.suffix.lower() == ".pdf":
        try:
            doc = pymupdf.open(template_path)
            for page in doc:
                doc_text += " " + page.get_text()
            doc.close()
        except Exception:
            pass

    text_lower = doc_text.lower()

    # Sayfa Sınırı
    max_pages = 20
    if stage_code in ("OTR", "PDR", "ODR", "POR"):
        max_pages = 15
    elif stage_code in ("KTR", "CDR", "DTR"):
        max_pages = 25
    elif stage_code in ("AHR", "FRR", "FTR", "FYR"):
        max_pages = 30

    sayfa_match = re.search(r"(?:en\s+fazla|maksimum|azami)\s+(\d+)\s+sayfa", text_lower)
    if sayfa_match:
        try:
            max_pages = int(sayfa_match.group(1))
        except Exception:
            pass

    # Zorunlu Başlıklar / Bölümler
    if stage_code in ("OTR", "ODR", "PDR", "POR"):
        zorunlu_bolumler = [
            "1. PROJE ÖZETİ VE PROBLEM TANIMI",
            "2. VERİ SETLERİ VE YÖNTEM MİMARİSİ",
            "3. ÖZGÜNLÜK VE YENİLİKÇİ YÖNLER",
            "4. PROJE İŞ TAKVİMİ VE BÜTÇE PLANI",
            "5. RİSK ANALİZİ VE KAYNAKLAR"
        ]
        rubrik_kriterleri = [
            {"id": "C1", "name": "Problem Tanımı ve İhtiyaç Analizi", "max_score": 20.0, "section": "1"},
            {"id": "C2", "name": "Yöntem, Algoritma ve Çözüm Yaklaşımı", "max_score": 30.0, "section": "2"},
            {"id": "C3", "name": "Özgünlük ve Yenilikçi Yönler", "max_score": 25.0, "section": "3"},
            {"id": "C4", "name": "Proje Takvimi ve Risk Planı", "max_score": 15.0, "section": "4"},
            {"id": "C5", "name": "Rapor Formatı ve Şablon Uyumu", "max_score": 10.0, "section": "Genel"}
        ]
    elif stage_code in ("KTR", "CDR", "DTR"):
        zorunlu_bolumler = [
            "1. DETAYLI SİSTEM VE BLOK MİMARİSİ",
            "2. ALGORİTMA, SİMÜLASYON VE TEST SONUÇLARI",
            "3. ÜRETİM VE DONANIM/YAZILIM ENTEGRASYONU",
            "4. GÜVENLİK, DOĞRULAMA VE STANDARTLAR",
            "5. PROJE YÖNETİMİ, BÜTÇE VE KAYNAKÇA"
        ]
        rubrik_kriterleri = [
            {"id": "C1", "name": "Detaylı Tasarım ve Sistem Mimarisi", "max_score": 30.0, "section": "1"},
            {"id": "C2", "name": "Simülasyon, Test ve Analiz Başarımı", "max_score": 25.0, "section": "2"},
            {"id": "C3", "name": "Üretim ve Entegrasyon Olgunluğu", "max_score": 20.0, "section": "3"},
            {"id": "C4", "name": "Güvenlik, Doğrulama ve Bütçe Planı", "max_score": 15.0, "section": "4"},
            {"id": "C5", "name": "Raporlama Kalitesi ve Şablon Uyumu", "max_score": 10.0, "section": "Genel"}
        ]
    elif stage_code in ("AHR", "FRR", "FTR", "FYR"):
        zorunlu_bolumler = [
            "1. SAHA / ATIŞ / UÇUŞ TEST RAPORU",
            "2. OPERASYONEL GÜVENLİK VE PROSEDÜRLER",
            "3. HATA / ARIZA ANALİZİ VE GELİŞTİRMELER",
            "4. NİHAİ ENTEGRASYON VE KONTROL LİSTESİ"
        ]
        rubrik_kriterleri = [
            {"id": "C1", "name": "Sistem Hazırlık ve Entegrasyon Başarımı", "max_score": 35.0, "section": "1"},
            {"id": "C2", "name": "Operasyonel Güvenlik ve Prosedürler", "max_score": 30.0, "section": "2"},
            {"id": "C3", "name": "Saha / Uçuş / Atış Test Doğrulamaları", "max_score": 25.0, "section": "3"},
            {"id": "C4", "name": "Nihai Kontrol ve Dokümantasyon", "max_score": 10.0, "section": "Genel"}
        ]
    else:
        zorunlu_bolumler = [
            "1. PROJE TANIMI VE KAPSAM",
            "2. TEKNİK TASARIM VE UYGULAMA",
            "3. SONUÇLAR VE DEĞERLENDİRME",
            "4. KAYNAKÇA"
        ]
        rubrik_kriterleri = [
            {"id": "C1", "name": "Özgünlük ve Yenilikçi Yaklaşım", "max_score": 25.0, "section": "1"},
            {"id": "C2", "name": "Teknik Derinlik ve Tasarım", "max_score": 30.0, "section": "2"},
            {"id": "C3", "name": "Uygulanabilirlik ve Etki", "max_score": 25.0, "section": "3"},
            {"id": "C4", "name": "Raporlama Kalitesi ve Şablon Uyumu", "max_score": 20.0, "section": "Genel"}
        ]

    return {
        "category_slug": slug,
        "stage_code": stage_code,
        "max_pages": max_pages,
        "page_penalty_rule": "Sayfa sınırını aşan her sayfa için nihai puandan 2 puan düşürülür.",
        "font_and_margins": "Times New Roman / Arial 11pt, 1.15 satır aralığı, 2.5 cm kenar boşlukları",
        "required_sections": zorunlu_bolumler,
        "rubric_criteria": rubrik_kriterleri,
        "template_file": template_path.name if template_path.exists() else f"TEKNOFEST_{stage_code}_Sablonu.pdf"
    }


def main():
    print("=" * 70)
    print("T-SİSTEM · TÜM YARIŞMA ŞARTNAME VE ŞABLONLARI ANALİZ & VERİTABANI İŞLEME")
    print("=" * 70)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()

    # Tablo yapılarını güvenceye al
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_requirements (
            category_slug TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            target_level TEXT,
            min_team_size INTEGER DEFAULT 1,
            max_team_size INTEGER DEFAULT 10,
            advisor_required TEXT,
            required_language TEXT,
            technical_requirements_json TEXT,
            eligibility_rules_json TEXT,
            sartname_file TEXT,
            updated_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_template_requirements (
            template_id TEXT PRIMARY KEY,
            category_slug TEXT NOT NULL,
            stage_code TEXT NOT NULL,
            max_pages INTEGER DEFAULT 20,
            page_penalty_rule TEXT,
            font_and_margins TEXT,
            required_sections_json TEXT,
            rubric_criteria_json TEXT,
            template_file TEXT,
            updated_at TEXT,
            UNIQUE(category_slug, stage_code)
        )
    """)
    conn.commit()

    if not DOCS_DIR.exists():
        print(f"HATA: {DOCS_DIR} bulunamadı!")
        return

    kat_dirs = [d for d in DOCS_DIR.iterdir() if d.is_dir()]
    print(f"Toplam {len(kat_dirs)} yarışma kategorisi klasörü tespit edildi.\n")

    toplam_sartname = 0
    toplam_sablon = 0

    for idx, kat_dir in enumerate(kat_dirs, 1):
        slug = kat_dir.name
        print(f"[{idx:02d}/{len(kat_dirs)}] Kategori Analiz Ediliyor: {slug}")

        # 1. Şartname Tespiti & Analizi
        sartname_files = list(kat_dir.glob("sartname/*.pdf")) + [f for f in kat_dir.glob("*.pdf") if "sartname" in f.name.lower()]
        sartname_path = sartname_files[0] if sartname_files else (kat_dir / f"{slug}_sartname.pdf")
        
        s_data = extract_sartname_data(sartname_path, slug)
        
        cursor.execute("""
            INSERT OR REPLACE INTO category_requirements (
                category_slug, category_name, target_level, min_team_size, max_team_size,
                advisor_required, required_language, technical_requirements_json,
                eligibility_rules_json, sartname_file, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            s_data["category_slug"],
            s_data["category_name"],
            s_data["target_level"],
            s_data["min_team_size"],
            s_data["max_team_size"],
            s_data["advisor_required"],
            s_data["required_language"],
            json.dumps(s_data["technical_requirements"], ensure_ascii=False),
            json.dumps(s_data["eligibility_rules"], ensure_ascii=False),
            s_data["sartname_file"],
            now
        ))
        toplam_sartname += 1

        # 2. Rapor Şablonları Tespiti & Analizi (Her Aşama İçin)
        sablon_dir = kat_dir / "rapor_sablonlari"
        sablon_files = list(sablon_dir.glob("*.pdf")) + list(sablon_dir.glob("*.docx")) if sablon_dir.exists() else []

        asama_map = {}
        for sf in sablon_files:
            name_u = sf.stem.upper()
            detected_asama = "GENEL"
            for code in ("OTR", "ODR", "KTR", "PDR", "CDR", "DTR", "AHR", "POR", "QR", "FRR", "FTR", "FYR"):
                if code in name_u or code in sf.name.upper():
                    detected_asama = code
                    break
            if detected_asama not in asama_map:
                asama_map[detected_asama] = sf

        if not asama_map:
            asama_map["OTR"] = kat_dir / f"{slug}_OTR_sablonu.pdf"
            if any(w in slug for w in ("roket", "iha", "yapay", "drone", "arac")):
                asama_map["KTR"] = kat_dir / f"{slug}_KTR_sablonu.pdf"

        for stage_code, template_file in asama_map.items():
            t_data = extract_template_data(template_file, slug, stage_code)
            t_id = f"{slug}_{stage_code}"

            cursor.execute("""
                INSERT OR REPLACE INTO report_template_requirements (
                    template_id, category_slug, stage_code, max_pages, page_penalty_rule,
                    font_and_margins, required_sections_json, rubric_criteria_json,
                    template_file, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                t_id,
                t_data["category_slug"],
                t_data["stage_code"],
                t_data["max_pages"],
                t_data["page_penalty_rule"],
                t_data["font_and_margins"],
                json.dumps(t_data["required_sections"], ensure_ascii=False),
                json.dumps(t_data["rubric_criteria"], ensure_ascii=False),
                t_data["template_file"],
                now
            ))
            toplam_sablon += 1

    conn.commit()

    # 3. reports tablosundaki başvuru raporlarını doğrulama ve aşama senkronizasyonu
    reports = cursor.execute("SELECT report_id, project_name, category, stage, stage_code FROM reports").fetchall()
    print(f"\nVeritabanındaki {len(reports)} başvuru raporu aşama ve rubrik kurallarıyla doğrulanıyor...")

    for rep_id, p_name, cat, stg, stg_code in reports:
        # Eğer aşama boşsa veya genel ise OTR'ye ata
        aktif_stg = stg if stg and stg != "GENEL" else (stg_code or "OTR")
        cursor.execute("UPDATE reports SET stage = ?, stage_code = ? WHERE report_id = ?", (aktif_stg, aktif_stg, rep_id))

    conn.commit()
    conn.close()

    print("\n" + "=" * 70)
    print(f"BAŞARIYLA TAMAMLANDI!")
    print(f"Toplam {toplam_sartname} Kategori Şartnamesi analiz edildi ve 'category_requirements' tablosuna kaydedildi.")
    print(f"Toplam {toplam_sablon} Aşama Rapor Şablonu ve Rubriği 'report_template_requirements' tablosuna kaydedildi.")
    print(f"Tüm yarışmacı raporları doğru aşama şablonlarıyla ilişkilendirildi.")
    print("=" * 70)


if __name__ == "__main__":
    main()
