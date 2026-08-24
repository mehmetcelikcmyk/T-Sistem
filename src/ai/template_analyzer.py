"""
Aşama Rapor Şablonu AI Analiz & Rubrik Çıkarıcı Modülü.
Admin Word (.docx) veya PDF şablonu yüklediğinde zorunlu başlıkları,
bölüm isterlerini ve 0-100 puan dağılımını (Rubrik) otomatik çıkarır.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import pymupdf

class TemplateAnalyzer:
    def extract_text_from_file(self, file_path: str) -> str:
        """Word veya PDF dosyasından metin çıkarır."""
        p = Path(file_path)
        if not p.exists():
            return ""
        
        if p.suffix.lower() == ".pdf":
            try:
                doc = pymupdf.open(str(p))
                text = [page.get_text() for page in doc]
                doc.close()
                return "\n".join(text)
            except Exception:
                return ""
        elif p.suffix.lower() == ".docx":
            try:
                import docx
                doc = docx.Document(str(p))
                paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
                for table in doc.tables:
                    for row in table.rows:
                        paragraphs.append(" | ".join(cell.text.strip() for cell in row.cells if cell.text.strip()))
                return "\n".join(paragraphs)
            except Exception:
                return ""
        return ""

    def analyze_template(self, file_path: str, stage_code: str = "OTR") -> Dict[str, Any]:
        """
        Şablonu analiz ederek kriterleri ve puan dağılımını (0-100) çıkarır.
        """
        raw_text = self.extract_text_from_file(file_path)
        
        # Standart başlık ve puan çıkarımı
        rubric_items = []
        
        # Regex ile başlık ve puan arama (Örn: "1. Problem Tanımı (20 Puan)")
        lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
        for line in lines:
            m = re.match(r"^(\d+)[\.\s]+([^\(\d]+)\s*(?:\((\d+)\s*(?:puan|pt|pts)?\))?", line, re.IGNORECASE)
            if m:
                sec_num = m.group(1)
                sec_title = m.group(2).strip()
                score_str = m.group(3)
                if len(sec_title) > 3 and not any(k["criterion_name"] == sec_title for k in rubric_items):
                    score = float(score_str) if score_str else 20.0
                    rubric_items.append({
                        "criterion_code": f"C{sec_num}",
                        "criterion_name": f"{sec_num}. {sec_title}",
                        "description": f"{sec_title} bölümünün şartname isterlerine uygunluğu ve teknik derinliği.",
                        "max_score": score,
                        "order_index": int(sec_num)
                    })

        # Eğer şablondan yeterli başlık yakalanamadıysa aşama tipine göre varsayılan zengin rubrik oluştur
        if len(rubric_items) < 3:
            stage_u = stage_code.upper()
            if stage_u in ("OTR", "PDR", "ODR"):
                rubric_items = [
                    {
                        "criterion_code": "C1",
                        "criterion_name": "1. Proje Özeti ve Problem Tanımı",
                        "description": "Problemin netliği, güncel literatür taraması ve hedeflenen çözüm vizyonu.",
                        "max_score": 20.0,
                        "order_index": 1
                    },
                    {
                        "criterion_code": "C2",
                        "criterion_name": "2. Özgünlük ve İnovatif Yönler",
                        "description": "Mevcut çözümlerden farkı, yerli/özgün algoritmalar ve yenilikçi yaklaşımlar.",
                        "max_score": 25.0,
                        "order_index": 2
                    },
                    {
                        "criterion_code": "C3",
                        "criterion_name": "3. Sistem ve Yöntem Mimarisi",
                        "description": "Blok diyagramlar, matematiksel/algoritmik modelleme ve yöntem tasarımı.",
                        "max_score": 30.0,
                        "order_index": 3
                    },
                    {
                        "criterion_code": "C4",
                        "criterion_name": "4. İş Takvimi, Bütçe ve Risk Analizi",
                        "description": "Proje zaman planı, kaynak planlaması, B planları ve güvenlik önlemleri.",
                        "max_score": 15.0,
                        "order_index": 4
                    },
                    {
                        "criterion_code": "C5",
                        "criterion_name": "5. Rapor Düzeni ve Şablon Uyumu",
                        "description": "Sayfa sınırı, akademik dil, formatlama ve referansların eksiksizliği.",
                        "max_score": 10.0,
                        "order_index": 5
                    }
                ]
            elif stage_u in ("KTR", "CDR", "DTR"):
                rubric_items = [
                    {
                        "criterion_code": "C1",
                        "criterion_name": "1. Detaylı Tasarım ve Sistem Mimarisi",
                        "description": "Mekanik, elektronik ve yazılım mimarisinin detaylı teknik çizim ve tasarımları.",
                        "max_score": 30.0,
                        "order_index": 1
                    },
                    {
                        "criterion_code": "C2",
                        "criterion_name": "2. Simülasyon, Test ve Analiz Sonuçları",
                        "description": "Deneysel veriler, simülasyon grafikleri ve performans analiz çıktıları.",
                        "max_score": 25.0,
                        "order_index": 2
                    },
                    {
                        "criterion_code": "C3",
                        "criterion_name": "3. Üretim ve Entegrasyon Olgunluğu",
                        "description": "Fiziksel prototip hazırlığı, bileşen uyumluluğu ve üretim takvimi.",
                        "max_score": 20.0,
                        "order_index": 3
                    },
                    {
                        "criterion_code": "C4",
                        "criterion_name": "4. Güvenlik ve Standartlara Uygunluk",
                        "description": "Operasyonel güvenlik prosedürleri, test protokolleri ve standart uyumu.",
                        "max_score": 15.0,
                        "order_index": 4
                    },
                    {
                        "criterion_code": "C5",
                        "criterion_name": "5. Raporlama Kalitesi ve Şablon Uyumu",
                        "description": "Şablondaki zorunlu başlıkların eksiksizliği ve teknik anlatım kalitesi.",
                        "max_score": 10.0,
                        "order_index": 5
                    }
                ]
            else:
                rubric_items = [
                    {
                        "criterion_code": "C1",
                        "criterion_name": "1. Teknik Olgunluk ve Tasarım",
                        "description": "Sistem mimarisinin derinliği, mühendislik yaklaşımları ve özgünlük.",
                        "max_score": 35.0,
                        "order_index": 1
                    },
                    {
                        "criterion_code": "C2",
                        "criterion_name": "2. Saha ve Test Doğrulamaları",
                        "description": "Test sonuçları, doğrulama adımları ve performans ölçümleri.",
                        "max_score": 35.0,
                        "order_index": 2
                    },
                    {
                        "criterion_code": "C3",
                        "criterion_name": "3. Uygulanabilirlik ve Etki",
                        "description": "Sistemin operasyonel başarımı ve hedeflenen problem üzerindeki etkisi.",
                        "max_score": 20.0,
                        "order_index": 3
                    },
                    {
                        "criterion_code": "C4",
                        "criterion_name": "4. Dokümantasyon ve Format",
                        "description": "Raporlama düzeni, görsel sunum ve kurallara uygunluk.",
                        "max_score": 10.0,
                        "order_index": 4
                    }
                ]

        # Puan toplamını 100 olacak şekilde kontrol ve normalize et
        total = sum(item["max_score"] for item in rubric_items)
        if total != 100.0 and total > 0:
            for item in rubric_items:
                item["max_score"] = round((item["max_score"] / total) * 100, 1)
            diff = 100.0 - sum(item["max_score"] for item in rubric_items)
            rubric_items[0]["max_score"] = round(rubric_items[0]["max_score"] + diff, 1)

        return {
            "stage_code": stage_code,
            "max_score": 100.0,
            "rubrics": rubric_items
        }


template_analyzer = TemplateAnalyzer()
