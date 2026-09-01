"""
T-Sistem · Tüm Resmî Duyurular Sayfası ve Duyuru Detay Görüntüleyici.
teknofest.org/tr/duyurular/ birebir tasarımında, kategori filtreli,
görsel kapaklı, detay modallı ve arama destekli duyuru merkezi.
"""

from __future__ import annotations

from pathlib import Path
import streamlit as st
from src.database.db import db


def render_announcement_detail_modal(ann: dict) -> None:
    """Seçili duyurunun tüm detaylarını içeren şık TEKNOFEST modalını render eder."""
    title = ann.get("title", "")
    content = ann.get("content", "")
    cat = ann.get("category", "GENEL")
    author = ann.get("author_name", "Yarışma Yönetimi")
    date_str = str(ann.get("created_at", ""))[:16]
    img_url = ann.get("image_url", "")

    st.markdown("""
    <style>
    .tf-modal-container {
        background: radial-gradient(circle at 80% 50%, rgba(40, 90, 148, 0.45) 0%, rgba(2, 20, 61, 0.98) 85%);
        border: 2px solid #3DD3FF;
        border-radius: 20px;
        padding: 32px 36px;
        margin-bottom: 28px;
        box-shadow: 0 16px 50px rgba(0, 0, 0, 0.7);
        color: #FFFFFF;
    }
    </style>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown('<div class="tf-modal-container">', unsafe_allow_html=True)
        m_top1, m_top2 = st.columns([4, 1.2])
        with m_top1:
            st.markdown(f"<span style='background:#DE380F; color:#FFFFFF; font-size:0.80rem; font-weight:800; padding:4px 14px; border-radius:6px;'>{cat}</span>", unsafe_allow_html=True)
            st.markdown(f"<h2 style='color:#FFFFFF; margin-top:10px; margin-bottom:4px; font-weight:900;'>{title}</h2>", unsafe_allow_html=True)
            st.markdown(f"<div style='color:#3DD3FF; font-size:0.84rem; font-weight:700;'>Yayınlayan: {author} · {date_str}</div>", unsafe_allow_html=True)
        with m_top2:
            if st.button("✕ Kapat", key="btn_close_ann_modal", type="secondary", use_container_width=True):
                st.session_state.selected_announcement = None
                st.rerun()

        st.markdown("<hr style='border-color:rgba(61,211,255,0.3); margin:18px 0;'>", unsafe_allow_html=True)

        if img_url:
            st.markdown(
                f"""
                <div style="width:100%; max-height:360px; display:flex; align-items:center; justify-content:center; background:#FFFFFF; border-radius:14px; margin-bottom:20px; padding:12px; border:1px solid rgba(61,211,255,0.35); box-shadow: 0 4px 20px rgba(0,0,0,0.3);">
                    <img src="{img_url}" style="max-width:100%; max-height:330px; object-fit:contain;" alt="{title}"/>
                </div>
                """,
                unsafe_allow_html=True
            )

        st.markdown(
            f"""
            <div style="font-size:1.05rem; color:#E2E8F0; line-height:1.75; white-space:pre-line; padding:8px 0;">
                {content}
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)


