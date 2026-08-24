"""T-Sistem · Yarışmacı Portalı.

Tamamen emojiden arındırılmış, takım raporu yükleme ve karne görüntüleme ekranı.
"""

from __future__ import annotations

import streamlit as st


def render() -> None:
    """Yarışmacı portalı arayüzünü render eder."""
    
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">Yarışmacı Rapor ve Başvuru Takip Paneli</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                Yarışma raporlarınızı yükleyin, biçimsel ön kontrolleri gerçekleştirin ve değerlendirme sonuçlarınızı görüntüleyin.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_yukle, tab_durum = st.tabs(["Rapor Yükleme ve Ön Kontrol", "Mevcut Başvuru ve Karne"])

    with tab_yukle:
        st.markdown("##### Yeni Rapor Yükleme")
        
        c1, c2 = st.columns(2)
        with c1:
            yarisma = st.selectbox(
                "Yarışma Kategorisi",
                ["İnsansız Hava Araçları (İHA) Yarışması", "Sağlıkta Yapay Zekâ Yarışması", "Ulaşımda Yapay Zekâ", "Roket Yarışması"]
            )
            asama = st.selectbox(
                "Rapor Aşaması",
                ["Ön Tasarım Raporu (ÖTR)", "Kritik Tasarım Raporu (KTR)", "Atış / Uçuş Hazırlık Raporu (AHR)", "Final Tasarım Raporu (FTR)"]
            )
        with c2:
            takim_adi = st.text_input("Takım Adı", placeholder="Örn: Hürkuş Gençlik Takımı")
            kurum_adi = st.text_input("Üniversite / Lise / Kurum", placeholder="Örn: Boğaziçi Üniversitesi")

        dosya = st.file_uploader("PDF Formatında Rapor Dosyasını Seçiniz (Maks. 25 MB)", type=["pdf"])

        if dosya:
            st.markdown(
                f"""
                <div style="padding: 12px 16px; background: #F0FDF4; border: 1px solid #BBF7D0; border-radius: 8px; margin: 12px 0; color: #166534; font-size: 0.90rem;">
                    <b>Dosya Algılandı:</b> {dosya.name} ({(dosya.size / (1024*1024)):.2f} MB)<br>
                    Sistem dosyanızı Cloudflare R2 Güvenli Depolama Havuzu'na yüklemeye hazırdır.
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("Raporu Sisteme Gönder ve AI Ön İncelemesini Başlat", type="primary", use_container_width=True):
                st.success("Rapor başarıyla Cloudflare R2 havuzuna yüklendi ve yapay zekâ ön değerlendirme kuyruğuna alındı.")

    with tab_durum:
        st.markdown("##### Başvuru Durumu ve Değerlendirme Karnesi")
        st.markdown(
            """
            <div class="ts-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                    <div style="font-size: 1.15rem; font-weight: 700; color: #0F172A;">Ön Tasarım Raporu (ÖTR) · Değerlendirme Tamamlandı</div>
                    <span class="ts-badge ts-badge-yarismaci">ONAYLANDI (BAŞARILI)</span>
                </div>
                <div style="font-size: 0.90rem; color: #475569; line-height: 1.7;">
                    <b>Rapor ID:</b> TF-2026-100004<br>
                    <b>Nihai Değerlendirme Puanı:</b> <span style="font-size: 1.1rem; font-weight: 800; color: #E30A17;">82.5 / 100</span><br>
                    <b>Aşama Geçme Eşiği:</b> 70.0 Puan (Geçti)<br>
                    <b>Hakem Değerlendirme Notu:</b> Tasarım hesaplamaları ve aerodinamik analizler oldukça detaylı ve tutarlıdır. Bir sonraki KTR aşamasında aviyonik haberleşme protokollerine ağırlık verilmesi tavsiye edilir.
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
