"""
T-Sistem · TEKNOFEST Birebir Resmî Tasarım, Otomatik Döngülü 60 Yarışma Slider & Detay Modalı & Canlı Duyurular Vitrini.
"""

from __future__ import annotations

import base64
import datetime
import time
from html import escape as _esc
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from src.database.db import db
from src.ui import sartname_rehber
from src.ui.logos import logo_data_uri


@st.cache_data(ttl=86400, show_spinner=False)
def _get_tsistem_logo_b64() -> str | None:
    logo_p = Path(__file__).resolve().parent.parent / "tsistem_logo.png"
    if not logo_p.exists():
        logo_p = Path(__file__).resolve().parent.parent / "tsistem_logo.jpg"
    if logo_p.exists():
        try:
            raw = logo_p.read_bytes()
            b64 = base64.b64encode(raw).decode("utf-8")
            mime = "image/png" if logo_p.suffix.lower() == ".png" else "image/jpeg"
            return f"data:{mime};base64,{b64}"
        except Exception:
            return None
    return None


@st.cache_data(ttl=3600)
def _load_all_competitions_for_showcase() -> list[dict]:
    """Tüm 60 TEKNOFEST yarışmasını veritabanından veya zengin yedek listeden yükler."""
    comps_list = []
    try:
        from src.data import repos
        d1_comps = repos().competitions.list(limit=100)
        if d1_comps:
            for c in d1_comps:
                comps_list.append({
                    "id": c.slug or c.competition_id,
                    "title": c.name or "TEKNOFEST Yarışması",
                    "category": (c.domain or "TEKNOFEST YARIŞMASI").upper(),
                    "desc": c.description or f"{c.name} kapsamında yarışmacı takımların yenilikçi projeleri, şartname ve rubrik kriterlerine göre yapay zekâ 4. göz motoruyla değerlendirilir.",
                    "image_url": f"https://cdn.teknofest.org/{c.logo_r2_key}" if c.logo_r2_key else "https://cdn.teknofest.org/media/upload/userFormUpload/t3-logo-TR-01_wnoJj_1_5TSjS.png",
                    "levels": c.levels or "Lise / Üniversite / Mezun",
                    "slug": c.slug
                })
    except Exception:
        pass

    if not comps_list:
        # Fallback listesi
        default_items = [
            ("havacilikta-yapay-zeka", "Havacılıkta Yapay Zeka Yarışması", "YAPAY ZEKA & YAZILIM", "Ulaşımda ve havacılıkta karşılaşılabilecek problemlere yapay zekâ ve derin öğrenme ile çözüm üretmek amaçlanmaktadır.", "https://cdn.teknofest.org/media/upload/userFormUpload/yapay-zeka_uxKxJ.png"),
            ("savasan-iha", "Savaşan İHA Yarışması", "HAVACILIK & OTONOM İHA", "Yüksek otonomi gerektiren İHA'lara it dalaşı, otonom hedef kilitlenme ve gerçek zamanlı takip kabiliyetleri kazandırılır.", "https://cdn.teknofest.org/media/upload/userFormUpload/222_49QT8-compressed_CfvKT.png"),
            ("roket", "Roket Yarışması", "UZAY & SAVUNMA", "Uzay teknolojileri alanında aviyonik tasarım, kademeli ayrılma ve faydalı yük fırlatma kabiliyetleri geliştirilir.", "https://cdn.teknofest.org/media/upload/userFormUpload/roket-2024-final_nrlZl.png"),
            ("model-uydu", "Model Uydu Yarışması", "UYDU & HABERLEŞME", "Gerçek bir uzay/uydu projesinin tasarımından fırlatılmasına, telemetri aktarımından görev icrasına kadar tüm süreçler tecrübe edilir.", "https://cdn.teknofest.org/media/upload/userFormUpload/model-uydu_rJvUM.png"),
            ("insansiz-su-alti", "İnsansız Su Altı Sistemleri Yarışması", "SU ALTI TEKNOLOJİLERİ", "Otonom veya uzaktan kumandalı su altı araçlarının (ROV/AUV) üretilmesi ve su altı hedef tespiti teşvik edilir.", "https://cdn.teknofest.org/media/upload/userFormUpload/robolig_rRQyE.png"),
            ("tarim-teknolojileri", "Tarım Teknolojileri Yarışması", "AKILLI TARIM & ÇEVRE", "İleri teknoloji, görüntü işleme ve robotik ile tarımdaki verimlilik ve hastalık tespit problemlerine yenilikçi çözümler üretilir.", "https://cdn.teknofest.org/media/upload/userFormUpload/tar%C4%B1m_86xVv.png"),
        ]
        for cid, cname, ccat, cdesc, cimg in default_items:
            comps_list.append({
                "id": cid,
                "title": cname,
                "category": ccat,
                "desc": cdesc,
                "image_url": cimg,
                "levels": "Tüm Eğitim Seviyeleri",
                "slug": cid
            })
    return comps_list


@st.cache_data(ttl=300, show_spinner=False)
def _get_cached_announcements() -> list[dict]:
    """Duyuruları 5 dakika önbelleğe alır — her render'da DB'ye gitmeyi önler."""
    try:
        return db.list_announcements() or []
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _get_cached_slider_payload() -> tuple[str, dict]:
    """Tüm yarışma listesini ve logolarını bir defa yükleyip JSON olarak önbelleğe alır (0ms)."""
    all_comps = _load_all_competitions_for_showcase()
    slider_list = []
    for c in all_comps:
        c_slug = c.get("slug") or c.get("id") or ""
        c_title = c.get("title", "")
        c_desc = c.get("desc", "")
        c_logo = (
            sartname_rehber.kategori_logosu_base64_getir(c_slug)
            or logo_data_uri(c_title)
            or c.get("image_url")
            or "https://cdn.teknofest.org/media/upload/userFormUpload/t3-logo-TR-01_wnoJj_1_5TSjS.png"
        )
        slider_list.append({
            "id": c.get("id", c_slug),
            "slug": c_slug,
            "title": c_title,
            "desc": c_desc,
            "logo": c_logo,
        })
    first_item = slider_list[0] if slider_list else {"title": "TEKNOFEST", "desc": "", "slug": "", "logo": ""}
    import json
    return json.dumps(slider_list), first_item