def render_announcements_page() -> None:
    """Tüm Resmî Duyurular sayfasını tam sayfa TEKNOFEST formatında render eder."""

    st.markdown("""
    <style>
    .ann-page-header {
        background: rgba(2, 28, 97, 0.85);
        border: 1.5px solid rgba(61, 211, 255, 0.35);
        border-radius: 16px;
        padding: 24px 30px;
        margin-bottom: 24px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        box-shadow: 0 8px 30px rgba(0, 0, 0, 0.35);
    }
    
    .tf-ann-grid-card {
        background: #DEEFF4;
        border-radius: 12px;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        height: 350px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.2);
    }
    .tf-ann-img-wrap {
        width: 100%;
        height: 145px;
        overflow: hidden;
        background: #02143D;
    }
    .tf-ann-img-wrap img {
        width: 100%;
        height: 100%;
        object-fit: cover;
    }
    .tf-ann-bar {
        background: #0E137A;
        padding: 6px 14px;
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    .tf-ann-bar-date {
        color: #FFFFFF;
        font-size: 0.76rem;
        font-weight: 700;
    }
    .tf-ann-bar-cat {
        background: #DE380F;
        color: #FFFFFF;
        font-size: 0.68rem;
        font-weight: 800;
        padding: 2px 8px;
        border-radius: 4px;
    }
    .tf-ann-desc-box {
        padding: 12px 14px;
        flex-grow: 1;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .tf-ann-t {
        color: #0E137A;
        font-size: 0.96rem;
        font-weight: 850;
        line-height: 1.35;
        margin-bottom: 6px;
    }
    .tf-ann-p {
        color: #334155;
        font-size: 0.80rem;
        line-height: 1.45;
        overflow: hidden;
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
    }
    .tf-ann-foot {
        font-size: 0.74rem;
        color: #64748B;
        font-weight: 600;
        padding-top: 6px;
        border-top: 1px solid #CBD5E1;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. DETAY MODALI AÇIKSA GÖSTER
    if st.session_state.get("selected_announcement"):
        render_announcement_detail_modal(st.session_state.selected_announcement)

    # 2. ÜST BAŞLIK VE GERİ DÖNÜŞ BUTONU
    c_back, c_title = st.columns([1.2, 4])
    with c_back:
        if st.button("← Ana Sayfaya Dön", key="btn_back_from_announcements", type="secondary", use_container_width=True):
            st.query_params.clear()
            st.rerun()

    with c_title:
        st.markdown("""
        <div style="font-size: 1.75rem; font-weight: 900; color: #FFFFFF; letter-spacing: -0.02em;">
            Resmî Duyurular ve Yarışma Bildirimleri
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

    # 3. FİLTRE VE ARAMA ÇUBUĞU
    f_c1, f_c2 = st.columns([2, 2])
    with f_c1:
        cat_filter = st.selectbox(
            "Kategoriye Göre Filtrele",
            ["TÜMÜ", "GENEL", "YARIŞMA", "ŞARTNAME", "HAKEM", "SONUÇLAR"],
            key="ann_page_cat_filter"
        )
    with f_c2:
        search_query = st.text_input(
            "Duyuru Ara",
            placeholder="Anahtar kelime veya yarışma adı...",
            key="ann_page_search"
        )

    st.markdown("<div style='height: 20px;'></div>", unsafe_allow_html=True)

    # 4. DUYURULARI LİSTELE
    announcements = db.list_announcements(cat_filter)
    if search_query:
        announcements = [
            a for a in announcements
            if search_query.lower() in (a.get("title", "") + a.get("content", "")).lower()
        ]

    fallback_covers = [
        "https://cdn.teknofest.org/media/upload/userFormUpload/kapak_gorsel_GqVNx.jpeg",
        "https://cdn.teknofest.org/media/upload/userFormUpload/dikeyini%C5%9Filitr_iXgg8_wggoj_mNPAa.jpg",
        "https://cdn.teknofest.org/media/upload/userFormUpload/harp-tr_gAM2G_FhhNk.jpg",
        "https://cdn.teknofest.org/media/upload/userFormUpload/tr_i_sualt%C4%B1_lnLq4_e65WY.jpg",
        "https://cdn.teknofest.org/media/upload/userFormUpload/tar%C4%B1m_tr_QZLL4.png"
    ]

    if announcements:
        cols = st.columns(3)
        for idx, a in enumerate(announcements):
            title = a.get("title", "")
            content = a.get("content", "")
            cat = a.get("category", "GENEL")
            author = a.get("author_name", "Yarışma Yönetimi")
            date_str = str(a.get("created_at", ""))[:10]
            is_pin = bool(a.get("is_pinned", 0))
            img_url = a.get("image_url") or fallback_covers[idx % len(fallback_covers)]
            a_id = a.get("announcement_id", f"ann_{idx}")

            with cols[idx % 3]:
                # Ana sayfadakiyle birebir aynı tek parça gömülü butonlu modern chip kart tasarımı
                st.markdown(
                    f"""
                    <div style="background:#DEEFF4; border-radius:14px; overflow:hidden; display:flex; flex-direction:column; justify-content:space-between; min-height:365px; box-shadow:0 6px 20px rgba(0,0,0,0.25); border:1px solid rgba(61,211,255,0.3); margin-bottom:20px; transition:transform 0.2s ease;">
                        <div>
                            <div style="width:100%; height:140px; display:flex; align-items:center; justify-content:center; background:#FFFFFF; padding:8px; border-bottom:1px solid #E2E8F0;">
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
                    """,
                    unsafe_allow_html=True
                )
    else:
        st.info("Arama kriterinize uygun duyuru bulunamadı.")
