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

from PIL import Image
from i18n import t
from auth_service import auth_service
from views import (
    admin_kullanicilar,
    admin_takimlar,
    auth_view,
    dashboard,
    hakem,
    karsilastirma,
    yarismaci,
    yonetici,
)
import theme
import sartname_rehber
import docx_gorunum
import pdf_gorunum
from src.database.db import db

# --- LOGO YÜKLEME (modül seviyesinde tek seferlik) ---
_UI_DIR = Path(__file__).resolve().parent
_LOGO_PATH = _UI_DIR / "tsistem_logo.png"
if not _LOGO_PATH.exists():
    _LOGO_PATH = _UI_DIR.parent.parent / "tsistem_logo.png"

# Image.open() pahalı — modül ilk import'ta bir kere çalışır, Streamlit'in
# hot-reload dışında sonraki render'larda tekrar çağrılmaz.
_fav_icon = Image.open(_LOGO_PATH) if _LOGO_PATH.exists() else "🚀"

# --- SAYFA YAPILANDIRMASI ---
st.set_page_config(
    page_title="T-Sistem · TEKNOFEST Kurumsal Portal",
    page_icon=_fav_icon,
    layout="wide",
    initial_sidebar_state="collapsed",
)

theme.inject_history_js(st)

# Dil Seçimi State
if "lang" not in st.session_state:
    st.session_state.lang = "tr"

current_lang = st.session_state.lang


@st.cache_data(show_spinner=False)
def _get_logo_base64() -> str:
    if _LOGO_PATH.exists():
        with open(_LOGO_PATH, "rb") as img_file:
            return f"data:image/png;base64,{base64.b64encode(img_file.read()).decode()}"
    return ""


@st.cache_data(show_spinner=False)
def _get_card_asset_b64(filename: str) -> str:
    asset_path = _UI_DIR / "assets" / filename
    if asset_path.exists():
        with open(asset_path, "rb") as f:
            return f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode()}"
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


# --- TEMA ---
# Onceki surumde burada ~98 satirlik ayri bir CSS blogu vardi ve `theme.py`
# hicbir yerden cagrilmadigi icin uygulama iki farkli tasarim dilinden
# besleniyordu (giris ekrani turuncu, geri kalan her yer Streamlit kirmizisi).
# Artik TEK kaynak `src/ui/theme.py`.
theme.bootstrap(st)

# ── URL TABANLI GERİ/İLERİ NAVİGASYON SİSTEMİ ──────────────────────────────
# Her sayfa geçişi benzersiz bir URL üretir:
#   ?view=landing           → Ana giriş sayfası
#   ?view=comp&slug=XXX     → Yarışma detay sayfası
#   ?view=ann               → Tüm duyurular sayfası
#   ?view=ann_detail&id=XXX → Tekil duyuru detay sayfası
#   ?tab=XXX                → Oturum açık menü sekmesi
#
# Böylece tarayıcının Geri/İleri butonları URL geçmişi üzerinden tam çalışır.
# ─────────────────────────────────────────────────────────────────────────────

# ── AKTİF OTURUM KONTROLÜ (Sayfa yenilemeleri & URL geçişlerinde oturumu koru) ──
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    _persisted_user = auth_service.get_active_session()
    if _persisted_user:
        st.session_state.authenticated = True
        st.session_state.user = _persisted_user

_view = st.query_params.get("view", "")
_slug = st.query_params.get("slug", "")
_ann_id = st.query_params.get("ann_id", "")
_comp_legacy = st.query_params.get("comp", "")  # eski format uyumu

# Eski ?comp= parametresini yeni formata yönlendir
if _comp_legacy and not _view:
    st.query_params["view"] = "comp"
    st.query_params["slug"] = _comp_legacy
    del st.query_params["comp"]
    st.rerun()

# Eski ?ann_id= parametresini yeni formata yönlendir
if _ann_id and not _view:
    st.query_params["view"] = "ann_detail"
    st.rerun()

# ── SAYFA YÖNLENDİRİCİSİ ────────────────────────────────────────────────────
_comp_target = _slug or _comp_legacy or st.query_params.get("id", "") or st.session_state.get("active_comp_detail_slug", "")
if _view == "comp" or st.session_state.get("active_comp_detail_slug"):
    _target_slug = _comp_target or "havacilikta-yapay-zeka"
    from src.ui.views import competition_detail_view
    is_auth = bool(st.session_state.get("authenticated", False))
    competition_detail_view.render_competition_detail_page(_target_slug, is_authenticated=is_auth)
    st.stop()

if _view == "ann_detail" and _ann_id:
    # Tekil Duyuru Detay Sayfası
    ann_item = db.get_announcement(_ann_id)
    if ann_item:
        from src.ui.views import announcement_detail_view
        announcement_detail_view.render_announcement_detail_page(ann_item)
        st.stop()

if _view == "ann":
    # Tüm Duyurular Sayfası
    from src.ui.views import announcements_view
    announcements_view.render_announcements_page()
    st.stop()

