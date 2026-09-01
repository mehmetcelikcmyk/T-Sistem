"""
T-Sistem · Ortak Yarışma Detay & Şartname Görüntüleme Modülü.
Hem açılış vitrininden (Landing Page / Girişsiz) hem de yarışmacı portalından (Girişli)
çağrılabilen, resmî şartname PDF önizleme, aşama şablonları, rubrik ve akıllı başvuru yönlendiricisi.
"""

from __future__ import annotations

import os
from pathlib import Path
from html import escape as _esc
import streamlit as st
from src.ui import sartname_rehber
from src.ui.logos import logo_data_uri


def render_competition_detail_page(competition_slug_or_id: str, is_authenticated: bool = False) -> None:
    """Yarışma detay sayfasını tam sayfa zengin formatta render eder."""
    slug = str(competition_slug_or_id or "").strip()
    if not slug:
        st.error("Yarışma kodu belirtilmedi.")
        return

    # D1 / repo veya rehberden yarışma meta bilgilerini çek
    comp_title = sartname_rehber.turkce_kategori_adi_formatla(slug)
    comp_domain = "TEKNOFEST YARIŞMASI"
    comp_desc = ""
    comp_levels = "Lise / Üniversite / Lisansüstü / Mezun"
    d1_stages = []
    d1_specs = []

    try:
        from src.data import repos
        r = repos()
        d1_comp = r.competitions.get(slug)
        if d1_comp:
            comp_title = d1_comp.name or comp_title
            comp_domain = (d1_comp.domain or comp_domain).upper()
            comp_desc = d1_comp.description or ""
            comp_levels = d1_comp.levels or comp_levels

        d1_specs = r.competitions.list_specs(slug) or []
        d1_stages = r.competitions.list_stages(slug) or []
    except Exception:
        pass

    # ── TEKNOFEST RESMÎ TEMASı + ANİMASYONLAR ──────────────────────────────────
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Muli:wght@300;400;600;700;800;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">

    <style>
    * {
        font-family: 'Muli', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Üst Boşluğu Tamamen Sıfırla (Streamlit Default Header Collapse) */
    header, [data-testid="stHeader"], [data-testid="stAppHeader"], div[data-testid="stHeader"], div[data-testid="stAppHeader"] {
        display: none !important;
        height: 0 !important;
        min-height: 0 !important;
        max-height: 0 !important;
        padding: 0 !important;
        margin: 0 !important;
    }

    .stApp {
        background: #02143D url('https://cdn.teknofest.org/media/upload/userFormUpload/TEKNOFEST-Istanbul-Web-Site-Zemin-1728x3365_oymmk.webp') no-repeat center top fixed !important;
        background-size: cover !important;
        color: #FFFFFF !important;
    }

    .block-container {
        padding-top: 0.2rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 1400px !important;
    }

    /* ── SAYFA GEÇİŞ ANİMASYONLARI ── */
    @keyframes floatUpDown {
        0%, 100% {
            transform: translateY(0) rotate(0deg);
        }
        50% {
            transform: translateY(-16px) rotate(2deg);
        }
    }

    @keyframes fadeInUp {
        0% {
            opacity: 0;
            transform: translateY(35px);
        }
        100% {
            opacity: 1;
            transform: translateY(0);
        }
    }

    @keyframes slideContentIn {
        0% {
            opacity: 0;
            transform: translateX(-40px);
        }
        100% {
            opacity: 1;
            transform: translateX(0);
        }
    }

    @keyframes fadeInScale {
        0% {
            opacity: 0;
            transform: scale(0.80);
        }
        100% {
            opacity: 1;
            transform: scale(1);
        }
    }

    @keyframes glowPulse {
        0%, 100% {
            box-shadow: 0 0 25px rgba(61, 211, 255, 0.30), inset 0 0 20px rgba(61, 211, 255, 0.10);
        }
        50% {
            box-shadow: 0 0 45px rgba(61, 211, 255, 0.60), inset 0 0 30px rgba(61, 211, 255, 0.20);
        }
    }

    /* ── DETAY HERO KARTI ── */
    .comp-detail-hero {
        background: radial-gradient(circle at 75% 50%, rgba(40, 90, 148, 0.45) 0%, rgba(2, 20, 61, 0.95) 80%);
        border: 1.5px solid rgba(61, 211, 255, 0.40);
        border-radius: 18px;
        padding: 28px 32px;
        margin-bottom: 24px;
        box-shadow: 0 12px 35px rgba(0, 23, 134, 0.45);
        animation: slideContentIn 0.65s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    /* ── YÜZEN LOGO DAİRESİ (Landing ile birebir aynı) ── */
    .tf-detail-floating-circle {
        position: relative;
        width: 240px;
        height: 240px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(61, 211, 255, 0.22) 0%, rgba(2, 28, 97, 0.10) 70%);
        border: 1.5px solid rgba(61, 211, 255, 0.45);
        box-shadow: 0 0 40px rgba(61, 211, 255, 0.30);
        display: flex;
        align-items: center;
        justify-content: center;
        flex-shrink: 0;
        animation: fadeInScale 0.75s cubic-bezier(0.16, 1, 0.3, 1) forwards,
                   glowPulse 3.5s ease-in-out infinite;
    }

    /* Yüzen logo resmi — landing'deki floatUpDown animasyonuyla aynı */
    .tf-detail-floating-img {
        max-width: 190px;
        max-height: 170px;
        object-fit: contain;
        animation: floatUpDown 4.5s ease-in-out infinite;
        filter: drop-shadow(0 15px 25px rgba(0, 0, 0, 0.55));
    }

    /* Hero sol metin bloğu kayarak gelir */
    .tf-detail-hero-text {
        animation: slideContentIn 0.60s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }

    /* Tab başlıkları ve içerik fade-in */
    .comp-detail-tabs-wrap {
        animation: fadeInUp 0.70s cubic-bezier(0.16, 1, 0.3, 1) 0.15s both;
    }

    /* Geri / Başvur butonları */
    div[data-testid="stButton"] > button[kind="secondary"] {
        background: rgba(2, 28, 97, 0.55) !important;
        border: 1.5px solid rgba(61, 211, 255, 0.55) !important;
        color: #3DD3FF !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
        backdrop-filter: blur(8px) !important;
        transition: all 0.22s ease !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"]:hover {
        background: rgba(61, 211, 255, 0.20) !important;
        border-color: #3DD3FF !important;
        color: #FFFFFF !important;
        transform: scale(1.04) !important;
    }
    div[data-testid="stButton"] > button[kind="primary"] {
        background: linear-gradient(135deg, #FF1A00 0%, #D80000 100%) !important;
        color: #FFFFFF !important;
        font-weight: 800 !important;
        border-radius: 8px !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        box-shadow: 0 4px 18px rgba(222, 56, 15, 0.55) !important;
        transition: all 0.22s ease !important;
    }
    div[data-testid="stButton"] > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #FF3300 0%, #FF0000 100%) !important;
        box-shadow: 0 6px 24px rgba(255, 50, 20, 0.85) !important;
        transform: scale(1.04) !important;
    }

    /* ── DİKKAT ÇEKİCİ BAŞLIK VE CANLI TURUNCU/KIRMIZI TAB BUTONLARI STİLİ ── */
    .stMarkdown h4 {
        font-size: 1.25rem !important;
        font-weight: 900 !important;
        color: #3DD3FF !important;
        letter-spacing: 0.03em !important;
        text-shadow: 0 0 14px rgba(61, 211, 255, 0.45) !important;
        border-bottom: 2px solid rgba(61, 211, 255, 0.35) !important;
        padding-bottom: 8px !important;
        margin-top: 14px !important;
        margin-bottom: 16px !important;
    }

    /* Tab List Yapısı */
    div[data-baseweb="tab-list"],
    div[role="tablist"],
    [data-testid="stTabs"] > div {
        gap: 12px !important;
        background: transparent !important;
        border-bottom: none !important;
        padding: 6px 0 16px 0 !important;
    }

    /* Tüm Sekme Butonları (Aktif ve Pasif) */
    div[data-baseweb="tab-list"] button,
    button[data-baseweb="tab"],
    div[role="tablist"] button,
    div[role="tablist"] [role="tab"],
    [data-testid="stTabs"] [role="tab"] {
        background: rgba(2, 28, 97, 0.88) !important;
        border: 1.5px solid rgba(61, 211, 255, 0.55) !important;
        color: #FFFFFF !important;
        font-weight: 850 !important;
        font-size: 0.98rem !important;
        border-radius: 10px !important;
        padding: 10px 24px !important;
        transition: all 0.22s ease !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4) !important;
        height: 48px !important;
    }

    /* Sekme Hover Hali */
    div[data-baseweb="tab-list"] button:hover,
    button[data-baseweb="tab"]:hover,
    div[role="tablist"] [role="tab"]:hover,
    [data-testid="stTabs"] [role="tab"]:hover {
        background: rgba(61, 211, 255, 0.30) !important;
        border-color: #3DD3FF !important;
        color: #FFFFFF !important;
    }

    /* Seçili (Aktif) Sekme Butonu — Tam Kırmızı/Turuncu Degrade Buton Görünümü */
    div[data-baseweb="tab-list"] button[aria-selected="true"],
    button[data-baseweb="tab"][aria-selected="true"],
    div[role="tablist"] [aria-selected="true"],
    [data-testid="stTabs"] [aria-selected="true"] {
        background: linear-gradient(135deg, #FF1A00 0%, #D80000 100%) !important;
        border: 1.5px solid rgba(255, 255, 255, 0.45) !important;
        color: #FFFFFF !important;
        font-weight: 900 !important;
        box-shadow: 0 4px 22px rgba(222, 56, 15, 0.88) !important;
        transform: translateY(-2px) !important;
    }

    /* Tab Yazılarının Net Beyaz Olması */
    div[data-baseweb="tab-list"] button *,
    button[data-baseweb="tab"] *,
    div[role="tablist"] [role="tab"] *,
    [data-testid="stTabs"] [role="tab"] * {
        color: #FFFFFF !important;
        font-weight: 850 !important;
        font-size: 0.98rem !important;
    }

    /* ── RAPOR ŞABLONU İNDİR VE SAĞ BUTONLAR (CANLI TURUNCU/KIRMIZI BUTON) ── */
    div[data-testid="stDownloadButton"] > button,
    div[data-testid="stButton"] > button[key*="btn_sablon_"],
    div[data-testid="stDownloadButton"] button {
        background: linear-gradient(135deg, #FF1A00 0%, #D80000 100%) !important;
        border: 1px solid rgba(255, 255, 255, 0.3) !important;
        color: #FFFFFF !important;
        font-weight: 850 !important;
        font-size: 0.95rem !important;
        border-radius: 8px !important;
        padding: 10px 20px !important;
        box-shadow: 0 4px 16px rgba(222, 56, 15, 0.65) !important;
        transition: all 0.22s ease !important;
        cursor: pointer !important;
        height: 44px !important;
    }
    div[data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stButton"] > button[key*="btn_sablon_"]:hover {
        background: linear-gradient(135deg, #FF3300 0%, #FF0000 100%) !important;
        box-shadow: 0 6px 24px rgba(255, 50, 20, 0.90) !important;
        transform: translateY(-2px) !important;
        color: #FFFFFF !important;
    }
    div[data-testid="stDownloadButton"] > button p,
    div[data-testid="stDownloadButton"] button p {
        color: #FFFFFF !important;
        font-weight: 850 !important;
        font-size: 0.95rem !important;
        margin: 0 !important;
    }

    /* Container borderlı kutuları koyu temaya çevir */
    [data-testid="stVerticalBlockBorderWrapper"] > div {
        background: rgba(2, 20, 61, 0.75) !important;
        border-color: rgba(61, 211, 255, 0.30) !important;
        border-radius: 10px !important;
        color: #E2E8F0 !important;
    }

    /* Markdown metinleri beyaz */
    .stMarkdown, .stMarkdown p, .stMarkdown li, .stMarkdown td, .stMarkdown th {
        color: #E2E8F0 !important;
    }
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        color: #FFFFFF !important;
    }
    table {
        background: rgba(2, 20, 61, 0.6) !important;
        color: #E2E8F0 !important;
        border-collapse: collapse !important;
        width: 100% !important;
    }
    th {
        background: rgba(14, 19, 122, 0.8) !important;
        color: #FFFFFF !important;
        padding: 10px 14px !important;
        border: 1px solid rgba(61, 211, 255, 0.3) !important;
    }
    td {
        padding: 9px 14px !important;
        border: 1px solid rgba(61, 211, 255, 0.15) !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. ÜST BAR: Geri Dönüş ve Başvuru Yap Butonları
    c_back, c_apply = st.columns([3.5, 1.5])
    with c_back:
        back_label = "← Ana Sayfaya Dön" if is_authenticated else "← Tanıtım Vitrinine Dön"
        if st.button(back_label, key="btn_back_from_comp_details", type="secondary"):
            st.query_params.clear()
            st.session_state["active_comp_detail_slug"] = None
            if is_authenticated:
                st.query_params["tab"] = "ana_sayfa"
                st.session_state.aktif_tab = "ana_sayfa"
            else:
                st.query_params["view"] = "landing"
            st.rerun()

    with c_apply:
        if is_authenticated:
            if st.button("Bu Yarışmaya Başvur →", key="btn_apply_authenticated", type="primary", use_container_width=True):
                st.session_state["selected_apply_comp"] = slug
                st.session_state["sel_app_comp_slug"] = slug
                st.session_state["show_new_app_form"] = True
                st.session_state.aktif_tab = "basvurular"
                st.query_params.clear()
                st.query_params["tab"] = "basvurular"
                st.rerun()
        else:
            if st.button("Başvuru Yap (Giriş Yap)", key="btn_apply_unauthenticated", type="primary", use_container_width=True):
                st.session_state.target_apply_comp = slug
                st.query_params.clear()
                st.query_params["view"] = "login"
                st.query_params["redirect_comp"] = slug
                st.rerun()

    st.markdown("<div style='height: 10px;'></div>", unsafe_allow_html=True)

    # 2. HERO KART: Yüzen Logo + Animasyonlu Başlık + Kategori
    logo_b64 = sartname_rehber.kategori_logosu_base64_getir(slug)
    logo_uri = logo_b64 or logo_data_uri(comp_title)

    # Yüzen daire içindeki logo (landing slider ile aynı animasyon)
    floating_circle_html = ""
    if logo_uri:
        floating_circle_html = f"""<div class="tf-detail-floating-circle">
<img class="tf-detail-floating-img" src="{logo_uri}" alt="{_esc(comp_title)}"/>
</div>"""

    desc_html = (
        f'<div style="font-size:0.95rem; color:#E2E8F0; margin-top:14px; line-height:1.6; '
        f'border-top:1px solid rgba(61,211,255,0.25); padding-top:12px;">{comp_desc}</div>'
        if comp_desc else ""
    )

    hero_html = f"""<div class="comp-detail-hero">
<div style="display:flex; align-items:center; justify-content:space-between; gap:28px; flex-wrap:wrap;">
<!-- Sol: Başlık & Bilgiler -->
<div class="tf-detail-hero-text" style="flex:1; min-width:260px;">
<div style="display:flex; align-items:center; gap:10px; margin-bottom:10px;">
<span style="background:#DE380F; color:#FFFFFF; font-size:0.75rem; font-weight:800; padding:3px 12px; border-radius:6px; letter-spacing:0.04em;">{_esc(comp_domain)}</span>
<span style="background:rgba(61,211,255,0.15); color:#3DD3FF; border:1px solid #3DD3FF; font-size:0.75rem; font-weight:700; padding:2px 10px; border-radius:6px;">2026 Resmî Dönem</span>
</div>
<div style="font-size:1.75rem; font-weight:900; color:#FFFFFF; line-height:1.2; text-shadow:0 2px 14px rgba(0,0,0,0.7); margin-bottom:10px;">
{_esc(comp_title)}
</div>
<div style="font-size:0.88rem; color:#CBD5E1; font-weight:600;">
<b style="color:#3DD3FF;">Hedef Seviye:</b> {_esc(comp_levels)}
&nbsp;|&nbsp;
<b style="color:#3DD3FF;">Değerlendirme:</b> AI 4. Göz & Resmî Hakem Heyeti
</div>
{desc_html}
</div>
<!-- Sağ: Yüzen Logo Dairesi -->
{floating_circle_html}
</div>
</div>"""
    st.markdown(hero_html, unsafe_allow_html=True)

    # 3. ŞARTNAME, AŞAMALAR VE TAKVİM BİLGİLERİ SEKME YAPISI
    st.markdown('<div class="comp-detail-tabs-wrap">', unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs([
        "Resmî Şartname ve Katılım Koşulları",
        "Değerlendirme Aşamaları & Rapor Şablonları",
        "2026 Resmî Yarışma Takvimi"
    ])

    # SEKME 1: Şartname ve Kurallar
    with tab1:
        rehber_info = sartname_rehber.klasor_bilgisi(slug)  # Tek seferinde çağrılır — iki kolonda paylaşılır
        sn_c1, sn_c2 = st.columns([1.1, 2.0])
        with sn_c1:
            st.markdown("#### Katılım ve Takım Kuralları")
            zk = sartname_rehber.sartnameden_kategori_zorunluluklarini_cikar(slug)
            min_t = zk.get("takim_uye_sayisi", {}).get("min", 2)
            max_t = zk.get("takim_uye_sayisi", {}).get("max", 6)
            dan_sarti = zk.get("danisman_sarti", "Lise kategorisi için zorunlu, üniversite ve üzeri için serbesttir.")

            st.markdown(f"""
- **Takım Büyüklüğü:** En az **{min_t}**, en fazla **{max_t}** üye
- **Danışman Şartı:** {dan_sarti}
- **Resmî Dil:** Türkçe raporlama (Teknik terimler parantez içinde belirtilebilir)
- **İntihal Toleransı:** Azami **%15** vektörel benzerlik sınırı
- **Etik İlke:** Rapor metninde takım/kişi bilgileri gizli (kör hakemlik) tutulmalıdır.
            """)

            # Resmî Şartname İndir Butonu
            sartname_pdf = rehber_info.get("sartname_pdf")
            if sartname_pdf and Path(sartname_pdf).exists():
                try:
                    pdf_bytes = Path(sartname_pdf).read_bytes()
                    st.download_button(
                        "Resmî Şartnameyi İndir (PDF)",
                        data=pdf_bytes,
                        file_name=f"{slug}_sartname_2026.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        type="primary"
                    )
                except Exception:
                    pass

        with sn_c2:
            st.markdown("#### Resmî Şartname Önizleme")
            sartname_yolu = str(rehber_info.get("sartname_pdf")) if rehber_info.get("sartname_pdf") else None
            if sartname_yolu and Path(sartname_yolu).exists():
                try:
                    import pdf_gorunum
                    pdf_gorunum.pdf_onizle(st, sartname_yolu, height=650, key=f"shared_detay_sn_{slug}")
                except Exception:
                    st.info("PDF önizleme hazırlanıyor...")
            else:
                st.info("Bu yarışmaya ait 2026 teknik şartname dokümanı sisteme işlenmektedir.")

    # SEKME 2: Aşamalar ve Şablonlar
    with tab2:
        st.markdown("#### Değerlendirme Aşamaları ve Rapor Şablonları")

        stages_data = []
        if d1_stages:
            for s in d1_stages:
                stages_data.append((
                    s.stage_code,
                    s.stage_name or s.stage_code,
                    f"Azami {s.max_pages} sayfa · {s.max_score} Azami Puan",
                    s.max_pages
                ))

        if not stages_data:
            stages_data = [
                ("OTR", "Ön Tasarım Raporu", "Takımın problem tanımı, yöntem yaklaşımı ve proje fizibilitesi incelenir.", 15),
                ("KTR", "Kritik Tasarım Raporu", "Algoritma mimarisi, donanım/yazılım entegrasyonu ve simülasyon test sonuçları değerlendirilir.", 25),
                ("FTR", "Final Değerlendirme & Saha", "Uçuş/saha görev performansı, canlı sistem sunumu ve operasyonel doğruluk test edilir.", 30),
            ]

        for scode, sname, sdesc, spages in stages_data:
            with st.container(border=True):
                stg_c1, stg_c2 = st.columns([3, 1.3])
                with stg_c1:
                    st.markdown(f"**{scode} · {sname}**")
                    st.caption(f"{sdesc} (Azami {spages} sayfa)")
                with stg_c2:
                    rehber_asama = sartname_rehber.dokuman_rehberi_getir(slug, scode)
                    sab_yol = rehber_asama.get("sablon_yolu")
                    if sab_yol and Path(sab_yol).exists():
                        try:
                            sab_bytes = Path(sab_yol).read_bytes()
                            st.download_button(
                                f"{scode} Rapor Şablonunu İndir (.docx)",
                                data=sab_bytes,
                                file_name=f"{slug}_{scode}_sablon.docx",
                                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                key=f"dl_sablon_{slug}_{scode}",
                                use_container_width=True
                            )
                        except Exception:
                            st.button(f"{scode} Rapor Şablonu", key=f"btn_sablon_{slug}_{scode}", use_container_width=True)
                    else:
                        st.button(f"{scode} Rapor Şablonu", key=f"btn_sablon_{slug}_{scode}", use_container_width=True)

    # SEKME 3: Takvim
    with tab3:
        st.markdown("#### TEKNOFEST 2026 Resmî Yarışma Takvimi")
        st.markdown("""
| Aşama | Tarih / Dönem | Açıklama |
| :--- | :--- | :--- |
| **Son Başvuru Tarihi** | 20 Şubat 2026 | Takım kaydı ve danışman onayı |
| **Ön Tasarım Raporu (ÖTR)** | 15 Mart 2026 | Resmî rapor şablonuna göre yükleme |
| **Kritik Tasarım Raporu (KTR)** | 15 Mayıs 2026 | Detaylı mimari ve simülasyon sonuçları |
| **Final Tasarım & Yeterlilik (FTR)** | 15 Temmuz 2026 | Canlı prototip ve saha test raporu |
| **TEKNOFEST 2026 Final Yarışları** | Ağustos / Eylül 2026 | Saha yarışları ve jüri değerlendirmesi |
        """)

    st.markdown('</div>', unsafe_allow_html=True)
