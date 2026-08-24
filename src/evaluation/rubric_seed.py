"""
Yarışma Şartname Tanımlarını data/rubrics/*.json -> Veritabanı Yükleyici (Seed)

KULLANIM:
  * Programatik:  from src.evaluation.rubric_seed import seed_rubrics_from_disk
                  seed_rubrics_from_disk()
  * Komut satırı: python -m src.evaluation.rubric_seed

Her JSON dosyası db.save_rubric() ile aynı şekle uymalıdır:
  {
    "category_name": "Roket",
    "stage": "KTR",
    "description": "...",
    "criteria": [{"id","name","max_score","description","guiding_questions"}],
    "required_sections": {"anahtar": "Görünen Ad", ...},
    "max_pages": 25
  }

Bozuk/eksik bir dosya tüm yüklemeyi ÇÖKERTMEZ; atlanır ve raporlanır.
"""
from __future__ import annotations

import os
import json
import glob
from typing import Dict, Any, List


_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUBRICS_DIR = os.getenv("TSISTEM_RUBRICS_DIR") or os.path.join(_PROJECT_ROOT, "data", "rubrics")


def load_rubric_files(directory: str = RUBRICS_DIR) -> List[Dict[str, Any]]:
    """Dizindeki tüm *.json şartname dosyalarını okur ve asgari doğrulama yapar."""
    tanimlar: List[Dict[str, Any]] = []
    if not os.path.isdir(directory):
        print(f"[SEED] Rubric dizini bulunamadı: {directory}")
        return tanimlar

    for yol in sorted(glob.glob(os.path.join(directory, "*.json"))):
        # "_" ile başlayan dosyalar rubric değildir (ör. _yarisma_katalogu.json); atla.
        if os.path.basename(yol).startswith("_"):
            continue
        try:
            with open(yol, "r", encoding="utf-8") as f:
                ham = json.load(f)
            if not ham.get("category_name") or not ham.get("criteria"):
                raise ValueError("category_name ve criteria zorunludur")
            tanimlar.append(ham)
        except Exception as e:
            print(f"[SEED HATASI] '{os.path.basename(yol)}' atlandı: {type(e).__name__}: {e}")
    return tanimlar


def seed_rubrics_from_disk(directory: str = RUBRICS_DIR, overwrite: bool = True) -> Dict[str, Any]:
    """
    Disk'teki şartname tanımlarını veritabanına yükler.

    Args:
        directory: JSON dosyalarının bulunduğu dizin
        overwrite: True ise mevcut (kategori, aşama) tanımının üzerine yazar.
                   False ise yalnızca eksik olanları ekler (mevcut düzenlemeler korunur).

    Returns:
        {"loaded": [...], "skipped": int, "total_files": int}
    """
    from src.database.db import db
    from src.evaluation.rubric import normalize_stage

    tanimlar = load_rubric_files(directory)
    yuklenen: List[str] = []
    atlanan = 0

    # Mevcut (kategori, aşama) ikilileri (overwrite=False için)
    mevcut = {
        (r.get("category_name", "").strip().lower(), r.get("stage", "GENEL"))
        for r in db.get_all_rubrics()
    }

    for tanim in tanimlar:
        kat = tanim.get("category_name", "").strip()
        asama = normalize_stage(tanim.get("stage"))
        if not overwrite and (kat.lower(), asama) in mevcut:
            atlanan += 1
            continue
        db.save_rubric(tanim)
        yuklenen.append(f"{kat}::{asama}")

    print(f"[SEED] {len(yuklenen)} şartname yüklendi, {atlanan} atlandı "
          f"({len(tanimlar)} geçerli dosya).")
    return {"loaded": yuklenen, "skipped": atlanan, "total_files": len(tanimlar)}


if __name__ == "__main__":
    print(json.dumps(seed_rubrics_from_disk(), ensure_ascii=False, indent=2))
