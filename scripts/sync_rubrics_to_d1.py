import sys
import json
import uuid
from pathlib import Path

BASE_DIR = Path(r"c:\Users\mehme\OneDrive\Desktop\T-Sistem")
sys.path.insert(0, str(BASE_DIR))

from src.database.db import db

print("="*70)
print("  TÜM YARIŞMALARIN RUBRİK PUANLAMA TABLOLARINI CLOUDFLARE D1'E SENKRONİZE ET")
print("="*70)

# 1. D1 Tablosunu Güvenceye Al
create_sql = """
CREATE TABLE IF NOT EXISTS competition_rubrics (
    rubric_id TEXT PRIMARY KEY,
    competition_id TEXT NOT NULL,
    stage_code TEXT NOT NULL,
    level TEXT DEFAULT 'Genel',
    criteria_json TEXT NOT NULL,
    total_score REAL DEFAULT 100.0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(competition_id, stage_code, level)
);
"""
try:
    db.execute_d1(create_sql)
    print("[OK] Cloudflare D1 'competition_rubrics' tablosu doğrulandı.")
except Exception as e:
    print(f"[HATA] Tablo oluşturulamadı: {e}")

# 2. data/ai_rapor_analizi altındaki tüm yarışma JSON'larını tara
ai_dir = BASE_DIR / "data" / "ai_rapor_analizi"
json_files = list(ai_dir.glob("*.json"))
print(f"Toplam Yüklenecek Yarışma Dosyası: {len(json_files)}\n")

total_inserted = 0

for jf in json_files:
    try:
        with open(jf, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        slug = data.get("slug") or jf.stem
        stages_data = data.get("stages", {})
        
        # stages bir dict (seviye bazlı) veya list olabilir
        stages_list = []
        if isinstance(stages_data, dict):
            for lvl_name, s_list in stages_data.items():
                if isinstance(s_list, list):
                    for stg in s_list:
                        if isinstance(stg, dict):
                            stg["_level"] = lvl_name
                            stages_list.append(stg)
        elif isinstance(stages_data, list):
            stages_list = stages_data
            
        for s in stages_list:
            if not isinstance(s, dict):
                continue
            stage_code = (s.get("stage") or "GENEL").upper().replace("Ö", "O").replace("Ü", "U").replace("İ", "I")
            level = s.get("_level") or s.get("level") or "Genel"
            rub = s.get("rubric")
            
            if rub and isinstance(rub, dict) and "criteria" in rub:
                criteria = rub.get("criteria", [])
                total_score = float(rub.get("total_score", 100.0))
                rubric_id = f"rub_{slug}_{stage_code}_{level}".replace(" ", "_")[:64]
                
                insert_sql = """
                INSERT OR REPLACE INTO competition_rubrics 
                (rubric_id, competition_id, stage_code, level, criteria_json, total_score)
                VALUES (?, ?, ?, ?, ?, ?);
                """
                db.execute_d1(insert_sql, [
                    rubric_id,
                    slug,
                    stage_code,
                    level,
                    json.dumps(criteria, ensure_ascii=False),
                    total_score
                ])
                total_inserted += 1
                print(f"  [OK] {slug} -> {stage_code} ({level}) : {len(criteria)} kriter D1'e yüklendi.")
    except Exception as e:
        print(f"  [HATA] {jf.name} işlenirken hata: {e}")

print("\n" + "="*70)
print(f"BAŞARIYLA TAMAMLANDI: Toplam {total_inserted} adet aşama rubriği Cloudflare D1'e senkronize edildi!")
print("="*70)
