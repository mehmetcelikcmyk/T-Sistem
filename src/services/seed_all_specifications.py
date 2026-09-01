"""
Tüm TEKNOFEST Yarışma Şartnamelerini ve Şablonlarını Tarayıp
Dinamik Kriterleri ve Rubrikleri Veritabanına ve Cloudflare D1'e Kaydeden Servis.
"""
import os
import sys
import json
import sqlite3
import datetime
from pathlib import Path

# Proje Kök Dizini
ROOT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "src" / "ui"))

import sartname_rehber
from src.database.db import db, DB_FILE

def seed_all_competitions_and_rubrics():
    import sys, io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

    docs_path = ROOT_DIR / "docs" / "yarismalar"
    if not docs_path.exists():
        print(f"[HATA] {docs_path} dizini bulunamadi.")
        return

    cats = sorted([d for d in docs_path.iterdir() if d.is_dir()])
    print("============================================================")
    print(f"  Toplam {len(cats)} Yarisma Sartnamesi ve Sablonu Taraniyor...")
    print("============================================================")


    # SQLite bağlantısını aç ve WAL modunu garantile
    conn = sqlite3.connect(DB_FILE, timeout=30.0)
    cursor = conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL;")
    cursor.execute("PRAGMA busy_timeout=30000;")
    conn.close()

    success_cat = 0
    success_tmpl = 0
    success_rubric = 0

    for idx, c_dir in enumerate(cats, 1):
        slug = c_dir.name
        tr_name = sartname_rehber.turkce_kategori_adi_formatla(slug)
        print(f"[{idx}/{len(cats)}] 📖 İnceleniyor: {tr_name} ({slug})...")

        try:
            # 1. KATEGORİ ŞARTNAME ZORUNLULUKLARI
            kz = sartname_rehber.sartnameden_kategori_zorunluluklarini_cikar(slug)
            db.save_category_requirement({
                "category_slug": slug,
                "category_name": tr_name,
                "target_level": kz.get("hedef_egitim_seviyesi", "Genel"),
                "min_team_size": kz.get("takim_uye_sayisi", {}).get("min", 2),
                "max_team_size": kz.get("takim_uye_sayisi", {}).get("max", 6),
                "advisor_required": kz.get("danisman_sarti", "İsteğe Bağlı"),
                "required_language": kz.get("dil_gereksinimi", "tr"),
                "technical_requirements": kz.get("temel_teknik_isterler", []),
                "eligibility_rules": kz.get("etik_ve_ozgunluk_kurallari", []),
                "sartname_file": kz.get("sartname_dosyasi", "")
            })
            success_cat += 1

            # 2. RAPOR ŞABLONLARI VE AŞAMAYA ÖZEL RUBRİK KRİTERLERİ
            kb = sartname_rehber.klasor_bilgisi(slug)
            asama_listesi = kb.get("asama_listesi", [])
            if not asama_listesi:
                asama_listesi = ["OTR", "KTR", "FTR"]

            for stage in asama_listesi:
                rz = sartname_rehber.sablondan_rapor_zorunluluklarini_cikar(slug, stage)
                db.save_report_template_requirement({
                    "category_slug": slug,
                    "stage": stage,
                    "max_pages": rz.get("maksimum_sayfa_siniri", 20),
                    "font_and_margins": rz.get("yazi_tipi_ve_marjin", "Times New Roman / Arial 11pt"),
                    "page_penalty_rule": rz.get("sayfa_asimi_kurali", "Sayfa sınırını aşan her sayfa için 2 puan düşülür."),
                    "required_sections": rz.get("zorunlu_basliklar", []),
                    "rubric_criteria": rz.get("rubrik_kriterleri", []),
                    "template_file": rz.get("sablon_dosyasi", "")
                })
                success_tmpl += 1

                # 3. RUBRİK TABLOSUNA VE CLOUDFLARE D1'E SENKRONİZASYON
                rub_kriterler = rz.get("rubrik_kriterleri", [])
                if rub_kriterler:
                    db.save_rubric({
                        "category_id": f"rub_{slug}_{stage.lower()}",
                        "category_name": slug,
                        "stage": stage,
                        "description": f"{tr_name} {stage} Değerlendirme Rubriği ve Şartname Kriterleri",
                        "criteria": rub_kriterler,
                        "required_sections": rz.get("zorunlu_basliklar", []),
                        "max_pages": rz.get("maksimum_sayfa_siniri", 20)
                    })
                    success_rubric += 1

        except Exception as e:
            print(f"  [!] Hata ({slug}): {e}")

    print(f"\n============================================================")
    print(f"  ✅ TAMAMLANDI!")
    print(f"  📦 Kaydedilen Kategori Şartnameleri: {success_cat}")
    print(f"  📑 Kaydedilen Aşama Şablonları:    {success_tmpl}")
    print(f"  ⚖️  Kaydedilen Dinamik Rubrikler:    {success_rubric}")
    print(f"  ☁️  Cloudflare D1 & SQLite Senkronizasyonu Başarılı!")
    print(f"============================================================\n")

if __name__ == "__main__":
    seed_all_competitions_and_rubrics()
