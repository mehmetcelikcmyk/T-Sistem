"""T-Sistem · TEKNOFEST & T3 Vakfı Yönetim, Değerlendirme ve İntihal Analiz Portalı (T3 KYS).

Tüm roller için görev ve yetkilerine göre özelleştirilmiş, amaca uygun profesyonel ekranlar:
- YARIŞMACI: Başvuru & Rapor Yükleme, Gelişim Karnesi, Biçim Kontrolleri, Karne PDF, Takımlar, Şartnameler
- HAKEM / JÜRİ: "AI 4. Göz" Kanıt Bazlı Rapor Değerlendirme, PDF Kanıt İşaretleme, Rubrik Puanlama
- SİSTEM YÖNETİCİSİ (ADMİN): Çoklu Kategori/Aşama Yönetimi, İntihal Isı Haritası & İkili Karşılaştırma, Cloudflare D1 Kullanıcı Yönetimi
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(_ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(_ROOT_DIR))

import base64
import os
import re
from datetime import date, datetime
import streamlit as st

def init_teams_global():
    import json
    from pathlib import Path
    teams_file = Path("data/takimlar.json")
    if "takim_verileri" not in st.session_state:
        if teams_file.exists():
            try:
                st.session_state.takim_verileri = json.loads(teams_file.read_text(encoding="utf-8"))
            except Exception:
                st.session_state.takim_verileri = []
        else:
            st.session_state.takim_verileri = []
            teams_file.parent.mkdir(parents=True, exist_ok=True)
            teams_file.write_text("[]", encoding="utf-8")
init_teams_global()

def _save_teams():
    import json
    from pathlib import Path
    teams_file = Path("data/takimlar.json")
    teams_file.parent.mkdir(parents=True, exist_ok=True)
    teams_file.write_text(json.dumps(st.session_state.takim_verileri, ensure_ascii=False, indent=2), encoding="utf-8")
from PIL import Image
from i18n import t
from auth_service import auth_service
from views import (
    admin_kullanicilar,
    auth_view,
    dashboard,
    hakem,
    karsilastirma,
    yarismaci,
    yonetici,
)
import sartname_rehber
import docx_gorunum
import pdf_gorunum
from src.database.db import db

# --- LOGO YÜKLEME ---
_UI_DIR = Path(__file__).resolve().parent
_LOGO_PATH = _UI_DIR / "tsistem_logo.png"
if not _LOGO_PATH.exists():
    _LOGO_PATH = _UI_DIR.parent.parent / "tsistem_logo.png"

_fav_icon = Image.open(_LOGO_PATH) if _LOGO_PATH.exists() else "🚀"

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="T-Sistem · TEKNOFEST Kurumsal Portal",
    page_icon=_fav_icon,
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Dil Seçimi State
if "lang" not in st.session_state:
    st.session_state.lang = "tr"

current_lang = st.session_state.lang


def _get_logo_base64() -> str:
    if _LOGO_PATH.exists():
        with open(_LOGO_PATH, "rb") as img_file:
            return f"data:image/png;base64,{base64.b64encode(img_file.read()).decode()}"
    return ""


def _format_phone(phone_raw: str, country_code: str) -> str:
    """Telefon numarasını ülke standartlarına göre formatlar."""
    digits = re.sub(r"\D", "", phone_raw)
    if not digits:
        return ""
    
    # Türkiye Standartı: Başında 0 varsa kaldır, (5XX) XXX XX XX
    if "+90" in country_code:
        if digits.startswith("90"):
            digits = digits[2:]
        if digits.startswith("0"):
            digits = digits[1:]
        digits = digits[:10]
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]} {digits[6:8]} {digits[8:10]}"
        elif len(digits) > 6:
            return f"({digits[:3]}) {digits[3:6]} {digits[6:]}"
        elif len(digits) > 3:
            return f"({digits[:3]}) {digits[3:]}"
        return f"({digits}" if digits else ""
        
    # ABD / Kanada Standartı: (XXX) XXX-XXXX
    elif "+1" in country_code:
        if digits.startswith("1"):
            digits = digits[1:]
        digits = digits[:10]
        if len(digits) == 10:
            return f"({digits[:3]}) {digits[3:6]}-{digits[6:10]}"
        elif len(digits) > 3:
            return f"({digits[:3]}) {digits[3:]}"
        return digits

    # Diğer Standartlar (+44, +49 vb.)
    else:
        digits = digits[:11]
        if len(digits) >= 8:
            return f"{digits[:4]} {digits[4:7]} {digits[7:]}"
        elif len(digits) >= 4:
            return f"{digits[:4]} {digits[4:]}"
        return digits


# --- T3 KYS KURUMSAL CSS ---
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif !important;
    }
    
    /* Menü Butonları */
    div[data-testid="stHorizontalBlock"] .stButton > button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        padding: 8px 12px !important;
        transition: all 0.2s ease !important;
    }

    /* Modül Kartları */
    .t3-module-card {
        background: linear-gradient(135deg, #F04823 0%, #D9381E 100%);
        border-radius: 14px;
        padding: 22px 18px;
        color: #FFFFFF;
        text-align: center;
        min-height: 210px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-shadow: 0 4px 14px rgba(240, 72, 35, 0.15);
        margin-bottom: 12px;
        transition: transform 0.2s ease;
    }
    .t3-module-card:hover {
        transform: translateY(-2px);
    }
    
    .t3-module-title {
        font-size: 1.12rem;
        font-weight: 800;
        margin-bottom: 6px;
        letter-spacing: -0.01em;
    }
    .t3-module-desc {
        font-size: 0.82rem;
        opacity: 0.92;
        line-height: 1.4;
    }
    
    /* Profil ve İçerik Kartı */
    .t3-content-card {
        background: #FFFFFF;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 20px 24px;
        margin-bottom: 18px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.02);
    }
    .t3-card-title {
        font-size: 1.35rem;
        font-weight: 800;
        color: #0F172A;
    }
    .t3-card-sub {
        font-size: 0.86rem;
        color: #64748B;
        margin-top: 3px;
    }
    
    /* Rozetler */
    .t3-badge-aktif {
        background: #DCFCE7;
        color: #15803D;
        font-size: 0.76rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 20px;
    }
    .t3-badge-pasif {
        background: #FEE2E2;
        color: #B91C1C;
        font-size: 0.76rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 20px;
    }
    .t3-badge-info {
        background: #E0F2FE;
        color: #0369A1;
        font-size: 0.76rem;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 20px;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Oturum Durumu Kontrolü
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    auth_view.render_auth_view()
    st.stop()

# --- OTURUM AÇILMIŞSA T3 KYS ANA PANELİ ---
aktif_kullanici = st.session_state.get("user") or {}
rol = str(aktif_kullanici.get("role", "yarismaci")).lower()

# Aktif Menü Sekmesi
if "aktif_tab" not in st.session_state:
    st.session_state.aktif_tab = "ana_sayfa"

# Varsayılan Kategori
if "secili_kategori" not in st.session_state:
    st.session_state.secili_kategori = "saglik_yapay_zeka"

# --- T3 KYS ÜST NAVBAR (ROL BAZLI) ---
n_col1, n_col2 = st.columns([1.5, 3.5])

with n_col1:
    logo_src = _get_logo_base64()
    logo_img = f'<img src="{logo_src}" style="width:38px; height:38px; object-fit:contain; border-radius:8px;" alt="Logo"/>' if logo_src else ''
    st.html(f"""
    <div style="display:flex; align-items:center; gap:12px; margin-top:2px;">
        {logo_img}
        <div>
            <div style="font-size:1.30rem; font-weight:900; color:#1E293B; letter-spacing:-0.03em; line-height:1;">{t("system_name", current_lang)}</div>
            <div style="font-size:0.65rem; font-weight:700; color:#64748B; letter-spacing:0.04em; text-transform:uppercase; margin-top:2px;">{t("system_sub", current_lang)}</div>
        </div>
    </div>
    """)

with n_col2:
    # 1. YARIŞMACI / ÜYE MENÜSÜ
    if rol in ("yarismaci", "uye"):
        menu_c1, menu_c2, menu_c3, menu_c4, menu_c5, menu_c6, menu_c7 = st.columns([1.1, 1.4, 1.2, 1.3, 1.1, 0.7, 0.8])
        with menu_c1:
            if st.button(t("nav_home", current_lang), key="nav_home", use_container_width=True, type="primary" if st.session_state.aktif_tab == "ana_sayfa" else "secondary"):
                st.session_state.aktif_tab = "ana_sayfa"
                st.rerun()
        with menu_c2:
            if st.button(t("nav_apps", current_lang), key="nav_basvuru", use_container_width=True, type="primary" if st.session_state.aktif_tab == "basvurular" else "secondary"):
                st.session_state.aktif_tab = "basvurular"
                st.rerun()
        with menu_c3:
            if st.button(t("nav_teams", current_lang), key="nav_takim", use_container_width=True, type="primary" if st.session_state.aktif_tab == "takimlar" else "secondary"):
                st.session_state.aktif_tab = "takimlar"
                st.rerun()
        with menu_c4:
            if st.button(t("nav_specs", current_lang), key="nav_sartname", use_container_width=True, type="primary" if st.session_state.aktif_tab == "sartnameler" else "secondary"):
                st.session_state.aktif_tab = "sartnameler"
                st.rerun()
        with menu_c5:
            if st.button(t("nav_profile", current_lang), key="nav_profil", use_container_width=True, type="primary" if st.session_state.aktif_tab == "profil" else "secondary"):
                st.session_state.aktif_tab = "profil"
                st.rerun()

    # 2. HAKEM / JÜRİ MENÜSÜ
    elif rol == "hakem":
        menu_c1, menu_c2, menu_c3, menu_c4, menu_c5, menu_c6, menu_c7 = st.columns([1.1, 1.6, 1.4, 1.1, 0.1, 0.7, 0.8])
        with menu_c1:
            if st.button(t("nav_home", current_lang), key="nav_home", use_container_width=True, type="primary" if st.session_state.aktif_tab == "ana_sayfa" else "secondary"):
                st.session_state.aktif_tab = "ana_sayfa"
                st.rerun()
        with menu_c2:
            if st.button(t("nav_eval", current_lang), key="nav_hakem_eval", use_container_width=True, type="primary" if st.session_state.aktif_tab == "degerlendirme" else "secondary"):
                st.session_state.aktif_tab = "degerlendirme"
                st.rerun()
        with menu_c3:
            if st.button(t("nav_specs_criteria", current_lang), key="nav_sartname", use_container_width=True, type="primary" if st.session_state.aktif_tab == "sartnameler" else "secondary"):
                st.session_state.aktif_tab = "sartnameler"
                st.rerun()
        with menu_c4:
            if st.button(t("nav_profile", current_lang), key="nav_profil", use_container_width=True, type="primary" if st.session_state.aktif_tab == "profil" else "secondary"):
                st.session_state.aktif_tab = "profil"
                st.rerun()
        with menu_c5:
            st.write("")

    # 3. SİSTEM YÖNETİCİSİ / ADMİN MENÜSÜ
    else:
        menu_c1, menu_c2, menu_c3, menu_c4, menu_c5, menu_c6, menu_c7 = st.columns([1.1, 1.4, 1.3, 1.3, 1.1, 0.7, 0.8])
        with menu_c1:
            if st.button(t("nav_admin_yonetim", current_lang), key="nav_admin_yonetim", use_container_width=True, type="primary" if st.session_state.aktif_tab == "ana_sayfa" else "secondary"):
                st.session_state.aktif_tab = "ana_sayfa"
                st.rerun()
        with menu_c2:
            if st.button(t("nav_admin_intihal", current_lang), key="nav_admin_intihal", use_container_width=True, type="primary" if st.session_state.aktif_tab == "intihal" else "secondary"):
                st.session_state.aktif_tab = "intihal"
                st.rerun()
        with menu_c3:
            if st.button(t("nav_admin_users", current_lang), key="nav_admin_users", use_container_width=True, type="primary" if st.session_state.aktif_tab == "kullanicilar" else "secondary"):
                st.session_state.aktif_tab = "kullanicilar"
                st.rerun()
        with menu_c4:
            if st.button(t("nav_specs", current_lang), key="nav_sartname", use_container_width=True, type="primary" if st.session_state.aktif_tab == "sartnameler" else "secondary"):
                st.session_state.aktif_tab = "sartnameler"
                st.rerun()
        with menu_c5:
            if st.button(t("nav_profile", current_lang), key="nav_profil", use_container_width=True, type="primary" if st.session_state.aktif_tab == "profil" else "secondary"):
                st.session_state.aktif_tab = "profil"
                st.rerun()

    # Ortak Dil ve Çıkış Butonları
    with menu_c6:
        diger_dil = "EN" if current_lang == "tr" else "TR"
        if st.button(f"🌐 {diger_dil}", key="btn_nav_lang", use_container_width=True):
            st.session_state.lang = diger_dil.lower()
            st.rerun()

    with menu_c7:
        if st.button(t("nav_logout", current_lang), key="nav_logout", use_container_width=True):
            st.session_state.authenticated = False
            st.session_state.user = None
            st.rerun()

st.markdown("<hr style='margin: 6px 0 12px 0; border-color: #F1F5F9;'>", unsafe_allow_html=True)

# ==============================================================================
# --- 1. ANA SAYFA GÖRÜNÜMÜ ---
# ==============================================================================
if st.session_state.aktif_tab == "ana_sayfa":
    # 1.1. YARIŞMACI / ÜYE İÇİN ANA SAYFA
    if rol in ("yarismaci", "uye"):
        card_c1, card_c2, card_c3, card_c4 = st.columns(4)
        with card_c1:
            st.html(f"""
            <div class="t3-module-card">
                <div>
                    <div style="width:54px; height:54px; border-radius:50%; background:#FFDE59; margin:0 auto 12px auto; display:flex; align-items:center; justify-content:center; font-size:1.5rem; color:#F04823; font-weight:900;">H</div>
                    <div class="t3-module-title">{t("card_account", current_lang)}</div>
                    <div class="t3-module-desc">{t("card_account_desc", current_lang)}</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_account", current_lang), key="btn_card_hesabim", use_container_width=True):
                st.session_state.aktif_tab = "basvurular"
                st.rerun()

        with card_c2:
            st.html(f"""
            <div class="t3-module-card">
                <div>
                    <div style="width:54px; height:54px; border-radius:50%; background:rgba(255,255,255,0.2); margin:0 auto 12px auto; display:flex; align-items:center; justify-content:center; font-size:1.2rem; color:#FFFFFF; font-weight:900;">TF</div>
                    <div class="t3-module-title">{t("card_tf_title", current_lang)}</div>
                    <div class="t3-module-desc">{t("card_tf_desc", current_lang)}</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_tf", current_lang), key="btn_card_tf", use_container_width=True):
                st.session_state.aktif_tab = "basvurular"
                st.rerun()

        with card_c3:
            st.html(f"""
            <div class="t3-module-card">
                <div>
                    <div style="width:54px; height:54px; border-radius:50%; background:rgba(255,255,255,0.2); margin:0 auto 12px auto; display:flex; align-items:center; justify-content:center; font-size:1.2rem; color:#FFFFFF; font-weight:900;">TK</div>
                    <div class="t3-module-title">{t("card_teams_title", current_lang)}</div>
                    <div class="t3-module-desc">{t("card_teams_desc", current_lang)}</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_teams", current_lang), key="btn_card_milli", use_container_width=True):
                st.session_state.aktif_tab = "takimlar"
                st.rerun()

        with card_c4:
            st.html(f"""
            <div class="t3-module-card">
                <div>
                    <div style="width:54px; height:54px; border-radius:50%; background:rgba(255,255,255,0.2); margin:0 auto 12px auto; display:flex; align-items:center; justify-content:center; font-size:1.2rem; color:#FFFFFF; font-weight:900;">ŞT</div>
                    <div class="t3-module-title">{t("card_specs_title", current_lang)}</div>
                    <div class="t3-module-desc">{t("card_specs_desc", current_lang)}</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_specs", current_lang), key="btn_card_gonullu", use_container_width=True):
                st.session_state.aktif_tab = "sartnameler"
                st.rerun()

        st.write("")
        # Üye Bilgilendirme ve Aşama Takvimi Panosu
        st.html("""
        <div class="t3-content-card">
            <div class="t3-card-title">TEKNOFEST 2026 Başvuru ve Rapor Takvimi</div>
            <div class="t3-card-sub">Ön Tasarım Raporu (ÖTR) ve Kritik Tasarım Raporu (KTR) son teslim tarihleri</div>
            <hr style="margin:12px 0; border-color:#E2E8F0;">
            <div style="display:grid; grid-template-columns: repeat(3, 1fr); gap:16px;">
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; padding:12px; border-radius:8px;">
                    <div style="font-size:0.80rem; color:#64748B; font-weight:600;">1. AŞAMA / STAGE 1</div>
                    <div style="font-size:0.95rem; font-weight:800; color:#1E293B;">Ön Tasarım Raporu (ÖTR / PDR)</div>
                    <div style="font-size:0.85rem; color:#F04823; font-weight:700; margin-top:4px;">Son Teslim: 15 Nisan 2026</div>
                </div>
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; padding:12px; border-radius:8px;">
                    <div style="font-size:0.80rem; color:#64748B; font-weight:600;">2. AŞAMA / STAGE 2</div>
                    <div style="font-size:0.95rem; font-weight:800; color:#1E293B;">Kritik Tasarım Raporu (KTR / CDR)</div>
                    <div style="font-size:0.85rem; color:#64748B; font-weight:700; margin-top:4px;">Son Teslim: 15 Haziran 2026</div>
                </div>
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; padding:12px; border-radius:8px;">
                    <div style="font-size:0.80rem; color:#64748B; font-weight:600;">FİNAL / FINAL</div>
                    <div style="font-size:0.95rem; font-weight:800; color:#1E293B;">TEKNOFEST 2026 Final Sergisi</div>
                    <div style="font-size:0.85rem; color:#16A34A; font-weight:700; margin-top:4px;">Tarih: 02-06 Eylül 2026</div>
                </div>
            </div>
        </div>
        """)

    # 1.2. HAKEM / JÜRİ İÇİN ANA SAYFA
    elif rol == "hakem":
        u_id = aktif_kullanici.get("user_id", "usr_hakem_ef6def")
        u_email = aktif_kullanici.get("email", "hakem@tsistem.org")
        
        # Hakeme atanan raporları çek
        h_reports = db.get_reports_for_referee(u_id)
        if not h_reports:
            h_reports = db.get_reports_for_referee(u_email)
        
        toplam_atanan = len(h_reports)
        tamamlanan_adet = sum(1 for r in h_reports if r.get("referee_score") is not None or r.get("status") == "tamamlandi")
        bekleyen_adet = max(0, toplam_atanan - tamamlanan_adet)

        st.html("""
        <div class="t3-content-card" style="margin-bottom:16px;">
            <div class="t3-card-title">Hakem Değerlendirme İstasyonu & Atanan Rapor Havuzu</div>
            <div class="t3-card-sub">Yarışma yöneticisi tarafından değerlendirmeniz için tarafınıza atanan güncel aşama raporları.</div>
        </div>
        """)
        hk_c1, hk_c2, hk_c3 = st.columns(3)
        with hk_c1:
            st.metric("Atanan Toplam Rapor", f"{toplam_atanan} Rapor")
        with hk_c2:
            oran = int((tamamlanan_adet / max(toplam_atanan, 1)) * 100)
            st.metric("Tamamlanan Puanlama", f"{tamamlanan_adet} Rapor (%{oran})")
        with hk_c3:
            st.metric("Bekleyen Raporlar", f"{bekleyen_adet} Rapor")

        st.write("")
        b_c1, b_c2, _ = st.columns([1.4, 1.4, 2.2])
        with b_c1:
            if st.button("Rapor Değerlendirme Ekranına Geç", type="primary", use_container_width=True):
                st.session_state.aktif_tab = "degerlendirme"
                st.rerun()
        with b_c2:
            if st.button("Şartname & Kriterleri İncele", use_container_width=True):
                st.session_state.aktif_tab = "sartnameler"
                st.rerun()

    # 1.3. SİSTEM YÖNETİCİSİ (ADMİN) İÇİN ANA SAYFA
    else:
        tab_admin1, tab_admin2 = st.tabs([t("tab_admin_ops", current_lang), t("tab_admin_cats", current_lang)])
        with tab_admin1:
            dashboard.goster(st, st.session_state.secili_kategori)
        with tab_admin2:
            yonetici.goster(st)

# ==============================================================================
# --- 2. YARIŞMACI: BAŞVURULARIM & GELİŞİM KARNESİ ---
# ==============================================================================
elif st.session_state.aktif_tab == "basvurular":
    if rol in ("yarismaci", "uye"):
        yarismaci.goster(st, st.session_state.secili_kategori)
    else:
        st.session_state.aktif_tab = "ana_sayfa"
        st.rerun()

# ==============================================================================
# --- 3. HAKEM / JÜRİ: RAPOR DEĞERLENDİRME & AI 4. GÖZ ---
# ==============================================================================
elif st.session_state.aktif_tab == "degerlendirme":
    if rol == "hakem":
        u_id = aktif_kullanici.get("user_id", "usr_hakem_ef6def")
        u_email = aktif_kullanici.get("email", "hakem@tsistem.org")
        
        # Sistemdeki TÜM 60+ TEKNOFEST Kategorisini Yükle
        kategori_secenekleri = sartname_rehber.tum_yarismalari_sozluk_getir()
        keys_list = list(kategori_secenekleri.keys())
        
        # Hakeme atanan raporları çek
        db_reports = db.get_reports_for_referee(u_id)
        if not db_reports:
            db_reports = db.get_reports_for_referee(u_email)

        kat_rapor_sayilari = {}
        for r in db_reports:
            c_raw = (r["category"] or "").strip().lower()
            matched_slug = None
            for slug in keys_list:
                slug_norm = slug.replace("-", " ").lower()
                c_clean = c_raw.replace("i", "ı").replace(" ", "")
                s_clean = slug_norm.replace("i", "ı").replace(" ", "")
                if c_clean in s_clean or s_clean in c_clean or c_raw in slug_norm:
                    matched_slug = slug
                    break
            if not matched_slug:
                if "hava" in c_raw or "yz" in c_raw:
                    matched_slug = "havacilikta-yapay-zeka-yarismasi"
                elif "insanlik" in c_raw:
                    matched_slug = "insanlik-yararina-teknolojiler-yarismasi-lise-seviyesi"
                elif "biyo" in c_raw:
                    matched_slug = "biyoteknoloji-inovasyon-yarismasi"
                elif "cip" in c_raw:
                    matched_slug = "cip-tasarim-yarismasi"
                elif "saglik" in c_raw:
                    matched_slug = "saglikta-yapay-zeka-yarismasi"
                elif "roket" in c_raw:
                    matched_slug = "roket-yarismasi"
                elif "savasan" in c_raw:
                    matched_slug = "savasan-iha-yarismasi"
                else:
                    matched_slug = "havacilikta-yapay-zeka-yarismasi"
            
            kat_rapor_sayilari[matched_slug] = kat_rapor_sayilari.get(matched_slug, 0) + 1

        # Raporu olan kategorileri listenin en başına taşı
        sirali_keys = sorted(keys_list, key=lambda k: kat_rapor_sayilari.get(k, 0), reverse=True)

        # --- HAKEM DEĞERLENDİRME İSTASYONU ---
        hakem.goster(
            st,
            st.session_state.secili_kategori,
            referee_id=u_id,
            kategori_secenekleri=kategori_secenekleri,
            sirali_keys=sirali_keys,
            kat_rapor_sayilari=kat_rapor_sayilari
        )
    elif rol == "admin":
        yonetici.goster(st)
    else:
        st.warning("Bu alana erişim yetkiniz bulunmamaktadır.")
        st.session_state.aktif_tab = "ana_sayfa"
        st.rerun()

# ==============================================================================
# --- 4. SİSTEM YÖNETİCİSİ: İNTİHAL ISISI & KARŞILAŞTIRMA ---
# ==============================================================================
elif st.session_state.aktif_tab == "intihal":
    if rol == "admin":
        karsilastirma.goster(st, st.session_state.secili_kategori)
    else:
        st.warning("Bu alana erişim yetkiniz bulunmamaktadır.")
        st.session_state.aktif_tab = "ana_sayfa"
        st.rerun()

# ==============================================================================
# --- 5. SİSTEM YÖNETİCİSİ: CLOUDFLARE D1 KULLANICILAR ---
# ==============================================================================
elif st.session_state.aktif_tab == "kullanicilar":
    if rol == "admin":
        admin_kullanicilar.render()
    else:
        st.warning("Bu alana yalnızca Sistem Yöneticisi erişebilir.")
        st.session_state.aktif_tab = "ana_sayfa"
        st.rerun()

# ==============================================================================
# --- 6. TAKIMLARIM (YARIŞMACILAR İÇİN) ---
# ==============================================================================
elif st.session_state.aktif_tab == "takimlar":
    st.html(f"""
    <div class="t3-content-card" style="margin-bottom: 16px;">
        <div style="display:flex; justify-content:space-between; align-items:center;">
            <div>
                <div class="t3-card-title">{t("teams_title", current_lang)}</div>
                <div class="t3-card-sub">{t("teams_sub", current_lang)}</div>
            </div>
        </div>
    </div>
    """)

    t_btn1, t_btn2, _ = st.columns([1.2, 1.2, 2.6])
    with t_btn1:
        if st.button(t("btn_create_team", current_lang), type="primary", use_container_width=True):
            st.session_state.show_create_team = not st.session_state.get("show_create_team", False)
            st.session_state.show_join_team = False
    with t_btn2:
        if st.button(t("btn_join_team", current_lang), use_container_width=True):
            st.session_state.show_join_team = not st.session_state.get("show_join_team", False)
            st.session_state.show_create_team = False

    if st.session_state.get("show_create_team"):
        with st.form("form_create_team"):
            st.subheader(t("btn_create_team", current_lang))
            tc1, tc2, tc3 = st.columns(3)
            with tc1:
                yeni_takim_adi = st.text_input(t("lbl_team_name", current_lang), placeholder="Örn: Bilig Yapay Zekâ")
            with tc2:
                yeni_seviye = st.selectbox("Eğitim Seviyesi *", [
                    "Lise Seviyesi",
                    "Ön Lisans / Lisans Seviyesi",
                    "Yüksek Lisans / Doktora",
                    "Ortaokul Seviyesi",
                    "İlkokul Seviyesi",
                    "Mezun / Serbest Girişimci"
                ], index=1)
            with tc3:
                yeni_kurum = st.text_input("Okul / Kurum / Üniversite", placeholder="Örn: İstanbul Teknik Üniversitesi")
            sub_t = st.form_submit_button(t("btn_submit_team", current_lang), type="primary")
            if sub_t:
                if not yeni_takim_adi:
                    st.error("Takım adı zorunludur.")
                else:
                    new_id = str(abs(hash(yeni_takim_adi)) % 900000 + 100000)
                    st.session_state.takim_verileri.insert(0, {
                        "id": new_id,
                        "tarih": datetime.today().strftime("%d.%m.%Y"),
                        "takim": yeni_takim_adi,
                        "seviye": yeni_seviye,
                        "kurum": yeni_kurum or "Bağımsız",
                        "rol": "Kaptan",
                        "uye": 1,
                        "durum": "Aktif"
                    })
                    _save_teams()
                    st.success(f"'{yeni_takim_adi}' takımı ({yeni_seviye}) başarıyla oluşturuldu! Takım Kodu: {new_id}")
                    st.session_state.show_create_team = False
                    st.rerun()

    if st.session_state.get("show_join_team"):
        with st.form("form_join_team"):
            st.subheader(t("btn_join_team", current_lang))
            takim_kodu = st.text_input(t("lbl_join_code", current_lang), placeholder="Örn: 1004562")
            sub_j = st.form_submit_button(t("btn_submit_join", current_lang), type="primary")
            if sub_j:
                if not takim_kodu:
                    st.error("Lütfen bir takım kodu giriniz.")
                else:
                    zaten_var = next((t for t in st.session_state.takim_verileri if str(t["id"]) == str(takim_kodu)), None)
                    if zaten_var:
                        st.error("Zaten bu takımdasınız!")
                    else:
                        st.session_state.takim_verileri.insert(0, {
                            "id": takim_kodu,
                            "tarih": datetime.today().strftime("%d.%m.%Y"),
                            "takim": f"Katılınan Takım {takim_kodu}",
                            "kategori": "TEKNOFEST 2026 · Havacılıkta Yapay Zeka Yarışması",
                            "rol": "Üye",
                            "uye": 2,
                            "durum": "Aktif"
                        })
                        _save_teams()
                        st.success(f"{takim_kodu} kodlu takıma başarıyla katıldınız!")
                        st.session_state.show_join_team = False
                        st.rerun()

    takim_verileri = st.session_state.takim_verileri

    for i, t_item in enumerate(takim_verileri):
        with st.container(border=True):
            t_col1, t_col2, t_col3, t_col4, t_col5, t_col6 = st.columns([1, 1.1, 2.2, 1.8, 1, 1.2])
            with t_col1:
                st.write(f"**ID:** {t_item['id']}")
            with t_col2:
                st.write(t_item["tarih"])
            with t_col3:
                st.markdown(f"<span style='font-weight: bold;'>{t_item['takim']}</span>", unsafe_allow_html=True)
                st.caption(f"Rolünüz: {t_item['rol']}")
            with t_col4:
                st.markdown(f"**{t_item.get('seviye', 'Ön Lisans / Lisans')}**")
                st.caption(t_item.get("kurum", "Bağımsız"))
            with t_col5:
                st.write(f"{t_item['uye']} Üye")
            with t_col6:
                if t_item["durum"] == "Aktif":
                    st.markdown("<span class='t3-badge-aktif'>Aktif</span>", unsafe_allow_html=True)
                else:
                    st.markdown("<span class='t3-badge-pasif'>Pasif</span>", unsafe_allow_html=True)

            with st.expander(t("exp_team_members", current_lang), expanded=False):
                kullanici_adi = st.session_state.user.get("name", "Mehmet Çelik") if st.session_state.get("user") else "Mehmet Çelik"
                st.markdown(f"- **{kullanici_adi}** (Kaptan)")
                if t_item['uye'] > 1:
                    st.markdown("- **Ahmet Yılmaz** (Üye)")
                if t_item['uye'] > 2:
                    st.markdown("- **Prof. Dr. Mehmet** (Danışman)")

                st.markdown("---")
                if st.button(t("btn_leave_team", current_lang), key=f"del_{t_item['id']}_{i}"):
                    st.session_state.takim_verileri.pop(i)
                    _save_teams()
                    st.rerun()

# ==============================================================================
# --- 7. ŞARTNAMELER & ŞABLONLAR / RAPORLAR (İNTERAKTİF ÖNİZLEME) ---
# ==============================================================================
elif st.session_state.aktif_tab == "sartnameler":
    st.html(f"""
    <div class="t3-content-card">
        <div class="t3-card-title">{t("specs_portal_title", current_lang)}</div>
        <div class="t3-card-sub">{t("specs_portal_sub", current_lang)}</div>
    </div>
    """)

    tab_sartname, tab_sablon_rapor = st.tabs([t("tab_specs", current_lang), t("tab_templates", current_lang)])

    # Tüm 60+ Kategoriyi Yükle
    kat_dict = sartname_rehber.tum_yarismalari_sozluk_getir()
    kat_keys = list(kat_dict.keys())

    # =========================================================================
    # TAB 1: RESMÎ ŞARTNAMELER
    # =========================================================================
    with tab_sartname:
        s_side, s_main = st.columns([1, 2.2])

        with s_side:
            with st.container(border=True):
                st.markdown("##### Şartname Doküman Gezgini")
                secili_kat_sn = st.selectbox(
                    t("sel_category", current_lang),
                    options=kat_keys,
                    format_func=lambda k: kat_dict[k],
                    key="sel_kat_sartname_page"
                )

                # Şartname bilgilerini çek
                sn_logo_b64 = sartname_rehber.kategori_logosu_base64_getir(secili_kat_sn)
                if sn_logo_b64:
                    st.markdown(
                        f"""
                        <div style="display:flex; align-items:center; gap:12px; margin:10px 0; background:#F8FAFC; padding:8px 12px; border-radius:8px; border:1px solid #E2E8F0;">
                            <img src="{sn_logo_b64}" style="width:42px; height:42px; object-fit:contain; border-radius:6px; background:#FFFFFF; border:1px solid #CBD5E1; padding:2px;" alt="Logo"/>
                            <span style="font-weight:750; font-size:0.86rem; color:#1E293B;">{kat_dict.get(secili_kat_sn, '')}</span>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                rehber_info = sartname_rehber.klasor_bilgisi(secili_kat_sn)
                sartname_yolu = str(rehber_info.get("sartname_pdf")) if rehber_info.get("sartname_pdf") else None
                toplam_sn_sayfa = 0
                if sartname_yolu and os.path.exists(sartname_yolu):
                    try:
                        import pymupdf
                        doc_sn = pymupdf.open(sartname_yolu)
                        toplam_sn_sayfa = len(doc_sn)
                        doc_sn.close()
                    except Exception:
                        pass

                if sartname_yolu and toplam_sn_sayfa > 0:
                    st.markdown("<hr style='margin:10px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                    st.caption(f"Dosya: {Path(sartname_yolu).name}")
                    st.caption(f"Toplam: {toplam_sn_sayfa} Sayfa")
                    
                    with open(sartname_yolu, "rb") as f_sn:
                        st.download_button(
                            "Şartnameyi İndir (PDF)",
                            data=f_sn.read(),
                            file_name=Path(sartname_yolu).name,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key=f"dl_sn_btn_{secili_kat_sn}"
                        )

        with s_main:
            if not sartname_yolu or toplam_sn_sayfa == 0:
                st.info("Bu yarışma kategorisi için şartname PDF dosyası henüz sisteme yüklenmemiş.")
            else:
                st.html(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <span style="font-size:1.00rem; font-weight:750; color:#1E293B;">{t("spec_doc_title", current_lang)} ({toplam_sn_sayfa} Sayfa)</span>
                    <span style="font-size:0.84rem; font-weight:600; color:#64748B;">{t("continuous_scroll_active", current_lang)}</span>
                </div>
                """)
                pdf_gorunum.pdf_onizle(st, sartname_yolu, height=760, key=f"app_sn_pdf_{secili_kat_sn}")

    # =========================================================================
    # TAB 2: ŞABLONLAR & RAPORLAR
    # =========================================================================
    with tab_sablon_rapor:
        sb_side, sb_main = st.columns([1, 2.2])

        with sb_side:
            with st.container(border=True):
                st.markdown("##### Şablon & Aşama Seçimi")
                secili_kat_sb = st.selectbox(
                    "Yarışma Kategorisi",
                    options=kat_keys,
                    format_func=lambda k: kat_dict[k],
                    key="sel_kat_sablon_page"
                )

                # Sadece bu seçilen kategoriye ait gerçek aşamaları dinamik olarak getir
                kb_info = sartname_rehber.klasor_bilgisi(secili_kat_sb)
                mevcut_asamalar = kb_info.get("asama_listesi", ["OTR"])
                if not mevcut_asamalar:
                    mevcut_asamalar = ["OTR"]
                
                asama_isim_haritasi = {
                    "OTR": "OTR (Ön Tasarım Raporu)",
                    "ODR": "ODR (Ön Değerlendirme Raporu)",
                    "PDR": "PDR (Proje Detay Raporu)",
                    "KTR": "KTR (Kritik Tasarım Raporu)",
                    "CDR": "CDR (Kritik İnceleme Raporu)",
                    "DTR": "DTR (Detaylı Tasarım Raporu)",
                    "AHR": "AHR (Atışa Hazırlık Raporu)",
                    "FRR": "FRR (Uçuşa Yeterlilik Raporu)",
                    "FTR": "FTR (Final Tasarım Raporu)",
                    "FYR": "FYR (Final Yeterlilik Raporu)",
                    "QR": "QR (Yeterlilik İnceleme Raporu)",
                    "POR": "POR (Proje Ön Raporu)",
                    "GENEL": "Aşama Raporu"
                }
                
                asama_gosterim_secenekleri = [asama_isim_haritasi.get(a, a) for a in mevcut_asamalar]
                secili_asama_sb = st.selectbox(
                    t("sel_stage", current_lang),
                    options=asama_gosterim_secenekleri,
                    key=f"sel_asama_sablon_{secili_kat_sb}"
                )

                asama_saf = secili_asama_sb.split()[0]
                sb_dokuman_info = sartname_rehber.dokuman_rehberi_getir(secili_kat_sb, asama_saf)

                sablon_raw_yolu = sb_dokuman_info.get("sablon_yolu")
                toplam_sb_sayfa = sb_dokuman_info.get("sablon_sayfa_sayisi", 0)

                # PDF ve DOCX yollarını belirle
                sablon_pdf_yolu = None
                sablon_docx_yolu = None

                if sablon_raw_yolu:
                    p_raw = Path(sablon_raw_yolu)
                    if p_raw.suffix.lower() == ".pdf" and p_raw.exists():
                        sablon_pdf_yolu = str(p_raw)
                        if p_raw.with_suffix(".docx").exists():
                            sablon_docx_yolu = str(p_raw.with_suffix(".docx"))
                    elif p_raw.suffix.lower() == ".docx" and p_raw.exists():
                        sablon_docx_yolu = str(p_raw)
                        if p_raw.with_suffix(".pdf").exists():
                            sablon_pdf_yolu = str(p_raw.with_suffix(".pdf"))
                        else:
                            sablon_pdf_yolu = str(p_raw)

                if sablon_pdf_yolu and Path(sablon_pdf_yolu).exists() and Path(sablon_pdf_yolu).suffix.lower() == ".pdf":
                    try:
                        import pymupdf
                        doc_sb = pymupdf.open(sablon_pdf_yolu)
                        toplam_sb_sayfa = len(doc_sb)
                        doc_sb.close()
                    except Exception:
                        pass

                if sablon_pdf_yolu or sablon_docx_yolu:
                    st.markdown("<hr style='margin:10px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                    st.caption(f"Dosya: {Path(sablon_pdf_yolu or sablon_docx_yolu).name}")
                    if toplam_sb_sayfa > 0:
                        st.caption(f"Toplam: {toplam_sb_sayfa} Sayfa")
                    
                    if sablon_pdf_yolu and Path(sablon_pdf_yolu).exists() and Path(sablon_pdf_yolu).suffix.lower() == ".pdf":
                        with open(sablon_pdf_yolu, "rb") as f_sb:
                            st.download_button(
                                "Şablonu İndir (PDF)",
                                data=f_sb.read(),
                                file_name=Path(sablon_pdf_yolu).name,
                                mime="application/pdf",
                                type="primary",
                                use_container_width=True,
                                key=f"dl_sb_pdf_btn_{secili_kat_sb}_{asama_saf}"
                            )

                    if sablon_docx_yolu and Path(sablon_docx_yolu).exists():
                        with open(sablon_docx_yolu, "rb") as f_sb_d:
                            st.download_button(
                                "Word Formatında İndir (.docx)",
                                data=f_sb_d.read(),
                                file_name=Path(sablon_docx_yolu).name,
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                use_container_width=True,
                                key=f"dl_sb_docx_btn_{secili_kat_sb}_{asama_saf}"
                            )

        with sb_main:
            if not sablon_pdf_yolu or not Path(sablon_pdf_yolu).exists():
                st.info("Bu aşama için şablon veya örnek rapor dosyası bulunamadı.")
            else:
                st.html(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                    <span style="font-size:1.00rem; font-weight:750; color:#1E293B;">{t("template_doc_title", current_lang)} ({asama_saf})</span>
                    <span style="font-size:0.84rem; font-weight:600; color:#64748B;">{toplam_sb_sayfa} Sayfa · {t("continuous_scroll_active", current_lang)}</span>
                </div>
                """)
                pdf_gorunum.pdf_onizle(st, sablon_pdf_yolu, height=760, key=f"app_sb_pdf_{secili_kat_sb}")

# ==============================================================================
# --- 8. PROFİLİM SAYFASI (EKSİKSİZ T3 KYS ALANLARI) ---
# ==============================================================================
elif st.session_state.aktif_tab == "profil":
    st.html(f"""
    <div class="t3-content-card">
        <div class="t3-card-title">{t("profile_title", current_lang)}</div>
        <div class="t3-card-sub">{t("profile_sub", current_lang)}</div>
    </div>
    """)

    # İsim ve Soyisim Ayrıştırma
    tam_ad = aktif_kullanici.get("name", "")
    ad_parcalar = tam_ad.split() if tam_ad else ["", ""]
    varsayilan_ad = ad_parcalar[0] if len(ad_parcalar) > 0 else ""
    varsayilan_soyad = " ".join(ad_parcalar[1:]) if len(ad_parcalar) > 1 else ""

    # Telefon ve Ülke Kodu Ayrıştırma
    tel_raw = aktif_kullanici.get("phone", "")
    if "+90" in tel_raw or tel_raw.startswith("90"):
        v_kod = "+90 (TR)"
    elif "+1" in tel_raw or tel_raw.startswith("1"):
        v_kod = "+1 (US)"
    elif "+44" in tel_raw:
        v_kod = "+44 (UK)"
    elif "+49" in tel_raw:
        v_kod = "+49 (DE)"
    else:
        v_kod = "+90 (TR)"

    v_tel_formatted = _format_phone(tel_raw, v_kod)

    with st.form("form_t3_profil_tam_duzenleme"):
        # BÖLÜM 1: PANEL BİLGİLERİ
        st.markdown(f"<div style='font-weight:750; color:#1E293B; margin-bottom:8px;'>{t('sec_panel_info', current_lang)}</div>", unsafe_allow_html=True)
        c_p1, c_p2, c_p3 = st.columns(3)
        with c_p1:
            yeni_username = st.text_input(t("lbl_username", current_lang), value=aktif_kullanici.get("username", aktif_kullanici.get("email", "").split("@")[0]))
        with c_p2:
            st.text_input(t("lbl_email_locked", current_lang), value=aktif_kullanici.get("email", ""), disabled=True)
        with c_p3:
            st.text_input(t("lbl_auth_method", current_lang), value=f"Google OAuth (Cloudflare D1)" if aktif_kullanici.get("auth_provider") == "google" else "E-Posta / Parola", disabled=True)

        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        # BÖLÜM 2: KİŞİSEL BİLGİLER
        st.markdown(f"<div style='font-weight:750; color:#1E293B; margin-bottom:8px;'>{t('sec_personal_info', current_lang)}</div>", unsafe_allow_html=True)
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            yeni_ad = st.text_input(t("lbl_name", current_lang), value=varsayilan_ad)
        with k2:
            yeni_soyad = st.text_input(t("lbl_surname", current_lang), value=varsayilan_soyad)
        with k3:
            tc_val = aktif_kullanici.get("tc_citizen", "Evet")
            yeni_tc = st.selectbox(t("lbl_tc", current_lang), ["Evet", "Hayır"] if current_lang == "tr" else ["Yes", "No"], index=0 if tc_val not in ("Hayır", "No") else 1)
        with k4:
            cinsiyet_val = aktif_kullanici.get("gender", "ERKEK")
            yeni_cinsiyet = st.selectbox(t("lbl_gender", current_lang), ["ERKEK", "KADIN"] if current_lang == "tr" else ["MALE", "FEMALE"], index=0 if cinsiyet_val in ("ERKEK", "MALE") else 1)

        # BÖLÜM 3: İLETİŞİM VE ADRES BİLGİLERİ (STANDART TELEFON ŞABLONU)
        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-weight:750; color:#1E293B; margin-bottom:8px;'>{t('sec_contact_info', current_lang)}</div>", unsafe_allow_html=True)
        
        i1, i2, i3, i4 = st.columns([1, 1.5, 1.2, 2.3])
        with i1:
            kod_secenekleri = ["+90 (TR)", "+1 (US)", "+44 (UK)", "+49 (DE)"]
            k_idx = kod_secenekleri.index(v_kod) if v_kod in kod_secenekleri else 0
            yeni_kod = st.selectbox(t("lbl_country_code", current_lang), kod_secenekleri, index=k_idx)
        with i2:
            placeholder_tel = "(5XX) XXX XX XX" if "+90" in yeni_kod else ("(XXX) XXX-XXXX" if "+1" in yeni_kod else "XXXX XXXXXX")
            yeni_tel_raw = st.text_input(t("lbl_phone", current_lang), value=v_tel_formatted, placeholder=placeholder_tel, help="TR numaralarında başında sıfır olmadan (5XX) XXX XX XX formatında giriniz.")
        with i3:
            yeni_ulke = st.selectbox(t("lbl_country", current_lang), ["TÜRKİYE", "DİĞER"] if current_lang == "tr" else ["TURKEY", "OTHER"], index=0)
        with i4:
            yeni_adres = st.text_input(t("lbl_address", current_lang), value=aktif_kullanici.get("address", ""), placeholder="Örn: Gaziantep, Şahinbey...")

        # BÖLÜM 4: EĞİTİM VE BÖLÜM / PROGRAM BİLGİLERİ
        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        st.markdown(f"<div style='font-weight:750; color:#1E293B; margin-bottom:8px;'>{t('sec_education_info', current_lang)}</div>", unsafe_allow_html=True)
        
        e1, e2, e3, e4 = st.columns([1, 1.2, 2, 2])
        with e1:
            mezun_val = aktif_kullanici.get("graduation_status", "Öğrenci")
            yeni_mezun = st.selectbox(t("lbl_grad_status", current_lang), ["Öğrenci", "Mezun"] if current_lang == "tr" else ["Student", "Graduated"], index=0 if mezun_val in ("Öğrenci", "Student") else 1)
        with e2:
            egitim_secenekleri = ["Lisans", "Önlisans", "Yüksek Lisans", "Doktora", "Lise", "Ortaokul"] if current_lang == "tr" else ["Bachelor", "Associate", "Master", "PhD", "High School", "Middle School"]
            cur_egitim = aktif_kullanici.get("education_level", "Lisans")
            idx_e = egitim_secenekleri.index(cur_egitim) if cur_egitim in egitim_secenekleri else 0
            yeni_egitim = st.selectbox(t("lbl_edu_level", current_lang), egitim_secenekleri, index=idx_e)
        with e3:
            yeni_okul = st.text_input(t("lbl_school", current_lang), value=aktif_kullanici.get("institution", ""), placeholder="Örn: Gaziantep İslam Bilim ve Teknoloji Üniversitesi")
        with e4:
            yeni_bolum = st.text_input(t("lbl_dept", current_lang), value=aktif_kullanici.get("department", ""), placeholder="Örn: Bilgisayar Mühendisliği Pr.")

        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        st.html("""
        <div style="background:#F0FDF4; border:1px solid #BBF7D0; border-radius:8px; padding:10px 14px; font-size:0.84rem; color:#166534; display:flex; align-items:center; justify-content:space-between;">
            <span>✓ KVKK Muvafakatnamesi ve Aydınlatma Metni Onaylıdır.</span>
            <span style="font-weight:700;">Durum: Aktif Üye</span>
        </div>
        """)

        st.write("")
        btn_c1, btn_c2, _ = st.columns([1.2, 1.2, 2.6])
        with btn_c1:
            btn_guncelle = st.form_submit_button(t("btn_save_profile", current_lang), type="primary", use_container_width=True)

        if btn_guncelle:
            formatted_phone = _format_phone(yeni_tel_raw, yeni_kod)
            tam_tel = f"{yeni_kod.split()[0]} {formatted_phone}".strip()
            tam_ad_yeni = f"{yeni_ad.strip()} {yeni_soyad.strip()}".strip()

            basari, mesaj = auth_service.complete_user_profile(
                user_id=aktif_kullanici.get("user_id"),
                profile_data={
                    "username": yeni_username,
                    "name": tam_ad_yeni,
                    "tc_citizen": yeni_tc,
                    "gender": yeni_cinsiyet,
                    "birth_date": aktif_kullanici.get("birth_date", "2000-01-01"),
                    "phone": tam_tel,
                    "address": f"{yeni_ulke} - {yeni_adres}".strip(),
                    "education_level": yeni_egitim,
                    "institution": yeni_okul,
                    "department": yeni_bolum,
                    "graduation_status": yeni_mezun,
                }
            )
            if basari:
                guncel_user = auth_service.get_user_by_email(aktif_kullanici.get("email"))
                st.session_state.user = guncel_user
                st.success(t("succ_profile_save", current_lang))
                st.rerun()
            else:
                st.error(mesaj)
