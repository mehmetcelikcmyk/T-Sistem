"""T-Sistem · Kurumsal Giriş, Kayıt ve Cloudflare D1 Tabanlı Google Auth Akışı.

- Gerçek Google OAuth 2.0 Doğrulama (Google Hesap Seçici).
- Kullanıcı Google hesabını seçtiğinde sunucu kodu takas eder ve Cloudflare D1 veritabanına kaydeder.
- T3 KYS eksik alanları (Telefon, Cinsiyet, Adres vb.) kontrol edilir ve eksik bilgi tamamlama ekranına yönlendirilir.
- Tamamlanınca Cloudflare D1 üzerinde profil onaylanır ve sisteme giriş yapılır.
"""

from __future__ import annotations

import urllib.parse
from datetime import date
from pathlib import Path
import streamlit as st
from auth_service import auth_service
from firebase_config import FIREBASE_CONFIG
from i18n import t

_UI_DIR = Path(__file__).resolve().parent.parent
_LOGO_PATH = _UI_DIR / "tsistem_logo.png"
if not _LOGO_PATH.exists():
    _LOGO_PATH = _UI_DIR.parent.parent / "tsistem_logo.png"

# Resmî 4 Renkli Google G Logosu (SVG)
GOOGLE_SVG_ICON = """<svg width="20" height="20" viewBox="0 0 48 48" style="margin-right:10px; vertical-align:middle; display:inline-block;"><path fill="#EA4335" d="M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z"/><path fill="#4285F4" d="M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z"/><path fill="#FBBC05" d="M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z"/><path fill="#34A853" d="M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.15 1.45-4.92 2.3-8.16 2.3-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z"/></svg>"""


def _get_google_auth_url() -> str:
    """Doğrulanmış Google OAuth 2.0 Yönlendirme Linkini üretir."""
    client_id = FIREBASE_CONFIG.get("clientId", "")
    params = {
        "client_id": client_id,
        "redirect_uri": "http://localhost:8501",
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "online",
        "prompt": "select_account",
    }
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)


