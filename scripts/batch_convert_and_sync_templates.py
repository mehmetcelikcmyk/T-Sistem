import os
import sys
import json
import urllib.parse
from pathlib import Path

BASE_DIR = Path(r"c:\Users\mehme\OneDrive\Desktop\T-Sistem")
sys.path.insert(0, str(BASE_DIR))

from src.services.doc_converter import docx_to_pdf
from src.services.r2_service import r2_service
from src.database.db import db

SOURCE_DIR = Path(r"C:\Users\mehme\OneDrive\Desktop\teknofest_yarismalar")

print("="*80)
print("  TÜM WORD ŞABLONLARINI ORİJİNAL PDF'E DÖNÜŞTÜRME VE R2/D1 SENKRONİZASYONU")
print("="*80)

# Tüm .docx dosyalarını tara
docx_files = list(SOURCE_DIR.glob("**/*.docx"))
total_files = len(docx_files)
print(f"Toplam Dönüştürülecek ve Yüklenecek Word Şablonu Sayısı: {total_files}\n")

temp_pdf_dir = BASE_DIR / "data" / "converted_pdfs"
temp_pdf_dir.mkdir(parents=True, exist_ok=True)

success_count = 0
fail_count = 0

for idx, docx_path in enumerate(docx_files, 1):
    comp_dir = docx_path.parent.parent.parent # yarismalar / {yarisma_slug} / asamalar / {asama} / sablon.docx
    comp_slug = docx_path.parents[2].name if len(docx_path.parents) >= 3 else "genel"
    stage_code = docx_path.parent.name.upper() if docx_path.parent.name != "sablon" else docx_path.parent.parent.name.upper()
    
    clean_stem = r2_service.slugify(docx_path.stem)
    temp_pdf_path = temp_pdf_dir / f"{comp_slug}_{stage_code}_{clean_stem}.pdf"
    
    print(f"[{idx:02d}/{total_files}] Dönüştürülüyor: {docx_path.name[:50]}...")
    
    try:
        # 1. Orijinal Word motoru ile PDF'e dönüştür
        docx_to_pdf(docx_path, temp_pdf_path)
        
        # 2. Cloudflare R2'ye hem DOCX hem PDF yükle
        docx_r2_key = f"sablonlar/{comp_slug}/{stage_code.lower()}/{clean_stem}.docx"
        pdf_r2_key = f"sablonlar/{comp_slug}/{stage_code.lower()}/{clean_stem}.pdf"
        
        r2_service.upload_file(docx_path.read_bytes(), docx_r2_key, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
        r2_service.upload_file(temp_pdf_path.read_bytes(), pdf_r2_key, "application/pdf")
        
        # 3. D1 veritabanındaki competition_stages tablosunu güncelle
        sql = """
        UPDATE competition_stages 
        SET sablon_docx_r2_key = ?, sablon_pdf_r2_key = ? 
        WHERE competition_id = ? AND stage_code LIKE ?;
        """
        db.execute_d1(sql, [docx_r2_key, pdf_r2_key, comp_slug, f"%{stage_code}%"])
        
        success_count += 1
        print(f"   [OK] R2 Yüklendi -> DOCX & PDF ({round(temp_pdf_path.stat().st_size/1024, 1)} KB) | D1 Güncellendi.")
        
    except Exception as e:
        fail_count += 1
        print(f"   [HATA] Dönüştürme/Yükleme başarısız: {e}")

print("\n" + "="*80)
print(f"İŞLEM TAMAMLANDI: {success_count} Başarılı, {fail_count} Başarısız")
print("="*80)
