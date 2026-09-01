"""T-Sistem · Kullanıcı ve Yetki Yönetim Paneli (Admin).

Yöneticinin yeni Hakem, Yarışmacı ve Yarışma Yöneticisi profilleri tanımlamasını,
durumlarını değiştirmesini ve yetkilendirmesini sağlar.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from auth_service import auth_service
from i18n import t


def render() -> None:
    """Admin Kullanıcı Yönetimi arayüzünü render eder."""
    lang = st.session_state.get("lang", "tr")

    st.markdown(
        f"""
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">{t("usr_panel_title", lang)}</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                {t("usr_panel_sub", lang)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kullanicilar = auth_service.get_all_users()
    toplam_sayi = len(kullanicilar)
    hakem_sayisi = len([u for u in kullanicilar if u.get("role") == "hakem"])
    yarismaci_sayisi = len([u for u in kullanicilar if u.get("role") == "yarismaci"])
    yonetici_sayisi = len([u for u in kullanicilar if u.get("role") in ("admin", "yonetici")])

    # Metrik Kartları
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("usr_toplam", lang)}</div>
                <div class="ts-metric-val">{toplam_sayi}</div>
                <div class="ts-metric-sub">{t("usr_toplam_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("usr_hakem", lang)}</div>
                <div class="ts-metric-val">{hakem_sayisi}</div>
                <div class="ts-metric-sub">{t("usr_hakem_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("usr_yarismaci", lang)}</div>
                <div class="ts-metric-val">{yarismaci_sayisi}</div>
                <div class="ts-metric-sub">{t("usr_yarismaci_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("usr_yonetici", lang)}</div>
                <div class="ts-metric-val">{yonetici_sayisi}</div>
                <div class="ts-metric-sub">{t("usr_yonetici_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # URL'den alt sekmeyi oku (Geri / İleri desteği)
    _u_subtab = st.query_params.get("subtab", "")
    if "admin_users_active_subtab" not in st.session_state:
        if _u_subtab in ("list", "new"):
            st.session_state.admin_users_active_subtab = _u_subtab
        else:
            st.session_state.admin_users_active_subtab = "list"
    elif _u_subtab in ("list", "new") and _u_subtab != st.session_state.admin_users_active_subtab:
        st.session_state.admin_users_active_subtab = _u_subtab

    u_cur = st.session_state.admin_users_active_subtab

    u_sw1, u_sw2 = st.columns(2)
    with u_sw1:
        u_b1 = "primary" if u_cur == "list" else "secondary"
        if st.button(t("usr_tab_liste", lang), key="sw_usr_list", use_container_width=True, type=u_b1):
            st.session_state.admin_users_active_subtab = "list"
            st.query_params["subtab"] = "list"
            st.rerun()
    with u_sw2:
        u_b2 = "primary" if u_cur == "new" else "secondary"
        if st.button(t("usr_tab_yeni", lang), key="sw_usr_new", use_container_width=True, type=u_b2):
            st.session_state.admin_users_active_subtab = "new"
            st.query_params["subtab"] = "new"
            st.rerun()

    st.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    # --- KULLANICI LİSTESİ ---
    if u_cur == "list":
        if not kullanicilar:
            st.info(t("usr_bos", lang))
        else:
            tablo_verisi = []
            for u in kullanicilar:
                tablo_verisi.append({
                    t("usr_id", lang): u["user_id"],
                    t("usr_ad_soyad", lang): u["name"],
                    t("usr_eposta", lang): u["email"],
                    t("usr_rol", lang): u["role"].upper(),
                    t("usr_kurum", lang): u["institution"] or t("usr_belirtilmedi", lang),
                    t("usr_durum", lang): u["status"].upper(),
                    t("usr_kayit", lang): u["created_at"][:10] if u.get("created_at") else "-",
                })

            df = pd.DataFrame(tablo_verisi)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown(f"#### {t('usr_duzenle_title', lang)}")

            kullanici_secenekleri = {f"{u['name']} ({u['email']}) · [{u['role'].upper()}]": u for u in kullanicilar}
            secilen_etiket = st.selectbox(t("usr_duzenle_sec", lang), list(kullanici_secenekleri.keys()))

            if secilen_etiket:
                secilen_u = kullanici_secenekleri[secilen_etiket]
                with st.container(border=True):
                    st.markdown(f"**{t('usr_profil_duzenle', lang)}:** `{secilen_u['user_id']}`")

                    e_col1, e_col2 = st.columns(2)
                    with e_col1:
                        edit_ad = st.text_input(t("usr_ad_soyad_lbl", lang), value=secilen_u.get("name", ""), key=f"edit_name_{secilen_u['user_id']}")
                        edit_email = st.text_input(t("usr_eposta_lbl", lang), value=secilen_u.get("email", ""), key=f"edit_email_{secilen_u['user_id']}")
                        edit_kurum = st.text_input(t("usr_kurum_lbl", lang), value=secilen_u.get("institution", ""), key=f"edit_inst_{secilen_u['user_id']}")
                    with e_col2:
                        rol_map = {
                            "hakem": t("usr_rol_hakem", lang),
                            "yonetici": t("usr_rol_yonetici", lang),
                            "yarismaci": t("usr_rol_yarismaci", lang),
                            "admin": t("usr_rol_admin", lang),
                        }
                        edit_rol = st.selectbox(
                            t("usr_rol_lbl", lang),
                            ["hakem", "yarismaci", "yonetici", "admin"],
                            index=["hakem", "yarismaci", "yonetici", "admin"].index(secilen_u["role"]) if secilen_u["role"] in ["hakem", "yarismaci", "yonetici", "admin"] else 1,
                            format_func=lambda x: rol_map.get(x, x),
                            key=f"edit_role_{secilen_u['user_id']}"
                        )
                        edit_durum = st.selectbox(
                            t("usr_durum_lbl", lang),
                            ["aktif", "pasif"],
                            index=0 if secilen_u.get("status") == "aktif" else 1,
                            format_func=lambda x: t("usr_aktif", lang) if x == "aktif" else t("usr_pasif", lang),
                            key=f"edit_status_{secilen_u['user_id']}"
                        )
                        edit_pass = st.text_input(
                            t("usr_sifre_lbl", lang),
                            type="password",
                            placeholder=t("usr_sifre_ph", lang),
                            key=f"edit_pass_{secilen_u['user_id']}"
                        )

                    st.markdown("<hr style='margin:12px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

                    b_col1, b_col2 = st.columns([3, 1])
                    with b_col1:
                        if st.button(f"💾 {t('usr_kaydet_btn', lang)}", type="primary", use_container_width=True, key=f"btn_save_{secilen_u['user_id']}"):
                            basari, msg = auth_service.update_user_by_admin(
                                user_id=secilen_u["user_id"],
                                name=edit_ad,
                                email=edit_email,
                                role=edit_rol,
                                status=edit_durum,
                                institution=edit_kurum,
                                new_password=edit_pass if edit_pass.strip() else None
                            )
                            if basari:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                    with b_col2:
                        if secilen_u["email"] != "admin@tsistem.org":
                            if st.button(f"🗑️ {t('usr_sil_btn', lang)}", use_container_width=True, key=f"btn_del_{secilen_u['user_id']}"):
                                silindi = auth_service.delete_user(secilen_u["user_id"])
                                if silindi:
                                    st.warning(f"'{secilen_u['name']}' {t('usr_sil_succ', lang)}")
                                    st.rerun()
                                else:
                                    st.error(t("usr_sil_err", lang))
                        else:
                            st.caption(f"🔒 {t('usr_sil_koruma', lang)}")

    # --- YENİ KULLANICI EKLEME ---
    elif u_cur == "new":
        st.markdown(f"##### {t('usr_yeni_title', lang)}")
        with st.form("form_yeni_kullanici", clear_on_submit=True):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                ad = st.text_input(t("usr_yeni_ad", lang), placeholder=t("usr_yeni_ad_ph", lang))
                email = st.text_input(t("usr_yeni_email", lang), placeholder=t("usr_yeni_email_ph", lang))
                sifre = st.text_input(t("usr_yeni_sifre", lang), type="password", placeholder=t("usr_yeni_sifre_ph", lang))

            with f_col2:
                rol_map2 = {
                    "hakem": t("usr_rol_hakem", lang),
                    "yonetici": t("usr_rol_yonetici", lang),
                    "yarismaci": t("usr_rol_yarismaci", lang),
                    "admin": t("usr_rol_admin", lang),
                }
                rol = st.selectbox(
                    t("usr_rol_lbl", lang),
                    options=["hakem", "yonetici", "yarismaci", "admin"],
                    format_func=lambda x: rol_map2.get(x, x)
                )
                kurum = st.text_input(t("usr_yeni_kurum", lang), placeholder=t("usr_yeni_kurum_ph", lang))

            submit_yeni = st.form_submit_button(t("usr_yeni_kaydet", lang), type="primary", use_container_width=True)

            if submit_yeni:
                if not ad or not email or not sifre:
                    st.error(t("usr_yeni_err", lang))
                else:
                    basari, msg = auth_service.register_user(
                        name=ad,
                        email=email,
                        password=sifre,
                        role=rol,
                        institution=kurum,
                    )
                    if basari:
                        st.success(f"{ad} {t('usr_yeni_succ', lang)}")
                        st.rerun()
                    else:
                        st.error(msg)