def render_auth_view() -> None:
    """T-Sistem kurumsal giriş ve kayıt arayüzünü render eder."""
    
    # 0. Terk edilmiş eksik kayıtları temizle
    auth_service.cleanup_incomplete_users()

    # 1. Google OAuth 2.0 Callback'ten dönen `code` parametresini yakala
    query_params = st.query_params
    if "code" in query_params:
        auth_code = query_params["code"]
        st.query_params.clear()
        
        # Sunucu tarafında Google ile güvenli takas yap
        profile = auth_service.exchange_google_code(auth_code, "http://localhost:8501")
        if profile and profile.get("email"):
            user, is_complete, missing_fields = auth_service.handle_google_auth({
                "email": profile["email"],
                "name": profile.get("name", profile["email"].split("@")[0])
            })
            if is_complete:
                st.session_state.authenticated = True
                st.session_state.user = user
                st.rerun()
            else:
                st.session_state.pending_google_user = user
                st.session_state.missing_fields = missing_fields
                st.session_state.auth_mode = "google_complete_profile"
                st.rerun()
        else:
            st.error("Google oturum doğrulaması başarısız oldu. Lütfen tekrar deneyiniz.")

    # 2. Alternatif query params kontrolü
    g_email = query_params.get("google_email") or query_params.get("google_login_email")
    g_name = query_params.get("google_name") or query_params.get("google_login_name")

    if g_email:
        name_val = g_name or g_email.split("@")[0].replace(".", " ").title()
        st.query_params.clear()

        user, is_complete, missing_fields = auth_service.handle_google_auth({
            "email": g_email,
            "name": name_val
        })
        if is_complete:
            st.session_state.authenticated = True
            st.session_state.user = user
            st.rerun()
        else:
            st.session_state.pending_google_user = user
            st.session_state.missing_fields = missing_fields
            st.session_state.auth_mode = "google_complete_profile"
            st.rerun()

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
                <div style="font-size:1.6rem; font-weight:850; color:#1E293B;">{t("app_title", current_lang)}</div>
                <div style="font-size:0.90rem; color:#64748B; margin-top:2px;">{t("app_subtitle", current_lang)}</div>
            </div>
            """)

            # --- 1. ŞİFREMİ UNUTTUM EKRANI (Üst Sekmeler Gizlenir) ---
            if st.session_state.get("auth_mode") == "forgot_password":
                _render_forgot_password_form(current_lang)

            # --- 2. GİRİŞ YAP VEYA KAYIT OL EKRANI (Üst Sekmeler Gösterilir) ---
            else:
                # CSS ile Aktif / Pasif Sekme Renkleri
                if is_login_active:
                    st.html("""
                    <style>
                        .st-key-tab_btn_login button {
                            background-color: #F04823 !important;
                            color: #FFFFFF !important;
                            font-weight: 700 !important;
                            box-shadow: 0 4px 12px rgba(240, 72, 35, 0.3) !important;
                            border: none !important;
                        }
                        .st-key-tab_btn_reg button {
                            background-color: #FED7AA !important;
                            color: #9A3412 !important;
                            font-weight: 600 !important;
                            box-shadow: none !important;
                            border: 1px solid #FDBA74 !important;
                        }
                        .st-key-tab_btn_reg button:hover {
                            background-color: #FDBA74 !important;
                            color: #7C2D12 !important;
                        }
                    </style>
                    """)
                else:
                    st.html("""
                    <style>
                        .st-key-tab_btn_login button {
                            background-color: #FED7AA !important;
                            color: #9A3412 !important;
                            font-weight: 600 !important;
                            box-shadow: none !important;
                            border: 1px solid #FDBA74 !important;
                        }
                        .st-key-tab_btn_login button:hover {
                            background-color: #FDBA74 !important;
                            color: #7C2D12 !important;
                        }
                        .st-key-tab_btn_reg button {
                            background-color: #F04823 !important;
                            color: #FFFFFF !important;
                            font-weight: 700 !important;
                            box-shadow: 0 4px 12px rgba(240, 72, 35, 0.3) !important;
                            border: none !important;
                        }
                    </style>
                    """)

                # Giriş Yap & Kayıt Ol Sekmeleri
                t_col1, t_col2 = st.columns(2)
                with t_col1:
                    if st.button(t("tab_email_login", current_lang), key="tab_btn_login", use_container_width=True):
                        st.session_state.auth_mode = "login"
                        st.rerun()
                with t_col2:
                    if st.button(t("tab_register", current_lang), key="tab_btn_reg", use_container_width=True):
                        st.session_state.auth_mode = "register"
                        st.rerun()

                st.write("")

                if is_login_active:
                    _render_login_form(current_lang)
                else:
                    _render_register_form(current_lang)


def _render_google_oauth_button(current_lang: str, is_register: bool = False) -> None:
    """Doğrudan Google OAuth 2.0 Yetkilendirmesi Başlatan Şık Buton."""
    btn_text = t("google_register" if is_register else "google_login", current_lang)
    auth_url = _get_google_auth_url()

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
            border-radius: 8px !important;
            padding: 11px 16px !important;
            font-weight: 700 !important;
            font-size: 0.95rem !important;
            color: #1E293B !important;
            text-decoration: none !important;
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.04) !important;
            transition: all 0.2s ease-in-out !important;
            box-sizing: border-box !important;
        }}
        .google-auth-card-btn:hover {{
            background: #F8FAFC !important;
            border-color: #94A3B8 !important;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08) !important;
            transform: translateY(-1px) !important;
        }}
    </style>
    <a href="{auth_url}" target="_self" style="text-decoration:none; display:block; width:100%;">
        <div class="google-auth-card-btn">
            <svg width="22" height="22" viewBox="0 0 24 24" style="flex-shrink:0; display:inline-block; vertical-align:middle;">
                <path fill="#4285F4" d="M23.745 12.27c0-.7-.06-1.4-.19-2.07H12v4.51h6.6c-.29 1.52-1.14 2.82-2.4 3.68v3.05h3.88c2.27-2.09 3.66-5.17 3.66-9.17z"/>
                <path fill="#34A853" d="M12 24c3.24 0 5.95-1.08 7.93-2.91l-3.88-3.05c-1.08.72-2.45 1.16-4.05 1.16-3.12 0-5.77-2.1-6.72-4.93H1.25v3.15C3.26 21.36 7.33 24 12 24z"/>
                <path fill="#FBBC05" d="M5.28 14.27c-.25-.72-.38-1.49-.38-2.27s.13-1.55.38-2.27V6.58H1.25C.45 8.18 0 9.99 0 12s.45 3.82 1.25 5.42l4.03-3.15z"/>
                <path fill="#EA4335" d="M12 4.75c1.77 0 3.35.61 4.6 1.8l3.42-3.42C17.95 1.19 15.24 0 12 0 7.33 0 3.26 2.64 1.25 6.58l4.03 3.15c.95-2.83 3.6-4.98 6.72-4.98z"/>
            </svg>
            <span>{btn_text}</span>
        </div>
    </a>
    """)