# ── Oturum açılmamışsa: Login / Register / Landing yönlendirmesi ───────────────
if "authenticated" not in st.session_state or not st.session_state.authenticated:
    # 1. Google OAuth Callback, Giriş/Kayıt veya Google Profil Tamamlama Modları
    if "code" in st.query_params or _view in ("login", "register") or st.session_state.get("auth_mode") == "google_complete_profile":
        if _view in ("login", "register"):
            st.markdown("""<div style="margin-bottom: 12px;">""", unsafe_allow_html=True)
            c_back, _ = st.columns([1.5, 4])
            with c_back:
                if st.button("← Tanıtım ve Duyurulara Geri Dön", key="btn_back_to_landing", type="secondary"):
                    st.query_params.clear()
                    st.session_state.auth_mode = "login"
                    st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
            if _view == "register":
                st.session_state.auth_mode = "register"
            else:
                st.session_state.auth_mode = "login"
        auth_view.render_auth_view()
        st.stop()

    # show_auth_modal eski session-state tabanlı sistem → URL'e çevir
    if st.session_state.get("show_auth_modal", False):
        st.session_state.show_auth_modal = False
        mode = st.session_state.get("auth_initial_mode", "login")
        st.query_params["view"] = mode  # "login" veya "register"
        st.rerun()
    # Landing sayfasına ?view=landing URL'i ekle
    if not _view or _view == "landing":
        if "tab" in st.query_params:
            del st.query_params["tab"]
        if not _view:
            st.query_params["view"] = "landing"
            st.rerun()
    from src.ui.views import landing_view
    landing_view.render_landing_view()
    st.stop()

# --- OTURUM AÇILMIŞSA T3 KYS ANA PANELİ ---
# Giriş yapılmışken URL'de kalan eski auth/landing parametrelerini temizle
if st.query_params.get("view") in ("login", "register", "landing"):
    del st.query_params["view"]

aktif_kullanici = st.session_state.get("user") or {}
rol = str(aktif_kullanici.get("role", "yarismaci")).lower()

def _rol_varsayilan_sekme(user_role: str) -> str:
    r = str(user_role or "").lower()
    if r == "admin":
        return "intihal"
    return "ana_sayfa"

varsayilan_sekme = _rol_varsayilan_sekme(rol)

rol_sekmeleri = {
    "admin": ["intihal", "kullanicilar", "admin_takimlar", "sartnameler", "yonetici_duyurular", "profil"],
    "hakem": ["ana_sayfa", "degerlendirme", "sartnameler", "profil"],
    "yonetici": ["ana_sayfa", "yonetici_duyurular", "sartnameler", "profil"],
    "yarismaci": ["ana_sayfa", "basvurular", "takimlar", "sartnameler", "profil"],
    "uye": ["ana_sayfa", "basvurular", "takimlar", "sartnameler", "profil"]
}
izin_verilen = rol_sekmeleri.get(rol, rol_sekmeleri["yarismaci"])

_qp_tab = st.query_params.get("tab")
u_id = aktif_kullanici.get("user_id")

if "last_logged_user" not in st.session_state or st.session_state.last_logged_user != u_id:
    st.session_state.last_logged_user = u_id
    if _qp_tab and _qp_tab in izin_verilen:
        st.session_state.aktif_tab = _qp_tab
    elif st.session_state.get("aktif_tab") in izin_verilen:
        st.query_params["tab"] = st.session_state.aktif_tab
    else:
        st.session_state.aktif_tab = varsayilan_sekme
        st.query_params.clear()
        st.query_params["tab"] = varsayilan_sekme
elif _qp_tab and _qp_tab in izin_verilen:
    st.session_state.aktif_tab = _qp_tab
elif "aktif_tab" not in st.session_state or st.session_state.aktif_tab not in izin_verilen:
    st.session_state.aktif_tab = varsayilan_sekme
    st.query_params.clear()
    st.query_params["tab"] = varsayilan_sekme

def git_sekme(yeni_tab: str, subtab: str | None = None):
    """Sekme değiştirildiğinde eski parametreleri temizleyip yeni sekme URL'ini ayarlar."""
    st.session_state.aktif_tab = yeni_tab
    st.query_params.clear()
    st.query_params["tab"] = yeni_tab
    if subtab:
        st.query_params["subtab"] = subtab
    st.rerun()



# Varsayılan Kategori
if "secili_kategori" not in st.session_state:
    st.session_state.secili_kategori = "saglik_yapay_zeka"

# ── TAKIM DAVET KABUL AKIŞI ─────────────────────────────────────────────────
_invite_token = st.query_params.get("accept_team_invite")
if _invite_token:
    st.query_params.clear()
    _invite_data = auth_view_module_unused = None
    try:
        from src.ui.auth_service import auth_service as _inv_svc
        _invite_data = _inv_svc.get_team_invite(_invite_token)
    except Exception:
        pass

    if not _invite_data:
        st.error("Bu davet bağlantısı geçersiz veya süresi dolmuş. Lütfen kaptandan yeni davet isteyin.")
    else:
        _inv_team_id   = _invite_data.get("team_id", "")
        _inv_team_name = _invite_data.get("team_name", "")
        _inv_email     = _invite_data.get("invited_email", "")
        _inv_by        = _invite_data.get("invited_by_name", "")
        _cur_email     = str(aktif_kullanici.get("email", "")).strip().lower()

        if _cur_email and _cur_email != _inv_email:
            st.warning(
                f"Bu davet **{_inv_email}** e-posta adresine gönderildi. "
                f"Şu an **{_cur_email}** hesabıyla giriş yapılı. "
                "Doğru hesapla giriş yapıp bağlantıya tekrar tıklayın."
            )
        else:
            try:
                from src.data import repos as _inv_repos
                from src.data.enums import TeamRole as _TR
                _inv_rp = _inv_repos()
                _inv_user_id = str(aktif_kullanici.get("user_id", "")).strip()
                _inv_team = _inv_rp.teams.get(_inv_team_id)
                _team_adv_email = (_inv_team.advisor_email or "").strip().lower() if _inv_team else ""
                _user_email = str(aktif_kullanici.get("email", "")).strip().lower()

                _assigned_role = _TR.DANISMAN if (_user_email and _team_adv_email and _user_email == _team_adv_email) else _TR.UYE
                _inv_rp.teams.add_member(_inv_team_id, _inv_user_id, _assigned_role)
            except Exception as _inv_ex:
                st.error(f"Takıma katılırken hata oluştu: {_inv_ex}")
                _inv_team_id = ""

            if _inv_team_id:
                try:
                    _inv_svc.clear_team_invite(_invite_token)
                except Exception:
                    pass
                st.success(
                    f"**{_inv_team_name}** takımına başarıyla katıldınız! "
                    "Takımlarım menüsünden takımınızı görüntüleyebilirsiniz."
                )
                st.session_state.aktif_tab = "takimlar"

