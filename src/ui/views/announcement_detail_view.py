"""
T-Sistem · Tekil Resmî Duyuru Detay Sayfası.
Tüm duyurular sayfası gibi tam ekran, kapak görseli, kategori rozeti,
yayınlayan birim bilgisi ve tek tıkla geri dönüş butonu barındırır.
"""

from __future__ import annotations

import streamlit as st


def render_announcement_detail_page(ann: dict) -> None:
    """Tekil bir duyurunun tam sayfa detayını TEKNOFEST resmî uzay temasında render eder."""
    title = ann.get("title", "")
    content = ann.get("content", "")
    cat = ann.get("category", "GENEL")
    author = ann.get("author_name", "Yarışma Yönetimi")
    date_str = str(ann.get("created_at", ""))[:16]
    img_url = ann.get("image_url", "")

    st.markdown("""
    <style>
    .ann-detail-hero {
        background: radial-gradient(circle at 80% 50%, rgba(40, 90, 148, 0.45) 0%, rgba(2, 20, 61, 0.95) 85%);
        border: 1.5px solid rgba(61, 211, 255, 0.35);
        border-radius: 20px;
        padding: 36px 42px;
        margin-bottom: 28px;
        box-shadow: 0 16px 45px rgba(0, 23, 134, 0.4);
        color: #FFFFFF;
    }
    .ann-detail-cover {
        width: 100%;
        max-height: 380px;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #FFFFFF;
        border-radius: 14px;
        margin: 20px 0;
        padding: 16px;
        border: 1.5px solid rgba(61, 211, 255, 0.4);
        box-shadow: 0 8px 30px rgba(0,0,0,0.35);
    }
    .ann-detail-cover img {
        max-width: 100%;
        max-height: 340px;
        width: auto;
        height: auto;
        object-fit: contain;
    }
    .ann-detail-body {
        font-size: 1.10rem;
        color: #E2E8F0;
        line-height: 1.85;
        white-space: pre-line;
        margin-top: 18px;
    }
    </style>
    """, unsafe_allow_html=True)

    # 1. ÜST BAR: Geri Dönüş Butonu
    c_back, _ = st.columns([1.5, 4.5])
    with c_back:
        if st.button("← Duyurulara Geri Dön", key="btn_back_from_ann_detail_page", type="secondary", use_container_width=True):
            st.query_params.clear()
            st.rerun()

    st.markdown("<div style='height: 12px;'></div>", unsafe_allow_html=True)

    # 2. HERO DETAY KARTI
    img_html = f'<div class="ann-detail-cover"><img src="{img_url}" alt="{title}"/></div>' if img_url else ''

    card_html = (
        f'<div class="ann-detail-hero">'
        f'<div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">'
        f'<span style="background:#DE380F; color:#FFFFFF; font-size:0.80rem; font-weight:800; padding:4px 14px; border-radius:6px; letter-spacing:0.04em;">{cat}</span>'
        f'<span style="background:rgba(61,211,255,0.15); color:#3DD3FF; border:1px solid #3DD3FF; font-size:0.78rem; font-weight:700; padding:3px 12px; border-radius:6px;">RESMÎ BİLDİRİM</span>'
        f'</div>'
        f'<div style="font-size:2.10rem; font-weight:900; color:#FFFFFF; line-height:1.25; margin-bottom:10px;">{title}</div>'
        f'<div style="font-size:0.88rem; color:#94A3B8; font-weight:600;">'
        f'Yayınlayan Birim: <b style="color:#FFFFFF;">{author}</b> &nbsp;|&nbsp; Yayın Tarihi: <b style="color:#3DD3FF;">{date_str}</b> &nbsp;|&nbsp; <b>TEKNOFEST 2026</b>'
        f'</div>'
        f'{img_html}'
        f'<hr style="border-color:rgba(61,211,255,0.25); margin:24px 0 18px 0;">'
        f'<div class="ann-detail-body">{content}</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)
