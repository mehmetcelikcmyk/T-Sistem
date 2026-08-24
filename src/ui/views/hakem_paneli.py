"""T-Sistem · Hakem Değerlendirme Paneli.

Tamamen emojiden arındırılmış, kurumsal TEKNOFEST rubrik ve AI destekli
rapor değerlendirme arayüzü.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd


def render() -> None:
    """Hakem değerlendirme arayüzünü render eder."""
    
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">Hakem Değerlendirme Paneli</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                Atanan yarışma raporlarını inceleyin, yapay zekâ ön analizini görüntüleyin ve rubrik puanlamasını tamamlayın.
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
                <div class="ts-metric-label">Atanan Rapor</div>
                <div class="ts-metric-val">12</div>
                <div class="ts-metric-sub">Ön Tasarım Raporu (ÖTR)</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            """
            <div class="ts-metric-box">
                <div class="ts-metric-label">Tamamlanan</div>
                <div class="ts-metric-val">8</div>
                <div class="ts-metric-sub">Puanlandı ve Onaylandı</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            """
            <div class="ts-metric-box">
                <div class="ts-metric-label">İnceleme Bekleyen</div>
                <div class="ts-metric-val">4</div>
                <div class="ts-metric-sub">Son Tarih: 15 Gün</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            """
            <div class="ts-metric-box">
                <div class="ts-metric-label">Ortalama Puan</div>
                <div class="ts-metric-val">76.4</div>
                <div class="ts-metric-sub">Sınıflandırma: Başarılı</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    # Örnek Rapor Seçimi
    st.markdown("#### İncelenecek Rapor Seçimi")
    
    rapor_listesi = [
        {"id": "TF-2026-100001", "takim": "Albatros Otonom İHA", "yarisma": "İnsansız Hava Araçları (İHA)", "asama": "ÖTR", "ai_puan": 84.5, "durum": "Bekliyor"},
        {"id": "TF-2026-100004", "takim": "Göktürk Yapay Zekâ", "yarisma": "Sağlıkta Yapay Zekâ", "asama": "ÖTR", "ai_puan": 78.0, "durum": "Bekliyor"},
        {"id": "TF-2026-100007", "takim": "Tulpar Su Altı Sistemleri", "yarisma": "İnsansız Su Altı Sistemleri", "asama": "ÖTR", "ai_puan": 91.0, "durum": "Tamamlandı"},
    ]
    
    secilen_id = st.selectbox(
        "Rapor Seçiniz",
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
                    <b>Rapor ID:</b> {rapor['id']}<br>
                    <b>Yarışma Kategorisi:</b> {rapor['yarisma']}<br>
                    <b>Değerlendirme Aşaması:</b> {rapor['asama']}<br>
                    <b>Yapay Zekâ Ön Skoru:</b> <span style="color:#0284C7; font-weight:700;">{rapor['ai_puan']} / 100</span><br>
                    <b>İntihal / Benzerlik Oranı:</b> <span style="color:#16A34A; font-weight:600;">%4.2 (Düşük Risk)</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("##### Yapay Zekâ Ön Değerlendirme Analizi")
        st.info(
            "AI Analiz Özeti: Rapor yapısı resmî TEKNOFEST şablonuna %98 oranında uygundur. "
            "Özgünlük, Sistem Mimarisi ve Test Doğrulama bölümleri eksiksizdir. "
            "Risk Yönetimi tablosunda olasılık derecelendirmesi detaylandırılmalıdır."
        )

    with col_puan:
        st.markdown("##### Hakem Rubrik Puanlama Formu")
        with st.form("form_hakem_puan"):
            p1 = st.slider("1. Özgünlük ve Yenilikçilik (Maks. 25 Puan)", 0, 25, 20)
            p2 = st.slider("2. Teknik Tasarım ve Sistem Mimarisi (Maks. 35 Puan)", 0, 35, 30)
            p3 = st.slider("3. Uygulanabilirlik ve Yöntem (Maks. 20 Puan)", 0, 20, 16)
            p4 = st.slider("4. Şartname Uyumu ve Format (Maks. 20 Puan)", 0, 20, 18)

            toplam_puan = p1 + p2 + p3 + p4
            st.markdown(
                f"""
                <div style="padding: 12px 16px; background: #F1F5F9; border-radius: 8px; margin: 12px 0; font-size: 1rem; font-weight: 700; color: #0F172A;">
                    Toplam Hakem Puanı: <span style="color: #E30A17;">{toplam_puan} / 100</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            hakem_notu = st.text_area("Takıma İletilecek Hakem Görüşü ve Geri Bildirim", placeholder="Rapor genel olarak başarılı ve kapsamlı...")

            btn_onayla = st.form_submit_button("Değerlendirmeyi Tamamla ve Kaydet", type="primary", use_container_width=True)
            if btn_onayla:
                st.success(f"{rapor['takim']} için {toplam_puan} puanlık değerlendirme başarıyla sisteme kaydedildi.")