# ── ÜST SAĞ MİNİ DİL DEĞİŞTİRİCİ ─────────────────────────────────────────────
# Dil desteği henüz tam olmadığı için buton geçici olarak gizlenmiştir.
# top_space, top_lang = st.columns([9.2, 0.8])
# with top_lang:
#     diger_dil = "EN" if current_lang == "tr" else "TR"
#     if st.button(f" {diger_dil}", key="btn_nav_lang_top", use_container_width=True, help="Dili Değiştir / Switch Language"):
#         st.session_state.lang = diger_dil.lower()
#         st.rerun()

# ── GLOBAL DUYURU & DETAY YÖNLENDİRMELERİ ───────────────────────────────────────
_qp_ann_id = st.query_params.get("ann_id")
if _qp_ann_id:
    ann_item = db.get_announcement(_qp_ann_id)
    if ann_item:
        st.session_state.view_announcement_item = ann_item
        st.query_params.clear()
        st.rerun()

if st.session_state.get("view_announcement_item"):
    from src.ui.views import announcement_detail_view
    announcement_detail_view.render_announcement_detail_page(st.session_state.view_announcement_item)
    st.stop()

if st.session_state.get("show_announcements_page", False):
    from src.ui.views import announcements_view
    announcements_view.render_announcements_page()
    st.stop()

# ── YARIŞMA DETAY SAYFASI GÖSTERİMİ (ORTAK MODÜL) ──────────────────────────
if st.session_state.get("view_competition_slug"):
    from src.ui.views import competition_detail_view
    competition_detail_view.render_competition_detail_page(st.session_state.view_competition_slug, is_authenticated=True)
    st.stop()

# ── NAVBAR ───────────────────────────────────────────────────────────────────

n_col1, n_col2 = st.columns([1.5, 3.5])

with n_col1:
    logo_src = _get_logo_base64()
    logo_img = f'<img src="{logo_src}" style="height:72px; width:auto; max-width:140px; object-fit:contain; filter:drop-shadow(0 2px 8px rgba(0,0,0,0.08));" alt="Logo"/>' if logo_src else ''
    st.html(f"""
    <div style="display:flex; align-items:center; gap:16px; margin-top:-4px; margin-bottom:4px;">
        {logo_img}
        <div>
            <div style="font-size:1.55rem; font-weight:900; color:#1E293B; letter-spacing:-0.03em; line-height:1.05;">{t("system_name", current_lang)}</div>
            <div style="font-size:0.75rem; font-weight:800; color:#64748B; letter-spacing:0.05em; text-transform:uppercase; margin-top:4px;">{t("system_sub", current_lang)}</div>
        </div>
    </div>
    """)

