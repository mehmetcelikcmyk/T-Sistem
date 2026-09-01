"""
TEKNOFEST 3D Yarışma Logoları ve Kategori Görselleri Modülü.
data/logos/ altındaki orijinal 3D web logolarını (.png, .webp, .svg, .jpg)
manifest ve isim eşleme ile Base64 Data URI olarak arayüze sunar.
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOGOS_DIR = ROOT / "data" / "logos"
MANIFEST_PATH = LOGOS_DIR / "logos_manifest.json"

_MANIFEST: dict | None = None


def _load_manifest() -> dict:
    global _MANIFEST
    if _MANIFEST is None:
        if MANIFEST_PATH.exists():
            try:
                _MANIFEST = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
            except Exception:
                _MANIFEST = {}
        else:
            _MANIFEST = {}
    return _MANIFEST


def tr_norm(s: str) -> str:
    s = str(s).lower()
    s = s.replace("ç", "c").replace("ğ", "g").replace("ı", "i").replace("ö", "o").replace("ş", "s").replace("ü", "u")
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def logo_bul(yarisma_adi: str) -> Path | None:
    """Yarışma adına göre data/logos/ altındaki en uygun resmi 3D TEKNOFEST logoyu bulur."""
    if not LOGOS_DIR.exists():
        return None

    manifest = _load_manifest()
    norm_query = tr_norm(yarisma_adi)

    # 1. Manifest slug ve başlık eşleşmesi
    for slug, meta in manifest.items():
        if slug in norm_query.replace(" ", "-") or tr_norm(meta.get("title", "")) in norm_query or norm_query in tr_norm(meta.get("title", "")):
            f_path = LOGOS_DIR / meta["file"]
            if f_path.exists():
                return f_path

    # 2. Kelime bazlı puanlama
    words = [w for w in norm_query.split() if len(w) >= 2 and w not in (
        "tekno", "teknofest", "2026", "yarismasi", "genel", "raporu", "ve", "ile", "tr", "otr", "ktr"
    )]

    ext_priority = {".png": 5, ".webp": 4, ".svg": 3, ".jpg": 2, ".jpeg": 1}
    best_file = None
    best_score = -1

    for f in LOGOS_DIR.glob("*.*"):
        if f.suffix.lower() not in ext_priority:
            continue
        f_norm = tr_norm(f.stem)
        match_count = sum(1 for w in words if w in f_norm)
        if match_count > 0:
            total_score = match_count * 10 + ext_priority.get(f.suffix.lower(), 0)
            if total_score > best_score:
                best_score = total_score
                best_file = f

    return best_file



def logo_data_uri(yarisma_adi: str) -> str | None:
    """Yarışma logosunu Base64 Data URI (data:image/png;base64,...) olarak döner."""
    f = logo_bul(yarisma_adi)
    if not f or not f.exists():
        return None
    try:
        data = f.read_bytes()
        b64 = base64.b64encode(data).decode("utf-8")
        ext = f.suffix.lstrip(".").lower()
        if ext == "svg":
            mime = "image/svg+xml"
        elif ext == "webp":
            mime = "image/webp"
        elif ext in ("jpg", "jpeg"):
            mime = "image/jpeg"
        else:
            mime = "image/png"
        return f"data:{mime};base64,{b64}"
    except Exception:
        return None
