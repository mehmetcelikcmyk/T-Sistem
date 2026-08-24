import sys
from pathlib import Path
import urllib.parse
import sqlite3

BASE_DIR = Path(r"c:\Users\mehme\OneDrive\Desktop\T-Sistem")
sys.path.insert(0, str(BASE_DIR / "src" / "ui"))
import sartname_rehber

YARISMALAR_DIR = BASE_DIR / "data" / "yarismalar"

# DB'den temiz isimleri al
db_path = BASE_DIR / "data" / "tsistem.db"
db_names = {}
if db_path.exists():
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute("SELECT slug, name FROM competitions;")
    for row in c.fetchall():
        db_names[row[0]] = row[1]
    conn.close()

renamed_count = 0
for yarisma_dir in sorted(YARISMALAR_DIR.iterdir()):
    if not yarisma_dir.is_dir():
        continue
        
    sartname_dir = yarisma_dir / "sartname"
    if not sartname_dir.exists():
        continue
        
    slug = yarisma_dir.name
    # İsim tespiti
    clean_title = sartname_rehber.turkce_kategori_adi_formatla(slug)
    if not clean_title or clean_title == slug:
        clean_title = db_names.get(slug, slug.replace("-", " ").title())
    
    # "Yarışması" kelimesini kontrol et
    clean_title = clean_title.strip()
    if not clean_title.endswith("Yarışması") and not clean_title.endswith("Yarışları") and not clean_title.endswith("Ödülleri") and not clean_title.endswith("Şampiyonası"):
        clean_title += " Yarışması"
        
    yeni_dosya_adi = f"{clean_title} Şartnamesi.pdf"
    
    # sartname altındaki tüm pdf dosyalarını bul ve yeniden adlandır
    pdf_files = list(sartname_dir.glob("*.pdf"))
    if len(pdf_files) == 1:
        old_file = pdf_files[0]
        new_file = sartname_dir / yeni_dosya_adi
        if old_file != new_file:
            try:
                old_file.rename(new_file)
                renamed_count += 1
                print(f"[YENİDEN ADLANDIRILDI]: {old_file.name} -> {new_file.name}")
            except Exception as e:
                print(f"[HATA] {old_file.name}: {e}")
    elif len(pdf_files) > 1:
        for idx, old_file in enumerate(pdf_files, 1):
            bolum_adi = f"{clean_title} Şartnamesi (Bölüm {idx}).pdf"
            new_file = sartname_dir / bolum_adi
            if old_file != new_file:
                try:
                    old_file.rename(new_file)
                    renamed_count += 1
                    print(f"[YENİDEN ADLANDIRILDI]: {old_file.name} -> {new_file.name}")
                except Exception as e:
                    print(f"[HATA] {old_file.name}: {e}")

print(f"\nToplam {renamed_count} adet şartname PDF dosyası Türkçe karakterli resmî isimlerine göre yeniden adlandırıldı!")