with n_col2:
    # 1. YARIŞMACI / ÜYE MENÜSÜ
    if rol in ("yarismaci", "uye"):
        menu_c1, menu_c2, menu_c3, menu_c4, menu_c5, menu_c6 = st.columns([1.1, 1.4, 1.1, 1.1, 1.0, 0.85])
        with menu_c1:
            if st.button(t("nav_home", current_lang), key="nav_home", use_container_width=True, type="primary" if st.session_state.aktif_tab == "ana_sayfa" else "secondary"):
                git_sekme("ana_sayfa")
        with menu_c2:
            if st.button(t("nav_apps", current_lang), key="nav_basvuru", use_container_width=True, type="primary" if st.session_state.aktif_tab == "basvurular" else "secondary"):
                git_sekme("basvurular")
        with menu_c3:
            if st.button(t("nav_teams", current_lang), key="nav_takim", use_container_width=True, type="primary" if st.session_state.aktif_tab == "takimlar" else "secondary"):
                git_sekme("takimlar")
        with menu_c4:
            if st.button(t("nav_specs", current_lang), key="nav_sartname", use_container_width=True, type="primary" if st.session_state.aktif_tab == "sartnameler" else "secondary"):
                git_sekme("sartnameler")
        with menu_c5:
            if st.button(t("nav_profile", current_lang), key="nav_profil", use_container_width=True, type="primary" if st.session_state.aktif_tab == "profil" else "secondary"):
                git_sekme("profil")
        with menu_c6:
            logout_txt = "Çıkış" if current_lang == "tr" else "Logout"
            if st.button(logout_txt, key="nav_logout_yarismaci", use_container_width=True):
                auth_service.clear_active_session()
                st.session_state.authenticated = False
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

    # 2. HAKEM / JÜRİ MENÜSÜ
    elif rol == "hakem":
        menu_c1, menu_c2, menu_c3, menu_c4, menu_c5 = st.columns([1.1, 1.6, 1.4, 1.1, 0.85])
        with menu_c1:
            if st.button(t("nav_home", current_lang), key="nav_home", use_container_width=True, type="primary" if st.session_state.aktif_tab == "ana_sayfa" else "secondary"):
                git_sekme("ana_sayfa")
        with menu_c2:
            if st.button(t("nav_eval", current_lang), key="nav_hakem_eval", use_container_width=True, type="primary" if st.session_state.aktif_tab == "degerlendirme" else "secondary"):
                git_sekme("degerlendirme")
        with menu_c3:
            if st.button(t("nav_specs_criteria", current_lang), key="nav_sartname", use_container_width=True, type="primary" if st.session_state.aktif_tab == "sartnameler" else "secondary"):
                git_sekme("sartnameler")
        with menu_c4:
            if st.button(t("nav_profile", current_lang), key="nav_profil", use_container_width=True, type="primary" if st.session_state.aktif_tab == "profil" else "secondary"):
                git_sekme("profil")
        with menu_c5:
            logout_txt = "Çıkış" if current_lang == "tr" else "Logout"
            if st.button(logout_txt, key="nav_logout_hakem", use_container_width=True):
                auth_service.clear_active_session()
                st.session_state.authenticated = False
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

    # 3. YARIŞMA YÖNETİCİSİ MENÜSÜ
    elif rol == "yonetici":
        menu_c1, menu_c2, menu_c3, menu_c4, menu_c5 = st.columns([1.5, 1.4, 1.1, 1.1, 0.85])
        with menu_c1:
            if st.button(t("nav_admin_yonetim", current_lang), key="nav_home", use_container_width=True, type="primary" if st.session_state.aktif_tab == "ana_sayfa" else "secondary"):
                git_sekme("ana_sayfa")
        with menu_c2:
            if st.button("Duyuru Yönetimi", key="nav_announcements_top_mgr", use_container_width=True, type="primary" if st.session_state.aktif_tab == "yonetici_duyurular" else "secondary"):
                git_sekme("yonetici_duyurular")
        with menu_c3:
            if st.button(t("nav_specs", current_lang), key="nav_sartname", use_container_width=True, type="primary" if st.session_state.aktif_tab == "sartnameler" else "secondary"):
                git_sekme("sartnameler")
        with menu_c4:
            if st.button(t("nav_profile", current_lang), key="nav_profil", use_container_width=True, type="primary" if st.session_state.aktif_tab == "profil" else "secondary"):
                git_sekme("profil")
        with menu_c5:
            logout_txt = "Çıkış" if current_lang == "tr" else "Logout"
            if st.button(logout_txt, key="nav_logout_yonetici", use_container_width=True):
                auth_service.clear_active_session()
                st.session_state.authenticated = False
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

    # 4. SİSTEM YÖNETİCİSİ / ADMİN MENÜSÜ
    else:
        menu_c1, menu_c2, menu_c3, menu_c4, menu_c5, menu_c6 = st.columns([1.3, 1.2, 1.2, 1.2, 1.0, 0.85])
        with menu_c1:
            if st.button(t("nav_admin_intihal", current_lang), key="nav_admin_intihal", use_container_width=True, type="primary" if st.session_state.aktif_tab == "intihal" else "secondary"):
                git_sekme("intihal")
        with menu_c2:
            if st.button(t("nav_admin_users", current_lang), key="nav_admin_users", use_container_width=True, type="primary" if st.session_state.aktif_tab == "kullanicilar" else "secondary"):
                git_sekme("kullanicilar")
        with menu_c3:
            if st.button("Takım Yönetimi", key="nav_admin_takimlar", use_container_width=True, type="primary" if st.session_state.aktif_tab == "admin_takimlar" else "secondary"):
                git_sekme("admin_takimlar")
        with menu_c4:
            if st.button(t("nav_specs", current_lang), key="nav_sartname", use_container_width=True, type="primary" if st.session_state.aktif_tab == "sartnameler" else "secondary"):
                git_sekme("sartnameler")
        with menu_c5:
            if st.button(t("nav_profile", current_lang), key="nav_profil", use_container_width=True, type="primary" if st.session_state.aktif_tab == "profil" else "secondary"):
                git_sekme("profil")
        with menu_c6:
            logout_txt = "Çıkış" if current_lang == "tr" else "Logout"
            if st.button(logout_txt, key="nav_logout_admin", use_container_width=True):
                auth_service.clear_active_session()
                st.session_state.authenticated = False
                st.session_state.user = None
                st.query_params.clear()
                st.rerun()

st.markdown("<hr style='margin: 6px 0 12px 0; border-color: #F1F5F9;'>", unsafe_allow_html=True)