def render_landing_view() -> None:
    """TEKNOFEST resmî teması ve T-Sistem değerlendirme altyapısı açılış vitrini."""

    if st.query_params.get("view") == "comp":
        active_slug = st.query_params.get("slug") or st.session_state.get("active_comp_detail_slug") or "havacilikta-yapay-zeka"
        from src.ui.views import competition_detail_view
        is_auth = bool(st.session_state.get("authenticated", False))
        competition_detail_view.render_competition_detail_page(active_slug, is_authenticated=is_auth)
        return

    all_comps = _load_all_competitions_for_showcase()
    total_comps = len(all_comps)
    comps_data_json, first_c = _get_cached_slider_payload()

    # 0. TEKNOFEST RESMÎ CDN VE CSS
    st.markdown("""
    <link href="https://fonts.googleapis.com/css2?family=Muli:wght@300;400;600;700;800;900&family=Rajdhani:wght@500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.2/css/all.min.css">
    
    <style>
    * {
        font-family: 'Muli', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    /* Streamlit bazen component iframe'lerine pointer-events:none uygular — zorla aç */
    [data-testid="stCustomComponentV1"] iframe,
    [data-testid="stCustomComponentV1"],
    .stCustomComponentV1 iframe,
    iframe[title*="st_custom"] {
        pointer-events: auto !important;
    }
    
    .stApp {
        background: #02143D url('https://cdn.teknofest.org/media/upload/userFormUpload/TEKNOFEST-Istanbul-Web-Site-Zemin-1728x3365_oymmk.webp') no-repeat center top fixed !important;
        background-size: cover !important;
        color: #FFFFFF !important;
    }

    [data-testid="stHeader"] {
        background: transparent !important;
    }
    
    .block-container {
        padding-top: 0.8rem !important;
        padding-bottom: 3.5rem !important;
        max-width: 1400px !important;
    }

    /* İnteraktif Hero Showcase Alanı */
    .tf-slider-container {
        background: transparent;
        border: none;
        padding: 0;
        margin-bottom: 24px;
        position: relative;
    }

    /* Sayaç Radar Tarama Çizgisi Animasyonu (Merkezden Dönen Işın) */
    @keyframes radarSweep {
        0% {
            transform: rotate(0deg);
        }
        100% {
            transform: rotate(360deg);
        }
    }

    .tf-radar-box {
        position: relative;
        background: linear-gradient(135deg, rgba(2, 28, 97, 0.88), rgba(1, 14, 46, 0.96));
        border: 1.5px solid #3DD3FF;
        border-radius: 16px;
        padding: 14px 28px;
        box-shadow: 0 0 25px rgba(61, 211, 255, 0.3), inset 0 0 20px rgba(61, 211, 255, 0.15);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 36px;
        min-width: 400px;
        overflow: hidden;
    }

    .tf-radar-box::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: conic-gradient(from 0deg at 50% 50%, transparent 0deg, transparent 300deg, rgba(61, 211, 255, 0.4) 360deg);
        animation: radarSweep 4s linear infinite;
        pointer-events: none;
        z-index: 1;
    }

    .tf-radar-content {
        position: relative;
        z-index: 2;
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }

    .tf-floating-circle {
        position: relative;
        width: 320px;
        height: 320px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(61, 211, 255, 0.22) 0%, rgba(2, 28, 97, 0.1) 70%);
        border: 1.5px solid rgba(61, 211, 255, 0.4);
        box-shadow: 0 0 35px rgba(61, 211, 255, 0.25);
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto;
        pointer-events: none;
    }

    .tf-floating-img {
        max-width: 270px;
        max-height: 240px;
        object-fit: contain;
        filter: drop-shadow(0 15px 25px rgba(0, 0, 0, 0.5));
        pointer-events: none;
    }

    .tf-slider-title {
        font-size: 2.35rem;
        font-weight: 900;
        color: #FFFFFF;
        line-height: 1.2;
        letter-spacing: -0.02em;
        margin-bottom: 16px;
    }

    .tf-slider-desc {
        font-size: 1.05rem;
        color: #CBD5E1;
        line-height: 1.65;
        margin-bottom: 24px;
        max-width: 650px;
    }

    /* Şeffaf ve Temaya Birebir Ok Tuşları */
    div.st-key-btn_prev_comp button, div.st-key-btn_next_comp button {
        background: rgba(2, 28, 97, 0.45) !important;
        border: 1.5px solid rgba(61, 211, 255, 0.55) !important;
        color: #3DD3FF !important;
        font-size: 1.4rem !important;
        font-weight: 900 !important;
        border-radius: 50% !important;
        width: 48px !important;
        height: 48px !important;
        padding: 0 !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        box-shadow: 0 4px 15px rgba(0,0,0,0.3) !important;
        backdrop-filter: blur(8px) !important;
        transition: all 0.2s ease !important;
    }
    div.st-key-btn_prev_comp button:hover, div.st-key-btn_next_comp button:hover {
        background: rgba(61, 211, 255, 0.25) !important;
        border-color: #3DD3FF !important;
        transform: scale(1.12) !important;
        color: #FFFFFF !important;
        box-shadow: 0 0 20px rgba(61, 211, 255, 0.6) !important;
    }

    /* Resmî Duyuru Kartı Stili (teknofest.org duyuruCard birebir) */
    .tf-ann-card-pro {
        background: #DEEFF4;
        border-radius: 10px;
        overflow: hidden;
        height: 100%;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        transition: transform 0.22s ease, box-shadow 0.22s ease;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.15);
    }
    .tf-ann-card-pro:hover {
        transform: translateY(-4px);
        box-shadow: 0 10px 24px rgba(222, 56, 15, 0.3);
    }
    .tf-ann-card-top {
        background: #0E137A;
        padding: 8px 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .tf-ann-card-date {
        color: #FFFFFF;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    }
    .tf-ann-card-cat {
        background: #DE380F;
        color: #FFFFFF;
        font-size: 0.68rem;
        font-weight: 800;
        padding: 2px 8px;
        border-radius: 4px;
        letter-spacing: 0.04em;
    }
    .tf-ann-card-body {
        padding: 16px 14px;
        flex-grow: 1;
    }
    .tf-ann-card-title {
        color: #0E137A;
        font-size: 0.98rem;
        font-weight: 800;
        line-height: 1.35;
        margin-bottom: 8px;
    }
    .tf-ann-card-snippet {
        color: #334155;
        font-size: 0.82rem;
        line-height: 1.45;
    }

    /* TEKNOFEST Neon Radar Göstergeleri */
    .tf-mini-stat {
        background: rgba(2, 28, 97, 0.75);
        border: 1px solid rgba(61, 211, 255, 0.35);
        border-radius: 12px;
        padding: 14px;
        text-align: center;
        box-shadow: 0 4px 16px rgba(55, 210, 255, 0.2);
    }
    .tf-mini-stat-num {
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.8rem;
        font-weight: 700;
        color: #3DD3FF;
        line-height: 1.1;
    }
    .tf-mini-stat-lbl {
        font-size: 0.74rem;
        color: #CBD5E1;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }

    /* Buton Tasarımları */
    div[data-testid="stButton"] > button[kind="primary"] {
        background: radial-gradient(40.93% 124% at 87.33% 62%, #FF0000 0%, rgba(255, 0, 0, 0) 100%),
                    linear-gradient(96.21deg, #DE380F 6.99%, #A02000 102.8%) !important;
        border: 1px solid #FF6A45 !important;
        color: #FFFFFF !important;
        font-weight: 800 !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 14px rgba(222, 56, 15, 0.45) !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"] {
        background: rgba(255, 255, 255, 0.12) !important;
        border: 1.5px solid rgba(255, 255, 255, 0.4) !important;
        color: #FFFFFF !important;
        font-weight: 700 !important;
        border-radius: 8px !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. ÜST HEADER (NAVBAR)
    with st.container():
        nav_c1, nav_c2 = st.columns([2.9, 1.3])
        with nav_c1:
            logo_b64 = _get_tsistem_logo_b64()
            if logo_b64:
                logo_badge_html = (
                    '<div style="position:relative; display:inline-flex; align-items:center; justify-content:center; padding:10px 14px; border-radius:24px; background:rgba(255, 255, 255, 0.18); backdrop-filter:blur(10px); box-shadow:0 0 35px rgba(255,255,255,0.45);">'
                    f'<img src="{logo_b64}" style="height:120px; max-width:150px; object-fit:contain; filter:drop-shadow(0 6px 18px rgba(255,255,255,0.6));" alt="T-Sistem Logo"/>'
                    '</div>'
                )
            else:
                logo_badge_html = ""

            header_brand_html = (
                '<div style="display:flex; align-items:center; gap:24px; padding: 6px 0;">'
                f'{logo_badge_html}'
                '<div>'
                '<div style="font-size:2.25rem; font-weight:900; color:#FFFFFF; letter-spacing:-0.02em; line-height:1.1; text-shadow:0 2px 12px rgba(0,0,0,0.6);">'
                '<span style="color:#FFA500;">T-SİSTEM</span>'
                '</div>'
                '<div style="font-size:0.84rem; font-weight:800; color:#3DD3FF; letter-spacing:0.08em; text-transform:uppercase; margin-top:4px;">'
                'Yapay Zekâ Destekli 4. Göz Rapor Değerlendirme İstasyonu'
                '</div>'
                '</div>'
                '</div>'
            )
            st.markdown(header_brand_html, unsafe_allow_html=True)

        with nav_c2:
            st.write("<div style='height:16px;'></div>", unsafe_allow_html=True)
            b_c1, b_c2 = st.columns(2)
            with b_c1:
                if st.button("DUYURULAR", key="tf_nav_announcements_top", type="secondary", use_container_width=True):
                    st.query_params["view"] = "ann"
                    st.rerun()
            with b_c2:
                is_auth = bool(st.session_state.get("authenticated", False))
                if is_auth:
                    if st.button("PANELİME GİT →", key="tf_nav_panel_top", type="primary", use_container_width=True):
                        st.query_params.clear()
                        st.query_params["tab"] = "ana_sayfa"
                        st.rerun()
                else:
                    if st.button("GİRİŞ YAP", key="tf_nav_login_top", type="primary", use_container_width=True):
                        st.query_params["view"] = "login"
                        st.rerun()

    # Navbar -> Slider boşluğu
    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # 2. İNTERAKTİF 60 YARIŞMA SLIDER'I & ŞEFFAF OK TUŞLARI (KAYARAK GELME & GİTME ANİMASYONU)
    if "landing_slider_idx" not in st.session_state:
        st.session_state.landing_slider_idx = 0

    import json
    try:
        comps = json.loads(comps_data_json) if comps_data_json else [first_c]
    except Exception:
        comps = [first_c]

    if not comps:
        comps = [first_c]

    current_idx = st.session_state.landing_slider_idx % len(comps)
    current_c = comps[current_idx]
    c_title = current_c.get("title", "")
    c_desc = current_c.get("desc", "")
    c_slug = current_c.get("slug") or current_c.get("id") or ""
    c_logo = current_c.get("logo", "")

    st.markdown("""
    <style>
    /* ── Slider Animasyonları ── */
    @keyframes slideInLeft {
        0%   { opacity: 0; transform: translateX(-48px); }
        100% { opacity: 1; transform: translateX(0); }
    }
    @keyframes fadeInScale {
        0%   { opacity: 0; transform: scale(0.82); }
        100% { opacity: 1; transform: scale(1); }
    }
    @keyframes floatUpDown {
        0%, 100% { transform: translateY(0px);   box-shadow: 0 0 40px rgba(61,211,255,0.30); }
        50%       { transform: translateY(-14px); box-shadow: 0 24px 50px rgba(61,211,255,0.50); }
    }

    .tf-carousel-container {
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: center;
        position: relative;
        min-height: 380px;
        margin: 10px 0 20px 0;
    }
    .tf-comp-title {
        font-size: 2.30rem;
        font-weight: 900;
        color: #FFFFFF;
        line-height: 1.22;
        letter-spacing: -0.02em;
        margin-bottom: 16px;
        text-shadow: 0 2px 14px rgba(0, 0, 0, 0.7);
        animation: slideInLeft 0.55s cubic-bezier(0.22,1,0.36,1) both;
    }
    .tf-comp-desc {
        font-size: 1.05rem;
        color: #CBD5E1;
        line-height: 1.60;
        margin-bottom: 22px;
        max-width: 620px;
        text-shadow: 0 1px 8px rgba(0, 0, 0, 0.6);
        animation: slideInLeft 0.70s 0.08s cubic-bezier(0.22,1,0.36,1) both;
    }
    .tf-circle-aura {
        position: relative;
        width: 310px;
        height: 310px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(61, 211, 255, 0.25) 0%, rgba(2, 28, 97, 0.12) 70%);
        border: 1.5px solid rgba(61, 211, 255, 0.45);
        display: flex;
        align-items: center;
        justify-content: center;
        margin: 0 auto;
        pointer-events: none;
        animation: floatUpDown 3.2s ease-in-out infinite, fadeInScale 0.6s 0.1s cubic-bezier(0.22,1,0.36,1) both;
    }
    .tf-circle-logo {
        max-width: 250px;
        max-height: 220px;
        object-fit: contain;
        filter: drop-shadow(0 15px 25px rgba(0, 0, 0, 0.5));
        pointer-events: none;
        animation: fadeInScale 0.55s cubic-bezier(0.22,1,0.36,1) both;
    }
    /* Sadece ileri/geri ok butonları daire — key ile scope edildi */
    div.st-key-btn_slider_prev button,
    div.st-key-btn_slider_next button {
        background: rgba(2, 28, 97, 0.65) !important;
        border: 1.5px solid rgba(61, 211, 255, 0.65) !important;
        color: #3DD3FF !important;
        font-size: 1.4rem !important;
        border-radius: 50% !important;
        width: 50px !important;
        height: 50px !important;
        min-width: 50px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        cursor: pointer !important;
        backdrop-filter: blur(8px) !important;
        transition: all 0.22s ease !important;
        box-shadow: 0 0 14px rgba(61, 211, 255, 0.35) !important;
        padding: 0 !important;
    }
    div.st-key-btn_slider_prev button:hover,
    div.st-key-btn_slider_next button:hover {
        background: rgba(61, 211, 255, 0.35) !important;
        border-color: #3DD3FF !important;
        color: #FFFFFF !important;
        transform: scale(1.15) !important;
        box-shadow: 0 0 22px rgba(61, 211, 255, 0.7) !important;
    }
    </style>
    """, unsafe_allow_html=True)

    # Geçiş yönü: ileri → sağdan, geri → soldan
    if "slider_direction" not in st.session_state:
        st.session_state.slider_direction = 1
    direction = st.session_state.slider_direction
    enter_anim = "enterFromRight" if direction > 0 else "enterFromLeft"

    slug_to_open = c_slug or "havacilikta-yapay-zeka"
    nav_slug = slug_to_open

    # ── SLIDER LAYOUT: prev | [components.html içerik] | next ──────────────
    st.markdown("""
    <style>
    div.st-key-btn_slider_prev button, div.st-key-btn_slider_next button {
        background: rgba(2,28,97,0.65) !important;
        border: 1.5px solid rgba(61,211,255,0.65) !important;
        color: #3DD3FF !important; font-size:1.4rem !important;
        border-radius:50% !important; width:50px !important; height:50px !important;
        min-width:50px !important; display:flex !important;
        align-items:center !important; justify-content:center !important;
        backdrop-filter:blur(8px) !important; padding:0 !important;
        box-shadow:0 0 14px rgba(61,211,255,0.35) !important;
        transition: all 0.22s ease !important;
    }
    div.st-key-btn_slider_prev button:hover, div.st-key-btn_slider_next button:hover {
        background:rgba(61,211,255,0.35) !important; border-color:#3DD3FF !important;
        color:#FFFFFF !important; transform:scale(1.15) !important;
        box-shadow:0 0 22px rgba(61,211,255,0.7) !important;
    }
    /* Gizli navigasyon tetikleyici buton */
    div.st-key-btn_detaylar_hidden {
        position:absolute !important; opacity:0 !important;
        pointer-events:none !important; width:0 !important; height:0 !important; overflow:hidden !important;
    }
    </style>
    """, unsafe_allow_html=True)

    c_prev, c_content, c_next = st.columns([0.8, 12, 0.8], vertical_alignment="center")

    with c_prev:
        if st.button("❮", key="btn_slider_prev", type="secondary", help="Önceki Yarışma"):
            st.session_state.slider_direction = -1
            st.session_state.landing_slider_idx -= 1
            st.rerun()

    with c_content:
        # components.html → her rerun'da iframe yeniden oluşur → animasyonlar KESINLIKLE çalışır
        slide_html = f"""<!DOCTYPE html>
