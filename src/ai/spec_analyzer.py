"""
Yarışma Şartnamesi AI Analiz Modülü.
Admin şartname (PDF) yüklediğinde kuralları, takım sınırlarını,
danışman şartını, hedef seviyeleri ve teknik isterleri otomatik çıkarır.
"""

from __future__ import annotations

import os
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import pymupdf

class SpecAnalyzer:
    def extract_text_from_pdf(self, pdf_path: str, max_pages: int = 15) -> str:
        """PDF dosyasından metin çıkarır."""
        p = Path(pdf_path)
        if not p.exists():
            return ""
        text = []
        try:
            doc = pymupdf.open(str(p))
            for idx, page in enumerate(doc):
                if idx >= max_pages:
                    break
                text.append(page.get_text())
            doc.close()
        except Exception:
            pass
        return "\n".join(text)

    def analyze_specification(self, pdf_path_or_text: str, competition_name: str = "") -> Dict[str, Any]:
        """
        Şartnameyi analiz ederek kuralları yapılandırılmış JSON olarak döndürür.
        """
        if os.path.exists(pdf_path_or_text):
            raw_text = self.extract_text_from_pdf(pdf_path_or_text)
        else:
            raw_text = pdf_path_or_text

        low_text = raw_text.lower()

        # 1. Takım Üye Sayısı Tespiti
        min_members = 1
        max_members = 6
        member_match = re.search(r"takım.*?(\d+)\s*(?:-|ila|veya|ile)\s*(\d+)\s*kişi", low_text)
        if member_match:
            try:
                min_members = int(member_match.group(1))
                max_members = int(member_match.group(2))
            except Exception:
                pass
        elif "en az 2" in low_text or "en az iki" in low_text:
            min_members = 2
        elif "en fazla 5" in low_text or "en çok 5" in low_text:
            max_members = 5

        # 2. Danışman Şartı Tespiti
        advisor_required = 0
        if "danışman zorunlu" in low_text or "danışman bulundurmak zorunludur" in low_text or "lise" in low_text:
            advisor_required = 1

        # 3. Seviye ve Hedef Kitle Tespiti
        levels = []
        if "ilkokul" in low_text:
            levels.append("İlkokul")
        if "ortaokul" in low_text:
            levels.append("Ortaokul")
        if "lise" in low_text:
            levels.append("Lise")
        if "üniversite" in low_text or "lisans" in low_text:
            levels.append("Üniversite ve Üzeri")
        if "mezun" in low_text:
            levels.append("Mezun")
        if not levels:
            levels = ["Lise", "Üniversite ve Üzeri", "Mezun"]

        # 4. Kurallar ve Ön Koşullar Listesi
        requirements = [
            {
                "rule_type": "takim_yapisi",
                "title": "Takım Büyüklüğü ve Üye Sınırı",
                "description": f"Takımlar asgari {min_members}, azami {max_members} kişiden oluşmalıdır.",
                "min_team_size": min_members,
                "max_team_size": max_members,
                "advisor_required": advisor_required,
                "is_mandatory": 1
            },
            {
                "rule_type": "danisman_kurali",
                "title": "Danışman Gereksinimi",
                "description": "Lise seviyesi takımlar için danışman öğretmen/akademisyen zorunludur." if advisor_required else "Danışman bulundurmak isteğe bağlıdır.",
                "min_team_size": min_members,
                "max_team_size": max_members,
                "advisor_required": advisor_required,
                "is_mandatory": advisor_required
            },
            {
                "rule_type": "ozgunluk_ve_intihal",
                "title": "Özgünlük ve İntihal Benzerlik Sınırı",
                "description": "Rapor intihal benzerlik oranı azami %15 olmalı, hakem kör değerlendirmesi için raporda takım/şahıs ismi bulunmamalıdır.",
                "min_team_size": min_members,
                "max_team_size": max_members,
                "advisor_required": advisor_required,
                "is_mandatory": 1
            },
            {
                "rule_type": "teknik_ister",
                "title": "Teknik Kapsam ve Problem Çözümü",
                "description": f"Proje, {competition_name or 'yarışma'} teknik şartnamesinde belirtilen problem senaryosuna ve isterlerine doğrudan uygun modellenmelidir.",
                "min_team_size": min_members,
                "max_team_size": max_members,
                "advisor_required": advisor_required,
                "is_mandatory": 1
            }
        ]

        # 5. Bağımsız Takvim Tarihleri Tespiti
        schedule = {
            "son_basvuru": "28.02.2026",
            "yarisma_tarihi": "15.09.2026 - 20.09.2026",
            "sonuc_tarihi": "25.09.2026"
        }
        dates_found = re.findall(r"\b(\d{1,2}[\.\/]\d{1,2}[\.\/]202[5-7])\b", raw_text)
        if len(dates_found) >= 2:
            schedule["son_basvuru"] = dates_found[0]
            schedule["yarisma_tarihi"] = dates_found[1]

        return {
            "min_team_size": min_members,
            "max_team_size": max_members,
            "advisor_required": advisor_required,
            "levels": levels,
            "requirements": requirements,
            "schedule": schedule
        }


spec_analyzer = SpecAnalyzer()
