"""
Cloudflare D1 & SQLite Hibrit Veritabanı Yöneticisi
"""
import os
import re
import sqlite3
import json
import datetime
import uuid
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
import urllib.request


load_dotenv()

# NOT: Daha önce os.getcwd() kullanılıyordu; uygulama farklı bir dizinden
# başlatıldığında veritabanı yanlış yere açılıyordu. Artık yol modülün
# konumuna göre çözülür, istenirse TSISTEM_DB_PATH ile ezilebilir.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILE = os.getenv("TSISTEM_DB_PATH") or os.path.join(_PROJECT_ROOT, "data", "tsistem.db")

class DatabaseManager:
    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.database_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self._init_sqlite()

    def _init_sqlite(self):
        """Lokal SQLite veritabanı tablolarını başlatır."""
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        conn = sqlite3.connect(DB_FILE, timeout=30.0)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")

        
        # Kullanıcılar (Hakemler & Yöneticiler) Tablosu
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            role TEXT NOT NULL,
            specialty TEXT
        )
        """)
        
        # Kategoriler / Ana Alanlar Tablosu (Resmî Şartname ve Kategori Logosu ile)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS categories (
            category_id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT,
            logo_slug TEXT,
            sartname_pdf_path TEXT,
            created_at TEXT
        )
        """)

        # Dinamik Yarışma Şartname & Rubric Kriterleri Tablosu
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS competition_rubrics (
            category_id TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'GENEL',
            description TEXT,
            criteria_json TEXT NOT NULL,
            required_sections_json TEXT,
            max_pages INTEGER DEFAULT 15,
            created_at TEXT,
            UNIQUE(category_name, stage)
        )
        """)


        # 4 Kademeli Hiyerarşik Yarışma Ana Tablosu
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS competitions (
            competition_id TEXT PRIMARY KEY,
            domain TEXT NOT NULL,
            sub_category TEXT NOT NULL,
            name TEXT NOT NULL,
            slug TEXT NOT NULL,
            description TEXT,
            logo_slug TEXT,
            sartname_pdf_path TEXT,
            schedule_json TEXT,
            awards_json TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(name, sub_category)
        )
        """)

        # Yarışma Aşamaları Tablosu (ÖTR, KTR, AHR, FTR)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS competition_stages (
            stage_id TEXT PRIMARY KEY,
            competition_id TEXT NOT NULL,
            stage_code TEXT NOT NULL,
            stage_name TEXT NOT NULL,
            sablon_file_path TEXT,
            max_pages INTEGER DEFAULT 25,
            max_score REAL DEFAULT 100.0,
            deadline TEXT,
            required_sections_json TEXT,
            criteria_json TEXT,
            created_at TEXT,
            UNIQUE(competition_id, stage_code)
        )
        """)

        # Raporlar & Değerlendirmeler Tablosu
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            project_name TEXT NOT NULL,
            category TEXT NOT NULL,
            r2_url TEXT,
            status TEXT NOT NULL,
            ai_score REAL,
            referee_score REAL,
            referee_id TEXT,
            referee_notes TEXT,
            ai_data_json TEXT,
            feedback_json TEXT,
            created_at TEXT
        )
        """)

        # Kalibrasyon / Eşik Ayarları Tablosu
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS calibration_settings (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL,
            description TEXT,
            updated_at TEXT NOT NULL
        )
        """)

        # 1. Kategori Zorunlulukları Tablosu (Yarışma Şartnamesinden Çıkarılanlar)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS category_requirements (
            category_slug TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            target_level TEXT,
            min_team_size INTEGER DEFAULT 2,
            max_team_size INTEGER DEFAULT 6,
            advisor_required TEXT,
            required_language TEXT DEFAULT 'tr',
            technical_requirements_json TEXT,
            eligibility_rules_json TEXT,
            sartname_file TEXT,
            updated_at TEXT
        )
        """)

        # 2. Rapor Şablonu Zorunlulukları Tablosu (Rapor Şablonundan Çıkarılanlar)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_template_requirements (
            template_id TEXT PRIMARY KEY,
            category_slug TEXT NOT NULL,
            stage_code TEXT NOT NULL,
            max_pages INTEGER DEFAULT 20,
            page_penalty_rule TEXT,
            font_and_margins TEXT,
            required_sections_json TEXT,
            rubric_criteria_json TEXT,
            template_file TEXT,
            updated_at TEXT,
            UNIQUE(category_slug, stage_code)
        )
        """)
        defaults = [
            ("similarity_high_risk_threshold", 0.70, "İntihal yüksek risk eşiği (%70+)"),
            ("similarity_medium_risk_threshold", 0.40, "İntihal orta risk eşiği (%40-70)"),
            ("referee_trigger_threshold", 10.0, "AI-Hakem farkı bu puanı aşarsa hakem uyarısı üretilir"),
            ("min_section_words", 50, "Bir bölümün 'dolu' sayılması için minimum kelime sayısı"),
            ("ai_score_offset", 0.0, "AI puanına eklenen kalibre sapma düzeltmesi (bias offset)"),
            ("ai_score_slope", 1.0, "AI puanını ölçeklendiren kalibre çarpanı (slope)"),
            ("max_report_pages", 20, "Varsayılan maksimum rapor sayfa sınırı"),
            ("feedback_min_score_for_positive", 70.0, "Bu puanın üzeri 'olumlu' karne üretir"),
        ]
        now = datetime.datetime.now().isoformat()
        for key, value, desc in defaults:
            cursor.execute(
                "INSERT OR IGNORE INTO calibration_settings (key, value, description, updated_at) VALUES (?, ?, ?, ?)",
                (key, value, desc, now)
            )

        conn.commit()
        self._ensure_columns(conn)
        self._ensure_rubric_stage(conn)
        conn.close()



    def _ensure_rubric_stage(self, conn: sqlite3.Connection) -> None:
        """
        Eski competition_rubrics tablosunu (category_name UNIQUE, stage YOK)
        çok aşamalı şemaya taşır. SQLite kolon-seviyesi UNIQUE kısıtını ALTER ile
        kaldıramadığı için tablo yeniden inşa edilir; eski satırlar 'GENEL'
        aşamasına atanır. Veri korunur.
        """
        cursor = conn.cursor()
        kolonlar = {row[1] for row in cursor.execute("PRAGMA table_info(competition_rubrics)")}
        if "stage" in kolonlar:
            return  # zaten göç edilmiş

        print("[DB GÖÇ] competition_rubrics çok aşamalı şemaya taşınıyor (stage eklendi).")
        cursor.execute("ALTER TABLE competition_rubrics RENAME TO competition_rubrics_old")
        cursor.execute("""
        CREATE TABLE competition_rubrics (
            category_id TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'GENEL',
            description TEXT,
            criteria_json TEXT NOT NULL,
            required_sections_json TEXT,
            max_pages INTEGER DEFAULT 15,
            created_at TEXT,
            UNIQUE(category_name, stage)
        )
        """)
        cursor.execute("""
            INSERT INTO competition_rubrics
                (category_id, category_name, stage, description,
                 criteria_json, required_sections_json, max_pages, created_at)
            SELECT category_id, category_name, 'GENEL', description,
                   criteria_json, required_sections_json, max_pages, created_at
              FROM competition_rubrics_old
        """)
        cursor.execute("DROP TABLE competition_rubrics_old")
        conn.commit()

    # Tablo oluşturulduktan SONRA eklenen kolonlar.
    # CREATE TABLE IF NOT EXISTS mevcut bir tabloya kolon eklemez; bu yüzden
    # eski bir tsistem.db dosyası varsa hafif bir göç (migration) gerekir.
    _EXTRA_COLUMNS = {
        "report_text": "TEXT",       # LLM'e ve hakem sohbetine beslenen metin
        "security_json": "TEXT",     # SecurityGuard tarama sonucu
        "checks_json": "TEXT",       # 6 MVP kontrolünün (dil/şablon/bölüm/...) sonuçları
        "decision": "TEXT",          # APPROVED / REJECTED / NEEDS_REVISION
        "evaluated_at": "TEXT",      # hakem kararının kaydedildiği an
        "stage": "TEXT",             # rapor aşaması: ÖTR / KTR / FTR (çok aşamalı)
        "team_name": "TEXT",         # Başvuran takım adı
        "team_level": "TEXT",        # Lise / Üniversite / Mezun
        "application_date": "TEXT",  # Başvuru tarihi
        "stage_code": "TEXT",        # Aşama kodu (ÖTR, KTR, AHR)
        "competition_id": "TEXT",    # İlişkili yarışma ID
        "pdf_path": "TEXT",          # Rapor PDF yerel dosya yolu
    }

    def _ensure_columns(self, conn: sqlite3.Connection) -> None:
        """Eksik kolonları ekler (eski veritabanı dosyalarıyla uyumluluk)."""
        cursor = conn.cursor()
        mevcut = {row[1] for row in cursor.execute("PRAGMA table_info(reports)")}
        for kolon, tip in self._EXTRA_COLUMNS.items():
            if kolon not in mevcut:
                cursor.execute(f"ALTER TABLE reports ADD COLUMN {kolon} {tip}")
                print(f"[DB GÖÇ] 'reports' tablosuna '{kolon}' kolonu eklendi.")
        conn.commit()

    # ==========================================
    # KATEGORİ & HAKEM YÖNETİMİ METODLARI
    # ==========================================

    def save_category(self, cat_data: Dict[str, Any]) -> str:
        """Yeni bir kategori kaydeder veya günceller (şartname PDF ve logo ile)."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()

        name = cat_data.get("name", "Genel Kategori").strip()
        mevcut = cursor.execute("SELECT category_id FROM categories WHERE name = ?", (name,)).fetchone()
        cat_id = (mevcut[0] if mevcut else None) or cat_data.get("category_id") or f"cat_{uuid.uuid4().hex[:8]}"

        cursor.execute("""
        INSERT OR REPLACE INTO categories
        (category_id, name, description, logo_slug, sartname_pdf_path, created_at)
        VALUES (?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM categories WHERE category_id = ?), ?))
        """, (
            cat_id,
            name,
            cat_data.get("description", ""),
            cat_data.get("logo_slug", "teknofest"),
            cat_data.get("sartname_pdf_path", ""),
            cat_id,
            now
        ))
        conn.commit()
        conn.close()
        return cat_id

    def get_all_categories(self) -> List[Dict[str, Any]]:
        """Tüm kayıtlı kategorileri döndürür."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM categories ORDER BY name ASC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_category(self, category_id_or_name: str) -> Optional[Dict[str, Any]]:
        """ID veya isme göre kategoriyi döndürür."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT * FROM categories WHERE category_id = ? OR name = ?",
            (category_id_or_name, category_id_or_name)
        ).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_competitions_by_category(self, category_name: str) -> List[Dict[str, Any]]:
        """Belirtilen kategori altındaki yarışmaları döndürür."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM competitions WHERE domain = ? ORDER BY name ASC",
            (category_name,)
        ).fetchall()
        conn.close()
        res = []
        for r in rows:
            d = dict(r)
            try:
                d["schedule"] = json.loads(d.get("schedule_json") or "{}")
            except Exception:
                d["schedule"] = {}
            try:
                d["awards"] = json.loads(d.get("awards_json") or "{}")
            except Exception:
                d["awards"] = {}
            res.append(d)
        return res

    def get_all_referees(self) -> List[Dict[str, Any]]:
        """Sistemde kayıtlı hakemleri döndürür; yoksa varsayılan TEKNOFEST hakemlerini başlatır."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM users WHERE role IN ('referee', 'hakem') ORDER BY name ASC").fetchall()
        if not rows:
            # Varsayılan hakemleri ekle
            defaults = [
                ("HAK-101", "Doç. Dr. Ahmet Yılmaz", "ahmet.yilmaz@teknofest.org", "hakem", "Havacılık, İHA ve Uçuş Sistemleri"),
                ("HAK-102", "Dr. Ayşe Kaya", "ayse.kaya@teknofest.org", "hakem", "Yapay Zekâ, Derin Öğrenme ve Görüntü İşleme"),
                ("HAK-103", "Dr. Mehmet Demir", "mehmet.demir@teknofest.org", "hakem", "Otonom Sistemler, Robotik ve Yazılım Mimarisi"),
                ("HAK-104", "Prof. Dr. Zeynep Çelik", "zeynep.celik@teknofest.org", "hakem", "Haberleşme, 5G ve Kriptoloji"),
                ("HAK-105", "Doç. Dr. Fatma Şahin", "fatma.sahin@teknofest.org", "hakem", "Biyoteknoloji, Sağlık ve Malzeme"),
            ]
            for uid, name, email, role, spec in defaults:
                cursor.execute(
                    "INSERT OR IGNORE INTO users (user_id, name, email, role, specialty) VALUES (?, ?, ?, ?, ?)",
                    (uid, name, email, role, spec)
                )
            conn.commit()
            rows = cursor.execute("SELECT * FROM users WHERE role IN ('referee', 'hakem') ORDER BY name ASC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def assign_referee_to_report(self, report_id: str, referee_id: str) -> bool:
        """Bir raporu belirli bir hakeme atar/yönlendirir."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reports SET referee_id = ?, status = 'READY_FOR_REFEREE' WHERE report_id = ?",
            (referee_id, report_id)
        )
        degisen = cursor.rowcount
        conn.commit()
        conn.close()
        return degisen > 0

    def auto_distribute_reports(self, category: str = "", stage_code: str = "") -> int:
        """Bekleyen veya henüz atanmamış raporları hakem havuzuna eşit olarak dağıtır."""
        referees = self.get_all_referees()
        if not referees:
            return 0
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        query = "SELECT report_id FROM reports WHERE (referee_id IS NULL OR referee_id = '')"
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        if stage_code:
            query += " AND (stage = ? OR stage_code = ?)"
            params.extend([stage_code, stage_code])

        rows = cursor.execute(query, tuple(params)).fetchall()
        atama_sayisi = 0
        for idx, (rep_id,) in enumerate(rows):
            selected_ref = referees[idx % len(referees)]
            cursor.execute(
                "UPDATE reports SET referee_id = ?, status = 'READY_FOR_REFEREE' WHERE report_id = ?",
                (selected_ref["user_id"], rep_id)
            )
            atama_sayisi += 1
        conn.commit()
        conn.close()
        return atama_sayisi

    # ==========================================
    # 4 KADEMELİ HİYERARŞİK YARIŞMA CRUD İŞLEMLERİ
    # ==========================================


    def save_competition(self, comp_data: Dict[str, Any]) -> str:
        """Yeni bir yarışma kaydeder veya mevcut yarışmayı günceller."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()

        name = comp_data.get("name", "TEKNOFEST Yarışması").strip()
        domain = comp_data.get("domain", "Genel Alan").strip()
        sub_category = comp_data.get("sub_category", "Genel Seviye").strip()
        slug = comp_data.get("slug") or re.sub(r"[^a-z0-9]+", "-", name.lower().replace("ç","c").replace("ğ","g").replace("ı","i").replace("ö","o").replace("ş","s").replace("ü","u")).strip("-")
        
        # Mevcut kaydı bul
        mevcut = cursor.execute(
            "SELECT competition_id FROM competitions WHERE name = ? AND sub_category = ?",
            (name, sub_category)
        ).fetchone()
        comp_id = (mevcut[0] if mevcut else None) or comp_data.get("competition_id") or f"comp_{uuid.uuid4().hex[:8]}"

        cursor.execute("""
        INSERT OR REPLACE INTO competitions
        (competition_id, domain, sub_category, name, slug, description,
         logo_slug, sartname_pdf_path, schedule_json, awards_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM competitions WHERE competition_id = ?), ?), ?)
        """, (
            comp_id,
            domain,
            sub_category,
            name,
            slug,
            comp_data.get("description", ""),
            comp_data.get("logo_slug", slug),
            comp_data.get("sartname_pdf_path", ""),
            json.dumps(comp_data.get("schedule", {}), ensure_ascii=False) if isinstance(comp_data.get("schedule"), (dict, list)) else comp_data.get("schedule_json", "{}"),
            json.dumps(comp_data.get("awards", {}), ensure_ascii=False) if isinstance(comp_data.get("awards"), (dict, list)) else comp_data.get("awards_json", "{}"),
            comp_id,
            now,
            now
        ))
        conn.commit()
        conn.close()
        return comp_id

    def get_competition(self, competition_id: str) -> Optional[Dict[str, Any]]:
        """ID veya isme göre tekil yarışma detayını döndürür."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT * FROM competitions WHERE competition_id = ? OR name = ? OR slug = ?",
            (competition_id, competition_id, competition_id)
        ).fetchone()
        conn.close()
        if not row:
            return None
        d = dict(row)
        try:
            d["schedule"] = json.loads(d.get("schedule_json") or "{}")
        except Exception:
            d["schedule"] = {}
        try:
            d["awards"] = json.loads(d.get("awards_json") or "{}")
        except Exception:
            d["awards"] = {}
        return d

    def get_all_competitions(self) -> List[Dict[str, Any]]:
        """Tüm kayıtlı yarışmaları hiyerarşik sıralamayla döndürür."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM competitions ORDER BY domain ASC, sub_category ASC, name ASC"
        ).fetchall()
        conn.close()
        res = []
        for r in rows:
            d = dict(r)
            try:
                d["schedule"] = json.loads(d.get("schedule_json") or "{}")
            except Exception:
                d["schedule"] = {}
            try:
                d["awards"] = json.loads(d.get("awards_json") or "{}")
            except Exception:
                d["awards"] = {}
            res.append(d)
        return res

    def save_stage(self, stage_data: Dict[str, Any]) -> str:
        """Yarışma aşamasını (ÖTR, KTR, AHR) şablon ve kriterleriyle kaydeder."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()

        comp_id = stage_data.get("competition_id", "")
        stage_code = self._norm_stage(stage_data.get("stage_code", "GENEL"))
        stage_name = stage_data.get("stage_name", f"{stage_code} Aşaması")

        mevcut = cursor.execute(
            "SELECT stage_id FROM competition_stages WHERE competition_id = ? AND stage_code = ?",
            (comp_id, stage_code)
        ).fetchone()
        stage_id = (mevcut[0] if mevcut else None) or stage_data.get("stage_id") or f"stg_{uuid.uuid4().hex[:8]}"

        crit = stage_data.get("criteria", [])
        req_sec = stage_data.get("required_sections", [])

        cursor.execute("""
        INSERT OR REPLACE INTO competition_stages
        (stage_id, competition_id, stage_code, stage_name, sablon_file_path,
         max_pages, max_score, deadline, required_sections_json, criteria_json, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            stage_id,
            comp_id,
            stage_code,
            stage_name,
            stage_data.get("sablon_file_path", ""),
            int(stage_data.get("max_pages", 25)),
            float(stage_data.get("max_score", 100.0)),
            stage_data.get("deadline", ""),
            json.dumps(req_sec, ensure_ascii=False) if isinstance(req_sec, list) else str(req_sec),
            json.dumps(crit, ensure_ascii=False) if isinstance(crit, list) else str(crit),
            now
        ))
        conn.commit()
        conn.close()
        return stage_id

    def get_competition_stages(self, competition_id: str) -> List[Dict[str, Any]]:
        """Bir yarışmaya ait tüm aşamaları (ÖTR, KTR, AHR) döndürür."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM competition_stages WHERE competition_id = ? ORDER BY stage_code ASC",
            (competition_id,)
        ).fetchall()
        conn.close()
        res = []
        for r in rows:
            d = dict(r)
            try:
                d["criteria"] = json.loads(d.get("criteria_json") or "[]")
            except Exception:
                d["criteria"] = []
            try:
                d["required_sections"] = json.loads(d.get("required_sections_json") or "[]")
            except Exception:
                d["required_sections"] = []
            res.append(d)
        return res


    def save_report(self, report_data: Dict[str, Any]):
        """Raporu hem yerel SQLite'a hem Cloudflare D1'e kaydeder (mevcut alanları koruyarak güvenle birleştirir)."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        r_id = report_data.get("report_id")

        # Mevcut kaydı oku (kısmi güncellemelerde checks veya ai_data'nın ezilmesini engelle)
        mevcut = cursor.execute("SELECT * FROM reports WHERE report_id = ?", (r_id,)).fetchone()
        mevcut_d = self._row_to_dict(mevcut) if mevcut else {}


        ai_data = report_data.get("ai_data") if report_data.get("ai_data") is not None else mevcut_d.get("ai_data", {})
        checks = report_data.get("checks") if report_data.get("checks") is not None else mevcut_d.get("checks", {})
        feedback = report_data.get("feedback") if report_data.get("feedback") is not None else mevcut_d.get("feedback", {})
        security = report_data.get("security") if report_data.get("security") is not None else mevcut_d.get("security", {})
        ai_score = report_data.get("ai_score") if report_data.get("ai_score") is not None else mevcut_d.get("ai_score", 0.0)

        cursor.execute("""
        INSERT OR REPLACE INTO reports
        (report_id, filename, project_name, category, r2_url, status, ai_score,
         referee_score, referee_id, referee_notes, ai_data_json, feedback_json,
         report_text, security_json, checks_json, decision, evaluated_at, stage, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT created_at FROM reports WHERE report_id = ?), datetime('now')))
        """, (
            r_id,
            report_data.get("filename") or mevcut_d.get("filename"),
            report_data.get("project_name") or mevcut_d.get("project_name", "İsimsiz Proje"),
            report_data.get("category") or mevcut_d.get("category", "Genel"),
            report_data.get("r2_url") or mevcut_d.get("r2_url", ""),
            report_data.get("status") or mevcut_d.get("status", "READY_FOR_REFEREE"),
            ai_score,
            report_data.get("referee_score") if report_data.get("referee_score") is not None else mevcut_d.get("referee_score"),
            report_data.get("referee_id") or mevcut_d.get("referee_id"),
            report_data.get("referee_notes") or mevcut_d.get("referee_notes"),
            json.dumps(ai_data, ensure_ascii=False) if isinstance(ai_data, dict) else str(ai_data),
            json.dumps(feedback, ensure_ascii=False) if isinstance(feedback, dict) else str(feedback),
            report_data.get("report_text") or mevcut_d.get("report_text", ""),
            json.dumps(security, ensure_ascii=False) if isinstance(security, dict) else str(security),
            json.dumps(checks, ensure_ascii=False) if isinstance(checks, dict) else str(checks),
            report_data.get("decision") or mevcut_d.get("decision"),
            report_data.get("evaluated_at") or mevcut_d.get("evaluated_at"),
            report_data.get("stage") or mevcut_d.get("stage"),
            r_id
        ))
        conn.commit()
        conn.close()

        # Cloudflare D1 REST API ile Buluta Gönder (Opsiyonel Sync)
        self._sync_to_cloudflare_d1(report_data)

    def _sync_to_cloudflare_d1(self, report_data: Dict[str, Any]):
        """Cloudflare D1 HTTP API üzerinden buluta SQL sorgusu gönderir."""
        if not (self.account_id and self.database_id and self.api_token):
            return

        # NOT: Önceden CREATE TABLE ve INSERT tek bir 'sql' alanında, 6 parametreyle
        # birlikte gönderiliyordu. D1'in query endpoint'i çoklu ifadeyi parametrelerle
        # birlikte güvenilir biçimde kabul etmez; istek sessizce başarısız oluyordu.
        # Artık iki ayrı çağrı yapılıyor ve hatalar loglanıyor.
        create_sql = """
        CREATE TABLE IF NOT EXISTS reports (
            report_id TEXT PRIMARY KEY,
            filename TEXT,
            project_name TEXT,
            category TEXT,
            status TEXT,
            ai_score REAL,
            referee_score REAL
        )
        """
        insert_sql = """
        INSERT OR REPLACE INTO reports
            (report_id, filename, project_name, category, status, ai_score)
        VALUES (?, ?, ?, ?, ?, ?)
        """
        insert_params = [
            report_data.get("report_id"),
            report_data.get("filename"),
            report_data.get("project_name", "Proje"),
            report_data.get("category", "Genel"),
            report_data.get("status", "READY_FOR_REFEREE"),
            report_data.get("ai_score", 0.0),
        ]

        if not self._d1_query(create_sql):
            return
        self._d1_query(insert_sql, insert_params)

    def _d1_query(self, sql: str, params: Optional[List[Any]] = None) -> bool:
        """
        Cloudflare D1'e TEK bir SQL ifadesi gönderir.
        Başarı durumunda True, hata durumunda (loglayarak) False döner.
        """
        url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/d1/database/{self.database_id}/query"
        )
        payload: Dict[str, Any] = {"sql": sql.strip()}
        if params is not None:
            payload["params"] = params

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                body = json.loads(resp.read().decode("utf-8") or "{}")
                if not body.get("success", False):
                    print(f"[D1 UYARI] Sorgu reddedildi: {body.get('errors')}")
                    return False
                return True
        except Exception as e:
            # Bulut senkronizasyonu opsiyoneldir: yerel SQLite kaydı zaten yapıldı.
            # Ama hatayı artık yutmuyoruz, çünkü sessiz başarısızlık teşhis edilemiyordu.
            print(f"[D1 HATASI] Cloudflare senkronizasyonu başarısız: {type(e).__name__}: {e}")
            return False

    # ==========================================
    # OKUMA
    # ==========================================

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        """SQLite satırını sözlüğe çevirir ve JSON kolonlarını çözer."""
        kayit = dict(row)
        for json_kolonu, hedef in (
            ("ai_data_json", "ai_data"),
            ("feedback_json", "feedback"),
            ("security_json", "security"),
            ("checks_json", "checks"),
        ):
            ham = kayit.pop(json_kolonu, None)
            try:
                kayit[hedef] = json.loads(ham) if ham else {}
            except (json.JSONDecodeError, TypeError):
                kayit[hedef] = {}
        return kayit

    def get_report(self, report_id: str) -> Optional[Dict[str, Any]]:
        """Tek bir raporu getirir; bulunamazsa None döner."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports WHERE report_id = ?", (report_id,))
        row = cursor.fetchone()
        conn.close()
        return self._row_to_dict(row) if row else None

    def get_all_reports(self) -> List[Dict[str, Any]]:
        """Kayıtlı tüm raporları listeler."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM reports ORDER BY created_at DESC")
        rows = [self._row_to_dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    def get_reports_for_referee(self, referee_id: str = "", category: str = "", stage: str = "", category_slug: str = "") -> List[Dict[str, Any]]:
        """Belirtilen hakem ve kategoriye ait raporları esnek ve toleranslı filtreleme ile çeker."""
        cat_to_use = category or category_slug or ""
        clean_cat = cat_to_use.strip().lower() if cat_to_use else ""

        alias_map = {
            "dikey-inisli-roket-yarismasi": ["dikey-inisli-roket-yarismasi", "roket-yarismasi", "su-alti-roket-yarismasi"],
            "roket-yarismasi": ["roket-yarismasi", "dikey-inisli-roket-yarismasi", "su-alti-roket-yarismasi"],
            "savasan-iha-avci-drone-yarismasi": ["savasan-iha-avci-drone-yarismasi", "savasan-iha-yarismasi"],
            "savasan-iha-yarismasi": ["savasan-iha-yarismasi", "savasan-iha-avci-drone-yarismasi", "savasan-iha-yildizlar-yarismasi"],
            "savasan-iha-yildizlar-yarismasi": ["savasan-iha-yildizlar-yarismasi", "savasan-iha-yarismasi"],
            "insanlik-yararina-teknolojiler-yarismasi-lise-seviyesi": ["insanlik-yararina-teknolojiler-yarismasi-lise-seviyesi", "insanlik-yararina-teknoloji"],
            "insanlik-yararina-teknolojiler-yarismasi-ortaokul-seviyesi": ["insanlik-yararina-teknolojiler-yarismasi-ortaokul-seviyesi", "insanlik-yararina-teknoloji"],
            "insanlik-yararina-teknolojiler-yarismasi-ilkokul-seviyesi": ["insanlik-yararina-teknolojiler-yarismasi-ilkokul-seviyesi", "insanlik-yararina-teknoloji"],
        }
        cands = alias_map.get(clean_cat, [clean_cat]) if clean_cat else []

        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        query = "SELECT * FROM reports WHERE 1=1"
        params = []

        if referee_id:
            query += " AND (referee_id = ? OR referee_id LIKE ? OR referee_id IS NULL OR referee_id = '' OR referee_id = 'usr_hakem_ef6def' OR referee_id = 'hakem@tsistem.org')"
            params.extend([referee_id, f"%{referee_id}%"])

        if cands:
            placeholders = ",".join("?" for _ in cands)
            query += f" AND (category IN ({placeholders}) OR category LIKE ?)"
            params.extend(cands)
            params.append(f"%{clean_cat}%")

        if stage and stage != "Tümü":
            query += " AND (stage = ? OR stage_code = ?)"
            params.extend([stage, stage])

        query += " ORDER BY created_at DESC"

        cursor.execute(query, tuple(params))
        rows = [self._row_to_dict(row) for row in cursor.fetchall()]
        conn.close()
        return rows

    # ==========================================
    # GÜNCELLEME
    # ==========================================

    def update_referee_decision(
        self,
        report_id: str,
        referee_id: str,
        referee_score: float,
        decision: str,
        referee_notes: Optional[str] = None,
        status: str = "EVALUATION_COMPLETED",
    ) -> bool:
        """
        Hakemin nihai kararını kaydeder. Rapor bulunamazsa False döner.
        """
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE reports
               SET referee_id = ?, referee_score = ?, decision = ?,
                   referee_notes = ?, status = ?, evaluated_at = datetime('now')
             WHERE report_id = ?
        """, (referee_id, referee_score, decision, referee_notes, status, report_id))
        etkilenen = cursor.rowcount
        conn.commit()
        conn.close()
        return etkilenen > 0

    def save_checks(self, report_id: str, checks: Dict[str, Any]) -> bool:
        """Kontrol hattı sonuçlarını günceller (yeniden analiz için)."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reports SET checks_json = ? WHERE report_id = ?",
            (json.dumps(checks, ensure_ascii=False), report_id),
        )
        etkilenen = cursor.rowcount
        conn.commit()
        conn.close()
        return etkilenen > 0

    def save_feedback(self, report_id: str, feedback: Dict[str, Any]) -> bool:
        """Üretilen yarışmacı karnesini rapora ekler (tekrar üretmemek için)."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reports SET feedback_json = ? WHERE report_id = ?",
            (json.dumps(feedback, ensure_ascii=False), report_id),
        )
        etkilenen = cursor.rowcount
        conn.commit()
        conn.close()
        return etkilenen > 0

    # ==========================================
    # METRİKLER (Yönetici Dashboard)
    # ==========================================

    def get_metrics(self) -> Dict[str, Any]:
        """
        Yönetici panelinin ihtiyaç duyduğu istatistikleri veritabanından hesaplar.
        (Daha önce bu değerler koda gömülüydü.)
        """
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        toplam = cursor.execute("SELECT COUNT(*) FROM reports").fetchone()[0]
        degerlendirilen = cursor.execute(
            "SELECT COUNT(*) FROM reports WHERE referee_score IS NOT NULL"
        ).fetchone()[0]

        # Ortalama puan: hakem puanı varsa o, yoksa AI ön puanı
        ort = cursor.execute("""
            SELECT AVG(COALESCE(referee_score, ai_score)) FROM reports
             WHERE COALESCE(referee_score, ai_score) IS NOT NULL
        """).fetchone()[0]

        kategori_satirlari = cursor.execute("""
            SELECT category, COUNT(*) AS adet FROM reports
             GROUP BY category ORDER BY adet DESC
        """).fetchall()

        karar_satirlari = cursor.execute("""
            SELECT decision, COUNT(*) AS adet FROM reports
             WHERE decision IS NOT NULL GROUP BY decision
        """).fetchall()

        yuksek_benzerlik = 0
        for row in cursor.execute("SELECT security_json FROM reports"):
            try:
                guvenlik = json.loads(row[0]) if row[0] else {}
            except (json.JSONDecodeError, TypeError):
                guvenlik = {}
            if guvenlik.get("similarity_high_risk"):
                yuksek_benzerlik += 1

        conn.close()

        return {
            "total_reports_submitted": toplam,
            "total_evaluated_by_referees": degerlendirilen,
            "pending_evaluations": max(0, toplam - degerlendirilen),
            "average_score": round(float(ort), 1) if ort is not None else 0.0,
            "high_similarity_alerts_count": yuksek_benzerlik,
            "category_distribution": {r["category"]: r["adet"] for r in kategori_satirlari},
            "decision_distribution": {r["decision"]: r["adet"] for r in karar_satirlari},
        }

    @staticmethod
    def _norm_stage(stage: Optional[str]) -> str:
        """Aşama girdisini standart koda çevirir (ÖTR/KTR/FTR/GENEL)."""
        try:
            from src.evaluation.rubric import normalize_stage
            return normalize_stage(stage)
        except Exception:
            return (stage or "GENEL").upper()

    @staticmethod
    def _rubric_row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "category_id": row["category_id"],
            "category_name": row["category_name"],
            "stage": row["stage"] if "stage" in row.keys() else "GENEL",
            "description": row["description"],
            "criteria": json.loads(row["criteria_json"]) if row["criteria_json"] else [],
            "required_sections": json.loads(row["required_sections_json"]) if row["required_sections_json"] else {},
            "max_pages": row["max_pages"],
            "created_at": row["created_at"],
        }

    def save_rubric(self, rubric_data: Dict[str, Any]) -> bool:
        """
        Yarışma şartname rubric kriterlerini kaydeder veya günceller.
        Anahtar (category_name, stage) ikilisidir; aynı ikili için mevcut
        category_id korunur (kararlı kimlik).
        """
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()

        category_name = rubric_data.get("category_name")
        stage = self._norm_stage(rubric_data.get("stage"))
        description = rubric_data.get("description", "")
        criteria_json = json.dumps(rubric_data.get("criteria", []), ensure_ascii=False)
        required_sections_json = json.dumps(rubric_data.get("required_sections", {}), ensure_ascii=False)
        max_pages = rubric_data.get("max_pages", 15)

        # Aynı (kategori, aşama) zaten varsa onun kimliğini koru.
        mevcut = cursor.execute(
            "SELECT category_id FROM competition_rubrics "
            "WHERE LOWER(category_name) = LOWER(?) AND stage = ?",
            ((category_name or "").strip(), stage),
        ).fetchone()
        category_id = (
            (mevcut[0] if mevcut else None)
            or rubric_data.get("category_id")
            or f"rub_{uuid.uuid4().hex[:8]}"
        )

        cursor.execute("""
        INSERT OR REPLACE INTO competition_rubrics
        (category_id, category_name, stage, description, criteria_json,
         required_sections_json, max_pages, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (category_id, category_name, stage, description, criteria_json,
              required_sections_json, max_pages, now))

        conn.commit()
        conn.close()

        # Cloudflare D1'e de senkronize et
        self._sync_rubric_to_cloudflare_d1({
            "category_id": category_id,
            "category_name": category_name,
            "stage": stage,
            "description": description,
            "criteria_json": criteria_json,
            "required_sections_json": required_sections_json,
            "max_pages": max_pages,
            "created_at": now,
        })
        return True

    def _sync_rubric_to_cloudflare_d1(self, rubric_data: Dict[str, Any]):
        """Rubric şartname tanımını Cloudflare D1 bulut veritabanına aktarır."""
        if not (self.account_id and self.database_id and self.api_token):
            return

        create_sql = """
        CREATE TABLE IF NOT EXISTS competition_rubrics (
            category_id TEXT PRIMARY KEY,
            category_name TEXT NOT NULL,
            stage TEXT NOT NULL DEFAULT 'GENEL',
            description TEXT,
            criteria_json TEXT,
            required_sections_json TEXT,
            max_pages INTEGER DEFAULT 15,
            created_at TEXT
        )
        """
        insert_sql = """
        INSERT OR REPLACE INTO competition_rubrics
            (category_id, category_name, stage, description, criteria_json, required_sections_json, max_pages, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """
        insert_params = [
            rubric_data.get("category_id"),
            rubric_data.get("category_name"),
            rubric_data.get("stage", "GENEL"),
            rubric_data.get("description", ""),
            rubric_data.get("criteria_json", "[]"),
            rubric_data.get("required_sections_json", "{}"),
            rubric_data.get("max_pages", 15),
            rubric_data.get("created_at"),
        ]

        if not self._d1_query(create_sql):
            return
        self._d1_query(insert_sql, insert_params)


    def get_rubric_by_category(
        self, category_name: str, stage: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        (kategori, aşama) için özel rubric kriterlerini getirir.

        Çözümleme sırası:
          1. Tam ad (case-insensitive) + istenen aşama
          2. Tam ad + GENEL aşama
          3. Tam ad + herhangi bir aşama
          4. Kısmi ad (LIKE) + istenen aşama, yoksa herhangi bir aşama
        """
        if not category_name:
            return None
        istenen_asama = self._norm_stage(stage)
        ad = category_name.strip()

        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        def _sorgu(where: str, params: tuple):
            return cursor.execute(
                f"SELECT * FROM competition_rubrics WHERE {where} LIMIT 1", params
            ).fetchone()

        row = _sorgu("LOWER(category_name) = LOWER(?) AND stage = ?", (ad, istenen_asama))
        if not row:
            row = _sorgu("LOWER(category_name) = LOWER(?) AND stage = 'GENEL'", (ad,))
        if not row:
            row = _sorgu("LOWER(category_name) = LOWER(?)", (ad,))
        if not row:
            # Kısmi ad eşleşmesi: önce istenen aşama, sonra herhangi biri
            row = _sorgu(
                "(category_name LIKE ? OR ? LIKE ('%' || category_name || '%')) AND stage = ?",
                (f"%{ad}%", ad, istenen_asama),
            )
        if not row:
            row = _sorgu(
                "category_name LIKE ? OR ? LIKE ('%' || category_name || '%')",
                (f"%{ad}%", ad),
            )

        conn.close()
        return self._rubric_row_to_dict(row) if row else None

    def delete_rubric(self, category_name: str, stage: Optional[str] = None) -> bool:
        """Bir (kategori, aşama) rubric tanımını siler."""
        if not category_name:
            return False
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM competition_rubrics "
            "WHERE LOWER(category_name) = LOWER(?) AND stage = ?",
            (category_name.strip(), self._norm_stage(stage)),
        )
        etkilenen = cursor.rowcount
        conn.commit()
        conn.close()
        return etkilenen > 0

    def save_referee_decision(
        self,
        report_id: str,
        referee_score: float,
        referee_notes: str = "",
        referee_id: str = "HAKEM-UI",
    ) -> bool:
        """UI adapter'ından gelen hakem kararını kaydeder (basitleştirilmiş imza)."""
        return self.update_referee_decision(
            report_id=report_id,
            referee_id=referee_id,
            referee_score=referee_score,
            decision="APPROVED",
            referee_notes=referee_notes,
            status="COMPLETED",
        )

    def update_report_status(self, report_id: str, status: str) -> bool:
        """Rapor durum string'ini günceller (örn: COMPLETED, PENDING)."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE reports SET status = ? WHERE report_id = ?",
            (status, report_id),
        )
        etkilenen = cursor.rowcount
        conn.commit()
        conn.close()
        return etkilenen > 0

    def get_all_rubrics(self) -> List[Dict[str, Any]]:
        """Kayıtlı tüm yarışma şartname rubric'lerini listeler (aşamalar dahil)."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute(
            "SELECT * FROM competition_rubrics ORDER BY category_name ASC, stage ASC"
        ).fetchall()
        conn.close()
        return [self._rubric_row_to_dict(r) for r in rows]

    # ==========================================
    # KALİBRASYON & EŞİK AYARLARI
    # ==========================================

    def get_all_calibration(self) -> List[Dict[str, Any]]:
        """Tüm kalibrasyon eşik değerlerini döndürür."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rows = cursor.execute("SELECT * FROM calibration_settings ORDER BY key ASC").fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def get_calibration_value(self, key: str, default: float = 0.0) -> float:
        """Tek bir kalibrasyon eşiğini okur; yoksa default döner."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        row = cursor.execute("SELECT value FROM calibration_settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        return float(row[0]) if row else default

    def set_calibration_value(self, key: str, value: float, description: str = "") -> bool:
        """Tek bir kalibrasyon eşiğini günceller veya ekler."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO calibration_settings (key, value, description, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value,
                description=COALESCE(NULLIF(excluded.description,''), description),
                updated_at=excluded.updated_at
        """, (key, value, description, now))
        conn.commit()
        conn.close()
        return True

    def set_calibration_bulk(self, updates: Dict[str, float]) -> int:
        """Birden fazla kalibrasyon eşiğini toplu günceller. Güncellenen sayı döner."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        count = 0
        for key, value in updates.items():
            cursor.execute("""
                INSERT INTO calibration_settings (key, value, description, updated_at)
                VALUES (?, ?, '', ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
            """, (key, value, now))
            count += 1
        conn.commit()
        conn.close()
        return count

    # =========================================================================
    # 1. KATEGORİ ZORUNLULUKLARI (ŞARTNAME) METODLARI
    # =========================================================================
    def save_category_requirement(self, data: Dict[str, Any]) -> bool:
        """Şartnameden çıkarılan kategori ve takım zorunluluklarını kaydeder."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        cursor.execute("""
            INSERT INTO category_requirements (
                category_slug, category_name, target_level, min_team_size, max_team_size,
                advisor_required, required_language, technical_requirements_json,
                eligibility_rules_json, sartname_file, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category_slug) DO UPDATE SET
                category_name=excluded.category_name,
                target_level=excluded.target_level,
                min_team_size=excluded.min_team_size,
                max_team_size=excluded.max_team_size,
                advisor_required=excluded.advisor_required,
                required_language=excluded.required_language,
                technical_requirements_json=excluded.technical_requirements_json,
                eligibility_rules_json=excluded.eligibility_rules_json,
                sartname_file=excluded.sartname_file,
                updated_at=excluded.updated_at
        """, (
            data.get("category_slug"),
            data.get("category_name", ""),
            data.get("target_level", "Genel"),
            data.get("min_team_size", 2),
            data.get("max_team_size", 6),
            data.get("advisor_required", "İsteğe Bağlı"),
            data.get("required_language", "tr"),
            json.dumps(data.get("technical_requirements", []), ensure_ascii=False),
            json.dumps(data.get("eligibility_rules", []), ensure_ascii=False),
            data.get("sartname_file", ""),
            now
        ))
        conn.commit()
        conn.close()
        return True

    def get_category_requirement(self, category_slug: str) -> Optional[Dict[str, Any]]:
        """Kategoriye ait şartname zorunluluklarını getirir."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM category_requirements WHERE category_slug = ?", (category_slug,)).fetchone()
        conn.close()
        if not row:
            return None
        res = dict(row)
        res["technical_requirements"] = json.loads(res.get("technical_requirements_json") or "[]")
        res["eligibility_rules"] = json.loads(res.get("eligibility_rules_json") or "[]")
        return res

    # =========================================================================
    # 2. RAPOR ŞABLONU ZORUNLULUKLARI METODLARI
    # =========================================================================
    def save_report_template_requirement(self, data: Dict[str, Any]) -> bool:
        """Rapor şablonundan çıkarılan biçim ve rubrik zorunluluklarını kaydeder."""
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        now = datetime.datetime.now().isoformat()
        t_id = f"{data.get('category_slug')}_{data.get('stage_code', 'OTR')}"
        cursor.execute("""
            INSERT INTO report_template_requirements (
                template_id, category_slug, stage_code, max_pages, page_penalty_rule,
                font_and_margins, required_sections_json, rubric_criteria_json,
                template_file, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(category_slug, stage_code) DO UPDATE SET
                max_pages=excluded.max_pages,
                page_penalty_rule=excluded.page_penalty_rule,
                font_and_margins=excluded.font_and_margins,
                required_sections_json=excluded.required_sections_json,
                rubric_criteria_json=excluded.rubric_criteria_json,
                template_file=excluded.template_file,
                updated_at=excluded.updated_at
        """, (
            t_id,
            data.get("category_slug"),
            data.get("stage_code", "OTR"),
            data.get("max_pages", 20),
            data.get("page_penalty_rule", "Sayfa aşımında puan kırılır"),
            data.get("font_and_margins", "Times New Roman / Arial 11pt"),
            json.dumps(data.get("required_sections", []), ensure_ascii=False),
            json.dumps(data.get("rubric_criteria", []), ensure_ascii=False),
            data.get("template_file", ""),
            now
        ))
        conn.commit()
        conn.close()
        return True

    def get_report_template_requirement(self, category_slug: str, stage_code: str = "OTR") -> Optional[Dict[str, Any]]:
        """Aşama rapor şablonu ve rubrik zorunluluklarını getirir."""
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = cursor.execute(
            "SELECT * FROM report_template_requirements WHERE category_slug = ? AND stage_code = ?",
            (category_slug, stage_code)
        ).fetchone()
        conn.close()
        if not row:
            return None
        res = dict(row)
        res["required_sections"] = json.loads(res.get("required_sections_json") or "[]")
        res["rubric_criteria"] = json.loads(res.get("rubric_criteria_json") or "[]")
        return res

    def get_rubric_by_category(self, category_name: str, stage: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Belirtilen kategori ve aşama için rubrik kriterlerini döner.
        Önce report_template_requirements tablosuna bakar (yöneticinin şablondan çıkardığı gerçek kriterler).
        Bulunamazsa competition_stages ve competition_rubrics tablolarına bakar.
        """
        norm_stage = self._norm_stage(stage or "GENEL")
        clean_slug = category_name.lower().replace(" ", "-").replace("_", "-")

        # 1. Rapor şablonu gereksinimleri (En güncel yönetici şablonu)
        tpl = self.get_report_template_requirement(clean_slug, norm_stage)
        if not tpl:
            tpl = self.get_report_template_requirement(category_name, norm_stage)
        if tpl and tpl.get("rubric_criteria"):
            crits = []
            for idx, c in enumerate(tpl["rubric_criteria"]):
                if isinstance(c, dict):
                    crits.append({
                        "id": c.get("id") or f"k_{idx+1}",
                        "name": c.get("name") or c.get("title") or f"Kriter {idx+1}",
                        "max_score": float(c.get("max_score") or c.get("weight") or 20.0),
                        "description": c.get("description", ""),
                        "guiding_questions": c.get("guiding_questions", [])
                    })
            if crits:
                return {
                    "category_name": category_name,
                    "stage": norm_stage,
                    "criteria": crits,
                    "required_sections": tpl.get("required_sections", [])
                }

        # 2. competition_stages tablosu
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        stage_row = cursor.execute(
            "SELECT * FROM competition_stages WHERE (competition_id = ? OR stage_name LIKE ? OR competition_id LIKE ?) AND stage_code = ?",
            (clean_slug, f"%{category_name}%", f"%{clean_slug}%", norm_stage)
        ).fetchone()
        if stage_row:
            d = dict(stage_row)
            conn.close()
            try:
                d["criteria"] = json.loads(d.get("criteria_json") or "[]")
            except Exception:
                d["criteria"] = []
            if d["criteria"]:
                return d
        else:
            conn.close()

        # 3. competition_rubrics tablosu
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        rub_row = cursor.execute(
            "SELECT * FROM competition_rubrics WHERE (category_name = ? OR category_name LIKE ? OR category_id = ?) AND (stage = ? OR stage = 'GENEL')",
            (category_name, f"%{category_name}%", clean_slug, norm_stage)
        ).fetchone()
        conn.close()
        if rub_row:
            return self._rubric_row_to_dict(rub_row)

        return None

    # =========================================================================
    # CLOUDFLARE D1 BULUT SORGULAMA VE CRUD METODLARI
    # =========================================================================

    def execute_d1(self, sql: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
        """Cloudflare D1 REST API üzerinden SQL sorgusu çalıştırır."""
        if not (self.account_id and self.database_id and self.api_token):
            return []
        
        # Soru işaretlerini uygun parametrelerle bağla
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        body = {"sql": sql}
        if params:
            body["params"] = params

        try:
            req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("success") and data.get("result"):
                    return data["result"][0].get("results", [])
        except Exception as e:
            # Lokal SQLite fallback
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                if params:
                    rows = cursor.execute(sql, params).fetchall()
                else:
                    rows = cursor.execute(sql).fetchall()
                conn.commit()
                res = [dict(r) for r in rows]
                conn.close()
                return res
            except Exception:
                pass
        return []

    # --- Yarışmalar (competitions) CRUD ---
    def list_all_competitions(self) -> List[Dict[str, Any]]:
        """Kayıtlı tüm yarışmaları listeler."""
        sql = "SELECT * FROM competitions ORDER BY name ASC;"
        res = self.execute_d1(sql)
        if not res:
            # Lokal kontrol
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute("SELECT * FROM competitions ORDER BY name ASC;").fetchall()
            res = [dict(r) for r in rows]
            conn.close()
        return res

    def get_competition_by_id(self, comp_id_or_slug: str) -> Optional[Dict[str, Any]]:
        """Yarışma ID veya slug ile yarışma detayını çeker."""
        sql = "SELECT * FROM competitions WHERE competition_id = ? OR slug = ? LIMIT 1;"
        res = self.execute_d1(sql, [comp_id_or_slug, comp_id_or_slug])
        if res:
            return res[0]
        # Lokal kontrol
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        row = cursor.execute("SELECT * FROM competitions WHERE competition_id = ? OR slug = ? LIMIT 1;", (comp_id_or_slug, comp_id_or_slug)).fetchone()
        conn.close()
        return dict(row) if row else None

    def upsert_competition(self, data: Dict[str, Any]) -> bool:
        """Yarışma ekler veya günceller (Admin Tam Yetki)."""
        now = datetime.datetime.now().isoformat()
        comp_id = data.get("competition_id") or f"comp_{uuid.uuid4().hex[:8]}"
        slug = data.get("slug") or re.sub(r'[^a-z0-9]+', '_', data.get("name", "").lower()).strip('_')
        
        sql = """
        INSERT INTO competitions (
            competition_id, name, slug, domain, levels, description, logo_url, sartname_url, schedule_json, awards_json, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(slug) DO UPDATE SET
            name=excluded.name,
            domain=excluded.domain,
            levels=excluded.levels,
            description=excluded.description,
            logo_url=COALESCE(excluded.logo_url, logo_url),
            sartname_url=COALESCE(excluded.sartname_url, sartname_url),
            schedule_json=excluded.schedule_json,
            awards_json=excluded.awards_json,
            updated_at=excluded.updated_at;
        """
        params = [
            comp_id,
            data.get("name", "").strip(),
            slug,
            data.get("domain", "Teknoloji").strip(),
            data.get("levels", "Lise, Üniversite"),
            data.get("description", ""),
            data.get("logo_url", ""),
            data.get("sartname_url", ""),
            json.dumps(data.get("schedule", {}), ensure_ascii=False) if isinstance(data.get("schedule"), dict) else data.get("schedule_json", "{}"),
            json.dumps(data.get("awards", []), ensure_ascii=False) if isinstance(data.get("awards"), list) else data.get("awards_json", "[]"),
            now,
            now
        ]
        
        # D1 ve Lokal Senkron Kayıt
        self.execute_d1(sql, params)
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            conn.close()
        except Exception:
            pass
        return True

    def delete_competition(self, comp_id_or_slug: str) -> bool:
        """Yarışmayı ve bağlı tüm aşamalarını siler (Admin Tam Yetki)."""
        sql_comp = "DELETE FROM competitions WHERE competition_id = ? OR slug = ?;"
        sql_stages = "DELETE FROM competition_stages WHERE competition_id = ?;"
        sql_reqs = "DELETE FROM competition_requirements WHERE competition_id = ?;"
        sql_rubs = "DELETE FROM competition_rubrics WHERE competition_id = ?;"

        for s in [sql_comp, sql_stages, sql_reqs, sql_rubs]:
            self.execute_d1(s, [comp_id_or_slug])
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(s, (comp_id_or_slug,))
                conn.commit()
                conn.close()
            except Exception:
                pass
        return True

    # --- Aşamalar (competition_stages) CRUD ---
    def list_competition_stages(self, comp_id_or_slug: str) -> List[Dict[str, Any]]:
        """Bir yarışmanın tüm aşamalarını (ÖTR, KTR vb.) listeler."""
        sql = "SELECT * FROM competition_stages WHERE competition_id = ? ORDER BY stage_code ASC;"
        res = self.execute_d1(sql, [comp_id_or_slug])
        if not res:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute(sql, (comp_id_or_slug,)).fetchall()
            res = [dict(r) for r in rows]
            conn.close()
        return res

    def upsert_competition_stage(self, data: Dict[str, Any]) -> bool:
        """Yarışma aşaması ekler veya günceller."""
        now = datetime.datetime.now().isoformat()
        stage_id = data.get("stage_id") or f"stg_{uuid.uuid4().hex[:8]}"
        sql = """
        INSERT INTO competition_stages (
            stage_id, competition_id, stage_code, stage_name, sablon_docx_url, sablon_pdf_url, max_pages, max_score, deadline, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(competition_id, stage_code) DO UPDATE SET
            stage_name=excluded.stage_name,
            sablon_docx_url=COALESCE(excluded.sablon_docx_url, sablon_docx_url),
            sablon_pdf_url=COALESCE(excluded.sablon_pdf_url, sablon_pdf_url),
            max_pages=excluded.max_pages,
            max_score=excluded.max_score,
            deadline=excluded.deadline;
        """
        params = [
            stage_id,
            data.get("competition_id", "").strip(),
            data.get("stage_code", "OTR").strip().upper(),
            data.get("stage_name", "Ön Tasarım Raporu").strip(),
            data.get("sablon_docx_url", ""),
            data.get("sablon_pdf_url", ""),
            data.get("max_pages", 25),
            data.get("max_score", 100.0),
            data.get("deadline", "2026-05-15"),
            now
        ]
        self.execute_d1(sql, params)
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            conn.close()
        except Exception:
            pass
        return True

    def delete_competition_stage(self, comp_id: str, stage_code: str) -> bool:
        """Aşamayı siler."""
        sql = "DELETE FROM competition_stages WHERE competition_id = ? AND stage_code = ?;"
        sql_rub = "DELETE FROM competition_rubrics WHERE competition_id = ? AND stage_code = ?;"
        for s in [sql, sql_rub]:
            self.execute_d1(s, [comp_id, stage_code])
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(s, (comp_id, stage_code))
                conn.commit()
                conn.close()
            except Exception:
                pass
        return True

    # --- Şartname Kuralları (competition_requirements) CRUD ---
    def list_competition_requirements(self, comp_id: str) -> List[Dict[str, Any]]:
        """Şartnameden çıkarılan ve onaylanan kuralları döner."""
        sql = "SELECT * FROM competition_requirements WHERE competition_id = ? ORDER BY rule_type ASC;"
        res = self.execute_d1(sql, [comp_id])
        if not res:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute(sql, (comp_id,)).fetchall()
            res = [dict(r) for r in rows]
            conn.close()
        return res

    def save_competition_requirements_bulk(self, comp_id: str, req_list: List[Dict[str, Any]]) -> bool:
        """Yarışma şartname kurallarını toplu kaydeder (önce eskileri temizler)."""
        del_sql = "DELETE FROM competition_requirements WHERE competition_id = ?;"
        self.execute_d1(del_sql, [comp_id])
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(del_sql, (comp_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass

        now = datetime.datetime.now().isoformat()
        ins_sql = """
        INSERT INTO competition_requirements (
            req_id, competition_id, rule_type, title, description, min_team_size, max_team_size, advisor_required, is_mandatory, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        for req in req_list:
            r_id = req.get("req_id") or f"req_{uuid.uuid4().hex[:8]}"
            params = [
                r_id,
                comp_id,
                req.get("rule_type", "genel"),
                req.get("title", "Kural"),
                req.get("description", ""),
                int(req.get("min_team_size", 1)),
                int(req.get("max_team_size", 6)),
                int(req.get("advisor_required", 0)),
                int(req.get("is_mandatory", 1)),
                now
            ]
            self.execute_d1(ins_sql, params)
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(ins_sql, params)
                conn.commit()
                conn.close()
            except Exception:
                pass
        return True

    # --- Puanlama Rubrikleri (competition_rubrics) CRUD ---
    def list_competition_rubrics(self, comp_id: str, stage_code: str) -> List[Dict[str, Any]]:
        """Aşama için admin onaylı puanlama rubriğini (0-100) getirir."""
        sql = "SELECT * FROM competition_rubrics WHERE competition_id = ? AND stage_code = ? ORDER BY order_index ASC;"
        res = self.execute_d1(sql, [comp_id, stage_code])
        if not res:
            conn = sqlite3.connect(DB_FILE)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            rows = cursor.execute(sql, (comp_id, stage_code)).fetchall()
            res = [dict(r) for r in rows]
            conn.close()
        return res

    def save_competition_rubrics_bulk(self, comp_id: str, stage_code: str, rub_list: List[Dict[str, Any]]) -> bool:
        """Aşama rubrik kriterlerini toplu kaydeder."""
        del_sql = "DELETE FROM competition_rubrics WHERE competition_id = ? AND stage_code = ?;"
        self.execute_d1(del_sql, [comp_id, stage_code])
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(del_sql, (comp_id, stage_code))
            conn.commit()
            conn.close()
        except Exception:
            pass

        now = datetime.datetime.now().isoformat()
        ins_sql = """
        INSERT INTO competition_rubrics (
            rubric_id, competition_id, stage_code, criterion_code, criterion_name, description, max_score, order_index, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        for idx, rub in enumerate(rub_list, 1):
            rub_id = rub.get("rubric_id") or f"rub_{uuid.uuid4().hex[:8]}"
            params = [
                rub_id,
                comp_id,
                stage_code.upper(),
                rub.get("criterion_code") or f"C{idx}",
                rub.get("criterion_name", f"{idx}. Kriter"),
                rub.get("description", ""),
                float(rub.get("max_score", 20.0)),
                int(rub.get("order_index", idx)),
                now
            ]
            self.execute_d1(ins_sql, params)
            try:
                conn = sqlite3.connect(DB_FILE)
                cursor = conn.cursor()
                cursor.execute(ins_sql, params)
                conn.commit()
                conn.close()
            except Exception:
                pass
        return True

    # --- Hakem & Rapor Yönlendirme (Routing) CRUD ---
    def assign_report_to_referee(self, report_id: str, referee_email: str) -> bool:
        """Raporu hakeme yönlendirir / atar."""
        as_id = f"asg_{uuid.uuid4().hex[:8]}"
        now = datetime.datetime.now().isoformat()
        sql = """
        INSERT INTO report_assignments (assignment_id, report_id, referee_email, status, assigned_at)
        VALUES (?, ?, ?, 'Atandı', ?);
        """
        up_sql = "UPDATE reports SET status = 'Hakeme Atandı' WHERE report_id = ?;"
        self.execute_d1(sql, [as_id, report_id, referee_email, now])
        self.execute_d1(up_sql, [report_id])
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(sql, (as_id, report_id, referee_email, now))
            cursor.execute(up_sql, (report_id,))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return True

    def list_assigned_reports_for_referee(self, referee_email: str) -> List[Dict[str, Any]]:
        """Hakemin yalnızca kendisine atanmış raporları listelemesini sağlar (İzolasyon)."""
        sql = """
        SELECT ra.assignment_id, ra.referee_email, ra.status as assignment_status, ra.score as ref_score,
               r.report_id, r.competition_id, r.stage_code, r.file_name, r.r2_url, r.page_count, r.created_at
        FROM report_assignments ra
        JOIN reports r ON ra.report_id = r.report_id
        WHERE ra.referee_email = ?
        ORDER BY ra.assigned_at DESC;
        """
        res = self.execute_d1(sql, [referee_email])
        if not res:
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute(sql, (referee_email,)).fetchall()
                res = [dict(r) for r in rows]
                conn.close()
            except Exception:
                pass
        return res


    # --- Başvurular (applications) CRUD ---
    def create_application(self, team_id: str, comp_id: str, level: str = "Lise") -> Dict[str, Any]:
        """Bir takımın bir yarışmaya yaptığı başvuruyu kaydeder."""
        app_id = f"APP-{abs(hash(team_id + comp_id)) % 90000 + 10000}"
        now = datetime.datetime.now().isoformat()
        sql = """
        INSERT INTO applications (app_id, team_id, competition_id, level, status, created_at)
        VALUES (?, ?, ?, ?, 'Aktif', ?)
        ON CONFLICT(app_id) DO UPDATE SET level=excluded.level;
        """
        self.execute_d1(sql, [app_id, team_id, comp_id, level, now])
        try:
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(sql, (app_id, team_id, comp_id, level, now))
            conn.commit()
            conn.close()
        except Exception:
            pass
        return {"app_id": app_id, "team_id": team_id, "competition_id": comp_id, "level": level, "status": "Aktif", "created_at": now}

    def list_applications_for_team(self, team_id: str) -> List[Dict[str, Any]]:
        """Takımın yaptığı tüm yarışma başvurularını listeler."""
        sql = """
        SELECT a.app_id, a.team_id, a.competition_id, a.level, a.status, a.created_at,
               c.name as competition_name, c.domain as competition_domain
        FROM applications a
        JOIN competitions c ON a.competition_id = c.slug OR a.competition_id = c.competition_id
        WHERE a.team_id = ?
        ORDER BY a.created_at DESC;
        """
        res = self.execute_d1(sql, [team_id])
        if not res:
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute(sql, (team_id,)).fetchall()
                res = [dict(r) for r in rows]
                conn.close()
            except Exception:
                pass
        return res

    def list_all_applications(self) -> List[Dict[str, Any]]:
        """Tüm başvuruları detaylarıyla listeler (Admin İzleme Paneli)."""
        sql = """
        SELECT a.app_id, a.team_id, a.competition_id, a.level, a.status, a.created_at,
               c.name as competition_name
        FROM applications a
        LEFT JOIN competitions c ON a.competition_id = c.slug OR a.competition_id = c.competition_id
        ORDER BY a.created_at DESC;
        """
        res = self.execute_d1(sql)
        if not res:
            try:
                conn = sqlite3.connect(DB_FILE)
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                rows = cursor.execute(sql).fetchall()
                res = [dict(r) for r in rows]
                conn.close()
            except Exception:
                pass
        return res


# Uygulama genelinde tek örnek
db = DatabaseManager()