<html>
<head>
<link href="https://fonts.googleapis.com/css2?family=Muli:wght@700;800;900&display=swap" rel="stylesheet">
<style>
*{{margin:0;padding:0;box-sizing:border-box;font-family:'Muli',sans-serif;}}
body{{background:transparent;overflow:hidden;}}

@keyframes enterFromRight{{
    from{{opacity:0;transform:translateX(70px);}}
    to{{opacity:1;transform:translateX(0);}}
}}
@keyframes enterFromLeft{{
    from{{opacity:0;transform:translateX(-70px);}}
    to{{opacity:1;transform:translateX(0);}}
}}
@keyframes exitToLeft{{
    from{{opacity:1;transform:translateX(0);}}
    to{{opacity:0;transform:translateX(-70px);}}
}}
@keyframes floatUpDown{{
    0%,100%{{transform:translateY(0px);}}
    50%{{transform:translateY(-22px);}}
}}
@keyframes circleGlow{{
    0%,100%{{box-shadow:0 0 30px rgba(61,211,255,0.35),0 15px 40px rgba(0,0,0,0.4);}}
    50%{{box-shadow:0 0 55px rgba(61,211,255,0.65),0 35px 60px rgba(61,211,255,0.25);}}
}}
@keyframes fadeInFromDir{{
    from{{opacity:0;transform:scale(0.78);}}
    to{{opacity:1;transform:scale(1);}}
}}
@keyframes imgFloat{{
    0%,100%{{filter:drop-shadow(0 8px 20px rgba(0,0,0,0.55));}}
    50%{{filter:drop-shadow(0 24px 40px rgba(61,211,255,0.5));}}
}}
@keyframes floatBtn{{
    0%,100%{{transform:translateY(0px);box-shadow:0 6px 28px rgba(222,56,15,0.55);}}
    50%{{transform:translateY(-12px);box-shadow:0 20px 44px rgba(222,56,15,0.85);}}
}}

