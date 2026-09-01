"""
TEKNOFEST 3D Logolarını Sıfırdan Temiz ve %100 Doğru İndiren Script.
Eski tüm PDF görsellerini siler ve teknofest.org yarışma kartlarındaki
özgün 3D amblem ve logoları indirerek manifest dosyası üretir.
"""
import os
import sys
import shutil
import ssl
import json
import re
import urllib.request
from pathlib import Path
from bs4 import BeautifulSoup

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parents[1]
LOGOS_DIR = ROOT / "data" / "logos"

# 1. Eski logo klasörünü tamamen temizle
if LOGOS_DIR.exists():
    for item in LOGOS_DIR.iterdir():
        if item.is_file():
            item.unlink()
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def tr_clean(text: str) -> str:
    # Başvuru Tamamlandı vb. fazlalıkları temizle
    text = re.sub(r"Başvuru\s+Tamamlandı", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Yeni", "", text, flags=re.IGNORECASE)
    text = text.replace("\n", " ").strip()
    return re.sub(r"\s+", " ", text).strip()

def download_clean():
    url = "https://www.teknofest.org/tr/yarismalar/"
    print(f"🌐 TEKNOFEST yarışmalar sayfası taranıyor: {url}")
    
    req = urllib.request.Request(url, headers=HEADERS)
    html = urllib.request.urlopen(req, context=ctx).read().decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    
    manifest = {}
    downloaded = 0

    # Kartları tara
    cards_seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if "/tr/yarismalar/" in href and href.strip("/") != "tr/yarismalar":
            slug = href.strip("/").split("/")[-1]
            if slug in cards_seen:
                continue
            
            img = a.find("img")
            if not img or not img.get("src"):
                continue
                
            src = img["src"]
            if any(bad in src for bad in ("continuing", "yeni-yarisma", "apply", "social", "icon")):
                continue
                
            raw_title = a.get_text()
            title = tr_clean(raw_title) or slug.replace("-", " ").title()
            
            if not src.startswith("http"):
                src = "https://www.teknofest.org" + src
                
            ext = src.split(".")[-1].split("?")[0].lower()
            if ext not in ("png", "jpg", "jpeg", "webp", "svg"):
                ext = "png"
                
            filename = f"{slug}.{ext}"
            target_path = LOGOS_DIR / filename
            
            try:
                img_data = urllib.request.urlopen(urllib.request.Request(src, headers=HEADERS), context=ctx).read()
                if len(img_data) > 1000:
                    target_path.write_bytes(img_data)
                    cards_seen.add(slug)
                    manifest[slug] = {
                        "file": filename,
                        "title": title,
                        "size": len(img_data)
                    }
                    downloaded += 1
                    print(f"  ✅ [{slug}] -> {filename} ({title})")
            except Exception as e:
                print(f"  ❌ [{slug}] İndirme hatası: {e}")

    # Manifest dosyasını kaydet
    manifest_path = LOGOS_DIR / "logos_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n🎉 Toplam {downloaded} özgün 3D TEKNOFEST logosu tertemiz indirildi ve manifest oluşturuldu.")

if __name__ == "__main__":
    download_clean()
