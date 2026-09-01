"""T-Sistem · Kurumsal Giriş, Kayıt ve Cloudflare D1 Tabanlı Google Auth Akışı.

- Gerçek Google OAuth 2.0 Doğrulama (Google Hesap Seçici).
- Kullanıcı Google hesabını seçtiğinde sunucu kodu takas eder ve Cloudflare D1 veritabanına kaydeder.
- T3 KYS eksik alanları (Telefon, Cinsiyet, Adres vb.) kontrol edilir ve eksik bilgi tamamlama ekranına yönlendirilir.
- Tamamlanınca Cloudflare D1 üzerinde profil onaylanır ve sisteme giriş yapılır.
"""

from __future__ import annotations

import hmac
import json
import secrets
import tempfile
import time
import urllib.parse
from datetime import date
from pathlib import Path
import streamlit as st
from auth_service import auth_service
from firebase_config import FIREBASE_CONFIG
from i18n import t

# OAuth state geçici klasörü (redirect sonrası session_state sıfırlanır, dosya sistemi kalıcıdır)
_STATE_DIR = Path(tempfile.gettempdir()) / "tsistem_oauth_states"

_UI_DIR = Path(__file__).resolve().parent.parent
_LOGO_PATH = _UI_DIR / "tsistem_logo.png"
if not _LOGO_PATH.exists():
    _LOGO_PATH = _UI_DIR.parent.parent / "tsistem_logo.png"