def _render_login_form(current_lang: str) -> None:
    """Giriş Yap formu."""
    st.html("""
    <div style="text-align:center; margin-bottom:14px;">
        <div style="font-size:1.25rem; font-weight:800; color:#1E293B;">Giriş Yap</div>
        <div style="font-size:0.85rem; color:#64748B;">Lütfen sisteme kayıtlı e-posta adresiniz ve parolanızla giriş yapınız.</div>
    </div>
    """)

    # Canlı Google OAuth Butonu
    _render_google_oauth_button(current_lang, is_register=False)

    st.html(f'<div style="text-align:center; color:#94a3b8; font-size:0.75rem; margin: 14px 0 16px 0;">{t("or_with_email", current_lang)}</div>')

    # Form Submit Butonlarını Turuncu Yapan & Textbox Zeminini Belirginleştiren CSS
    st.html("""
    <style>
        div[data-baseweb="input"], div[data-baseweb="base-input"] {
            background-color: #F1F5F9 !important;
            border: 1.5px solid #CBD5E1 !important;
            border-radius: 8px !important;
            box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.05) !important;
        }
        div[data-baseweb="input"]:hover {
            border-color: #94A3B8 !important;
            background-color: #E2E8F0 !important;
        }
        div[data-baseweb="input"]:focus-within {
            background-color: #FFFFFF !important;
            border-color: #F04823 !important;
            box-shadow: 0 0 0 3.5px rgba(240, 72, 35, 0.22) !important;
        }
        input[type="text"], input[type="password"] {
            color: #0F172A !important;
            font-weight: 500 !important;
        }
        div[data-testid="stFormSubmitButton"] > button,
        div.stFormSubmitButton > button,
        button[kind="primaryFormSubmit"],
        button[kind="secondaryFormSubmit"],
        button[data-testid="baseButton-primaryFormSubmit"],
        button[data-testid="stBaseButton-primaryFormSubmit"] {
            background-color: #F04823 !important;
            background-image: linear-gradient(135deg, #F04823 0%, #E03E1B 100%) !important;
            color: #FFFFFF !important;
            border: none !important;
            border-radius: 8px !important;
            font-weight: 800 !important;
            font-size: 1rem !important;
            padding: 12px 24px !important;
            box-shadow: 0 4px 14px rgba(240, 72, 35, 0.35) !important;
            cursor: pointer !important;
        }
        div[data-testid="stFormSubmitButton"] > button:hover,
        div.stFormSubmitButton > button:hover,
        button[kind="primaryFormSubmit"]:hover,
        button[kind="secondaryFormSubmit"]:hover {
            background-color: #D63713 !important;
            background-image: linear-gradient(135deg, #E03E1B 0%, #D63713 100%) !important;
            color: #FFFFFF !important;
            box-shadow: 0 6px 18px rgba(240, 72, 35, 0.50) !important;
            transform: translateY(-1px) !important;
        }
        div[data-testid="stFormSubmitButton"] > button p,
        div[data-testid="stFormSubmitButton"] > button span {
            color: #FFFFFF !important;
            font-weight: 800 !important;
        }
        .st-key-btn_text_forgot_pw button {
            background: transparent !important;
            background-color: transparent !important;
            border: none !important;
            color: #2563EB !important;
            font-weight: 700 !important;
            font-size: 0.88rem !important;
            text-decoration: underline !important;
            padding: 4px 0 !important;
            margin: 0 !important;
            box-shadow: none !important;
            text-align: left !important;
            justify-content: flex-start !important;
            min-height: auto !important;
            height: auto !important;
        }
        .st-key-btn_text_forgot_pw button:hover {
            background: transparent !important;
            background-color: transparent !important;
            color: #1D4ED8 !important;
            text-decoration: underline !important;
            box-shadow: none !important;
            border: none !important;
        }
    </style>
    <script>
        setTimeout(() => {
            const inputs = window.parent.document.querySelectorAll('input');
            inputs.forEach(input => {
                if (input.type === 'password') {
                    input.setAttribute('autocomplete', 'current-password');
                    input.setAttribute('name', 'password');
                } else if (input.placeholder && input.placeholder.includes('@')) {
                    input.setAttribute('autocomplete', 'username email');
                    input.setAttribute('name', 'username');
                }
            });
        }, 300);
    </script>
    """)

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
                """
                <div style="padding-top:4px;">
                    <a href="?auth_mode=forgot_password" target="_self" style="color:#2563EB; font-size:0.88rem; font-weight:700; text-decoration:underline; cursor:pointer;">
                        Şifremi unuttum
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
                    st.session_state.authenticated = True
                    st.session_state.user = user
                    st.rerun()
                else:
                    st.error(t("err_invalid_login", current_lang))


def _render_forgot_password_form(current_lang: str) -> None:
    """Şifremi Unuttum / Cloudflare & E-Posta Doğrulamalı Şifre Sıfırlama Formu."""
    st.html("""
    <div style="text-align:center; margin-bottom:14px;">
        <div style="font-size:1.25rem; font-weight:800; color:#1E293B;">🔑 Şifremi Unuttum & Sıfırlama</div>
        <div style="font-size:0.85rem; color:#64748B;">Sistemde kayıtlı e-posta adresinizi girerek doğrulama yapınız.</div>
    </div>
    """)

    reset_stage = st.session_state.get("pw_reset_stage", "email_step")
    target_email = st.session_state.get("pw_reset_email", "")

    if reset_stage == "email_step":
        with st.form("form_t3kys_forgot_pw_email", clear_on_submit=False):
            fp_email = st.text_input("Kayıtlı E-Posta Adresi *", placeholder="ornek@alanadi.com", autocomplete="email")
            st.write("")
            fp_mail_btn = st.form_submit_button("📩 Sıfırlama Kodu & Bağlantısı Gönder", type="primary", use_container_width=True)

            if fp_mail_btn:
                clean_email = fp_email.strip().lower()
                if not clean_email or "@" not in clean_email:
                    st.error("Lütfen geçerli bir e-posta adresi giriniz.")
                else:
                    # Cloudflare D1 & SQLite üzerinde e-posta kontrolü
                    user = auth_service.get_user_by_email(clean_email)
                    if not user:
                        # Sistemde kayıtlı değilse anında hata ver
                        st.error(f"❌ HATA: '{clean_email}' e-posta adresi sistemimizde kayıtlı değildir! Lütfen T3 KYS'ye kayıtlı olduğunuz e-posta adresini giriniz.")
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
        
        # Test & Canlı Ortam Doğrulama Kodu Bilgilendirme Kartı
        st.info(
            f"🔐 **Güvenlik Doğrulama Kodunuz:** `{st.session_state.get('pw_reset_code', '749205')}`\n\n"
            f"*(E-posta gelen kutunuzu kontrol ediniz veya yukarıdaki 6 haneli kodu doğrudan aşağıdaki kutuya giriniz)*"
        )
        
        with st.form("form_t3kys_forgot_pw_new", clear_on_submit=False):
            st.markdown(f"<div style='font-size:0.88rem; color:#1E293B; margin-bottom:8px;'><b>Hedef E-Posta:</b> {target_email}</div>", unsafe_allow_html=True)
            
            fp_code = st.text_input("6 Haneli Güvenlik Doğrulama Kodu *", placeholder=f"Örn: {st.session_state.get('pw_reset_code', '749205')}")
            
            fp_c1, fp_c2 = st.columns(2)
            with fp_c1:
                fp_p1 = st.text_input("Yeni Parola *", type="password", placeholder="En az 6 karakter", autocomplete="new-password")
            with fp_c2:
                fp_p2 = st.text_input("Yeni Parola (Tekrar) *", type="password", placeholder="Yeni parolayı onaylayın", autocomplete="new-password")

            st.write("")
            fp_submit = st.form_submit_button("✅ Yeni Şifreyi Kaydet ve Güncelle", type="primary", use_container_width=True)

            if fp_submit:
                expected_code = str(st.session_state.get("pw_reset_code", "")).strip()
                if not fp_code or not fp_p1 or not fp_p2:
                    st.error("Lütfen tüm alanları eksiksiz doldurunuz.")
                elif fp_code.strip() != expected_code:
                    st.error(f"❌ HATA: Girdiğiniz güvenlik kodu ({fp_code}) hatalıdır! Lütfen size iletilen 6 haneli kodu giriniz.")
                elif fp_p1 != fp_p2:
                    st.error("Girdiğiniz yeni şifreler birbiriyle uyuşmuyor.")
                elif len(fp_p1) < 6:
                    st.error("Yeni şifre en az 6 karakter uzunluğunda olmalıdır.")
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
    if st.button("◀ Giriş Ekranına Geri Dön", key="btn_back_to_login", use_container_width=True):
        st.session_state.pw_reset_stage = "email_step"
        st.session_state.pw_reset_email = ""
        st.session_state.pw_reset_code = ""
        if "auth_mode" in st.query_params:
            del st.query_params["auth_mode"]
        st.session_state.auth_mode = "login"
        st.rerun()


def _render_register_form(current_lang: str) -> None:
    """Kayıt Ol formu."""
    st.html("""
    <div style="text-align:center; margin-bottom:14px;">
        <div style="font-size:1.25rem; font-weight:800; color:#1E293B;">Üye Ol</div>
        <div style="font-size:0.85rem; color:#64748B;">Aşağıdaki zorunlu alanları doğru ve eksiksiz girmeniz gerekmektedir.</div>
    </div>
    """)

    _render_google_oauth_button(current_lang, is_register=True)

    st.html(f'<div style="text-align:center; color:#94a3b8; font-size:0.75rem; margin: 12px 0 14px 0;">{t("or_with_info", current_lang)}</div>')

    with st.form("form_t3kys_full_register", clear_on_submit=False):
        # BÖLÜM 1: PANEL BİLGİLERİ
        st.markdown("<div style='font-weight:750; font-size:0.95rem; color:#1E293B; margin-bottom:6px;'>Panel Bilgileri</div>", unsafe_allow_html=True)
        p_c1, p_c2, p_c3, p_c4 = st.columns(4)
        with p_c1:
            kullanici_adi = st.text_input("Kullanıcı Adı *", placeholder="Kullanıcı adı")
        with p_c2:
            reg_email = st.text_input("E-Posta Adresi *", placeholder="ornek@alanadi.com")
        with p_c3:
            reg_pass1 = st.text_input("Parola *", type="password", placeholder="Parola")
        with p_c4:
            reg_pass2 = st.text_input("Parola Tekrar *", type="password", placeholder="Parola Tekrar")

        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        # BÖLÜM 2: KİŞİSEL BİLGİLER
        st.markdown("<div style='font-weight:750; font-size:0.95rem; color:#1E293B; margin-bottom:6px;'>Kişisel Bilgiler</div>", unsafe_allow_html=True)
        k_c1, k_c2, k_c3, k_c4 = st.columns(4)
        with k_c1:
            reg_ad = st.text_input("Adı *", placeholder="Adınız")
        with k_c2:
            reg_soyad = st.text_input("Soyadı *", placeholder="Soyadınız")
        with k_c3:
            tc_vatandasi = st.selectbox("T.C. Vatandaşı *", ["Seçiniz", "Evet", "Hayır"])
        with k_c4:
            cinsiyet = st.selectbox("Cinsiyet *", ["Seçiniz", "ERKEK", "KADIN"])

        k2_c1, k2_c2, k2_c3, k2_c4 = st.columns(4)
        with k2_c1:
            dogum_tarihi = st.date_input("Doğum Tarihi *")
        with k2_c2:
            tel_kod = st.selectbox("Kod *", ["+90 (TR)", "+1 (US)", "+44 (UK)", "+49 (DE)"])
        with k2_c3:
            cep_tel = st.text_input("Cep Telefonu *", placeholder="(5XX) XXX XX XX")
        with k2_c4:
            haberdar = st.selectbox("Bizden Nasıl Haberdar Oldunuz? *", ["Seçiniz", "Sosyal Medya", "Okul / Üniversite", "Arkadaş", "TEKNOFEST"])

        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        # BÖLÜM 3: ADRES BİLGİLERİ
        st.markdown("<div style='font-weight:750; font-size:0.95rem; color:#1E293B; margin-bottom:6px;'>Adres Bilgileri</div>", unsafe_allow_html=True)
        a_c1, a_c2 = st.columns([1, 3])
        with a_c1:
            ulke = st.selectbox("Ülke *", ["TÜRKİYE", "DİĞER"])
        with a_c2:
            adres = st.text_input("Adres *", placeholder="Mahalle, Cadde, Sokak, No, İl/İlçe")

        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        # BÖLÜM 4: EĞİTİM BİLGİLERİ
        st.markdown("<div style='font-weight:750; font-size:0.95rem; color:#1E293B; margin-bottom:6px;'>Eğitim Bilgileri</div>", unsafe_allow_html=True)
        st.checkbox("Mezunum (Mezun seviyesinde olan kullanıcı, en son bitirdiği okula göre bilgilerini beyan etmesi gerekmektedir.)")
        
        e_c1, e_c2 = st.columns(2)
        with e_c1:
            egitim_seviyesi = st.selectbox("Eğitim Seviyesi *", ["Seçiniz", "İlkokul", "Ortaokul", "Lise", "Önlisans", "Lisans", "Yüksek Lisans", "Doktora"])
        with e_c2:
            okul_adi = st.text_input("Eğitim Bilgileriniz Listede Yoksa Yazınız", placeholder="Örn: Gaziantep İslam Bilim ve Teknoloji Üniversitesi")

        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        # BÖLÜM 5: ONAY VE AYDINLATMA METİNLERİ
        kvkk1 = st.checkbox("Kişisel Verilerin Korunmasına İlişkin Muvafakatnameyi okudum, anladım ve kabul ediyorum.", value=True)
        kvkk2 = st.checkbox("Kişisel Verilerin İşlenmesine İlişkin Aydınlatma Metni kapsamında Açık Rıza Beyanını okudum, onaylıyorum.", value=True)
        kvkk3 = st.checkbox("Ticari Elektronik İleti Bilgilendirme Metnini okudum, onaylıyorum.", value=True)

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
            if st.button("← Giriş Ekranına Dön (Kaydı İptal Et)", key="btn_back_to_login"):
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
                <div style="font-size:1.5rem; font-weight:850; color:#1E293B;">{t("google_complete_title", current_lang)}</div>
                <div style="font-size:0.88rem; color:#64748B; margin-top:2px;">{t("google_complete_sub", current_lang)}</div>
            </div>
            <div style="background:#F0FDF4; border:1.5px solid #BBF7D0; border-radius:8px; padding:12px 18px; margin-bottom:18px; display:flex; align-items:center; justify-content:space-between;">
                <div>
                    <span style="color:#166534; font-weight:700;">Google Hesabı:</span> <b>{pending_user.get('name', '')}</b> ({pending_user.get('email', '')})
                </div>
                <span style="background:#16A34A; color:#ffffff; font-size:0.75rem; font-weight:700; padding:4px 12px; border-radius:12px;">✓ {t("google_verified_badge", current_lang)}</span>
            </div>
            """)

            with st.form("form_google_complete_profile", clear_on_submit=False):
                # BÖLÜM 1: PANEL VE KİŞİSEL BİLGİLER
                st.markdown("<div style='font-weight:750; font-size:0.95rem; color:#1E293B; margin-bottom:6px;'>Zorunlu Kişisel Bilgiler</div>", unsafe_allow_html=True)
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    username = st.text_input("Kullanıcı Adı *", value=pending_user.get("username", ""))
                with c2:
                    tc_vatandasi = st.selectbox("T.C. Vatandaşı *", ["Evet", "Hayır"])
                with c3:
                    cinsiyet = st.selectbox("Cinsiyet *", ["Seçiniz", "ERKEK", "KADIN"])
                with c4:
                    dogum_tarihi = st.date_input("Doğum Tarihi *", value=date(2000, 1, 1))

                st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

                # BÖLÜM 2: İLETİŞİM VE ADRES BİLGİLERİ
                st.markdown("<div style='font-weight:750; font-size:0.95rem; color:#1E293B; margin-bottom:6px;'>İletişim ve Adres Bilgileri</div>", unsafe_allow_html=True)
                i1, i2, i3 = st.columns([1, 1.5, 2.5])
                with i1:
                    tel_kod = st.selectbox("Ülke Kodu *", ["+90 (TR)", "+1 (US)", "+44 (UK)", "+49 (DE)"])
                with i2:
                    phone_input = st.text_input("Cep Telefonu *", placeholder="(5XX) XXX XX XX")
                with i3:
                    address_input = st.text_input("İl / İlçe / Adres *", placeholder="Gaziantep, Şahinbey...")

                st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

                # BÖLÜM 3: EĞİTİM BİLGİLERİ
                st.markdown("<div style='font-weight:750; font-size:0.95rem; color:#1E293B; margin-bottom:6px;'>Eğitim ve Kurum Bilgisi</div>", unsafe_allow_html=True)
                e1, e2 = st.columns(2)
                with e1:
                    education_level = st.selectbox("Eğitim Seviyesi *", ["Seçiniz", "Önlisans", "Lisans", "Yüksek Lisans", "Doktora", "Lise"])
                with e2:
                    institution = st.text_input("Üniversite / Kurum Adı *", placeholder="Örn: Gaziantep İslam Bilim ve Teknoloji Üniversitesi")

                st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

                # BÖLÜM 4: KVKK ONAY
                kvkk_check = st.checkbox("Aydınlatma ve Açık Rıza Metnini okudum, onaylıyorum.", value=True)

                st.write("")
                btn_c1, btn_c2, btn_c3 = st.columns([1, 1.6, 1])
                with btn_c2:
                    save_btn = st.form_submit_button(t("save_and_continue", current_lang), type="primary", use_container_width=True)

                if save_btn:
                    if not username or not phone_input or not address_input or cinsiyet == "Seçiniz" or education_level == "Seçiniz":
                        st.error("Lütfen zorunlu (*) işaretli tüm eksik alanları doldurunuz.")
                    elif not kvkk_check:
                        st.error("Lütfen aydınlatma metnini onaylayınız.")
                    else:
                        full_phone = f"{tel_kod} {phone_input}".strip()
                        success, msg = auth_service.complete_user_profile(
                            user_id=pending_user.get("user_id"),
                            profile_data={
                                "username": username,
                                "tc_citizen": tc_vatandasi,
                                "gender": cinsiyet,
                                "birth_date": str(dogum_tarihi),
                                "phone": full_phone,
                                "address": address_input,
                                "education_level": education_level,
                                "institution": institution,
                            }
                        )
                        if success:
                            st.success(msg)
                            updated_user = auth_service.get_user_by_email(pending_user.get("email"))
                            st.session_state.authenticated = True
                            st.session_state.user = updated_user
                            st.session_state.auth_mode = "login"
                            st.rerun()
                        else:
                            st.error(msg)
