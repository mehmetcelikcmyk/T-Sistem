import os
import json
import sys
from pathlib import Path

# src dizinini path'e ekle
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.ingestion.rulebook_parser import process_competition_folder

DOCS_DIR = os.path.join(project_root, "docs", "yarismalar")
OUTPUT_DIR = os.path.join(project_root, "data", "dynamic_rubrics")

def main():
    if not os.path.exists(DOCS_DIR):
        print(f"[HATA] {DOCS_DIR} bulunamadı.")
        return

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    competitions = [d for d in os.listdir(DOCS_DIR) if os.path.isdir(os.path.join(DOCS_DIR, d))]
    
    print(f"Toplam {len(competitions)} yarisma klasoru bulundu. Dinamik RAG islemi baslatiliyor...")
    
    for comp in competitions:
        comp_path = os.path.join(DOCS_DIR, comp)
        sartname_path = os.path.join(comp_path, "sartname")
        
        # Sadece sartname klasörü olanları işle
        if not os.path.exists(sartname_path):
            continue
            
        print(f"-> Isleniyor: {comp}...")
        
        # RAG Çıkarımı Yap
        rubrics_list = process_competition_folder(comp_path)
        
        if rubrics_list:
            for rubric_data in rubrics_list:
                stage = rubric_data.get("stage", "GENEL")
                # Çıktıyı kaydet
                output_file = os.path.join(OUTPUT_DIR, f"{comp}_{stage}.json")
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(rubric_data, f, ensure_ascii=False, indent=4)
                print(f"  [BASARILI] Dinamik rubrik olusturuldu -> {output_file}")
        else:
            print(f"  [ATLANDI] {comp} (PDF bulunamadı veya okunamadı)")

if __name__ == "__main__":
    main()
