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
import json
import os
import sqlite3
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from firebase_config import FIREBASE_CONFIG

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
            print(f"[Cloudflare D1 Warning] {e}")
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
                "profile_completed": bool(row[13]),
                "status": row[14],
                "created_at": row[15],
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

    def handle_google_auth(self, google_profile: Dict[str, str]) -> tuple[Optional[Dict[str, Any]], bool, List[str]]:
        """Google ile giriş yapıldığında Cloudflare D1 ve yerelde kullanıcıyı açar."""
        email = google_profile.get("email", "").strip().lower()
        name = google_profile.get("name", "").strip() or "Google Kullanıcısı"

        user = self.get_user_by_email(email)
        now = datetime.now().isoformat()

        if not user:
            user_id = f"usr_google_{uuid.uuid4().hex[:8]}"
            
            # Cloudflare D1'e Kaydet
            self._query_d1("""
            INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [user_id, email.split("@")[0], name, email, "GOOGLE_OAUTH_TOKEN", "yarismaci", "", "", "Öğrenci", "google", 0, "aktif", now])

            # Yerel SQLite'a Kaydet
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, auth_provider, profile_completed, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, email.split("@")[0], name, email, "GOOGLE_AUTH_TOKEN", "yarismaci", "", "", "Öğrenci", "google", 0, "aktif", now))
            conn.commit()
            conn.close()
            user = self.get_user_by_email(email)

        is_complete, missing_fields = self.check_mandatory_fields_complete(user)
        return (user, is_complete, missing_fields)

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
        self._query_d1("""
        INSERT INTO auth_users (user_id, username, name, email, password_hash, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, auth_provider, profile_completed, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [user_id, u_name, name, clean_email, pwd_hash, role, institution, department, graduation_status, tc_citizen, gender, birth_date, phone, address, education_level, "cloudflare_d1", 1, "aktif", now])

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
        """Tüm kullanıcıları Cloudflare D1 veya yerel veritabanından listeler."""
        d1_res = self._query_d1("SELECT user_id, username, name, email, role, institution, department, graduation_status, phone, auth_provider, status, created_at FROM auth_users ORDER BY created_at DESC")
        if d1_res:
            return d1_res

        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, username, name, email, role, institution, department, graduation_status, phone, auth_provider, status, created_at FROM auth_users ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        return [
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


    def delete_user(self, user_id: str) -> bool:
        """Kullanıcıyı Cloudflare D1 ve yerel veritabanından tamamen siler."""
        return self.delete_user_by_id(user_id)

    def delete_user_by_id(self, user_id: str) -> bool:
        """Kullanıcıyı Cloudflare D1 ve yerel veritabanından tamamen siler."""
        if not user_id:
            return False
        try:
            # 1. Cloudflare D1'den Sil
            self._query_d1("DELETE FROM auth_users WHERE user_id = ?", [user_id])

            # 2. Yerel SQLite'tan Sil
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
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
        """Profil tamamlama aşamasında terk edilen (profile_completed = 0) geçersiz kayıtları temizler."""
        try:
            self._query_d1("DELETE FROM auth_users WHERE profile_completed = 0 AND role = 'yarismaci'")
            conn = sqlite3.connect(DB_FILE)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM auth_users WHERE profile_completed = 0 AND role = 'yarismaci'")
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[Cleanup Error] {e}")

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
                <div style="font-family: Arial, sans-serif; max-width: 500px; margin: auto; padding: 20px; border: 1px solid #E2E8F0; border-radius: 12px;">
                    <h2 style="color: #1E3A8A; text-align: center;">T-Sistem Şifre Sıfırlama</h2>
                    <p>Merhaba,</p>
                    <p>T-Sistem hesabınız için şifre sıfırlama talebinde bulunuldu. Şifrenizi yenilemek için aşağıdaki 6 haneli güvenlik kodunu kullanabilirsiniz:</p>
                    <div style="text-align: center; margin: 24px 0;">
                        <span style="font-size: 28px; font-weight: 800; letter-spacing: 6px; color: #DC2626; background: #FEF2F2; padding: 10px 24px; border-radius: 8px; border: 1px solid #FECACA; display: inline-block;">
                            {code}
                        </span>
                    </div>
                    <p style="color: #64748B; font-size: 13px;">Bu talep sizin tarafınızdan yapılmadıysa lütfen bu e-postayı dikkate almayınız.</p>
                </div>
                """
                msg.attach(MIMEText(html_content, "html"))

                with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                    server.starttls()
                    server.login(smtp_user, smtp_pass)
                    server.sendmail(smtp_user, [email], msg.as_string())

                return True, "E-posta başarıyla SMTP sunucusu üzerinden gönderildi."
            except Exception as e:
                return False, f"SMTP Gönderim Hatası: {str(e)}"
        
        return True, "SMTP yapılandırılmadı (Geliştirici / Test modunda doğrulama kodu ekranda görüntülenecektir)."


# Singleton instance
auth_service = AuthService()