def _get_google_auth_url(redirect_comp: str = "") -> str:
    """Dogrulanmis Google OAuth 2.0 yonlendirme linkini uretir (state ile)."""
    client_id = FIREBASE_CONFIG.get("clientId", "")
    params = {
        "client_id": client_id,
        "redirect_uri": _redirect_uri(),
        "state": _issue_oauth_state(redirect_comp),
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def _redirect_uri() -> str:
    """OAuth donus adresi. Prod'da .env icindeki TSISTEM_OAUTH_REDIRECT kullanilir."""
    import os
    return os.getenv("TSISTEM_OAUTH_REDIRECT", "http://localhost:8501").rstrip("/")


def _issue_oauth_state(redirect_comp: str = "") -> str:
    """CSRF korumasi: state'i gecici dosyaya yazar (redirect sonrasi session_state sifirlanir)."""
    state = secrets.token_urlsafe(24)
    _STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_file = _STATE_DIR / f"{state}.json"
    state_file.write_text(json.dumps({"state": state, "ts": time.time(), "redirect_comp": redirect_comp}))
    # 10 dakikadan eski dosyaları temizle
    for old in _STATE_DIR.glob("*.json"):
        try:
            if time.time() - json.loads(old.read_text()).get("ts", 0) > 600:
                old.unlink(missing_ok=True)
        except Exception:
            pass
    return state


def _verify_oauth_state(received: str | None) -> tuple[bool, dict]:
    """State'i gecici dosyadan okur ve tek kullanim sonrasi siler."""
    if not received:
        return False, {}
    # Güvenlik: yalnızca alfanumerik + - _ karakterlerine izin ver
    safe = all(c.isalnum() or c in "-_" for c in received)
    if not safe:
        return False, {}
    state_file = _STATE_DIR / f"{received}.json"
    if not state_file.exists():
        return False, {}
    try:
        data = json.loads(state_file.read_text())
        state_file.unlink(missing_ok=True)  # tek kullanım
        stored = data.get("state", "")
        if time.time() - data.get("ts", 0) > 600:  # 10 dk geçmişse geçersiz
            return False, {}
        if hmac.compare_digest(str(stored), str(received)):
            return True, data
        return False, {}
    except Exception:
        return False, {}


def render_auth_view() -> None:
    """T-Sistem ana giriş, kayıt ve Google OAuth görünümü."""
    current_lang = st.session_state.get("lang", "tr")

    # 0. Terk edilmiş eksik kayıtları temizle
    auth_service.cleanup_incomplete_users()

    # 1. Google OAuth 2.0 Callback'ten dönen `code` parametresini yakala
    query_params = st.query_params
    if "code" in query_params:
        auth_code = query_params["code"]
        received_state = query_params.get("state")
        st.query_params.clear()
        is_valid, state_data = _verify_oauth_state(received_state)
        if not is_valid:
            st.error(t("auth_oauth_state_error", current_lang) if "current_lang" in dir() else
                     "Google oturum dogrulamasi guvenlik kontrolunden gecemedi. Lutfen yeniden deneyiniz.")
            auth_code = ""
        
        redirect_comp_from_state = state_data.get("redirect_comp", "")
        
        # Sunucu tarafında Google ile güvenli takas yap
        profile = auth_service.exchange_google_code(auth_code, _redirect_uri()) if auth_code else None
        if profile and profile.get("email"):
            user, is_complete, missing_fields = auth_service.handle_google_auth({
                "email": profile["email"],
                "name": profile.get("name", profile["email"].split("@")[0])
            })
            if is_complete:
                st.session_state.authenticated = True
                st.session_state.user = user
                auth_service.set_active_session(user)
                target_comp = redirect_comp_from_state or st.session_state.get("target_apply_comp") or st.query_params.get("redirect_comp")
                st.query_params.clear()
                if target_comp:
                    st.session_state.pop("target_apply_comp", None)
                    st.query_params["view"] = "comp"
                    st.query_params["slug"] = target_comp
                else:
                    st.query_params["tab"] = "ana_sayfa"
                st.rerun()
                st.stop()
            else:
                if redirect_comp_from_state:
                    st.session_state.target_apply_comp = redirect_comp_from_state
                st.session_state.pending_google_user = user
                st.session_state.missing_fields = missing_fields
                st.session_state.auth_mode = "google_complete_profile"
                st.rerun()
                st.stop()
        else:
            st.error(t("auth_google_failed", st.session_state.get("lang", "tr")))

    # 2. GUVENLIK: "google_email" query parametresiyle giris KALDIRILDI.
    #        http://localhost:8501/?google_email=admin@tsistem.org
    #    Bu adresi acan herkes sifresiz TAM ADMIN oturumu aciyordu; bilinmeyen bir
    #    e-posta girildiginde ise otomatik yeni hesap olusuyordu.
    #
    #    Google girisi artik YALNIZCA yukaridaki (1) numarali OAuth callback
    #    akisindan, sunucu tarafi kod takasi ve state dogrulamasiyla yapilir.
    for _legacy_param in ("google_email", "google_login_email", "google_name", "google_login_name"):
        if _legacy_param in query_params:
            st.query_params.clear()
            st.error(
                "Guvenlik nedeniyle adres cubugu uzerinden giris devre disi birakilmistir. "
                "Lutfen 'Google ile Giris Yap' butonunu kullaniniz."
            )
            break

    if "lang" not in st.session_state:
        st.session_state.lang = "tr"
    
    current_lang = st.session_state.lang

    if st.query_params.get("auth_mode") == "forgot_password":
        st.session_state.auth_mode = "forgot_password"

    if "auth_mode" not in st.session_state:
        st.session_state.auth_mode = "login"

    # --- 3. GOOGLE EKSİK BİLGİLERİ TAMAMLAMA EKRANI ---
    if st.session_state.auth_mode == "google_complete_profile":
        _render_google_complete_profile_view(current_lang)
        return

    is_login_active = (st.session_state.auth_mode == "login")

    # Hem Giriş Yap hem Kayıt Ol için birebir aynı ortalama ve ferah genişlik
    _, col_center, _ = st.columns([0.15, 3.7, 0.15])

    with col_center:
        # Karta turuncu üst şerit
        st.html("""
        <style>
            div[data-testid="stVerticalBlockBorderWrapper"] > div > div > div[data-testid="stVerticalBlock"] {
                border-top: 4px solid var(--ts-brand) !important;
                border-radius: 12px !important;
            }
        </style>
        """)
        with st.container(border=True):
            # Sağ Üst Mini Dil Seçimi
            d1, d2 = st.columns([4.2, 0.8])
            with d2:
                diger_dil = "EN" if current_lang == "tr" else "TR"
                if st.button(f"🌐 {diger_dil}", key="btn_lang_switch", use_container_width=True, help="Dili Değiştir / Switch Language"):
                    st.session_state.lang = diger_dil.lower()
                    st.rerun()

            # Logo
            sub_c1, sub_c2, sub_c3 = st.columns([1.5, 1.0, 1.5])
            with sub_c2:
                if _LOGO_PATH.exists():
                    st.image(str(_LOGO_PATH), use_container_width=True)

            # Başlık ve Açıklama
            st.html(f"""
            <div style="text-align:center; margin-top:-6px; margin-bottom:18px;">
                <div style="font-size:1.6rem; font-weight:800; color:var(--ts-brand);">{t("app_title", current_lang)}</div>
                <div style="font-size:0.92rem; color:var(--ts-muted); margin-top:2px;">{t("app_subtitle", current_lang)}</div>
            </div>
            """)

            # --- 1. ŞİFREMİ UNUTTUM EKRANI (Üst Sekmeler Gizlenir) ---
            if st.session_state.get("auth_mode") == "forgot_password":
                _render_forgot_password_form(current_lang)

            # --- 2. GİRİŞ YAP VEYA KAYIT OL EKRANI (Üst Sekmeler Gösterilir) ---
            else:
                # Giriş Yap & Kayıt Ol Sekmeleri
                # Aktif sekme → type="primary" (tema turuncu gradient'ini otomatik alır)
                # Pasif sekme → type="secondary" (beyaz/açık zemin)
                t_col1, t_col2 = st.columns(2)
                with t_col1:
                    if st.button(
                        t("tab_email_login", current_lang),
                        key="tab_btn_login",
                        use_container_width=True,
                        type="primary" if is_login_active else "secondary",
                    ):
                        st.session_state.auth_mode = "login"
                        st.query_params["view"] = "login"
                        st.rerun()
                with t_col2:
                    if st.button(
                        t("tab_register", current_lang),
                        key="tab_btn_reg",
                        use_container_width=True,
                        type="primary" if not is_login_active else "secondary",
                    ):
                        st.session_state.auth_mode = "register"
                        st.query_params["view"] = "register"
                        st.rerun()

                st.write("")

                if is_login_active:
                    _render_login_form(current_lang)
                else:
                    _render_register_form(current_lang)


def _render_google_oauth_button(current_lang: str, is_register: bool = False) -> None:
    """Doğrudan Google OAuth 2.0 Yetkilendirmesi Başlatan Şık Buton."""
    btn_text = t("google_register" if is_register else "google_login", current_lang)
    target_comp = st.query_params.get("redirect_comp") or st.session_state.get("target_apply_comp") or ""
    auth_url = _get_google_auth_url(target_comp)

    st.html(f"""
    <style>
        .google-auth-card-btn {{
            display: flex !important;
            align-items: center !important;
            justify-content: center !important;
            gap: 12px !important;
            width: 100% !important;
            background: #FFFFFF !important;
            border: 1.5px solid #CBD5E1 !important;
            border-radius: 10px !important;
            padding: 11px 16px !important;
            font-weight: 700 !important;
            font-size: 0.95rem !important;
            color: #1E293B !important;
            text-decoration: none !important;
            box-shadow: 0 2px 6px rgba(0, 0, 0, 0.06) !important;
            transition: all 0.2s ease-in-out !important;
            box-sizing: border-box !important;
        }}
        .google-auth-card-btn:hover {{
            background: #F8FAFC !important;
            border-color: #94A3B8 !important;
            box-shadow: 0 4px 14px rgba(0, 0, 0, 0.10) !important;
            transform: translateY(-1px) !important;
            color: #0F172A !important;
        }}
        .google-auth-card-btn img {{
            width: 22px !important;
            height: 22px !important;
            object-fit: contain !important;
            flex-shrink: 0 !important;
            display: inline-block !important;
        }}
    </style>
    <a href="{auth_url}" target="_self" style="text-decoration:none; display:block; width:100%;">
        <div class="google-auth-card-btn">
            <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="Google Logo" />
            <span>{btn_text}</span>
        </div>
    </a>
    """)


def _render_login_form(current_lang: str) -> None:
    """Giriş Yap formu."""
    st.html(f"""
    <div style="text-align:center; margin-bottom:14px;">
        <div style="font-size:1.25rem; font-weight:800; color:var(--ts-brand);">{t("login_title", current_lang)}</div>
        <div style="font-size:0.85rem; color:var(--ts-muted);">{t("login_sub", current_lang)}</div>
    </div>
    """)

    # Canlı Google OAuth Butonu
    _render_google_oauth_button(current_lang, is_register=False)

    st.html(f'<div style="text-align:center; color:var(--ts-muted); font-size:0.78rem; margin: 14px 0 16px 0;">{t("or_with_email", current_lang)}</div>')

    # Form Submit Butonlarını Turuncu Yapan & Textbox Zeminini Belirginleştiren CSS
    # NOT: Buradaki input + submit buton CSS blogu KALDIRILDI.
    #      Eski kodda bu blok YALNIZCA giris formunda enjekte ediliyordu; kayit,
    #      sifre sifirlama ve profil tamamlama formlari bu CSS'i hic gormuyordu.
    #      Sonuc: "Giris Yap" sekmesinde buton turuncu, "Kayit Ol" sekmesine
    #      gecildiginde AYNI EKRANDA Streamlit kirmizisina donuyordu.
    #      Artik tum formlar src/ui/theme.py uzerinden ayni stili aliyor.

    saved_email = auth_service.get_remembered_email()

    with st.form("form_t3kys_login", clear_on_submit=False):
        l_c1, l_c2 = st.columns(2)
        with l_c1:
            email = st.text_input(t("email_label", current_lang), value=saved_email, placeholder=t("email_placeholder", current_lang), autocomplete="username")
        with l_c2:
            password = st.text_input(t("password_label", current_lang), type="password", placeholder=t("password_placeholder", current_lang), autocomplete="current-password")

        # Sol tarafta Şifremi Unuttum (tıklanabilir metin), Sağ tarafta Beni Hatırla (varsayılan işaretsiz)
        act_c1, act_c2 = st.columns([1.2, 1.0])
        with act_c1:
            st.markdown(
                f"""
                <div style="padding-top:4px;">
                    <a href="?auth_mode=forgot_password" target="_self" style="color:var(--ts-info); font-size:0.88rem; font-weight:700; text-decoration:underline; cursor:pointer;">
                        {t("forgot_password_link", current_lang)}
                    </a>
                </div>
                """,
                unsafe_allow_html=True
            )
        with act_c2:
            remember_me = st.checkbox(t("remember_me", current_lang), value=False, key="chk_remember_me")

        st.write("")
        submit_btn = st.form_submit_button(t("login_btn", current_lang), type="primary", use_container_width=True)

        if submit_btn:
            if not email or not password:
                st.error(t("err_fill_fields", current_lang))
            else:
                user = auth_service.authenticate(email, password)
                if user:
                    # Beni Hatırla durumuna göre e-postayı kaydet / temizle
                    auth_service.save_remembered_email(email, remember_me)
                    auth_service.set_active_session(user)
                    st.session_state.authenticated = True
                    st.session_state.user = user
                    u_role = str(user.get("role", "")).lower()
                    
                    target_comp = st.session_state.get("target_apply_comp") or st.query_params.get("redirect_comp")
                    st.query_params.clear()
                    
                    if target_comp:
                        st.session_state.pop("target_apply_comp", None)
                        st.query_params["view"] = "comp"
                        st.query_params["slug"] = target_comp
                    elif u_role == "admin":
                        st.session_state.aktif_tab = "intihal"
                        st.query_params["tab"] = "intihal"
                    else:
                        st.session_state.aktif_tab = "ana_sayfa"
                        st.query_params["tab"] = "ana_sayfa"
                    st.rerun()
                    st.stop()
                else:
                    st.error(t("err_invalid_login", current_lang))


def _render_forgot_password_form(current_lang: str) -> None:
    """Şifremi Unuttum / Cloudflare & E-Posta Doğrulamalı Şifre Sıfırlama Formu."""
    st.html(f"""
    <div style="text-align:center; margin-bottom:14px;">
        <div style="font-size:1.25rem; font-weight:800; color:var(--ts-brand);">{t("fp_title", current_lang)}</div>
        <div style="font-size:0.85rem; color:var(--ts-muted);">{t("fp_sub", current_lang)}</div>
    </div>
    """)

    reset_stage = st.session_state.get("pw_reset_stage", "email_step")
    target_email = st.session_state.get("pw_reset_email", "")

    if reset_stage == "email_step":
        with st.form("form_t3kys_forgot_pw_email", clear_on_submit=False):
            fp_email = st.text_input(t("fp_email_label", current_lang), placeholder="ornek@alanadi.com", autocomplete="email")
            st.write("")
            fp_mail_btn = st.form_submit_button(t("fp_send_btn", current_lang), type="primary", use_container_width=True)

            if fp_mail_btn:
                clean_email = fp_email.strip().lower()
                if not clean_email or "@" not in clean_email:
                    st.error(t("fp_err_email", current_lang))
                else:
                    # Cloudflare D1 & SQLite üzerinde e-posta kontrolü
                    user = auth_service.get_user_by_email(clean_email)
                    if not user:
                        # Sistemde kayıtlı değilse anında hata ver
                        st.error(f"HATA: '{clean_email}' e-posta adresi sistemimizde kayıtlı değildir! Lütfen T-Sistem'e kayıtlı olduğunuz e-posta adresini giriniz.")
                    else:
                        import random
                        simulated_code = str(random.randint(100000, 999999))
                        st.session_state.pw_reset_email = clean_email
                        st.session_state.pw_reset_code = simulated_code
                        st.session_state.pw_reset_stage = "code_step"
                        
                        # SMTP veya yerel bildirim ile gönder
                        auth_service.send_password_reset_email(clean_email, simulated_code)
                        st.rerun()

    else:
        # Kod Gönderildi - Yeni Şifre Belirleme Aşaması
        st.success(f"✓ **E-posta Doğrulandı:** `{target_email}` adresi için 6 haneli güvenlik doğrulama kodu oluşturuldu.")
        
        st.info(
            f"6 haneli doğrulama kodu **{target_email}** adresine gönderildi. "
            f"Lütfen e-posta kutunuzu kontrol ediniz."
        )

        with st.form("form_t3kys_forgot_pw_new", clear_on_submit=False):
            st.markdown(f"<div style='font-size:0.88rem; color:var(--ts-ink); margin-bottom:8px;'><b>Hedef E-Posta:</b> {target_email}</div>", unsafe_allow_html=True)

            fp_code = st.text_input(t("fp_code_label", current_lang), placeholder="6 haneli kodu giriniz")
            
            fp_c1, fp_c2 = st.columns(2)
            with fp_c1:
                fp_p1 = st.text_input(t("fp_new_pass", current_lang), type="password", placeholder=t("fp_new_pass_ph", current_lang), autocomplete="new-password")
            with fp_c2:
                fp_p2 = st.text_input(t("fp_new_pass_repeat", current_lang), type="password", placeholder=t("fp_new_pass_repeat_ph", current_lang), autocomplete="new-password")

            st.write("")
            fp_submit = st.form_submit_button(t("fp_save_btn", current_lang), type="primary", use_container_width=True)

            if fp_submit:
                expected_code = str(st.session_state.get("pw_reset_code", "")).strip()
                if not fp_code or not fp_p1 or not fp_p2:
                    st.error(t("fp_err_all_fields", current_lang))
                elif fp_code.strip() != expected_code:
                    st.error(f"HATA: Girdiğiniz güvenlik kodu ({fp_code}) hatalıdır! Lütfen size iletilen 6 haneli kodu giriniz.")
                elif fp_p1 != fp_p2:
                    st.error(t("fp_err_pass_mismatch", current_lang))
                elif len(fp_p1) < 6:
                    st.error(t("fp_err_pass_short", current_lang))
                else:
                    # Cloudflare D1 ve SQLite şifre güncelleme
                    basari, msg = auth_service.reset_password(target_email, fp_p1)
                    if basari:
                        st.session_state.pw_reset_stage = "email_step"
                        st.session_state.pw_reset_email = ""
                        st.session_state.pw_reset_code = ""
                        if "auth_mode" in st.query_params:
                            del st.query_params["auth_mode"]
                        st.session_state.auth_mode = "login"
                        st.success(f"✓ {msg}")
                        st.rerun()
                    else:
                        st.error(msg)

    st.write("")
    if st.button(t("fp_back_btn", current_lang), key="btn_back_to_login", use_container_width=True):
        st.session_state.pw_reset_stage = "email_step"
        st.session_state.pw_reset_email = ""
        st.session_state.pw_reset_code = ""
        if "auth_mode" in st.query_params:
            del st.query_params["auth_mode"]
        st.session_state.auth_mode = "login"
        st.rerun()


def _render_register_form(current_lang: str) -> None:
    """Kayıt Ol formu."""
    st.html(f"""
    <div style="text-align:center; margin-bottom:14px;">
        <div style="font-size:1.25rem; font-weight:800; color:var(--ts-brand);">{t("reg_title", current_lang)}</div>
        <div style="font-size:0.85rem; color:var(--ts-muted);">{t("reg_sub", current_lang)}</div>
    </div>
    """)

    _render_google_oauth_button(current_lang, is_register=True)

    st.html(f'<div style="text-align:center; color:var(--ts-muted); font-size:0.78rem; margin: 12px 0 14px 0;">{t("or_with_info", current_lang)}</div>')

    with st.form("form_t3kys_full_register", clear_on_submit=False):
        # BÖLÜM 1: PANEL BİLGİLERİ
        st.markdown(f'<div class="t3-form-section">{t("reg_sec_panel", current_lang)}</div>', unsafe_allow_html=True)
        p_c1, p_c2, p_c3, p_c4 = st.columns(4)
        with p_c1:
            kullanici_adi = st.text_input(t("reg_username", current_lang), placeholder=t("reg_username_ph", current_lang))
        with p_c2:
            reg_email = st.text_input(t("reg_email_lbl", current_lang), placeholder="ornek@alanadi.com")
        with p_c3:
            reg_pass1 = st.text_input(t("reg_pass_lbl", current_lang), type="password", placeholder=t("reg_pass_ph", current_lang))
        with p_c4:
            reg_pass2 = st.text_input(t("reg_pass_repeat", current_lang), type="password", placeholder=t("reg_pass_repeat_ph", current_lang))

        st.markdown('<hr class="t3-sep">', unsafe_allow_html=True)

        # BÖLÜM 2: KİŞİSEL BİLGİLER
        st.markdown(f'<div class="t3-form-section">{t("reg_sec_personal", current_lang)}</div>', unsafe_allow_html=True)
        k_c1, k_c2, k_c3, k_c4 = st.columns(4)
        with k_c1:
            reg_ad = st.text_input(t("reg_first_name", current_lang), placeholder=t("reg_first_name_ph", current_lang))
        with k_c2:
            reg_soyad = st.text_input(t("reg_last_name", current_lang), placeholder=t("reg_last_name_ph", current_lang))
        with k_c3:
            tc_vatandasi = st.selectbox(t("reg_tc_citizen", current_lang), [t("reg_tc_select", current_lang), t("reg_tc_yes", current_lang), t("reg_tc_no", current_lang)])
        with k_c4:
            cinsiyet = st.selectbox(t("reg_gender", current_lang), [t("reg_tc_select", current_lang), t("reg_gender_male", current_lang), t("reg_gender_female", current_lang)])

        k2_c1, k2_c2, k2_c3, k2_c4 = st.columns(4)
        with k2_c1:
            dogum_tarihi = st.date_input(t("reg_birth_date", current_lang))
        with k2_c2:
            tel_kod = st.selectbox(t("reg_country_code", current_lang), ["+90 (TR)", "+1 (US)", "+44 (UK)", "+49 (DE)"])
        with k2_c3:
            cep_tel = st.text_input(t("reg_phone", current_lang), placeholder="(5XX) XXX XX XX")
        with k2_c4:
            haberdar = st.selectbox(t("reg_how_heard", current_lang), [t("reg_tc_select", current_lang), t("reg_how_social", current_lang), t("reg_how_school", current_lang), t("reg_how_friend", current_lang), "TEKNOFEST"])

        st.markdown('<hr class="t3-sep">', unsafe_allow_html=True)

        # BÖLÜM 3: ADRES BİLGİLERİ
        st.markdown(f'<div class="t3-form-section">{t("reg_sec_address", current_lang)}</div>', unsafe_allow_html=True)
        a_c1, a_c2 = st.columns([1, 3])
        with a_c1:
            ulke = st.selectbox(t("reg_country", current_lang), [t("reg_country_turkey", current_lang), t("reg_country_other", current_lang)])
        with a_c2:
            adres = st.text_input(t("reg_address", current_lang), placeholder=t("reg_address_ph", current_lang))

        st.markdown('<hr class="t3-sep">', unsafe_allow_html=True)

        # BÖLÜM 4: EĞİTİM BİLGİLERİ
        st.markdown(f'<div class="t3-form-section">{t("reg_sec_education", current_lang)}</div>', unsafe_allow_html=True)
        st.checkbox(t("reg_graduate_chk", current_lang))

        e_c1, e_c2 = st.columns(2)
        with e_c1:
            egitim_seviyesi = st.selectbox(t("reg_edu_level", current_lang), [t("reg_tc_select", current_lang), "İlkokul", "Ortaokul", "Lise", "Önlisans", "Lisans", "Yüksek Lisans", "Doktora"])
        with e_c2:
            okul_adi = st.text_input(t("reg_school_other", current_lang), placeholder=t("reg_school_other_ph", current_lang))

        st.markdown('<hr class="t3-sep">', unsafe_allow_html=True)

        # BÖLÜM 5: ONAY VE AYDINLATMA METİNLERİ
        kvkk1 = st.checkbox(t("reg_kvkk1", current_lang), value=True)
        kvkk2 = st.checkbox(t("reg_kvkk2", current_lang), value=True)
        kvkk3 = st.checkbox(t("reg_kvkk3", current_lang), value=True)

        st.write("")
        submit_reg = st.form_submit_button(t("register_btn", current_lang), type="primary", use_container_width=True)

        if submit_reg:
            if not reg_ad or not reg_soyad or not reg_email or not reg_pass1:
                st.error(t("err_fill_fields", current_lang))
            elif reg_pass1 != reg_pass2:
                st.error(t("err_pass_mismatch", current_lang))
            elif not (kvkk1 and kvkk2):
                st.error(t("err_accept_kvkk", current_lang))
            else:
                ad_tam = f"{reg_ad.strip()} {reg_soyad.strip()}"
                basari, msg = auth_service.register_user(
                    name=ad_tam,
                    email=reg_email,
                    password=reg_pass1,
                    username=kullanici_adi,
                    role="yarismaci",
                    institution=okul_adi or "Belirtilmedi",
                    tc_citizen=tc_vatandasi,
                    gender=cinsiyet,
                    birth_date=str(dogum_tarihi),
                    phone=f"{tel_kod} {cep_tel}".strip(),
                    address=f"{ulke} - {adres}".strip(),
                    education_level=egitim_seviyesi,
                )
                if basari:
                    st.success(t("succ_reg", current_lang))
                    st.session_state.auth_mode = "login"
                    st.rerun()
                else:
                    st.error(msg)


def _render_google_complete_profile_view(current_lang: str) -> None:
    """Google ile giriş sonrası eksik zorunlu bilgileri tamamlama sayfası."""
    pending_user = st.session_state.get("pending_google_user", {})

    _, col_center, _ = st.columns([0.15, 3.7, 0.15])

    with col_center:
        with st.container(border=True):
            # Geri Dön Butonu (Eksik kullanıcıyı veritabanından tamamen siler)
            if st.button(t("gc_back_btn", current_lang), key="btn_back_to_login"):
                if pending_user.get("user_id"):
                    auth_service.delete_user_by_id(pending_user.get("user_id"))
                st.session_state.pending_google_user = None
                st.session_state.auth_mode = "login"
                st.rerun()

            # Üst Bar & Logo
            sub_c1, sub_c2, sub_c3 = st.columns([1.5, 1.0, 1.5])
            with sub_c2:
                if _LOGO_PATH.exists():
                    st.image(str(_LOGO_PATH), use_container_width=True)

            st.html(f"""
            <div style="text-align:center; margin-bottom:16px;">
                <div style="font-size:1.5rem; font-weight:800; color:var(--ts-brand);">{t("google_complete_title", current_lang)}</div>
                <div style="font-size:0.88rem; color:var(--ts-muted); margin-top:2px;">{t("google_complete_sub", current_lang)}</div>
            </div>
            <div style="background:var(--ts-ok-soft); border:1.5px solid var(--ts-ok); border-radius:8px; padding:12px 18px; margin-bottom:18px; display:flex; align-items:center; justify-content:space-between;">
                <div>
                    <span style="color:var(--ts-ok-ink); font-weight:700;">Google Hesabı:</span> <b>{pending_user.get('name', '')}</b> ({pending_user.get('email', '')})
                </div>
                <span style="background:var(--ts-ok); color:var(--ts-on-brand); font-size:0.75rem; font-weight:700; padding:4px 12px; border-radius:12px;">✓ {t("google_verified_badge", current_lang)}</span>
            </div>
            """)

            with st.form("form_google_complete_profile", clear_on_submit=False):
                # BÖLÜM 1: PANEL VE KİŞİSEL BİLGİLER
                st.markdown(f'<div class="t3-form-section">{t("gc_sec_personal", current_lang)}</div>', unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    username = st.text_input(t("gc_username_lbl", current_lang), value=pending_user.get("username", ""))
                with c2:
                    tc_vatandasi = st.selectbox(t("reg_tc_citizen", current_lang), [t("reg_tc_yes", current_lang), t("reg_tc_no", current_lang)])
                with c3:
                    cinsiyet = st.selectbox(t("reg_gender", current_lang), [t("reg_tc_select", current_lang), t("reg_gender_male", current_lang), t("reg_gender_female", current_lang)])
                with c4:
                    dogum_tarihi = st.date_input(t("reg_birth_date", current_lang), value=date(2000, 1, 1))

                st.markdown('<hr class="t3-sep">', unsafe_allow_html=True)

                # BÖLÜM 2: İLETİŞİM VE ADRES BİLGİLERİ
                st.markdown(f'<div class="t3-form-section">{t("gc_sec_contact", current_lang)}</div>', unsafe_allow_html=True)
                i1, i2, i3 = st.columns([1, 1.5, 2.5])
                with i1:
                    tel_kod = st.selectbox(t("gc_country_code", current_lang), ["+90 (TR)", "+1 (US)", "+44 (UK)", "+49 (DE)"])
                with i2:
                    phone_input = st.text_input(t("gc_phone", current_lang), placeholder=t("gc_phone_ph", current_lang))
                with i3:
                    address_input = st.text_input(t("gc_address", current_lang), placeholder=t("gc_address_ph", current_lang))

                st.markdown('<hr class="t3-sep">', unsafe_allow_html=True)

                # BÖLÜM 3: EĞİTİM BİLGİLERİ
                st.markdown(f'<div class="t3-form-section">{t("gc_sec_education", current_lang)}</div>', unsafe_allow_html=True)
                e1, e2 = st.columns(2)
                with e1:
                    education_level = st.selectbox(t("gc_edu_level", current_lang), ["Seçiniz", "Önlisans", "Lisans", "Yüksek Lisans", "Doktora", "Lise"])
                with e2:
                    institution = st.text_input(t("gc_institution", current_lang), placeholder=t("gc_institution_ph", current_lang))

                st.markdown('<hr class="t3-sep">', unsafe_allow_html=True)

                # BÖLÜM 4: KVKK ONAY
                kvkk_check = st.checkbox(t("gc_kvkk", current_lang), value=True)

                st.write("")
                btn_c1, btn_c2, btn_c3 = st.columns([1, 1.6, 1])
                with btn_c2:
                    save_btn = st.form_submit_button(t("save_and_continue", current_lang), type="primary", use_container_width=True)

                if save_btn:
                    if not username or not phone_input or not address_input or cinsiyet == "Seçiniz" or education_level == "Seçiniz":
                        st.error(t("gc_err_fill_fields", current_lang))
                    elif not kvkk_check:
                        st.error(t("gc_err_kvkk", current_lang))
                    else:
                        full_phone = f"{tel_kod} {phone_input}".strip()
                        profile_data = {
                            "username": username,
                            "tc_citizen": tc_vatandasi,
                            "gender": cinsiyet,
                            "birth_date": str(dogum_tarihi),
                            "phone": full_phone,
                            "address": address_input,
                            "education_level": education_level,
                            "institution": institution,
                            "department": "",
                        }
                        
                        is_new = pending_user.get("is_new", False) or not pending_user.get("user_id")
                        if is_new:
                            success, msg = auth_service.create_google_user(
                                email=pending_user.get("email", ""),
                                name=pending_user.get("name", ""),
                                profile_data=profile_data,
                            )
                        else:
                            success, msg = auth_service.complete_user_profile(
                                user_id=pending_user.get("user_id"),
                                profile_data=profile_data
                            )

                        if success:
                            updated_user = auth_service.get_user_by_email(pending_user.get("email"))
                            if updated_user:
                                st.success(msg)
                                auth_service.set_active_session(updated_user)
                                st.session_state.authenticated = True
                                st.session_state.user = updated_user
                                st.session_state.auth_mode = "login"
                                target_comp = st.session_state.get("target_apply_comp") or st.query_params.get("redirect_comp")
                                st.query_params.clear()
                                if target_comp:
                                    st.session_state.pop("target_apply_comp", None)
                                    st.query_params["view"] = "comp"
                                    st.query_params["slug"] = target_comp
                                else:
                                    st.query_params["tab"] = "ana_sayfa"
                                st.rerun()
                            else:
                                st.error("Kullanıcı kaydedilemedi. Lütfen sayfayı yenileyip tekrar deneyin.")
                        else:
                            st.error(msg)
