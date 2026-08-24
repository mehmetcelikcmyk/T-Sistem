"""T-Sistem · Yarışma Yöneticisi & İzleme Paneli.

Tamamen emojiden arındırılmış, intihal matrisi ve jüri puan analizleri.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import plotly.express as px


def render() -> None:
    """Yarışma yöneticisi genel izleme arayüzünü render eder."""
    
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">Yarışma ve Değerlendirme Yönetim Paneli</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                Genel yarışma istatistikleri, jüri puanlama ilerlemesi ve benzerlik/intihal analizleri.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # İstatistik Kartları
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            """
            <div class="ts-metric-box">
                <div class="ts-metric-label">Toplam Başvuru</div>
                <div class="ts-metric-val">142</div>
                <div class="ts-metric-sub">Tüm Kategoriler</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="ts-metric-box">
                <div class="ts-metric-label">Değerlendirilen</div>
                <div class="ts-metric-val">118</div>
                <div class="ts-metric-sub">%83.1 Tamamlanma</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class="ts-metric-box">
                <div class="ts-metric-label">İntihal Riski</div>
                <div class="ts-metric-val">3</div>
                <div class="ts-metric-sub">%40 Üzeri Benzerlik</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            """
            <div class="ts-metric-box">
                <div class="ts-metric-label">Ortalama Puan</div>
                <div class="ts-metric-val">74.8</div>
                <div class="ts-metric-sub">Standart Sapma: 11.2</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    tab_ilerleme, tab_benzerlik = st.tabs(["Kategori Bazlı İlerleme", "Benzerlik & İntihal Denetimi"])

    with tab_ilerleme:
        data = {
            "Kategori": ["İHA", "Sağlıkta YZ", "Ulaşımda YZ", "Su Altı", "Roket"],
            "Toplam Rapor": [45, 32, 28, 20, 17],
            "Değerlendirilen": [38, 28, 22, 18, 12],
        }
        df = pd.DataFrame(data)
        fig = px.bar(
            df, x="Kategori", y=["Değerlendirilen", "Toplam Rapor"],
            barmode="group",
            title="Kategori Bazında Değerlendirme Tamamlanma Durumu",
            color_discrete_sequence=["#0284C7", "#CBD5E1"]
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab_benzerlik:
        st.markdown("##### Şüpheli Benzerlik Eşleşmeleri (Yüksek / Orta Risk)")
        intihal_verisi = [
            {"Rapor A": "TF-2026-100012 (Kartal İHA)", "Rapor B": "TF-2026-100088 (Atmaca İHA)", "Benzerlik": "%74.2", "Kritik Bölüm": "Sistem Tasarımı & Donanım Şeması", "Durum": "İnceleme Gerektiriyor"},
            {"Rapor A": "TF-2026-100045 (MedVision YZ)", "Rapor B": "TF-2025-900210 (Geçen Yıl Raporu)", "Benzerlik": "%61.0", "Kritik Bölüm": "Yöntem & Metodoloji Metni", "Durum": "Hakem Heyetine Sevk Edildi"},
        ]
        df_intihal = pd.DataFrame(intihal_verisi)
        st.dataframe(df_intihal, use_container_width=True, hide_index=True)
