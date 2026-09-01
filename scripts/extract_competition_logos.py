"""
TEKNOFEST Yarışma Logolarını ve Görsellerini Şartnamelerden Otomatik Çıkarma ve İndirme Scripti.
Her yarışmanın docs/yarismalar/<kategori>/sartname/*.pdf dosyasından orijinal yüksek çözünürlüklü
logo ve amblem görsellerini data/logos/ dizinine kaydeder.
"""
import os
import sys
import re
import glob
from pathlib import Path
import pymupdf

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
YARISMALAR_DIR = ROOT / "docs" / "yarismalar"
LOGOS_DIR = ROOT / "data" / "logos"

LOGOS_DIR.mkdir(parents=True, exist_ok=True)


def extract_logos():
    count = 0
    extracted_map = {}

    folders = sorted([f for f in YARISMALAR_DIR.iterdir() if f.is_dir()])
    print(f"🔍 Toplam {len(folders)} yarışma klasörü taranıyor...")

    for folder in folders:
        slug = folder.name
        # Şartname ve rapor şablonu PDF'lerini ara
        pdfs = list((folder / "sartname").glob("*.pdf")) + list((folder / "rapor_sablonlari").glob("*.pdf"))
        
        logo_saved = False
        
        for pdf_path in pdfs:
            if logo_saved:
                break
            try:
                doc = pymupdf.open(pdf_path)
                # Kapak sayfası veya ilk 3 sayfadaki görselleri tara
                for page_idx in range(min(3, len(doc))):
                    if logo_saved:
                        break
                    page = doc[page_idx]
                    images = page.get_images()
                    
                    for img_idx, img_info in enumerate(images):
                        xref = img_info[0]
                        base_img = doc.extract_image(xref)
                        w = base_img.get("width", 0)
                        h = base_img.get("height", 0)
                        ext = base_img.get("ext", "png")
                        img_bytes = base_img.get("image", b"")
                        
                        # Logo boyutu kriterleri: Genellikle genişlik/yükseklik 80px - 2500px arası ve logo oranı
                        if len(img_bytes) > 2000 and (w >= 100 or h >= 100) and w <= 3000 and h <= 3000:
                            # Çok büyük tam sayfa arka planları elemek için en/boy oranı veya boyut kontrolü
                            ratio = max(w, h) / max(min(w, h), 1)
                            if ratio < 6.0:  # aşırı ince şerit değilse
                                out_file = LOGOS_DIR / f"{slug}.{ext}"
                                out_file.write_bytes(img_bytes)
                                extracted_map[slug] = str(out_file.relative_to(ROOT))
                                count += 1
                                logo_saved = True
                                print(f"  ✅ [{slug}] logo çıkarıldı: {out_file.name} ({w}x{h}, {len(img_bytes)} B)")
                                break
            except Exception as e:
                # print(f"  ⚠️ {pdf_path.name} okunamadı: {e}")
                pass
                
        # Eğer PDF'ten çıkarılamadıysa ilk sayfa kapak amblemini render et
        if not logo_saved and pdfs:
            try:
                doc = pymupdf.open(pdfs[0])
                if len(doc) > 0:
                    page = doc[0]
                    # Kapak sayfasının üst 1/3'lük kısmını (logo alanı) render et
                    rect = page.rect
                    clip_rect = pymupdf.Rect(rect.x0, rect.y0, rect.x1, rect.y0 + rect.height * 0.40)
                    pix = page.get_pixmap(clip=clip_rect, dpi=150)
                    out_file = LOGOS_DIR / f"{slug}.png"
                    pix.save(str(out_file))
                    extracted_map[slug] = str(out_file.relative_to(ROOT))
                    count += 1
                    print(f"  📸 [{slug}] kapak logo alanı render edildi: {out_file.name}")
            except Exception as e:
                pass

    print(f"\n🎉 İşlem tamamlandı! Toplam {count} yarışma logosu data/logos/ dizinine kaydedildi.")

if __name__ == "__main__":
    extract_logos()
