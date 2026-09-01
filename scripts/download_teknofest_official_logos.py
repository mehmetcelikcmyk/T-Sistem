"""
TEKNOFEST Resmi Web Sitesinden (teknofest.org/tr/yarismalar/) 
Tüm 3D Yarışma Logolarını Otomatik İndiren Script.
"""
import os
import sys
import re
import ssl
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
LOGOS_DIR.mkdir(parents=True, exist_ok=True)

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def tr_slug(s: str) -> str:
    s = s.lower()
    s = s.replace("ç", "c").replace("ğ", "g").replace("ı", "i").replace("ö", "o").replace("ş", "s").replace("ü", "u")
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s

def download_all_logos():
    url = "https://www.teknofest.org/tr/yarismalar/"
    print(f"🌐 TEKNOFEST yarışmalar sayfası taranıyor: {url}")
    
    req = urllib.request.Request(url, headers=HEADERS)
    html = urllib.request.urlopen(req, context=ctx).read().decode("utf-8")
    soup = BeautifulSoup(html, "html.parser")
    
    downloaded = 0

    # 1. Yarışma kartlarını bul
    # Genellikle <a href="/tr/yarismalar/..."> veya kart içindeki <img> etiketleri
    links = soup.find_all("a", href=True)
    comp_links = {}
    for a in links:
        href = a["href"]
        if "/tr/yarismalar/" in href and href != "/tr/yarismalar/":
            slug = href.strip("/").split("/")[-1]
            img = a.find("img")
            text = a.get_text().strip()
            if img and img.get("src"):
                comp_links[slug] = {
                    "src": img["src"],
                    "title": text or img.get("alt", slug)
                }

    # Ayrıca sayfadaki tüm yarışma görsellerini tara
    all_imgs = soup.find_all("img")
    for img in all_imgs:
        src = img.get("src", "")
        alt = img.get("alt", "").strip()
        parent_a = img.find_parent("a", href=True)
        if parent_a and "/tr/yarismalar/" in parent_a["href"]:
            slug = parent_a["href"].strip("/").split("/")[-1]
            if slug not in comp_links and src:
                comp_links[slug] = {"src": src, "title": alt or slug}

    print(f"📦 Toplam {len(comp_links)} yarışma kartı ve logosu tespit edildi.")

    for slug, info in comp_links.items():
        src = info["src"]
        if not src.startswith("http"):
            src = "https://www.teknofest.org" + src
            
        ext = src.split(".")[-1].split("?")[0].lower()
        if ext not in ("png", "jpg", "jpeg", "webp", "svg"):
            ext = "png"
            
        target_path = LOGOS_DIR / f"{slug}.{ext}"
        
        try:
            img_req = urllib.request.Request(src, headers=HEADERS)
            img_data = urllib.request.urlopen(img_req, context=ctx).read()
            if len(img_data) > 500:
                target_path.write_bytes(img_data)
                downloaded += 1
                print(f"  ✅ [{slug}] İndirildi: {target_path.name} ({len(img_data)} B)")
        except Exception as e:
            print(f"  ❌ [{slug}] İndirme hatası ({src}): {e}")

    # Eksik olan yarışma sayfalarını tek tek ziyaret edip içerideki ana logoyu çek
    for a in links:
        href = a["href"]
        if "/tr/yarismalar/" in href and href != "/tr/yarismalar/":
            slug = href.strip("/").split("/")[-1]
            target_matches = list(LOGOS_DIR.glob(f"{slug}.*"))
            if not target_matches:
                full_comp_url = "https://www.teknofest.org" + href if not href.startswith("http") else href
                try:
                    c_req = urllib.request.Request(full_comp_url, headers=HEADERS)
                    c_html = urllib.request.urlopen(c_req, context=ctx).read().decode("utf-8")
                    c_soup = BeautifulSoup(c_html, "html.parser")
                    # Sayfa içindeki ana görseli bul
                    for c_img in c_soup.find_all("img"):
                        c_src = c_img.get("src", "")
                        if "userFormUpload" in c_src or "competitions" in c_src:
                            if not c_src.startswith("http"):
                                c_src = "https://www.teknofest.org" + c_src
                            c_ext = c_src.split(".")[-1].split("?")[0].lower()
                            if c_ext in ("png", "jpg", "jpeg", "webp", "svg"):
                                t_path = LOGOS_DIR / f"{slug}.{c_ext}"
                                c_img_data = urllib.request.urlopen(urllib.request.Request(c_src, headers=HEADERS), context=ctx).read()
                                if len(c_img_data) > 1000:
                                    t_path.write_bytes(c_img_data)
                                    downloaded += 1
                                    print(f"  🎯 [Detay Sayfası: {slug}] İndirildi: {t_path.name}")
                                    break
                except Exception:
                    pass

    print(f"\n🎉 Tamamlandı! Toplam {downloaded} resmi TEKNOFEST 3D yarışma logosu data/logos/ dizinine başarıyla indirildi.")

if __name__ == "__main__":
    download_all_logos()
