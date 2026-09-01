"""T-Sistem · Resmî Şablon ve Doküman Görüntüleyici.

DOCX ve PDF rapor/şablon dokümanlarını Microsoft Word motoru (birebir A4,
resmî kapak, logolar, tablolar ve Türkçe karakterler ile) kesintisiz PDF
görüntüleyici ile render eder. Hem .docx hem de .pdf formatında indirme
seçeneği sunar.
"""

from __future__ import annotations

import os
from pathlib import Path
import streamlit as st

try:
    import docx2pdf
    DOCX2PDF_VAR = True
except ImportError:
    DOCX2PDF_VAR = False


def docx_to_pdf(docx_path: str | Path) -> Path | None:
    """DOCX dosyasını Microsoft Office motoruyla birebir orijinal PDF dokümanına dönüştürür."""
    p = Path(docx_path)
    if not p.exists():
        return None

    # Zaten .pdf ise doğrudan dön
    if p.suffix.lower() == ".pdf":
        return p

    pdf_p = p.with_suffix(".pdf")
    
    # Eğer PDF zaten varsa ve boyutu 100KB'dan büyükse (orijinal Office PDF) kullan
    if pdf_p.exists() and pdf_p.stat().st_size > 100_000:
        return pdf_p

    # Microsoft Word Native PDF Çıktısı
    if DOCX2PDF_VAR:
        try:
            docx2pdf.convert(str(p), str(pdf_p))
            if pdf_p.exists() and pdf_p.stat().st_size > 0:
                return pdf_p
        except Exception as e:
            print(f"[docx2pdf] Office dönüştürme hatası ({p.name}): {e}")

    if pdf_p.exists() and pdf_p.stat().st_size > 0:
        return pdf_p

    return None


def docx_onizle(
    st_obj,
    docx_path: str | Path,
    baslik: str = "Resmî Şablon Dokümanı",
    key: str = "docx_view",
    r2_public_url: str | None = None
) -> None:
    """DOCX ve PDF dokümanını 2 indirme seçeneği ve kesintisiz PDF görüntüleyici ile render eder."""
    p = Path(docx_path)
    if not p.exists():
        st_obj.warning("Belirtilen dosya mevcut değil.")
        return

    # PDF eşleniğini bul veya oluştur
    pdf_p = docx_to_pdf(p) if p.suffix.lower() == ".docx" else p
    if not pdf_p or not pdf_p.exists():
        pdf_counterpart = p.with_suffix(".pdf")
        if pdf_counterpart.exists():
            pdf_p = pdf_counterpart

    docx_p = p if p.suffix.lower() == ".docx" else p.with_suffix(".docx")
    has_docx = docx_p.exists()
    has_pdf = pdf_p is not None and pdf_p.exists()

    with st_obj.container(border=True):
        # 1. ÜST BAŞLIK VE ÇİFT İNDİRME BUTONU BANDI
        h_col1, h_col2 = st_obj.columns([2.0, 2.0])
        with h_col1:
            st_obj.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:8px; margin-bottom:4px;">
                    <span style="background:#E30A17; color:#FFFFFF; font-weight:800; font-size:0.75rem; padding:3px 8px; border-radius:4px;">TEKNOFEST</span>
                    <span style="font-weight:750; color:#0F172A; font-size:0.92rem;">{p.name}</span>
                </div>
                """,
                unsafe_allow_html=True
            )
            st_obj.caption("Resmî Aşama Şablonu · Kesintisiz Kaydırma, Yakınlaştırma ve İnceleme")

        with h_col2:
            btn_c1, btn_c2 = st_obj.columns(2)
            with btn_c1:
                if has_docx:
                    with open(docx_p, "rb") as f_d:
                        st_obj.download_button(
                            "Word İndir (.docx)",
                            data=f_d.read(),
                            file_name=docx_p.name,
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            type="secondary",
                            use_container_width=True,
                            key=f"dl_btn_docx_{key}"
                        )
            with btn_c2:
                if has_pdf:
                    with open(pdf_p, "rb") as f_p:
                        st_obj.download_button(
                            "PDF İndir (.pdf)",
                            data=f_p.read(),
                            file_name=pdf_p.name,
                            mime="application/pdf",
                            type="primary",
                            use_container_width=True,
                            key=f"dl_btn_pdf_{key}"
                        )

        st_obj.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

        # 2. KESİNTİSİZ PDF GÖRÜNTÜLEYİCİ (Zoom + / -, Kaydırma, 2'li Sayfa Modu)
        if has_pdf:
            import pdf_gorunum
            pdf_gorunum.pdf_onizle(st_obj, pdf_p, height=740, key=f"preview_pdf_{key}")
        else:
            st_obj.info(f"Doküman PDF önizlemesi hazırlanıyor... ({p.name})")