# ==============================================================================
# --- 1. ANA SAYFA GÖRÜNÜMÜ ---
# ==============================================================================
if st.session_state.aktif_tab == "ana_sayfa":
    # 1.1. YARIŞMACI / ÜYE İÇİN ANA SAYFA
    if rol in ("yarismaci", "uye"):
        # --- MODERN HIZLI ERİŞİM KARTLARI ---
        card_c1, card_c2, card_c3, card_c4 = st.columns(4)
        
        img_report_b64 = _get_card_asset_b64("card_report.jpg")
        img_rocket_b64 = _get_card_asset_b64("card_rocket.jpg")
        img_team_b64 = _get_card_asset_b64("card_team.jpg")
        img_spec_b64 = _get_card_asset_b64("card_spec.jpg")

        with card_c1:
            icon_tag = f'<img src="{img_report_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px;" alt="Karne"/>' if img_report_b64 else ''
            st.html(f"""
            <div style="background: linear-gradient(145deg, #FFFFFF, #FFF7ED); border: 1.5px solid #FDBA74; border-radius: 14px; padding: 22px 18px 16px 18px; box-shadow: 0 4px 16px rgba(249, 115, 22, 0.08); display:flex; flex-direction:column; align-items:center; text-align:center; justify-content:space-between; min-height: 200px;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:10px; width:100%;">
                    <div style="width:52px; height:52px; border-radius:12px; background:#FFFFFF; display:flex; align-items:center; justify-content:center; box-shadow:0 3px 10px rgba(249,115,22,0.18); border:1px solid #FFEDD5;">
                        {icon_tag}
                    </div>
                    <div style="font-weight:850; font-size:1.02rem; color:#1E293B; letter-spacing:-0.01em;">Başvurularım & Karne</div>
                    <div style="color:#64748B; font-size:0.84rem; line-height:1.45;">Rapor yükleme, yapay zekâ ön kontrolü ve gelişim karneniz.</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_account", current_lang), key="btn_card_hesabim", use_container_width=True, type="secondary"):
                git_sekme("basvurular")

        with card_c2:
            icon_tag = f'<img src="{img_rocket_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px;" alt="TEKNOFEST"/>' if img_rocket_b64 else ''
            st.html(f"""
            <div style="background: linear-gradient(145deg, #FFF1F2, #FFF7ED); border: 1.5px solid #F43F5E; border-radius: 14px; padding: 22px 18px 16px 18px; box-shadow: 0 4px 16px rgba(244, 63, 94, 0.10); display:flex; flex-direction:column; align-items:center; text-align:center; justify-content:space-between; min-height: 200px;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:10px; width:100%;">
                    <div style="width:52px; height:52px; border-radius:12px; background:#FFFFFF; display:flex; align-items:center; justify-content:center; box-shadow:0 3px 10px rgba(244,63,94,0.18); border:1px solid #FFE4E6;">
                        {icon_tag}
                    </div>
                    <div style="font-weight:850; font-size:1.02rem; color:#1E293B; letter-spacing:-0.01em;">TEKNOFEST 2026</div>
                    <div style="color:#64748B; font-size:0.84rem; line-height:1.45;">Tüm yarışma kategorilerini inceleyin ve anında başvurun.</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_tf", current_lang), key="btn_card_tf", use_container_width=True, type="primary"):
                st.session_state["show_new_app_form"] = True
                git_sekme("basvurular")

        with card_c3:
            icon_tag = f'<img src="{img_team_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px;" alt="Takımlar"/>' if img_team_b64 else ''
            st.html(f"""
            <div style="background: linear-gradient(145deg, #FFFFFF, #EFF6FF); border: 1.5px solid #93C5FD; border-radius: 14px; padding: 22px 18px 16px 18px; box-shadow: 0 4px 16px rgba(59, 130, 246, 0.08); display:flex; flex-direction:column; align-items:center; text-align:center; justify-content:space-between; min-height: 200px;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:10px; width:100%;">
                    <div style="width:52px; height:52px; border-radius:12px; background:#FFFFFF; display:flex; align-items:center; justify-content:center; box-shadow:0 3px 10px rgba(59,130,246,0.18); border:1px solid #DBEAFE;">
                        {icon_tag}
                    </div>
                    <div style="font-weight:850; font-size:1.02rem; color:#1E293B; letter-spacing:-0.01em;">Takımlarım</div>
                    <div style="color:#64748B; font-size:0.84rem; line-height:1.45;">Takım oluşturun, üyelerinizi yönetin ve davet kodu paylaşın.</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_teams", current_lang), key="btn_card_milli", use_container_width=True, type="secondary"):
                git_sekme("takimlar")

        with card_c4:
            icon_tag = f'<img src="{img_spec_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px;" alt="Şartnameler"/>' if img_spec_b64 else ''
            st.html(f"""
            <div style="background: linear-gradient(145deg, #FFFFFF, #F5F3FF); border: 1.5px solid #C4B5FD; border-radius: 14px; padding: 22px 18px 16px 18px; box-shadow: 0 4px 16px rgba(139, 92, 246, 0.08); display:flex; flex-direction:column; align-items:center; text-align:center; justify-content:space-between; min-height: 200px;">
                <div style="display:flex; flex-direction:column; align-items:center; gap:10px; width:100%;">
                    <div style="width:52px; height:52px; border-radius:12px; background:#FFFFFF; display:flex; align-items:center; justify-content:center; box-shadow:0 3px 10px rgba(139,92,246,0.18); border:1px solid #EDE9FE;">
                        {icon_tag}
                    </div>
                    <div style="font-weight:850; font-size:1.02rem; color:#1E293B; letter-spacing:-0.01em;">Şartnameler</div>
                    <div style="color:#64748B; font-size:0.84rem; line-height:1.45;">Resmî teknik şartnameleri ve rapor şablonlarını indirin.</div>
                </div>
            </div>
            """)
            if st.button(t("card_btn_specs", current_lang), key="btn_card_gonullu", use_container_width=True, type="secondary"):
                git_sekme("sartnameler")

        st.markdown("<div id='yarismalar-bolumu' style='margin: 18px 0 10px 0;'></div>", unsafe_allow_html=True)
        if st.session_state.get("scroll_to_vitrin"):
            st.session_state["scroll_to_vitrin"] = False
            st.html("""
            <script>
                setTimeout(() => {
                    const el = window.parent.document.getElementById('yarismalar-bolumu');
                    if (el) {
                        el.scrollIntoView({ behavior: 'smooth', block: 'start' });
                    }
                }, 150);
            </script>
            """)

        # Doğrudan Ana Sayfa İçeriği: Yarışma Vitrini
        yarismaci.render_vitrin(st, aktif_kullanici, current_lang)


    # 1.2. HAKEM / JÜRİ İÇİN ANA SAYFA
    elif rol == "hakem":
        u_id = str(aktif_kullanici.get("user_id", "")).strip()
        
        # Hakeme atanan gerçek raporları D1 üzerinden çek (Tam İzolasyon)
        try:
            from src.data import repos
            r = repos()
            
            # Sadece bu hakeme atanmış kayıtları çek (fallback kesinlikle yok)
            h_reports = r.evaluations.list_for_referee(u_id) if u_id else []
            toplam_atanan = len(h_reports)
            
            # Tamamlanan adet
            tamamlanan_adet = 0
            for rep in h_reports:
                st_raw = str(rep.get("assignment_status") or rep.get("status") or "").upper()
                score = rep.get("referee_score")
                if score is not None or st_raw in ("DEGERLENDIRILDI", "TAMAMLANDI", "COMPLETED"):
                    tamamlanan_adet += 1
                    
        except Exception as e:
            print(f"[APP_HAKEM_HOME] Hata: {e}")
            toplam_atanan = 0
            tamamlanan_adet = 0

        bekleyen_adet = max(0, toplam_atanan - tamamlanan_adet)

        st.html(f"""
        <div class="t3-content-card" style="margin-bottom:16px;">
            <div class="t3-card-title">{t("hk_home_title", current_lang)}</div>
            <div class="t3-card-sub">{t("hk_home_sub", current_lang)}</div>
        </div>
        """)
        hk_c1, hk_c2, hk_c3 = st.columns(3)
        _rapor_lbl = t("hk_metric_rapor", current_lang)
        with hk_c1:
            st.markdown(f"""
            <div style="background: linear-gradient(145deg, #F8FAFC, #F1F5F9); border: 1px solid #E2E8F0; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                <div style="font-size: 0.9rem; font-weight: 700; color: #475569; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">{t('hk_metric_atanan', current_lang)}</div>
                <div style="font-size: 2.2rem; font-weight: 900; color: #0F172A; line-height: 1;">{toplam_atanan}</div>
                <div style="font-size: 0.85rem; color: #64748B; margin-top: 4px;">{_rapor_lbl}</div>
            </div>
            """, unsafe_allow_html=True)
        with hk_c2:
            oran = int((tamamlanan_adet / max(toplam_atanan, 1)) * 100)
            st.markdown(f"""
            <div style="background: linear-gradient(145deg, #F0FDF4, #DCFCE7); border: 1px solid #BBF7D0; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                <div style="font-size: 0.9rem; font-weight: 700; color: #166534; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">{t('hk_metric_tamamlanan', current_lang)}</div>
                <div style="font-size: 2.2rem; font-weight: 900; color: #15803D; line-height: 1;">{tamamlanan_adet}</div>
                <div style="font-size: 0.85rem; color: #166534; margin-top: 4px;">{_rapor_lbl} <b style="background:#22C55E; color:white; padding:2px 6px; border-radius:8px; font-size:0.75rem; margin-left:4px;">%{oran}</b></div>
            </div>
            """, unsafe_allow_html=True)
        with hk_c3:
            st.markdown(f"""
            <div style="background: linear-gradient(145deg, #FEF2F2, #FEE2E2); border: 1px solid #FECACA; border-radius: 12px; padding: 20px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.02);">
                <div style="font-size: 0.9rem; font-weight: 700; color: #991B1B; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px;">{t('hk_metric_bekleyen', current_lang)}</div>
                <div style="font-size: 2.2rem; font-weight: 900; color: #B91C1C; line-height: 1;">{bekleyen_adet}</div>
                <div style="font-size: 0.85rem; color: #991B1B; margin-top: 4px;">{_rapor_lbl}</div>
            </div>
            """, unsafe_allow_html=True)

        st.write("")
        b_c1, b_c2, _ = st.columns([1.4, 1.4, 2.2])
        with b_c1:
            if st.button(t("hk_btn_eval", current_lang), type="primary", use_container_width=True):
                git_sekme("degerlendirme")
        with b_c2:
            if st.button(t("hk_btn_specs", current_lang), use_container_width=True):
                git_sekme("sartnameler")

        st.markdown("<br><hr><br>", unsafe_allow_html=True)
        from src.ui.views import yarismaci
        yarismaci.render_vitrin(st, aktif_kullanici, current_lang)

    # 1.3. YARIŞMA YÖNETİCİSİ İÇİN ANA SAYFA
    elif rol == "yonetici":
        u_ad = aktif_kullanici.get("name", "Yönetici")
        st.html(f"""
        <div class="t3-content-card" style="margin-bottom:20px;">
            <div class="t3-card-title">Yarışma Yönetim Merkezi</div>
            <div class="t3-card-sub">Hoş geldiniz, <strong>{u_ad}</strong>. Kategoriler, aşamalar, şartnameler, değerlendirme kriterleri ve hakem atamaları bu panel üzerinden yürütülür.</div>
        </div>
        """)

        yn_c1, yn_c2, yn_c3, yn_c4 = st.columns(4)
        
        img_yn_comp_b64 = _get_card_asset_b64("card_yn_competitions.jpg")
        img_yn_pool_b64 = _get_card_asset_b64("card_yn_pool.jpg")
        img_yn_rubric_b64 = _get_card_asset_b64("card_yn_rubric.jpg")
        img_yn_templates_b64 = _get_card_asset_b64("card_yn_templates.jpg")

        with yn_c1:
            icon_tag = f'<img src="{img_yn_comp_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px; box-shadow:0 4px 12px rgba(249,115,22,0.20);" alt="Yarışmalar"/>' if img_yn_comp_b64 else ''
            st.html(f"""
            <div style="background:linear-gradient(145deg,#FFFFFF,#FFF7ED);border:1.5px solid #FDBA74;border-radius:14px;padding:20px 18px 14px 18px;box-shadow:0 4px 16px rgba(249,115,22,0.08);min-height:160px;">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                    {icon_tag}
                    <div style="font-weight:800;font-size:0.98rem;color:#1E293B;">Yarışma & Kategoriler</div>
                </div>
                <div style="color:#64748B;font-size:0.84rem;line-height:1.45;">Yarışma oluşturun, aşama ve takvim tanımlayın.</div>
            </div>
            """)
            if st.button("Yarışma Yönetimine Git", key="yn_btn_cat", use_container_width=True, type="primary"):
                st.session_state.yonetici_active_subtab = "competitions"
                st.session_state.aktif_tab = "ana_sayfa"
                st.query_params["tab"] = "ana_sayfa"
                st.query_params["subtab"] = "competitions"
                st.rerun()

        with yn_c2:
            icon_tag = f'<img src="{img_yn_pool_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px; box-shadow:0 4px 12px rgba(59,130,246,0.20);" alt="Hakemler"/>' if img_yn_pool_b64 else ''
            st.html(f"""
            <div style="background:linear-gradient(145deg,#FFFFFF,#EFF6FF);border:1.5px solid #93C5FD;border-radius:14px;padding:20px 18px 14px 18px;box-shadow:0 4px 16px rgba(59,130,246,0.08);min-height:160px;">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                    {icon_tag}
                    <div style="font-weight:800;font-size:0.98rem;color:#1E293B;">Hakem Havuzu</div>
                </div>
                <div style="color:#64748B;font-size:0.84rem;line-height:1.45;">Hakem ekleyin, rapor eşleştirmesi yapın.</div>
            </div>
            """)
            if st.button("Hakem Havuzuna Git", key="yn_btn_hakem", use_container_width=True, type="secondary"):
                st.session_state.yonetici_active_subtab = "pool"
                st.session_state.aktif_tab = "ana_sayfa"
                st.query_params["tab"] = "ana_sayfa"
                st.query_params["subtab"] = "pool"
                st.rerun()

        with yn_c3:
            icon_tag = f'<img src="{img_yn_rubric_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px; box-shadow:0 4px 12px rgba(139,92,246,0.20);" alt="Rubrik"/>' if img_yn_rubric_b64 else ''
            st.html(f"""
            <div style="background:linear-gradient(145deg,#FFFFFF,#F5F3FF);border:1.5px solid #C4B5FD;border-radius:14px;padding:20px 18px 14px 18px;box-shadow:0 4px 16px rgba(139,92,246,0.08);min-height:160px;">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                    {icon_tag}
                    <div style="font-weight:800;font-size:0.98rem;color:#1E293B;">Rubrik & Kriterler</div>
                </div>
                <div style="color:#64748B;font-size:0.84rem;line-height:1.45;">Değerlendirme rubriği ve puanlama kriterlerini belirleyin.</div>
            </div>
            """)
            if st.button("Kriterlere Git", key="yn_btn_rubrik", use_container_width=True, type="secondary"):
                st.session_state.yonetici_active_subtab = "calibration"
                st.session_state.aktif_tab = "ana_sayfa"
                st.query_params["tab"] = "ana_sayfa"
                st.query_params["subtab"] = "calibration"
                st.rerun()

        with yn_c4:
            icon_tag = f'<img src="{img_yn_templates_b64}" style="width:46px; height:46px; object-fit:contain; border-radius:10px; box-shadow:0 4px 12px rgba(34,197,94,0.20);" alt="Şablonlar"/>' if img_yn_templates_b64 else ''
            st.html(f"""
            <div style="background:linear-gradient(145deg,#FFFFFF,#F0FDF4);border:1.5px solid #86EFAC;border-radius:14px;padding:20px 18px 14px 18px;box-shadow:0 4px 16px rgba(34,197,94,0.08);min-height:160px;">
                <div style="display:flex;align-items:center;gap:12px;margin-bottom:10px;">
                    {icon_tag}
                    <div style="font-weight:800;font-size:0.98rem;color:#1E293B;">Şartname & Şablonlar</div>
                </div>
                <div style="color:#64748B;font-size:0.84rem;line-height:1.45;">Şartname PDF ve rapor şablonlarını yükleyin.</div>
            </div>
            """)
            if st.button("Şartnamelere Git", key="yn_btn_sartname", use_container_width=True, type="secondary"):
                st.session_state.aktif_tab = "sartnameler"
                st.query_params["tab"] = "sartnameler"
                if "subtab" in st.query_params:
                    del st.query_params["subtab"]
                st.rerun()

        st.markdown("<hr style='margin:20px 0 16px 0;border-color:#F1F5F9;'>", unsafe_allow_html=True)
        yonetici.goster(st, aktif_kullanici, current_lang)

    # 1.4. SİSTEM YÖNETİCİSİ (ADMİN) İÇİN ANA SAYFA
    # GUVENLIK: eskiden `else:` idi; `yarismaci`/`hakem` disindaki HER rol
    # (tanimsiz roller dahil) admin panelini goruyordu.
    elif rol == "admin":
        dashboard.goster(st, st.session_state.secili_kategori)
    else:
        st.warning(
            "Rolunuz icin tanimli bir ana sayfa bulunamadi. "
            "Lutfen sistem yoneticisi ile iletisime geciniz."
        )

# ==============================================================================
# --- 2. YARIŞMACI: BAŞVURULARIM & GELİŞİM KARNESİ ---
# ==============================================================================
elif st.session_state.aktif_tab == "basvurular":
    if rol in ("yarismaci", "uye"):
        yarismaci.render_basvurular(st, aktif_kullanici, current_lang)
    else:
        st.session_state.aktif_tab = "ana_sayfa"
        st.rerun()

# ==============================================================================
# --- 3. HAKEM / JÜRİ: RAPOR DEĞERLENDİRME & AI 4. GÖZ ---
# ==============================================================================
elif st.session_state.aktif_tab == "degerlendirme":
    if rol == "hakem":
        hakem.goster(st, aktif_kullanici, current_lang)
    elif rol == "admin":
        yonetici.goster(st, aktif_kullanici, current_lang)
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
# --- 5.1. SİSTEM YÖNETİCİSİ: TAKIM YÖNETİM MERKEZİ ---
# ==============================================================================
elif st.session_state.aktif_tab == "admin_takimlar":
    if rol == "admin":
        admin_takimlar.render()
    else:
        st.warning("Bu alana yalnızca Sistem Yöneticisi erişebilir.")
        st.session_state.aktif_tab = "ana_sayfa"
        st.rerun()

# ==============================================================================
# --- 6. TAKIMLARIM (YARIŞMACILAR İÇİN) ---
# ==============================================================================
elif st.session_state.aktif_tab == "takimlar":
    if rol in ("yarismaci", "uye"):
        yarismaci.render_takimlar(st, aktif_kullanici, current_lang)
    else:
        st.warning("Bu alana yalnızca yarışmacılar erişebilir.")
        st.session_state.aktif_tab = "ana_sayfa"
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

    # URL'den alt sekmeyi oku (geri/ileri butonu desteği)
    _sn_url_subtab = st.query_params.get("subtab", "")
    if "sartname_active_subtab" not in st.session_state:
        if _sn_url_subtab in ("specs", "templates"):
            st.session_state.sartname_active_subtab = _sn_url_subtab
        else:
            st.session_state.sartname_active_subtab = "specs"
    elif _sn_url_subtab in ("specs", "templates") and _sn_url_subtab != st.session_state.sartname_active_subtab:
        st.session_state.sartname_active_subtab = _sn_url_subtab

    cur_subtab = st.session_state.sartname_active_subtab

    sw_c1, sw_c2 = st.columns(2)
    with sw_c1:
        btn_type1 = "primary" if cur_subtab == "specs" else "secondary"
        if st.button("1. Teknik Şartnameler (Kurallar & İsterler)", key="sw_btn_specs", use_container_width=True, type=btn_type1):
            st.session_state.sartname_active_subtab = "specs"
            st.query_params["subtab"] = "specs"
            st.rerun()
    with sw_c2:
        btn_type2 = "primary" if cur_subtab == "templates" else "secondary"
        if st.button("2. Rapor Şablonları (Aşama Formatları)", key="sw_btn_templates", use_container_width=True, type=btn_type2):
            st.session_state.sartname_active_subtab = "templates"
            st.query_params["subtab"] = "templates"
            st.rerun()

    st.markdown("<div style='margin-bottom: 12px;'></div>", unsafe_allow_html=True)

    # Tüm 60+ Kategoriyi Yükle
    kat_dict = sartname_rehber.tum_yarismalari_sozluk_getir()
    kat_keys = list(kat_dict.keys())

    # =========================================================================
    # TAB 1: RESMÎ ŞARTNAMELER
    # =========================================================================
    if cur_subtab == "specs":
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
    elif cur_subtab == "templates":
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
# --- 7.1. YARIŞMA YÖNETİCİSİ / ADMİN: MÜSTAKİL DUYURU YÖNETİM EKRANI ---
# ==============================================================================
elif st.session_state.aktif_tab == "yonetici_duyurular":
    if rol in ("yonetici", "admin"):
        yonetici.render_announcements_view(st, aktif_kullanici, current_lang)
    else:
        st.warning("Bu alana yalnızca Yarışma Yöneticisi erişebilir.")
        st.session_state.aktif_tab = "ana_sayfa"
        st.rerun()

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
