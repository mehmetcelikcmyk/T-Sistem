"""T-Sistem · Hakem Değerlendirme Paneli.

Tamamen emojiden arındırılmış, kurumsal TEKNOFEST rubrik ve AI destekli
rapor değerlendirme arayüzü.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from i18n import t


def render() -> None:
    """Hakem değerlendirme arayüzünü render eder."""
    lang = st.session_state.get("lang", "tr")

    st.markdown(
        f"""
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">{t("hp_title", lang)}</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                {t("hp_sub", lang)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # İstatistik Kartları
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("hp_atanan_rapor", lang)}</div>
                <div class="ts-metric-val">12</div>
                <div class="ts-metric-sub">{t("hp_atanan_rapor_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("hp_tamamlanan", lang)}</div>
                <div class="ts-metric-val">8</div>
                <div class="ts-metric-sub">{t("hp_tamamlanan_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("hp_bekleyen", lang)}</div>
                <div class="ts-metric-val">4</div>
                <div class="ts-metric-sub">{t("hp_bekleyen_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("hp_ort_puan", lang)}</div>
                <div class="ts-metric-val">76.4</div>
                <div class="ts-metric-sub">{t("hp_ort_puan_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown(f"#### {t('hp_rapor_sec_title', lang)}")

    rapor_listesi = [
        {"id": "TF-2026-100001", "takim": "Albatros Otonom İHA", "yarisma": "İnsansız Hava Araçları (İHA)", "asama": "ÖTR", "ai_puan": 84.5, "durum": "Bekliyor"},
        {"id": "TF-2026-100004", "takim": "Göktürk Yapay Zekâ", "yarisma": "Sağlıkta Yapay Zekâ", "asama": "ÖTR", "ai_puan": 78.0, "durum": "Bekliyor"},
        {"id": "TF-2026-100007", "takim": "Tulpar Su Altı Sistemleri", "yarisma": "İnsansız Su Altı Sistemleri", "asama": "ÖTR", "ai_puan": 91.0, "durum": "Tamamlandı"},
    ]

    secilen_id = st.selectbox(
        t("hp_rapor_sec", lang),
        options=[r["id"] for r in rapor_listesi],
        format_func=lambda x: next(f"{r['id']} - {r['takim']} ({r['yarisma']}) [AI: {r['ai_puan']}]" for r in rapor_listesi if r["id"] == x)
    )

    rapor = next(r for r in rapor_listesi if r["id"] == secilen_id)

    col_detay, col_puan = st.columns([1.1, 1.2], gap="medium")

    with col_detay:
        st.markdown(
            f"""
            <div class="ts-card">
                <div style="font-size: 1.15rem; font-weight: 700; color: #0F172A; margin-bottom: 8px;">{rapor['takim']}</div>
                <div style="font-size: 0.88rem; color: #64748B; line-height: 1.6;">
                    <b>{t("hp_rapor_id", lang)}:</b> {rapor['id']}<br>
                    <b>{t("hp_yarisma", lang)}:</b> {rapor['yarisma']}<br>
                    <b>{t("hp_asama", lang)}:</b> {rapor['asama']}<br>
                    <b>{t("hp_ai_onskor", lang)}:</b> <span style="color:#0284C7; font-weight:700;">{rapor['ai_puan']} / 100</span><br>
                    <b>{t("hp_intihal", lang)}:</b> <span style="color:#16A34A; font-weight:600;">%4.2 ({t("hp_risk_dusuk", lang)})</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(f"##### {t('hp_ai_analiz', lang)}")
        st.info(t("hp_ai_analiz_text", lang))

    with col_puan:
        st.markdown(f"##### {t('hp_rubrik_title', lang)}")
        with st.form("form_hakem_puan"):
            p1 = st.slider(t("hp_rubrik_1", lang), 0, 25, 20)
            p2 = st.slider(t("hp_rubrik_2", lang), 0, 35, 30)
            p3 = st.slider(t("hp_rubrik_3", lang), 0, 20, 16)
            p4 = st.slider(t("hp_rubrik_4", lang), 0, 20, 18)

            toplam_puan = p1 + p2 + p3 + p4
            st.markdown(
                f"""
                <div style="padding: 12px 16px; background: #F1F5F9; border-radius: 8px; margin: 12px 0; font-size: 1rem; font-weight: 700; color: #0F172A;">
                    {t("hp_toplam_puan", lang)}: <span style="color: #E30A17;">{toplam_puan} / 100</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            hakem_notu = st.text_area(t("hp_hakem_gorusu", lang), placeholder=t("hp_hakem_gorusu_ph", lang))

            btn_onayla = st.form_submit_button(t("hp_onayla_btn", lang), type="primary", use_container_width=True)
            if btn_onayla:
                st.success(t("hp_succ_kayit", lang).format(takim=rapor["takim"], puan=toplam_puan))
