"""
Veritabanı Kayıt Modelleri (SQLite / Cloudflare D1 Uyumlu)

NOT: Bu modeller sade Python sınıflarıdır (ORM değil). Kayıtlar
src/database/db.py içindeki DatabaseManager tarafından ham SQL ile yazılır.
"""
from datetime import datetime, timezone
from typing import Optional, List
import json

class User:
    def __init__(self, user_id: str, name: str, email: str, role: str):
        self.user_id = user_id
        self.name = name
        self.email = email
        self.role = role  # ADMIN, REFEREE, CONTESTANT

class ReportRecord:
    def __init__(
        self,
        report_id: str,
        filename: str,
        project_name: str,
        category: str,
        r2_url: str,
        status: str = "READY_FOR_REFEREE",
        ai_score: float = 0.0,
        referee_score: Optional[float] = None,
        referee_id: Optional[str] = None,
        referee_notes: Optional[str] = None
    ):
        self.report_id = report_id
        self.filename = filename
        self.project_name = project_name
        self.category = category
        self.r2_url = r2_url
        self.status = status
        self.ai_score = ai_score
        self.referee_score = referee_score
        self.referee_id = referee_id
        self.referee_notes = referee_notes
        # datetime.utcnow() Python 3.12+ ile deprecated; timezone-aware kullanılıyor.
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self):
        return {
            "report_id": self.report_id,
            "filename": self.filename,
            "project_name": self.project_name,
            "category": self.category,
            "r2_url": self.r2_url,
            "status": self.status,
            "ai_score": self.ai_score,
            "referee_score": self.referee_score,
            "referee_id": self.referee_id,
            "referee_notes": self.referee_notes,
            "created_at": self.created_at
        }