.layout{{
    display:flex;align-items:center;justify-content:space-between;
    gap:28px;padding:20px 4px;min-height:410px;
}}
.text-side{{flex:1.3;display:flex;flex-direction:column;gap:0;}}
.text-title{{
    font-size:2.20rem;font-weight:900;color:#FFFFFF;
    line-height:1.22;letter-spacing:-0.02em;margin-bottom:16px;
    text-shadow:0 2px 14px rgba(0,0,0,0.7);
    animation:{enter_anim} 0.55s cubic-bezier(0.22,1,0.36,1) both;
}}
.text-desc{{
    font-size:1.02rem;color:#CBD5E1;line-height:1.60;
    text-shadow:0 1px 8px rgba(0,0,0,0.6);
    animation:{enter_anim} 0.72s 0.09s cubic-bezier(0.22,1,0.36,1) both;
    margin-bottom:52px;
}}
/* DETAYLAR — slide ile birlikte girer, float ayrı wrapper'da */
.detaylar-area{{
    animation:{enter_anim} 0.88s 0.18s cubic-bezier(0.22,1,0.36,1) both;
}}
.detaylar-hint{{
    font-size:0.74rem;font-weight:700;color:#64748B;
    letter-spacing:0.14em;text-transform:uppercase;margin-bottom:8px;
}}
.detaylar-float{{
    display:inline-block;
    animation:floatBtn 3.2s ease-in-out infinite;
}}
.detaylar-btn{{
    background:linear-gradient(135deg,#FF1A00 0%,#C80000 100%);
    color:#FFFFFF;font-family:'Muli',sans-serif;font-weight:900;
    font-size:1.05rem;letter-spacing:0.08em;padding:14px 52px;
    border-radius:10px;border:1.5px solid rgba(255,120,80,0.5);
    cursor:pointer;width:100%;
}}
.detaylar-btn:hover{{filter:brightness(1.18);}}
/* fadeIn → circle-wrapper'a, floatUpDown → circle'a ayrı elementlerde
   böylece transform çakışmaz */
.circle-side{{
    flex:0.9;display:flex;justify-content:center;
    animation:fadeInFromDir 0.65s 0.10s cubic-bezier(0.22,1,0.36,1) both;
}}
.circle-wrapper{{
    animation:floatUpDown 3.2s ease-in-out infinite;
}}
.circle{{
    width:390px;height:390px;border-radius:50%;
    background:radial-gradient(circle,rgba(61,211,255,0.25) 0%,rgba(2,28,97,0.12) 70%);
    border:1.5px solid rgba(61,211,255,0.45);
    display:flex;align-items:center;justify-content:center;
    animation:circleGlow 3.2s ease-in-out infinite;
}}
.circle img{{
    max-width:320px;max-height:300px;width:320px;height:300px;object-fit:contain;
    animation:imgFloat 3.2s ease-in-out infinite;
}}
</style>
</head>
<body>
<div class="layout">
    <div class="text-side">
        <div class="text-title">{_esc(c_title)}</div>
        <div class="text-desc">{_esc(c_desc)}</div>
        <div class="detaylar-area">
            <div class="detaylar-hint">↓ Yarışmayı İncele</div>
            <div class="detaylar-float">
                <button class="detaylar-btn"
                    onclick="(function(){{var b=window.parent.document.querySelector('div.st-key-btn_detaylar_hidden button');if(b)b.click();}})()">
                    DETAYLAR
                </button>
            </div>
        </div>
    </div>
    <div class="circle-side">
        <div class="circle-wrapper">
            <div class="circle">
                <img src="{_esc(c_logo)}" alt="Logo"/>
            </div>
        </div>
    </div>
</div>
</body>
</html>"""
        components.html(slide_html, height=520)

    with c_next:
        if st.button("❯", key="btn_slider_next", type="secondary", help="Sonraki Yarışma"):
            st.session_state.slider_direction = 1
            st.session_state.landing_slider_idx += 1
            st.rerun()

    # Gizli navigasyon butonu — iframe içindeki DETAYLAR bunu JS ile tıklar
    if st.button("__detaylar_nav__", key="btn_detaylar_hidden", type="primary"):
        st.query_params.clear()
        st.query_params["view"] = "comp"
        st.query_params["slug"] = nav_slug
        st.rerun()

    # OTOMATİK GEÇİŞ — 5 saniyede ❯ butonuna JS ile tıklar; manuel tıklamada timer sıfırlar
    components.html("""<script>
(function(){
    var D=5000,t;
    function goNext(){
        var b=window.parent.document.querySelectorAll('button');
        for(var i=0;i<b.length;i++){if(b[i].textContent.trim()==='❯'){b[i].click();break;}}
    }
    function reset(){clearTimeout(t);t=setTimeout(goNext,D);}
    reset();
    window.parent.document.addEventListener('click',reset);
})();
</script>""", height=0)

    # CANLI TEKNOFEST 2026 GERİ SAYIM SAYACI (Dikey/Yatay Tam Ortada ve Radar Tarama Çizgili)
    now_dt = datetime.datetime.now()
    target_dt = datetime.datetime(2026, 9, 30, 9, 0, 0)
    diff_secs = max(0, int((target_dt - now_dt).total_seconds()))
    init_days = diff_secs // 86400
    init_hours = (diff_secs % 86400) // 3600
    init_mins = (diff_secs % 3600) // 60
    init_secs = diff_secs % 60
    # CANLI TEKNOFEST 2026 GERİ SAYIM SAYACI (HTML5 Canvas ile Tam Köşelere Ulaşan 360° Neon Radar Işını)
    countdown_component_code = """
    <!DOCTYPE html>
    <html>
    <head>
    <link href="https://fonts.googleapis.com/css2?family=Muli:wght@600;700;800;900&family=Rajdhani:wght@600;700;800&display=swap" rel="stylesheet">
    <style>
    * {
        box-sizing: border-box;
        margin: 0;
        padding: 0;
        user-select: none;
        font-family: 'Muli', sans-serif;
    }
    body {
        background: transparent;
        display: flex;
        justify-content: center;
        align-items: center;
        overflow: hidden;
    }
    .tf-radar-box {
        position: relative;
        background: linear-gradient(135deg, rgba(2, 28, 97, 0.95), rgba(1, 14, 46, 0.98));
        border: 1.5px solid #3DD3FF;
        border-radius: 16px;
        padding: 14px 28px;
        box-shadow: 0 0 25px rgba(61, 211, 255, 0.35), inset 0 0 20px rgba(61, 211, 255, 0.15);
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 36px;
        width: 100%;
        max-width: 480px;
        overflow: hidden;
    }
    #radarCanvas {
        position: absolute;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        pointer-events: none;
        z-index: 1;
    }
    .tf-radar-content {
        position: relative;
        z-index: 2;
        width: 100%;
        display: flex;
        align-items: center;
        justify-content: space-between;
    }
    .tf-left-title {
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.25rem;
        font-weight: 900;
        color: #FFFFFF;
        letter-spacing: 0.04em;
        line-height: 1.1;
    }
    .tf-left-sub {
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.10rem;
        font-weight: 800;
        color: #FFA500;
        letter-spacing: 0.06em;
        line-height: 1.1;
    }
    .tf-left-loc {
        font-size: 0.74rem;
        color: #94A3B8;
        margin-top: 2px;
        font-weight: 600;
    }
    .tf-right-days {
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.65rem;
        font-weight: 850;
        color: #FFFFFF;
        line-height: 1;
        text-shadow: 0 0 12px rgba(61,211,255,0.7);
        text-align: right;
    }
    .tf-right-time {
        font-family: 'Rajdhani', sans-serif;
        font-size: 1.30rem;
        font-weight: 700;
        color: #3DD3FF;
        letter-spacing: 0.08em;
        margin-top: 3px;
        text-shadow: 0 0 10px rgba(61,211,255,0.8);
        text-align: right;
    }
    </style>
    </head>
    <body>
        <div class="tf-radar-box" id="radarContainer">
            <canvas id="radarCanvas"></canvas>
            <div class="tf-radar-content">
                <div>
                    <div class="tf-left-title">TEKNOFEST 2026</div>
                    <div class="tf-left-sub">GÜNEYDOĞU</div>
                    <div class="tf-left-loc">Şanlıurfa GAP Havalimanı</div>
                </div>
                <div>
                    <div id="days_val" class="tf-right-days">29 Gün</div>
                    <div id="time_val" class="tf-right-time">17:23:54</div>
                </div>
            </div>
        </div>

        <script>
        // 1. CANLI GERİ SAYIM MOTORU
        const targetDate = new Date(2026, 8, 30, 9, 0, 0).getTime();
        function update() {
            const now = new Date().getTime();
            const diff = targetDate - now;
            if (diff > 0) {
                const days = Math.floor(diff / (1000 * 60 * 60 * 24));
                const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((diff % (1000 * 60)) / 1000);

                const dEl = document.getElementById('days_val');
                const tEl = document.getElementById('time_val');
                if (dEl) dEl.innerText = days + ' Gün';
                if (tEl) {
                    const hStr = hours < 10 ? '0' + hours : hours;
                    const mStr = minutes < 10 ? '0' + minutes : minutes;
                    const sStr = seconds < 10 ? '0' + seconds : seconds;
                    tEl.innerText = hStr + ':' + mStr + ':' + sStr;
                }
            }
        }
        setInterval(update, 1000);
        update();

        // 2. KUTUNUN TAM KÖŞELERİNE ULAŞAN GERÇEK RADAR IŞINI (HTML5 Canvas)
        const canvas = document.getElementById('radarCanvas');
        const ctx = canvas.getContext('2d');
        const box = document.getElementById('radarContainer');

        function resizeCanvas() {
            canvas.width = box.clientWidth;
            canvas.height = box.clientHeight;
        }
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);

        let angle = 0;
        function drawRadar() {
            const w = canvas.width;
            const h = canvas.height;
            const cx = w / 2;
            const cy = h / 2;
            const maxRadius = Math.sqrt(cx * cx + cy * cy) + 10; // Tam köşelere yetişen yarıçap

            ctx.clearRect(0, 0, w, h);

            // Radar fan kuyruğu (Gradient)
            const sweepSpan = Math.PI / 3; // 60 derecelik ışıltı fanı
            const steps = 30;
            for (let i = 0; i < steps; i++) {
                const a1 = angle - (sweepSpan * (i / steps));
                const a2 = angle - (sweepSpan * ((i + 1) / steps));
                const opacity = (1 - (i / steps)) * 0.38;

                ctx.beginPath();
                ctx.moveTo(cx, cy);
                ctx.arc(cx, cy, maxRadius, a2, a1);
                ctx.closePath();
                ctx.fillStyle = `rgba(61, 211, 255, ${opacity})`;
                ctx.fill();
            }

            // Ana Radar Öncü Işını (Parlak Çizgi)
            const lx = cx + Math.cos(angle) * maxRadius;
            const ly = cy + Math.sin(angle) * maxRadius;

            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(lx, ly);
            ctx.strokeStyle = 'rgba(61, 211, 255, 0.95)';
            ctx.lineWidth = 2.0;
            ctx.shadowColor = '#3DD3FF';
            ctx.shadowBlur = 12;
            ctx.stroke();
            ctx.shadowBlur = 0;

            angle += 0.025; // Akıcı radar tarama dönüş hızı
            requestAnimationFrame(drawRadar);
        }
        requestAnimationFrame(drawRadar);
        </script>
    </body>
    </html>
    """
    components.html(countdown_component_code, height=115)

    # GENİŞ BOŞLUK: Sayaç -> Metrikler
    st.markdown("<div style='height:75px;'></div>", unsafe_allow_html=True)

    # 3. SİSTEM GÖSTERGELERİ METRİKLERİ
    m1, m2, m3, m4 = st.columns(4)
    with m1:
        st.markdown(f"""
        <div class="tf-mini-stat">
            <div class="tf-mini-stat-lbl">Yarışma Kapsamı</div>
            <div class="tf-mini-stat-num">{total_comps}</div>
            <div style="font-size:0.72rem; color:#3DD3FF; font-weight:700;">Tüm TEKNOFEST Alanları</div>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        st.markdown("""
        <div class="tf-mini-stat">
            <div class="tf-mini-stat-lbl">AI 4. Göz Doğruluğu</div>
            <div class="tf-mini-stat-num">%98.4</div>
            <div style="font-size:0.72rem; color:#CBD5E1; font-weight:600;">Şartname Kural Denetimi</div>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown("""
        <div class="tf-mini-stat">
            <div class="tf-mini-stat-lbl">İntihal Analizi</div>
            <div class="tf-mini-stat-num">Semantik</div>
            <div style="font-size:0.72rem; color:#FFA07A; font-weight:600;">Vektörel Benzerlik Matrisi</div>
        </div>
        """, unsafe_allow_html=True)
    with m4:
        st.markdown("""
        <div class="tf-mini-stat">
            <div class="tf-mini-stat-lbl">Karar Güvenliği</div>
            <div class="tf-mini-stat-num">Mühürlü</div>
            <div style="font-size:0.72rem; color:#CBD5E1; font-weight:600;">Resmî Hakem Karnesi</div>
        </div>
        """, unsafe_allow_html=True)

    # GENİŞ BOŞLUK: Metrikler -> Duyurular
    st.markdown("<div style='height:75px;'></div>", unsafe_allow_html=True)

    # 4. RESMÎ DUYURULAR AKIŞI (TEKNOFEST BİREBİR KARTLAR & TÜM DUYURULAR BUTONU)
    ann_head1, ann_head2 = st.columns([3.5, 1.2])
    with ann_head1:
        st.markdown(
            """
            <div style="font-size:1.35rem; font-weight:900; color:#FFFFFF; letter-spacing:0.02em;">
                Resmî Duyurular ve Yarışma Bildirimleri
            </div>
            """,
            unsafe_allow_html=True
        )
    with ann_head2:
        if st.button("Tüm Duyurular →", key="btn_go_all_announcements", type="primary", use_container_width=True):
            st.query_params["view"] = "ann"
            st.rerun()

    st.markdown("<div style='height:24px;'></div>", unsafe_allow_html=True)

    # DUYURU DETAY MODALI AÇIKSA GÖSTER
    if st.session_state.get("selected_announcement"):
        from src.ui.views.announcements_view import render_announcement_detail_modal
        render_announcement_detail_modal(st.session_state.selected_announcement)

    announcements = _get_cached_announcements()
    fallback_covers = [
        "https://cdn.teknofest.org/media/upload/userFormUpload/kapak_gorsel_GqVNx.jpeg",
        "https://cdn.teknofest.org/media/upload/userFormUpload/dikeyini%C5%9Filitr_iXgg8_wggoj_mNPAa.jpg",
        "https://cdn.teknofest.org/media/upload/userFormUpload/harp-tr_gAM2G_FhhNk.jpg",
        "https://cdn.teknofest.org/media/upload/userFormUpload/tr_i_sualt%C4%B1_lnLq4_e65WY.jpg"
    ]

    if announcements:
        cols = st.columns(4)
        for i, a in enumerate(announcements[:4]):
            title = _esc(str(a.get("title", "")))
            content = _esc(str(a.get("content", "")))
            cat = _esc(str(a.get("category", "GENEL")))
            date_str = _esc(str(a.get("created_at", ""))[:10])
            is_pin = bool(a.get("is_pinned", 0))
            img_url = _esc(str(a.get("image_url") or fallback_covers[i % len(fallback_covers)]))
            a_id = _esc(str(a.get("announcement_id", f"land_ann_{i}")))

            with cols[i]:
                # Kartın tamamı tek parça chip kutusu halinde render edilir, buton alt footer kısmına gömülüdür
                card_chip_html = f"""
                <div style="background:#DEEFF4; border-radius:14px; overflow:hidden; display:flex; flex-direction:column; justify-content:space-between; min-height:360px; box-shadow:0 6px 20px rgba(0,0,0,0.25); border:1px solid rgba(61,211,255,0.3); transition:transform 0.2s ease;">
                    <div>
                        <div style="width:100%; height:135px; display:flex; align-items:center; justify-content:center; background:#FFFFFF; padding:8px; border-bottom:1px solid #E2E8F0;">
                            <img src="{img_url}" style="max-width:100%; max-height:100%; object-fit:contain;" alt="{title}"/>
                        </div>
                        <div style="background:#0E137A; padding:6px 12px; display:flex; justify-content:space-between; align-items:center;">
                            <span style="color:#FFFFFF; font-size:0.75rem; font-weight:700;">{date_str}</span>
                            <span style="background:#DE380F; color:#FFFFFF; font-size:0.68rem; font-weight:800; padding:2px 8px; border-radius:4px;">{"ÖNE ÇIKAN" if is_pin else cat}</span>
                        </div>
                        <div style="padding:12px 14px;">
                            <div style="color:#0E137A; font-size:0.95rem; font-weight:850; line-height:1.3; margin-bottom:6px; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;">
                                {title}
                            </div>
                            <div style="color:#334155; font-size:0.80rem; line-height:1.45; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;">
                                {content}
                            </div>
                        </div>
                    </div>
                    <div style="padding:10px 14px 14px 14px; background:rgba(14,19,122,0.06); border-top:1px solid rgba(14,19,122,0.12); display:flex; align-items:center; justify-content:space-between;">
                        <span style="font-size:0.72rem; color:#64748B; font-weight:700;">TEKNOFEST 2026</span>
                        <a href="?view=ann_detail&ann_id={a_id}" target="_top" style="background:#0E137A; color:#FFFFFF; font-size:0.78rem; font-weight:800; padding:6px 14px; border-radius:6px; text-decoration:none; display:inline-flex; align-items:center; gap:6px; box-shadow:0 2px 8px rgba(14,19,122,0.3); transition:background 0.2s ease;">
                            Duyuruyu Oku ➔
                        </a>
                    </div>
                </div>
                """
                st.markdown(card_chip_html, unsafe_allow_html=True)
    else:
        st.info("Şu anda yayında aktif bir duyuru bulunmuyor.")

    # GENİŞ BOŞLUK: Duyurular -> Alt Çağrı Kartı
    st.markdown("<div style='height:75px;'></div>", unsafe_allow_html=True)

    # 5. PORTALA GİRİŞ VE SİSTEME KATILIM ÇAĞRISI
    st.markdown(
        """
        <div style="background:rgba(2, 28, 97, 0.85); border:1.5px solid rgba(61, 211, 255, 0.35); border-radius:16px; padding:32px 36px; text-align:center; box-shadow:0 8px 30px rgba(0,0,0,0.3);">
            <div style="font-size:1.35rem; font-weight:900; color:#FFFFFF; margin-bottom:10px;">
                T-Sistem Değerlendirme Masasına Katılın
            </div>
            <div style="font-size:0.95rem; color:#CBD5E1; max-width:720px; margin:0 auto 24px auto; line-height:1.6;">
                Yarışmacı takımlar aşama raporlarını yükleyebilir, hakemler 4. göz yapay zekâ asistanıyla puanlama yapabilir ve yöneticiler tüm süreci yönetebilir.
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("<div style='height:20px;'></div>", unsafe_allow_html=True)

    _, c_center, _ = st.columns([1.5, 2.0, 1.5])
    with c_center:
        is_auth = bool(st.session_state.get("authenticated", False))
        if is_auth:
            if st.button("Panelime Dön →", key="tf_bottom_panel", type="primary", use_container_width=True):
                st.query_params.clear()
                st.query_params["tab"] = "ana_sayfa"
                st.rerun()
        else:
            if st.button("Giriş Yaparak Başla", key="tf_bottom_login", type="primary", use_container_width=True):
                st.query_params["view"] = "login"
                st.rerun()

    # GENİŞ BOŞLUK: Buton -> Tanıtım Kartı
    st.markdown("<div style='height:75px;'></div>", unsafe_allow_html=True)

    # 6. TEKNOFEST RESMÎ FOOTER & PLATFORM TANITIM BANNERI (İKİ AYRI KART)
    logo_b64 = _get_tsistem_logo_b64()
    if logo_b64:
        footer_logo_tag = (
            '<div style="display:inline-flex; align-items:center; justify-content:center; padding:8px 12px; border-radius:18px; background:rgba(255, 255, 255, 0.18); backdrop-filter:blur(8px); box-shadow:0 0 25px rgba(255,255,255,0.40); margin-bottom:14px;">'
            f'<img src="{logo_b64}" style="height:90px; max-width:120px; object-fit:contain; filter:drop-shadow(0 4px 12px rgba(255,255,255,0.6));" alt="T-Sistem Logo"/>'
            '</div>'
        )
    else:
        footer_logo_tag = ''

    # KART 1: Platform ve Mobil Modül Tanıtım Kartı
    promo_html = (
        '<div style="background: rgba(2, 20, 61, 0.85); border: 1.5px solid rgba(61, 211, 255, 0.35); border-radius: 18px; padding: 24px 36px; margin-bottom: 28px; box-shadow: 0 10px 30px rgba(0,0,0,0.35);">'
        '<div style="display:flex; justify-content:space-around; align-items:center; flex-wrap:wrap; gap:30px;">'
        '<div style="display:flex; align-items:center; gap:20px;">'
        '<div style="width:52px; height:52px; border-radius:12px; background:linear-gradient(135deg, #DE380F, #A02000); display:flex; align-items:center; justify-content:center; box-shadow:0 4px 14px rgba(222,56,15,0.4);">'
        '<i class="fa-solid fa-mobile-screen-button" style="font-size:1.6rem; color:#FFFFFF;"></i>'
        '</div>'
        '<div>'
        '<div style="font-size:1.05rem; font-weight:850; color:#FFFFFF; line-height:1.2;">T-Sistem Rapor ve Karne Takibi</div>'
        '<div style="font-size:0.80rem; color:#94A3B8; margin-top:3px;">Takım aşama durumları ve hakem bildirimleri</div>'
        '</div>'
        '</div>'
        '<div style="width:1px; height:50px; background:rgba(61,211,255,0.25);"></div>'
        '<div style="display:flex; align-items:center; gap:20px;">'
        '<div style="width:52px; height:52px; border-radius:12px; background:linear-gradient(135deg, #0284C7, #0369A1); display:flex; align-items:center; justify-content:center; box-shadow:0 4px 14px rgba(2,132,199,0.4);">'
        '<i class="fa-solid fa-microchip" style="font-size:1.6rem; color:#FFFFFF;"></i>'
        '</div>'
        '<div>'
        '<div style="font-size:1.05rem; font-weight:850; color:#FFFFFF; line-height:1.2;">4. Göz Yapay Zekâ Motoru</div>'
        '<div style="font-size:0.80rem; color:#94A3B8; margin-top:3px;">Otomatik kural denetimi ve intihal matrisi</div>'
        '<div style="display:flex; gap:12px; margin-top:6px; font-size:0.75rem; font-weight:700; color:#3DD3FF;">'
        '<span><i class="fa-solid fa-shield-halved"></i> Mühürlü Hakem Karnesi</span>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(promo_html, unsafe_allow_html=True)

    # KART 2: Kurumsal Linkler ve Sosyal Medya Footer Kartı
    footer_html = (
        '<div style="background: rgba(1, 14, 46, 0.95); border: 1.5px solid rgba(61, 211, 255, 0.25); border-radius: 18px; padding: 40px 32px 24px 32px; box-shadow: 0 12px 40px rgba(0,0,0,0.5);">'
        '<div style="display:flex; justify-content:space-between; flex-wrap:wrap; gap:36px; max-width:1300px; margin:0 auto;">'
        '<div style="flex: 1 1 280px;">'
        f'{footer_logo_tag}'
        '<div style="font-size:0.84rem; color:#94A3B8; line-height:1.6;">T-Sistem, TEKNOFEST Havacılık, Uzay ve Teknoloji Festivali yarışma şartnamelerine tam uyumlu yapay zekâ destekli 4. göz rapor değerlendirme istasyonudur.</div>'
        '</div>'
        '<div style="flex: 1 1 180px;">'
        '<div style="font-size:0.95rem; font-weight:850; color:#FFFFFF; margin-bottom:14px; letter-spacing:0.02em;">Kurumsal & Sistem</div>'
        '<div style="display:flex; flex-direction:column; gap:8px; font-size:0.84rem; color:#CBD5E1;">'
        '<span>Hakkımızda</span><span>T-Sistem & Paydaşlar</span><span>Değerlendirme İlkeleri</span><span>Gizlilik & KVKK Politikası</span>'
        '</div>'
        '</div>'
        '<div style="flex: 1 1 180px;">'
        '<div style="font-size:0.95rem; font-weight:850; color:#FFFFFF; margin-bottom:14px; letter-spacing:0.02em;">Yarışma Masası</div>'
        '<div style="display:flex; flex-direction:column; gap:8px; font-size:0.84rem; color:#CBD5E1;">'
        '<span>60 Resmî Yarışma</span><span>Teknik Şartnameler (2026)</span><span>Aşama Rapor Şablonları</span><span>Hakem Heyeti Kriterleri</span>'
        '</div>'
        '</div>'
        '<div style="flex: 1 1 180px;">'
        '<div style="font-size:0.95rem; font-weight:850; color:#FFFFFF; margin-bottom:14px; letter-spacing:0.02em;">Yardım & Destek</div>'
        '<div style="display:flex; flex-direction:column; gap:8px; font-size:0.84rem; color:#CBD5E1;">'
        '<span>Sıkça Sorulan Sorular (SSS)</span><span>Duyurular ve Bildirimler</span><span>Takım Başvuru Kılavuzu</span><span>İletişim & Masası</span>'
        '</div>'
        '</div>'
        '</div>'
        '<div style="display:flex; justify-content:center; gap:16px; margin:32px 0 20px 0;">'
        '<div style="width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-size:0.95rem;"><i class="fa-brands fa-x-twitter"></i></div>'
        '<div style="width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-size:0.95rem;"><i class="fa-brands fa-instagram"></i></div>'
        '<div style="width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-size:0.95rem;"><i class="fa-brands fa-facebook-f"></i></div>'
        '<div style="width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-size:0.95rem;"><i class="fa-brands fa-youtube"></i></div>'
        '<div style="width:38px; height:38px; border-radius:50%; background:rgba(255,255,255,0.08); border:1px solid rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; color:#FFFFFF; font-size:0.95rem;"><i class="fa-brands fa-linkedin-in"></i></div>'
        '</div>'
        '<div style="text-align:center; font-size:0.78rem; color:#64748B; padding-top:14px; border-top:1px solid rgba(255,255,255,0.1);">'
        '2026 T-Sistem | Tüm hakları saklıdır. © | KVKK Aydınlatma Metni'
        '</div>'
        '</div>'
    )
    st.markdown(footer_html, unsafe_allow_html=True)
