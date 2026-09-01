"""T-Sistem · Yarışma Yöneticisi & İzleme Paneli.

Tamamen emojiden arındırılmış, intihal matrisi ve jüri puan analizleri.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px
from i18n import t


def render() -> None:
    """Yarışma yöneticisi genel izleme arayüzünü render eder."""
    lang = st.session_state.get("lang", "tr")

    st.markdown(
        f"""
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">{t("vp_title", lang)}</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                {t("vp_sub", lang)}
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
                <div class="ts-metric-label">{t("vp_toplam_basvuru", lang)}</div>
                <div class="ts-metric-val">142</div>
                <div class="ts-metric-sub">{t("vp_tum_kategoriler", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("vp_degerlendirilen", lang)}</div>
                <div class="ts-metric-val">118</div>
                <div class="ts-metric-sub">{t("vp_tamamlanma", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("vp_intihal_riski", lang)}</div>
                <div class="ts-metric-val">3</div>
                <div class="ts-metric-sub">{t("vp_intihal_sub", lang)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">{t("vp_ort_puan", lang)}</div>
                <div class="ts-metric-val">74.8</div>
                <div class="ts-metric-sub">{t("vp_std_sapma", lang)}: 11.2</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    tab_ilerleme, tab_benzerlik = st.tabs([t("vp_tab_ilerleme", lang), t("vp_tab_benzerlik", lang)])

    with tab_ilerleme:
        data = {
            t("vp_kategori", lang): [t("vp_cat_iha", lang), t("vp_cat_saglik", lang), t("vp_cat_ulasim", lang), t("vp_cat_sualti", lang), t("vp_cat_roket", lang)],
            t("vp_toplam_rapor", lang): [45, 32, 28, 20, 17],
            t("vp_degerlendirilen_col", lang): [38, 28, 22, 18, 12],
        }
        df = pd.DataFrame(data)
        fig = px.bar(
            df,
            x=t("vp_kategori", lang),
            y=[t("vp_degerlendirilen_col", lang), t("vp_toplam_rapor", lang)],
            barmode="group",
            title=t("vp_chart_title", lang),
            color_discrete_sequence=["#0284C7", "#CBD5E1"]
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_benzerlik:
        st.markdown(f"##### {t('vp_benzerlik_title', lang)}")
        intihal_verisi = [
            {
                t("vp_rapor_a", lang): "TF-2026-100012 (Kartal İHA)",
                t("vp_rapor_b", lang): "TF-2026-100088 (Atmaca İHA)",
                t("vp_benzerlik_col", lang): "%74.2",
                t("vp_kritik_bolum", lang): t("vp_kritik_sistem", lang),
                t("vp_durum", lang): t("vp_durum_inceleme", lang)
            },
            {
                t("vp_rapor_a", lang): "TF-2026-100045 (MedVision YZ)",
                t("vp_rapor_b", lang): "TF-2025-900210 (Geçen Yıl Raporu)",
                t("vp_benzerlik_col", lang): "%61.0",
                t("vp_kritik_bolum", lang): t("vp_kritik_yontem", lang),
                t("vp_durum", lang): t("vp_durum_hakem_sevk", lang)
            },
        ]
        df_intihal = pd.DataFrame(intihal_verisi)
        st.dataframe(df_intihal, use_container_width=True, hide_index=True)
