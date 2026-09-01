"""T-Sistem · Yarışmacı Portalı.

Tamamen emojiden arındırılmış, takım raporu yükleme ve karne görüntüleme ekranı.
"""

from __future__ import annotations

import streamlit as st
from i18n import t


def render() -> None:
    """Yarışmacı portalı arayüzünü render eder."""
    lang = st.session_state.get("lang", "tr")

    st.markdown(
        f"""
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">{t("yp_title", lang)}</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                {t("yp_sub", lang)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_yukle, tab_durum = st.tabs([t("yp_tab_yukle", lang), t("yp_tab_durum", lang)])

    with tab_yukle:
        st.markdown(f"##### {t('yp_yukle_title', lang)}")

        c1, c2 = st.columns(2)
        with c1:
            yarisma = st.selectbox(
                t("yp_yarisma_sec", lang),
                [t("yp_cat_iha", lang), t("yp_cat_saglik", lang), t("yp_cat_ulasim", lang), t("yp_cat_roket", lang)]
            )
            asama = st.selectbox(
                t("yp_asama_sec", lang),
                [t("yp_stage_otr", lang), t("yp_stage_ktr", lang), t("yp_stage_ahr", lang), t("yp_stage_ftr", lang)]
            )
        with c2:
            takim_adi = st.text_input(t("yp_takim_adi", lang), placeholder=t("yp_takim_adi_ph", lang))
            kurum_adi = st.text_input(t("yp_kurum_adi", lang), placeholder=t("yp_kurum_ph", lang))

        dosya = st.file_uploader(t("yp_dosya_sec", lang), type=["pdf"])

        if dosya:
            st.markdown(
                f"""
                <div style="padding: 12px 16px; background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; margin: 12px 0; color: #166534; font-size: 0.90rem;">
                    <b>{t("yp_dosya_algilandi", lang)}:</b> {dosya.name} ({(dosya.size / (1024*1024)):.2f} MB)<br>
                    {t("yp_r2_hazir", lang)}
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button(t("yp_yukle_btn", lang), type="primary", use_container_width=True):
                st.success(t("yp_yukle_succ", lang))

    with tab_durum:
        st.markdown(f"##### {t('yp_durum_title', lang)}")
        st.markdown(
            f"""
            <div class="ts-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="font-size: 1.15rem; font-weight: 700; color: #0F172A;">{t("yp_durum_otr_title", lang)}</div>
                    <span class="ts-badge ts-badge-yarismaci">{t("yp_durum_onayli", lang)}</span>
                </div>
                <div style="font-size: 0.90rem; color: #475569; line-height: 1.7;">
                    <b>{t("yp_rapor_id", lang)}:</b> TF-2026-100004<br>
                    <b>{t("yp_final_puan", lang)}:</b> <span style="font-size: 1.1rem; font-weight: 800; color: #E30A17;">82.5 / 100</span><br>
                    <b>{t("yp_gecis_esigi", lang)}:</b> {t("yp_gecis_esigi_val", lang)}<br>
                    <b>{t("yp_hakem_notu", lang)}:</b> {t("yp_hakem_notu_val", lang)}
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
