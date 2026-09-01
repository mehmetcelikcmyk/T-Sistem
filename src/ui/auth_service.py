"""T-Sistem Kullanıcı Kimlik Doğrulama ve Yönetim Servisi.

Doğrudan Cloudflare D1 Cloud Veritabanı ve Google OAuth 2.0 ile:
- Yönetici (Admin), Hakem ve Yarışmacı kimlik doğrulaması
- Güvenli SHA-256 Parola Hashleme
- Cloudflare D1 üzerinde bulut tabanlı kullanıcı tablosu
- Google OAuth Code Takası ve Canlı Profil Senkronizasyonu
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import tempfile
import time
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
try:
    from src.ui.firebase_config import FIREBASE_CONFIG
except ImportError:
    try:
        from firebase_config import FIREBASE_CONFIG
    except ImportError:
        FIREBASE_CONFIG = {}

_RESET_DIR = Path(tempfile.gettempdir()) / "tsistem_pw_resets"

load_dotenv()

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_FILE = os.getenv("TSISTEM_DB_PATH") or os.path.join(_PROJECT_ROOT, "data", "tsistem.db")


def _hash_password(password: str) -> str:
    """Şifreyi SHA-256 ile hashler."""
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.database_id = os.getenv("CLOUDFLARE_D1_DATABASE_ID")
        self.api_token = os.getenv("CLOUDFLARE_API_TOKEN")
        self.d1_url = f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/d1/database/{self.database_id}/query" if self.account_id and self.database_id else None
        self._init_db()

    def _query_d1(self, sql: str, params: list = None) -> Optional[List[Dict[str, Any]]]:
        """Cloudflare D1 veritabanında sorgu çalıştırır."""
        if not self.d1_url or not self.api_token:
            return None
        
        payload = json.dumps({"sql": sql, "params": params or []}).encode("utf-8")
        req = urllib.request.Request(
            self.d1_url,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_token}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode("utf-8"))
                if data.get("success") and data.get("result"):
                    return data["result"][0].get("results", [])
        except Exception as e:
            err_body = e.read().decode('utf-8') if hasattr(e, 'read') else ''
            print(f"[Cloudflare D1 Warning] {e} {err_body}")
        return None

    def _init_db(self) -> None:
        """Cloudflare D1 ve yerel yedek veritabanında kullanıcılar tablosunu oluşturur/günceller."""
        create_sql = """
        CREATE TABLE IF NOT EXISTS auth_users (
            user_id TEXT PRIMARY KEY,
            username TEXT DEFAULT '',
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT DEFAULT '',
            role TEXT NOT NULL DEFAULT 'yarismaci',
            institution TEXT DEFAULT '',
            department TEXT DEFAULT '',
            graduation_status TEXT DEFAULT 'Öğrenci',
            tc_citizen TEXT DEFAULT 'Evet',
            gender TEXT DEFAULT '',
            birth_date TEXT DEFAULT '',
            phone TEXT DEFAULT '',
            address TEXT DEFAULT '',
            education_level TEXT DEFAULT '',
            auth_provider TEXT DEFAULT 'local',
            profile_completed INTEGER DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'aktif',
            created_at TEXT NOT NULL
        );
        """
        # 1. Cloudflare D1 Cloud Veritabanını Başlat
        self._query_d1(create_sql)
        # D1 tablosu eski şemayla oluşturulmuşsa eksik kolonları ekle
        _d1_alter = [
            "ALTER TABLE auth_users ADD COLUMN tc_citizen TEXT DEFAULT 'Evet'",
            "ALTER TABLE auth_users ADD COLUMN gender TEXT DEFAULT ''",
            "ALTER TABLE auth_users ADD COLUMN birth_date TEXT DEFAULT ''",
            "ALTER TABLE auth_users ADD COLUMN phone TEXT DEFAULT ''",
            "ALTER TABLE auth_users ADD COLUMN address TEXT DEFAULT ''",
            "ALTER TABLE auth_users ADD COLUMN education_level TEXT DEFAULT ''",
            "ALTER TABLE auth_users ADD COLUMN username TEXT DEFAULT ''",
            "ALTER TABLE auth_users ADD COLUMN department TEXT DEFAULT ''",
            "ALTER TABLE auth_users ADD COLUMN graduation_status TEXT DEFAULT 'Öğrenci'",
            "ALTER TABLE auth_users ADD COLUMN auth_provider TEXT DEFAULT 'local'",
            "ALTER TABLE auth_users ADD COLUMN profile_completed INTEGER DEFAULT 1",
        ]
        for _stmt in _d1_alter:
            self._query_d1(_stmt)  # Kolon zaten varsa D1 hata döner, _query_d1 yakalar

        # 2. Yerel SQLite Başlat
        os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(create_sql)

        # Tablo daha önceden varsa eksik kolonları güvenle ekle
        mevcut_kolonlar = [col[1] for col in cursor.execute("PRAGMA table_info(auth_users)").fetchall()]
        eklenecekler = [
            ("username", "TEXT DEFAULT ''"),
            ("department", "TEXT DEFAULT ''"),
            ("graduation_status", "TEXT DEFAULT 'Öğrenci'"),
            ("tc_citizen", "TEXT DEFAULT 'Evet'"),
            ("gender", "TEXT DEFAULT ''"),
            ("birth_date", "TEXT DEFAULT ''"),
            ("phone", "TEXT DEFAULT ''"),
            ("address", "TEXT DEFAULT ''"),
            ("education_level", "TEXT DEFAULT ''"),
            ("auth_provider", "TEXT DEFAULT 'local'"),
            ("profile_completed", "INTEGER DEFAULT 1"),
        ]
        for col_name, col_type in eklenecekler:
            if col_name not in mevcut_kolonlar:
                cursor.execute(f"ALTER TABLE auth_users ADD COLUMN {col_name} {col_type}")

        # Cloudflare D1 & Yerel Admin Hesabı
        admin_email = "admin@tsistem.org"
        admin_pass = _hash_password("admin123")
        now = datetime.now().isoformat()
        
        cursor.execute("SELECT user_id FROM auth_users WHERE email = ?", (admin_email,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, phone, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("usr_admin_master", "admin", "Sistem Yöneticisi", admin_email, admin_pass, "admin", "TEKNOFEST İcra Kurulu", "Yönetim", "Mezun", "Evet", "+90 555 000 00 01", "cloudflare_d1", 1, "aktif", now))
            
            # Cloudflare D1'e de yaz
            self._query_d1("""
            INSERT OR REPLACE INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, phone, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ["usr_admin_master", "admin", "Sistem Yöneticisi", admin_email, admin_pass, "admin", "TEKNOFEST İcra Kurulu", "Yönetim", "Mezun", "Evet", "+90 555 000 00 01", "cloudflare_d1", 1, "aktif", now])

        # Hakem Hesabı
        hakem_email = "hakem@tsistem.org"
        cursor.execute("SELECT user_id FROM auth_users WHERE email = ?", (hakem_email,))
        if not cursor.fetchone():
            cursor.execute("""
            INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, phone, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ("usr_hakem_master", "hakem", "Prof. Dr. Ahmet Yılmaz", hakem_email, _hash_password("hakem123"), "hakem", "T3 Vakfı Değerlendirme Kurulu", "Havacılık ve Uzay Mühendisliği", "Mezun", "Evet", "+90 555 000 00 02", "cloudflare_d1", 1, "aktif", now))

            self._query_d1("""
            INSERT OR REPLACE INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, phone, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, ["usr_hakem_master", "hakem", "Prof. Dr. Ahmet Yılmaz", hakem_email, _hash_password("hakem123"), "hakem", "T3 Vakfı Değerlendirme Kurulu", "Havacılık ve Uzay Mühendisliği", "Mezun", "Evet", "+90 555 000 00 02", "cloudflare_d1", 1, "aktif", now])

        conn.commit()
        conn.close()

    def exchange_google_code(self, code: str, redirect_uri: str) -> Optional[Dict[str, str]]:
        """Google OAuth kodunu sunucuda takas eder ve doğrulanmış profili döner."""
        try:
            token_url = "https://oauth2.googleapis.com/token"
            data = urllib.parse.urlencode({
                "code": code,
                "client_id": FIREBASE_CONFIG.get("clientId"),
                "client_secret": FIREBASE_CONFIG.get("clientSecret"),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code"
            }).encode("utf-8")

            req = urllib.request.Request(token_url, data=data, method="POST")
            with urllib.request.urlopen(req, timeout=10) as resp:
                token_data = json.loads(resp.read().decode("utf-8"))

            id_token = token_data.get("id_token")
            if id_token:
                parts = id_token.split(".")
                if len(parts) >= 2:
                    padding = "=" * (4 - (len(parts[1]) % 4))
                    decoded = base64.urlsafe_b64decode(parts[1] + padding).decode("utf-8")
                    payload = json.loads(decoded)
                    return {
                        "email": payload.get("email", ""),
                        "name": payload.get("name", payload.get("email", "").split("@")[0]),
                        "sub": payload.get("sub", "")
                    }
        except Exception as e:
            print(f"[Google OAuth Exchange Error] {e}")
        return None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """E-posta adresine göre kullanıcıyı Cloudflare D1 veya yerel veritabanından döner."""
        clean_email = email.strip().lower()

        # Önce Cloudflare D1 Bulut Veritabanından Sor
        d1_res = self._query_d1("SELECT * FROM auth_users WHERE LOWER(email) = LOWER(?) LIMIT 1", [clean_email])
        if d1_res and len(d1_res) > 0:
            return d1_res[0]

        # Yerel Yedekten Sor
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT user_id, username, name, email, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, auth_provider, profile_completed, status, created_at
        FROM auth_users WHERE LOWER(email) = LOWER(?)
        """, (clean_email,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "user_id": row[0],
                "username": row[1],
                "name": row[2],
                "email": row[3],
                "role": row[4],
                "institution": row[5],
                "department": row[6],
                "graduation_status": row[7],
                "tc_citizen": row[8],
                "gender": row[9],
                "birth_date": row[10],
                "phone": row[11],
                "address": row[12],
                "education_level": row[13],
                "auth_provider": row[14],
                "profile_completed": bool(row[15]),
                "status": row[16],
                "created_at": row[17],
            }
        return None

    def authenticate(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Cloudflare D1 ve yerel hash kontrolü ile kimlik doğrular."""
        clean_email = email.strip().lower()
        pwd_hash = _hash_password(password)

        # 1. Cloudflare D1 Bulut Kontrolü
        d1_res = self._query_d1(
            "SELECT * FROM auth_users WHERE (LOWER(email) = LOWER(?) OR LOWER(username) = LOWER(?)) AND password_hash = ? AND status = 'aktif' LIMIT 1",
            [clean_email, clean_email, pwd_hash]
        )
        if d1_res and len(d1_res) > 0:
            user = d1_res[0]
            user["profile_completed"] = bool(user.get("profile_completed", 1))
            return user

        # 2. Yerel Kontrol
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("""
        SELECT user_id, username, name, email, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, auth_provider, profile_completed, status, created_at
        FROM auth_users
        WHERE (LOWER(email) = LOWER(?) OR LOWER(username) = LOWER(?))
          AND password_hash = ?
          AND status = 'aktif'
        """, (clean_email, clean_email, pwd_hash))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "user_id": row[0],
                "username": row[1],
                "name": row[2],
                "email": row[3],
                "role": row[4],
                "institution": row[5],
                "department": row[6],
                "graduation_status": row[7],
                "tc_citizen": row[8],
                "gender": row[9],
                "birth_date": row[10],
                "phone": row[11],
                "address": row[12],
                "education_level": row[13],
                "auth_provider": row[14],
                "profile_completed": bool(row[15]),
                "status": row[16],
                "created_at": row[17],
            }
        return None

    def check_mandatory_fields_complete(self, user: Dict[str, Any]) -> tuple[bool, List[str]]:
        """T3 KYS için zorunlu alanların dolu olup olmadığını denetler. Admin ve Hakem hesapları için tam kabul edilir."""
        if not user:
            return (False, ["Kullanıcı bulunamadı"])

        # Admin ve Hakem hesapları için eksik bilgi ekranı açılmaz, doğrudan tam kabul edilir
        user_role = str(user.get("role", "")).lower()
        user_email = str(user.get("email", "")).lower()
        if user_role in ("admin", "hakem") or user_email in ("admin@tsistem.org", "hakem@tsistem.org"):
            return (True, [])

        eksikler = []
        if not user.get("username"):
            eksikler.append("Kullanıcı Adı")
        if not user.get("phone"):
            eksikler.append("Cep Telefonu")
        if not user.get("gender") or user.get("gender") == "Seçiniz":
            eksikler.append("Cinsiyet")
        if not user.get("birth_date"):
            eksikler.append("Doğum Tarihi")
        if not user.get("address"):
            eksikler.append("Adres")
        if not user.get("education_level") or user.get("education_level") == "Seçiniz":
            eksikler.append("Eğitim Seviyesi")

        return (len(eksikler) == 0, eksikler)

    def handle_google_auth(self, google_profile: Dict[str, str]) -> tuple[Dict[str, Any], bool, list]:
        """Google ile giriş yapıldığında kullanıcıyı kontrol eder."""
        email = google_profile.get("email", "").strip().lower()
        name = google_profile.get("name", "").strip() or "Google Kullanıcısı"

        with open("debug_auth.log", "a", encoding="utf-8") as f:
            f.write(f"\n--- HANDLE GOOGLE AUTH START ---\n")
            f.write(f"Email: {email}\n")
        user = self.get_user_by_email(email)

        if not user:
            with open("debug_auth.log", "a", encoding="utf-8") as f:
                f.write(f"User NOT found in DB. Returning placeholder with is_new=True.\n")
            placeholder = {
                "user_id": None,
                "email": email,
                "name": name,
                "username": email.split("@")[0],
                "auth_provider": "google",
                "is_new": True,
            }
            return (placeholder, False, ["Profil bilgileri eksik"])

        with open("debug_auth.log", "a", encoding="utf-8") as f:
            f.write(f"User FOUND in DB. user_id: {user.get('user_id')}\n")
        is_complete, missing_fields = self.check_mandatory_fields_complete(user)
        return (user, is_complete, missing_fields)

    def create_google_user(self, email: str, name: str, profile_data: Dict[str, Any]) -> tuple[bool, str]:
        """Google ile giriş yapan YENİ kullanıcıyı profil tamamlanmış olarak kaydeder."""
        with open("debug_auth.log", "a", encoding="utf-8") as f:
            f.write(f"\\n--- CREATE GOOGLE USER START ---\\n")
            f.write(f"Email: {email}, Name: {name}\\n")
        try:
            user_id = f"usr_google_{uuid.uuid4().hex[:8]}"
            now = datetime.now().isoformat()
            username = profile_data.get("username", email.split("@")[0])

            password = profile_data.get("password")
            pwd_hash = _hash_password(password) if password else "GOOGLE_OAUTH_TOKEN"

            params = [
                user_id, username, name, email.strip().lower(),
                pwd_hash, "yarismaci",
                profile_data.get("institution", ""),
                profile_data.get("department", ""),
                profile_data.get("graduation_status", profile_data.get("graduation_status", "Öğrenci")),
                profile_data.get("tc_citizen", profile_data.get("tc_citizen", "Evet")),
                profile_data.get("gender", ""),
                profile_data.get("birth_date", ""),
                profile_data.get("phone", ""),
                profile_data.get("address", ""),
                profile_data.get("education_level", ""),
                "google", 1, "aktif", now
            ]
            sql = """
            INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            
            with open("debug_auth.log", "a", encoding="utf-8") as f:
                f.write(f"Executing D1 query...\\n")
            d1_ok = self._query_d1(sql, params)
            with open("debug_auth.log", "a", encoding="utf-8") as f:
                f.write(f"D1 result: {d1_ok}\\n")

            with open("debug_auth.log", "a", encoding="utf-8") as f:
                f.write(f"Connecting to SQLite: {DB_FILE}\\n")
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            conn.commit()
            conn.close()
            with open("debug_auth.log", "a", encoding="utf-8") as f:
                f.write(f"SQLite commit successful.\\n")
            return True, "Kullanıcı başarıyla kaydedildi."
        except Exception as e:
            with open("debug_auth.log", "a", encoding="utf-8") as f:
                f.write(f"EXCEPTION in create_google_user: {str(e)}\\n")
            return False, f"Kayıt hatası: {str(e)}"

    def complete_user_profile(self, user_id: str, profile_data: Dict[str, Any]) -> tuple[bool, str]:
        """Eksik profil bilgilerini Cloudflare D1 ve yerel veritabanında günceller."""
        try:
            # 1. Cloudflare D1 Güncellemesi
            self._query_d1("""
            UPDATE auth_users SET
                username = ?,
                name = ?,
                tc_citizen = ?,
                gender = ?,
                birth_date = ?,
                phone = ?,
                address = ?,
                education_level = ?,
                institution = ?,
                department = ?,
                graduation_status = ?,
                profile_completed = 1
            WHERE user_id = ?
            """, [
                profile_data.get("username", ""),
                profile_data.get("name", ""),
                profile_data.get("tc_citizen", "Evet"),
                profile_data.get("gender", ""),
                profile_data.get("birth_date", ""),
                profile_data.get("phone", ""),
                profile_data.get("address", ""),
                profile_data.get("education_level", ""),
                profile_data.get("institution", ""),
                profile_data.get("department", ""),
                profile_data.get("graduation_status", "Öğrenci"),
                user_id
            ])

            # 2. Yerel Güncelleme
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
            UPDATE auth_users SET
                username = ?,
                name = ?,
                tc_citizen = ?,
                gender = ?,
                birth_date = ?,
                phone = ?,
                address = ?,
                education_level = ?,
                institution = ?,
                department = ?,
                graduation_status = ?,
                profile_completed = 1
            WHERE user_id = ?
            """, (
                profile_data.get("username", ""),
                profile_data.get("name", ""),
                profile_data.get("tc_citizen", "Evet"),
                profile_data.get("gender", ""),
                profile_data.get("birth_date", ""),
                profile_data.get("phone", ""),
                profile_data.get("address", ""),
                profile_data.get("education_level", ""),
                profile_data.get("institution", ""),
                profile_data.get("department", ""),
                profile_data.get("graduation_status", "Öğrenci"),
                user_id
            ))
            
            if cursor.rowcount == 0:
                conn.close()
                return False, "Kullanıcı bulunamadı. Lütfen giriş sayfasına dönüp tekrar deneyin."
                
            conn.commit()
            conn.close()
            return True, "Profil bilgileriniz başarıyla güncellendi!"
        except Exception as e:
            return False, f"Profil güncelleme hatası: {str(e)}"

    def register_user(
        self,
        name: str,
        email: str,
        password: str,
        username: str = "",
        role: str = "yarismaci",
        institution: str = "",
        department: str = "",
        graduation_status: str = "Öğrenci",
        tc_citizen: str = "Evet",
        gender: str = "",
        birth_date: str = "",
        phone: str = "",
        address: str = "",
        education_level: str = "",
    ) -> tuple[bool, str]:
        """T3 KYS üzerinden Cloudflare D1 bulut veritabanına yeni kullanıcı kaydı oluşturur."""
        clean_email = email.strip().lower()
        if not clean_email or not password:
            return False, "E-posta ve parola zorunludur."

        if self.get_user_by_email(clean_email):
            return False, "Bu e-posta adresi ile kayıtlı bir kullanıcı zaten mevcut."

        user_id = f"usr_{uuid.uuid4().hex[:8]}"
        pwd_hash = _hash_password(password)
        now = datetime.now().isoformat()
        u_name = username or clean_email.split("@")[0]

        # 1. Cloudflare D1'e Kaydet
        d1_sonuc = self._query_d1("""
        INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, auth_provider, profile_completed, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [user_id, u_name, name, clean_email, pwd_hash, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, "email", 1, "aktif", now])
        print(f"[Register] D1 INSERT -> {'OK' if d1_sonuc is not None else 'FAIL (yerel SQLite yedek kullanilacak)'} | email={clean_email}")

        # 2. Yerel SQLite'a Kaydet
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        try:
            cursor.execute("""
            INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, u_name, name, clean_email, pwd_hash, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, "local", 1, "aktif", now))
            conn.commit()
            conn.close()
            return True, "Kullanıcı başarıyla kaydedildi."
        except Exception as e:
            conn.close()
            return False, f"Veritabanı kayıt hatası: {str(e)}"

    def get_all_users(self) -> List[Dict[str, Any]]:
        """Tüm kullanıcıları anında yerel SQLite ve Cloudflare D1'den listeler."""
        _SQL = "SELECT user_id, username, name, email, role, institution, department, graduation_status, phone, auth_provider, status, created_at FROM auth_users ORDER BY created_at DESC"

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute(_SQL)
        rows = cursor.fetchall()
        conn.close()

        local_list = [
            {
                "user_id": r[0],
                "username": r[1],
                "name": r[2],
                "email": r[3],
                "role": r[4],
                "institution": r[5],
                "department": r[6],
                "graduation_status": r[7],
                "phone": r[8],
                "auth_provider": r[9],
                "status": r[10],
                "created_at": r[11],
            }
            for r in rows
        ]

        # Cloudflare D1'den ek kayıt varsa arka planda/kısa sürede çekip birleştir
        try:
            d1_res = self._query_d1(_SQL) or []
            if d1_res:
                local_ids = {u["user_id"] for u in local_list}
                for u in d1_res:
                    if u.get("user_id") not in local_ids:
                        local_list.append(u)
        except Exception:
            pass

        return local_list


    def delete_user(self, user_id: str) -> bool:
        """Kullanıcıyı Cloudflare D1 ve yerel veritabanından tamamen siler."""
        return self.delete_user_by_id(user_id)

    def delete_user_by_id(self, user_id: str) -> bool:
        """Kullanıcıyı Cloudflare D1 ve yerel veritabanından tamamen siler."""
        if not user_id:
            return False
        try:
            # 1. Cloudflare D1'den Kaskat Sil (Bağımlılıkları kaldır)
            self._query_d1("DELETE FROM team_members WHERE user_id = ?", [user_id])
            self._query_d1("DELETE FROM report_assignments WHERE referee_user_id = ?", [user_id])
            self._query_d1("DELETE FROM notifications WHERE user_id = ?", [user_id])
            self._query_d1("DELETE FROM applications WHERE team_id IN (SELECT team_id FROM teams WHERE captain_user_id = ?)", [user_id])
            self._query_d1("DELETE FROM teams WHERE captain_user_id = ?", [user_id])
            self._query_d1("DELETE FROM auth_users WHERE user_id = ?", [user_id])

            # 2. Yerel SQLite'tan Kaskat Sil
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM team_members WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM report_assignments WHERE referee_user_id = ?", (user_id,))
            cursor.execute("DELETE FROM notifications WHERE user_id = ?", (user_id,))
            cursor.execute("DELETE FROM applications WHERE team_id IN (SELECT team_id FROM teams WHERE captain_user_id = ?)", (user_id,))
            cursor.execute("DELETE FROM teams WHERE captain_user_id = ?", (user_id,))
            cursor.execute("DELETE FROM auth_users WHERE user_id = ?", (user_id,))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[Delete User Error] {e}")
            return False

    def update_user_role(self, user_id: str, new_role: str) -> bool:
        """Kullanıcının sistem rolünü Cloudflare D1 ve yerelde günceller."""
        try:
            self._query_d1("UPDATE auth_users SET role = ? WHERE user_id = ?", [new_role, user_id])
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE auth_users SET role = ? WHERE user_id = ?", (new_role, user_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[Update Role Error] {e}")
            return False

    def update_user_status(self, user_id: str, new_status: str) -> bool:
        """Kullanıcının hesap durumunu (aktif/pasif) Cloudflare D1 ve yerelde günceller."""
        try:
            self._query_d1("UPDATE auth_users SET status = ? WHERE user_id = ?", [new_status, user_id])
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("UPDATE auth_users SET status = ? WHERE user_id = ?", (new_status, user_id))
            conn.commit()
            conn.close()
            return True
        except Exception as e:
            print(f"[Update Status Error] {e}")
            return False

    def update_user_by_admin(
        self,
        user_id: str,
        name: str,
        email: str,
        role: str,
        status: str = "aktif",
        institution: str = "",
        new_password: Optional[str] = None
    ) -> tuple[bool, str]:
        """Admin panelinden kullanıcı bilgilerini (ad, e-posta, rol, durum, kurum, parola) veritabanında günceller."""
        if not user_id:
            return False, "Kullanıcı ID geçersiz."

        clean_name = name.strip()
        clean_email = email.strip().lower()
        if not clean_name or not clean_email:
            return False, "Ad Soyad ve E-Posta alanları boş bırakılamaz."

        try:
            pwd_hash = _hash_password(new_password) if new_password and new_password.strip() else None

            # 1. Cloudflare D1 Güncelleme
            if pwd_hash:
                self._query_d1(
                    "UPDATE auth_users SET name = ?, email = ?, role = ?, status = ?, institution = ?, password_hash = ? WHERE user_id = ?",
                    [clean_name, clean_email, role, status, institution, pwd_hash, user_id]
                )
            else:
                self._query_d1(
                    "UPDATE auth_users SET name = ?, email = ?, role = ?, status = ?, institution = ? WHERE user_id = ?",
                    [clean_name, clean_email, role, status, institution, user_id]
                )

            # 2. Yerel SQLite Güncelleme
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            if pwd_hash:
                cursor.execute(
                    "UPDATE auth_users SET name = ?, email = ?, role = ?, status = ?, institution = ?, password_hash = ? WHERE user_id = ?",
                    (clean_name, clean_email, role, status, institution, pwd_hash, user_id)
                )
            else:
                cursor.execute(
                    "UPDATE auth_users SET name = ?, email = ?, role = ?, status = ?, institution = ? WHERE user_id = ?",
                    (clean_name, clean_email, role, status, institution, user_id)
                )
            conn.commit()
            conn.close()
            return True, f"'{clean_name}' kullanıcısının bilgileri veritabanında başarıyla güncellendi."
        except Exception as e:
            return False, f"Veritabanı güncelleme hatası: {str(e)}"

    def reset_password(self, email: str, new_password: str) -> tuple[bool, str]:
        """Kullanıcının şifresini e-posta adresine göre sıfırlar ve günceller."""
        clean_email = email.strip().lower()
        if not clean_email or not new_password:
            return False, "E-posta ve yeni şifre alanları zorunludur."
        if len(new_password) < 6:
            return False, "Yeni şifre en az 6 karakter uzunluğunda olmalıdır."

        user = self.get_user_by_email(clean_email)
        if not user:
            return False, f"'{clean_email}' adresine kayıtlı bir kullanıcı bulunamadı."

        try:
            pwd_hash = _hash_password(new_password)
            # 1. Cloudflare D1
            self._query_d1(
                "UPDATE auth_users SET password_hash = ? WHERE email = ?",
                [pwd_hash, clean_email]
            )
            # 2. Yerel SQLite
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE auth_users SET password_hash = ? WHERE email = ?",
                (pwd_hash, clean_email)
            )
            conn.commit()
            conn.close()
            return True, "Şifreniz başarıyla güncellendi! Yeni şifrenizle giriş yapabilirsiniz."
        except Exception as e:
            return False, f"Şifre sıfırlama hatası: {str(e)}"

    def cleanup_incomplete_users(self) -> None:
        """30 dakikadan uzun süredir profil tamamlamamış geçici kayıtları temizler.
        Yeni oluşturulmuş (aktif form doldurma aşamasındaki) kayıtlara dokunmaz.
        """
        try:
            cutoff = (datetime.now() - timedelta(minutes=30)).isoformat()
            self._query_d1(
                "DELETE FROM auth_users WHERE profile_completed = 0 AND role = 'yarismaci' AND created_at < ?",
                [cutoff]
            )
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM auth_users WHERE profile_completed = 0 AND role = 'yarismaci' AND created_at < ?",
                (cutoff,)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Cleanup Error] {e}")

    def get_active_session(self) -> dict | None:
        """Kullanıcının aktif oturumunu diskten geri yükler."""
        try:
            p = os.path.join(_PROJECT_ROOT, "data", ".active_session.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    email = data.get("email", "")
                    if email:
                        user = self.get_user_by_email(email)
                        return user
        except Exception:
            pass
        return None

    def set_active_session(self, user: dict) -> None:
        """Kullanıcı giriş yaptığında oturumu diske kaydeder."""
        try:
            p = os.path.join(_PROJECT_ROOT, "data", ".active_session.json")
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"email": str(user.get("email", "")).strip().lower(), "user_id": str(user.get("user_id", "")), "role": str(user.get("role", ""))}, f)
        except Exception:
            pass

    def clear_active_session(self) -> None:
        """Kullanıcı çıkış yaptığında oturum dosyasını siler."""
        try:
            p = os.path.join(_PROJECT_ROOT, "data", ".active_session.json")
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

    def get_remembered_email(self) -> str:
        """Beni Hatırla ile kaydedilmiş e-posta adresini döner."""
        try:
            p = os.path.join(_PROJECT_ROOT, "data", ".remembered_user.json")
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("email", "")
        except Exception:
            pass
        return ""

    def save_remembered_email(self, email: str, remember: bool) -> None:
        """Beni Hatırla seçeneğine göre e-posta adresini kaydeder veya siler."""
        try:
            p = os.path.join(_PROJECT_ROOT, "data", ".remembered_user.json")
            if remember and email:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump({"email": email.strip().lower()}, f)
            else:
                if os.path.exists(p):
                    os.remove(p)
        except Exception:
            pass

    def is_smtp_configured(self) -> bool:
        """SMTP e-posta gönderiminin yapılandırılıp yapılandırılmadığını döner."""
        host = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER")
        user = os.getenv("SMTP_USER") or os.getenv("SMTP_EMAIL")
        pw = os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")
        return bool(host and user and pw)

    def send_password_reset_email(self, email: str, code: str) -> tuple[bool, str]:
        """Kullanıcının e-posta adresine gerçek SMTP sunucusu veya bildirim ile 6 haneli kod iletir."""
        smtp_host = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER") or os.getenv("SMTP_EMAIL")
        smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")

        if smtp_host and smtp_user and smtp_pass:
            try:
                import smtplib
                from email.mime.text import MIMEText
                from email.mime.multipart import MIMEMultipart

                msg = MIMEMultipart("alternative")
                msg["Subject"] = "T-Sistem · Şifre Sıfırlama Güvenlik Kodu"
                msg["From"] = f"T-Sistem Güvenlik <{smtp_user}>"
                msg["To"] = email

                html_content = f"""
                <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 20px; border: 1px solid #E2E8F0; border-radius: 12px; background: #ffffff;">
                    <div style="text-align: center; margin-bottom: 20px;">
                        <h2 style="color: #F04823; margin: 0;">T-Sistem</h2>
                        <p style="color: #64748B; font-size: 14px; margin-top: 4px;">Şifre Sıfırlama Talebi</p>
                    </div>
                    <p style="color: #1E293B; font-size: 15px;">Merhaba,</p>
                    <p style="color: #334155; font-size: 14px; line-height: 1.5;">T-Sistem hesabınız için şifre sıfırlama talebinde bulunuldu. Şifrenizi yenilemek için aşağıdaki 6 haneli güvenlik kodunu kullanabilirsiniz:</p>
                    <div style="text-align: center; margin: 26px 0;">
                        <span style="font-size: 32px; font-weight: 800; letter-spacing: 8px; color: #F04823; background: #FEEDE8; padding: 12px 28px; border-radius: 10px; border: 1.5px solid #FDBA74; display: inline-block;">
                            {code}
                        </span>
                    </div>
                    <p style="color: #64748B; font-size: 13px; line-height: 1.4;">Bu kod 10 dakika boyunca geçerlidir. Bu talep sizin tarafınızdan yapılmadıysa lütfen bu e-postayı dikkate almayınız.</p>
                </div>
                """
                msg.attach(MIMEText(html_content, "html"))

                clean_pass = str(smtp_pass).replace(" ", "").strip()
                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(smtp_user, clean_pass)
                    server.sendmail(smtp_user, [email], msg.as_string())

                return True, "E-posta başarıyla SMTP sunucusu üzerinden gönderildi."
            except Exception as e:
                return False, f"SMTP Gönderim Hatası: {str(e)}"
        
        return True, "SMTP yapılandırılmadı."

    def create_password_reset_code(self, email: str) -> str:
        """Kullanıcı için 6 haneli güvenli sıfırlama kodu üretir ve 10 dk geçerli olmak üzere saklar."""
        clean_email = email.strip().lower()
        code = f"{secrets.randbelow(900000) + 100000}"
        _RESET_DIR.mkdir(parents=True, exist_ok=True)
        
        email_hash = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:20]
        code_file = _RESET_DIR / f"{email_hash}.json"
        code_file.write_text(json.dumps({
            "email": clean_email,
            "code": code,
            "ts": time.time()
        }))
        return code

    def verify_password_reset_code(self, email: str, code: str) -> bool:
        """Kullanıcının girdiği kodun doğruluğunu ve süresini (10 dk) kontrol eder."""
        clean_email = email.strip().lower()
        clean_code = str(code).strip()
        email_hash = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:20]
        code_file = _RESET_DIR / f"{email_hash}.json"
        
        if not code_file.exists():
            return False
        try:
            data = json.loads(code_file.read_text())
            if time.time() - data.get("ts", 0) > 600:  # 10 dakikadan eski
                code_file.unlink(missing_ok=True)
                return False
            if hmac.compare_digest(str(data.get("code", "")), clean_code):
                return True
        except Exception:
            pass
        return False

    def clear_password_reset_code(self, email: str) -> None:
        """Kullanılan veya süresi dolan kodu temizler."""
        clean_email = email.strip().lower()
        email_hash = hashlib.sha256(clean_email.encode("utf-8")).hexdigest()[:20]
        code_file = _RESET_DIR / f"{email_hash}.json"
        code_file.unlink(missing_ok=True)

    # ─────────────────────────────────────────────────────────────────────────
    # ORTAK SMTP YARDIMCISI
    # ─────────────────────────────────────────────────────────────────────────
    def _send_smtp(self, to_email: str, subject: str, html_body: str) -> tuple[bool, str]:
        """Verilen alıcıya SMTP ile HTML e-posta gönderir."""
        smtp_host = os.getenv("SMTP_HOST") or os.getenv("SMTP_SERVER")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER") or os.getenv("SMTP_EMAIL")
        smtp_pass = os.getenv("SMTP_PASSWORD") or os.getenv("SMTP_PASS")

        if not (smtp_host and smtp_user and smtp_pass):
            return False, "SMTP yapılandırılmadı."

        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"T-Sistem <{smtp_user}>"
            msg["To"] = to_email
            msg.attach(MIMEText(html_body, "html"))

            clean_pass = str(smtp_pass).replace(" ", "").strip()
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, clean_pass)
                server.sendmail(smtp_user, [to_email], msg.as_string())

            return True, "E-posta başarıyla gönderildi."
        except Exception as e:
            return False, f"SMTP Gönderim Hatası: {e}"

    # ─────────────────────────────────────────────────────────────────────────
    # DANIŞMAN BİLDİRİM E-POSTASI
    # ─────────────────────────────────────────────────────────────────────────
    def send_team_advisor_email(
        self, advisor_email: str, advisor_name: str,
        team_name: str, team_code: str, captain_name: str
    ) -> tuple[bool, str]:
        """Takım oluşturulduğunda danışmana bildirim e-postası gönderir."""
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;
                    padding:24px;border:1px solid #E2E8F0;border-radius:12px;background:#fff;">
          <div style="text-align:center;margin-bottom:20px;">
            <h2 style="color:#F04823;margin:0;">T-Sistem</h2>
            <p style="color:#64748B;font-size:13px;margin-top:4px;">TEKNOFEST Değerlendirme Platformu</p>
          </div>
          <p style="color:#1E293B;font-size:15px;">Sayın {advisor_name},</p>
          <p style="color:#334155;font-size:14px;line-height:1.6;">
            <strong>{captain_name}</strong> tarafından oluşturulan
            <strong>"{team_name}"</strong> takımında danışman olarak gösterildiniz.
          </p>
          <div style="background:#F8FAFC;border:1px solid #E2E8F0;border-radius:8px;
                      padding:16px;margin:20px 0;text-align:center;">
            <div style="font-size:12px;color:#64748B;font-weight:600;margin-bottom:6px;">TAKIM DAVET KODU</div>
            <div style="font-size:28px;font-weight:900;letter-spacing:6px;color:#F04823;">
              {team_code}
            </div>
          </div>
          <p style="color:#64748B;font-size:13px;">
            T-Sistem platformuna giriş yaparak bu kodu kullanabilir veya takım üyelerini
            bilgilendirebilirsiniz.
          </p>
          <p style="color:#64748B;font-size:12px;margin-top:24px;">
            Bu e-posta otomatik olarak gönderilmiştir. Herhangi bir sorunuz için
            sistem yöneticisiyle iletişime geçiniz.
          </p>
        </div>
        """
        return self._send_smtp(
            advisor_email,
            f"T-Sistem · {team_name} Takımı Danışman Bildirimi",
            html,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # TAKIM ÜYE DAVET TOKEN'I
    # ─────────────────────────────────────────────────────────────────────────
    _INVITE_DIR = Path(tempfile.gettempdir()) / "tsistem_team_invites"

    def create_team_invite_token(
        self, team_id: str, team_name: str, invited_email: str, invited_by_name: str
    ) -> str:
        """48 saat geçerli benzersiz davet token'ı üretir ve disk üzerine saklar."""
        token = secrets.token_urlsafe(32)
        self._INVITE_DIR.mkdir(parents=True, exist_ok=True)
        (self._INVITE_DIR / f"{token}.json").write_text(json.dumps({
            "token": token,
            "team_id": team_id,
            "team_name": team_name,
            "invited_email": invited_email.strip().lower(),
            "invited_by_name": invited_by_name,
            "ts": time.time(),
        }))
        return token

    def get_team_invite(self, token: str) -> dict | None:
        """Token geçerliyse ve süresi dolmamışsa davet bilgisini döner."""
        f = self._INVITE_DIR / f"{token}.json"
        if not f.exists():
            return None
        try:
            data = json.loads(f.read_text())
            if time.time() - data.get("ts", 0) > 172800:  # 48 saat
                f.unlink(missing_ok=True)
                return None
            return data
        except Exception:
            return None

    def clear_team_invite(self, token: str) -> None:
        """Kullanılmış veya süresi dolmuş daveti temizler."""
        (self._INVITE_DIR / f"{token}.json").unlink(missing_ok=True)

    def list_team_invites(self, team_id: str) -> list[dict]:
        """Verilen takım ID'sine ait, süresi dolmamış bekleyen davetleri listeler."""
        invites: list[dict] = []
        if not self._INVITE_DIR.exists():
            return invites
        for f in self._INVITE_DIR.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                if data.get("team_id") != team_id:
                    continue
                if time.time() - data.get("ts", 0) > 172800:  # 48 saat
                    f.unlink(missing_ok=True)
                    continue
                invites.append(data)
            except Exception:
                continue
        invites.sort(key=lambda d: d.get("ts", 0), reverse=True)
        return invites

    def send_team_invite_email(
        self, to_email: str, team_name: str, invited_by: str,
        token: str, base_url: str = "http://localhost:8501"
    ) -> tuple[bool, str]:
        """Davet edilen kişiye kabul bağlantısı içeren e-posta gönderir."""
        accept_url = f"{base_url}?accept_team_invite={token}"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;
                    padding:24px;border:1px solid #E2E8F0;border-radius:12px;background:#fff;">
          <div style="text-align:center;margin-bottom:20px;">
            <h2 style="color:#F04823;margin:0;">T-Sistem</h2>
            <p style="color:#64748B;font-size:13px;margin-top:4px;">TEKNOFEST Değerlendirme Platformu</p>
          </div>
          <p style="color:#1E293B;font-size:15px;">Merhaba,</p>
          <p style="color:#334155;font-size:14px;line-height:1.6;">
            <strong>{invited_by}</strong>, sizi <strong>"{team_name}"</strong>
            TEKNOFEST yarışma takımına üye olmaya davet etti.
          </p>
          <div style="text-align:center;margin:28px 0;">
            <a href="{accept_url}"
               style="background:linear-gradient(135deg,#F97316,#EA580C);color:#fff;
                      font-weight:800;font-size:15px;padding:14px 32px;border-radius:10px;
                      text-decoration:none;display:inline-block;
                      box-shadow:0 4px 14px rgba(249,115,22,0.45);">
              Daveti Kabul Et ve Takıma Katıl
            </a>
          </div>
          <p style="color:#64748B;font-size:13px;line-height:1.5;">
            Butona tıklayamıyorsanız aşağıdaki bağlantıyı tarayıcınıza yapıştırın:<br/>
            <a href="{accept_url}" style="color:#3B82F6;word-break:break-all;">{accept_url}</a>
          </p>
          <p style="color:#94A3B8;font-size:12px;margin-top:24px;">
            Bu davet 48 saat geçerlidir. T-Sistem hesabınıza giriş yapmanız gerekecektir.
            Bu e-posta size yanlışlıkla gönderildiyse dikkate almayınız.
          </p>
        </div>
        """
        return self._send_smtp(
            to_email,
            f"T-Sistem · {team_name} Takımı Üye Daveti",
            html,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ÜYE ÇIKARILMA BİLDİRİMİ
    # ─────────────────────────────────────────────────────────────────────────
    def send_member_removed_email(
        self, to_email: str, member_name: str,
        team_name: str, captain_name: str
    ) -> tuple[bool, str]:
        """Kaptan tarafından çıkarılan üyeye bildirim e-postası gönderir."""
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;
                    padding:24px;border:1px solid #E2E8F0;border-radius:12px;background:#fff;">
          <div style="text-align:center;margin-bottom:20px;">
            <h2 style="color:#F04823;margin:0;">T-Sistem</h2>
            <p style="color:#64748B;font-size:13px;margin-top:4px;">TEKNOFEST Değerlendirme Platformu</p>
          </div>
          <p style="color:#1E293B;font-size:15px;">Sayın {member_name},</p>
          <p style="color:#334155;font-size:14px;line-height:1.6;">
            <strong>"{team_name}"</strong> takımından kaptan
            <strong>{captain_name}</strong> tarafından çıkarıldınız.
          </p>
          <p style="color:#64748B;font-size:13px;line-height:1.5;">
            Başka bir takıma katılmak veya yeni takım oluşturmak için T-Sistem platformuna
            giriş yapabilirsiniz. Herhangi bir sorunuz olursa sistem yöneticisiyle
            iletişime geçiniz.
          </p>
          <p style="color:#94A3B8;font-size:12px;margin-top:24px;">
            Bu e-posta otomatik olarak gönderilmiştir.
          </p>
        </div>
        """
        return self._send_smtp(
            to_email,
            f"T-Sistem · {team_name} Takımı Üyeliği Sona Erdi",
            html,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # ÜYE AYRILMA BİLDİRİMİ (danışmana veya kaptana)
    # ─────────────────────────────────────────────────────────────────────────
    def send_member_left_email(
        self, to_email: str, recipient_name: str,
        member_name: str, team_name: str
    ) -> tuple[bool, str]:
        """Bir üye takımdan ayrıldığında danışmana/kaptana bildirim gönderir."""
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:540px;margin:auto;
                    padding:24px;border:1px solid #E2E8F0;border-radius:12px;background:#fff;">
          <div style="text-align:center;margin-bottom:20px;">
            <h2 style="color:#F04823;margin:0;">T-Sistem</h2>
            <p style="color:#64748B;font-size:13px;margin-top:4px;">TEKNOFEST Değerlendirme Platformu</p>
          </div>
          <p style="color:#1E293B;font-size:15px;">Sayın {recipient_name},</p>
          <p style="color:#334155;font-size:14px;line-height:1.6;">
            <strong>"{team_name}"</strong> takımından
            <strong>{member_name}</strong> adlı üye kendi isteğiyle ayrıldı.
          </p>
          <p style="color:#64748B;font-size:13px;line-height:1.5;">
            Güncel üye listesini T-Sistem platformundan görüntüleyebilirsiniz.
          </p>
          <p style="color:#94A3B8;font-size:12px;margin-top:24px;">
            Bu e-posta otomatik olarak gönderilmiştir.
          </p>
        </div>
        """
        return self._send_smtp(
            to_email,
            f"T-Sistem · {team_name} Takımında Üye Değişikliği",
            html,
        )


# Singleton instance
auth_service = AuthService()
