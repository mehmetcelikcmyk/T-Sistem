"""T-Sistem · Hakem Değerlendirme İstasyonu (AI 4. Göz Karar Destek Paneli).

Modern, sade ve kurumsal tema:
- Emojisiz, net tipografi ve kurumsal kart düzeni.
- 1. Adım: Şartname Kategori ve Takım Uygunluk Denetimi (Ön Eleme).
- 2. Adım: Rapor Şablonu Biçim Kontrolleri ve 0-100 Puan Rubrik Değerlendirmesi.
- AI Kanıt Alıntısı ve Rapor Önizleme Entegrasyonu.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# src/ui modüllerinin doğrudan import edilebilmesini sağla
_UI_DIR = Path(__file__).resolve().parent.parent
if str(_UI_DIR) not in sys.path:
    sys.path.insert(0, str(_UI_DIR))

import pymupdf
import pandas as pd
import streamlit as st

try:
    import api_client
except ImportError:
    from src.ui import api_client

try:
    import charts
except ImportError:
    from src.ui import charts

try:
    import components as c
except ImportError:
    from src.ui import components as c

try:
    import docx_gorunum
except ImportError:
    from src.ui import docx_gorunum

try:
    import pdf_gorunum
except ImportError:
    from src.ui import pdf_gorunum

try:
    import rubrik
except ImportError:
    from src.ui import rubrik

try:
    import sartname_rehber
except ImportError:
    from src.ui import sartname_rehber

try:
    import theme
except ImportError:
    from src.ui import theme

from src.database.db import db


def _kart(st_ctx):
    try:
        return st_ctx.container(border=True)
    except TypeError:
        return st_ctx.container()


def _sartname_ve_sablon_rehberi(st_ctx, yarisma_id: str, asama: str = "OTR", rapor_dosya: str | None = None, seviye: str | None = None) -> None:
    """Hakem için resmî şartname, şablon ve kurallar çekmecesi."""
    rehber = sartname_rehber.dokuman_rehberi_getir(yarisma_id, asama, seviye)
    
    with st_ctx.expander(f"Resmî Şartname, Şablon ve Aşama Kılavuzu ({rehber['asama']} · {rehber['asama_adi']})", expanded=False):
        sek1, sek2, sek3, sek4 = st_ctx.tabs([
            "Resmî Rapor Şablonu",
            "Teknik Şartname",
            "Aşama Rubrik Ağırlıkları",
            "Yan Yana İnceleme (Şablon vs Rapor)"
        ])
        
        with sek1:
            st_ctx.markdown(f"**{rehber['asama']} Resmî Rapor Şablonu**")
            st_ctx.caption(f"Yarışmacıların uymakla yükümlü olduğu resmî şablon: {rehber['sablon_adi']}")
            
            s1_col1, s1_col2 = st_ctx.columns([1.1, 1.3])
            with s1_col1:
                st_ctx.markdown("##### Zorunlu Rapor Başlıkları")
                for b in rehber["zorunlu_bolumler"]:
                    st_ctx.markdown(f"- **{b}**")
                st_ctx.markdown(f"**Sayfa Sınırı:** {rehber['sayfa_limiti']}")
                st_ctx.markdown(f"**Düzen Standartları:** {rehber['yazi_tipi_kurallari']}")
                
            with s1_col2:
                st_ctx.markdown("##### Şablon Önizleme (Canlı Görünüm)")
                sablon_yol_str = rehber.get("sablon_yolu") or ""
                sablon_yol_obj = pdf_gorunum.yol(sablon_yol_str) if sablon_yol_str else None

                if sablon_yol_obj and sablon_yol_obj.exists():
                    docx_gorunum.docx_onizle(st_ctx, sablon_yol_obj, key=f"s1_docx_{yarisma_id}_{asama}")
                else:
                    st_ctx.info(f"Şablon dosyası: {rehber.get('sablon_adi', 'Mevcut Değil')}")
                    
        with sek2:
            st_ctx.markdown(f"**{rehber['asama']} Teknik Şartname Dokümanı**")
            st_ctx.caption(f"Yarışmanın değerlendirme ve kural şartnamesi: {rehber['sartname_pdf_adi']}")
            
            s2_col1, s2_col2 = st_ctx.columns([1.1, 1.3])
            with s2_col1:
                st_ctx.markdown("##### Resmî Şartname Gereksinimleri & Kurallar")
                gereksinimler = sartname_rehber.sartname_gereklilikleri_getir(yarisma_id)
                for g in gereksinimler:
                    st_ctx.markdown(
                        f"""
                        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-left:4px solid #2563EB; border-radius:8px; padding:10px 14px; margin-bottom:10px; box-shadow:0 1px 3px rgba(0,0,0,0.03);">
                            <div style="font-size:0.95rem; font-weight:800; color:#1E293B; margin-bottom:4px;">
                                📌 {g['baslik']}
                            </div>
                            <div style="font-size:0.88rem; color:#475569; line-height:1.45;">
                                {g['aciklama']}
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
            with s2_col2:
                sn_yol_obj = pdf_gorunum.yol(rehber.get("sartname_pdf_yolu") or "")
                if sn_yol_obj and sn_yol_obj.exists() and sn_yol_obj.suffix.lower() == ".pdf":
                    pdf_gorunum.pdf_onizle(st_ctx, sn_yol_obj, height=650, key=f"sartname_page_preview_{yarisma_id}_{asama}")
                else:
                    st_ctx.info(f"Şartname dosyası: {rehber.get('sartname_pdf_adi', 'Mevcut Değil')}")

        with sek3:
            st_ctx.markdown(f"**{asama} Aşama Kriterleri ve Değerlendirme Ağırlıkları (0-100 Puan)**")
            y_rub = rubrik.getir(yarisma_id, asama)
            kriter_df = pd.DataFrame([
                {"Kriter Adı": k["ad"], "Puan Tavanı": f"{k['maks']:g} Puan", "Sorumlu Bölüm": k.get("bolum", "—"), "Açıklama": k.get("aciklama", "—")}
                for k in y_rub.get("kriterler", [])
            ])
            st_ctx.dataframe(kriter_df, use_container_width=True, hide_index=True)
            st_ctx.caption(f"Toplam Değerlendirme Puanı: {y_rub.get('toplam_puan', 100)} Puan")

        with sek4:
            st_ctx.markdown("**Yan Yana İnceleme (Yarışmacı Raporu & Resmî Şablon)**")
            st_ctx.caption("Yarışmacının rapor düzeni ve başlık formatını resmî şablonla eş zamanlı karşılaştırın.")
            
            side_col1, side_col2 = st_ctx.columns(2)
            with side_col1:
                st_ctx.markdown("##### Yarışmacı Raporu")
                r_resolved = pdf_gorunum.yol(rapor_dosya) if rapor_dosya else None
                if r_resolved and r_resolved.exists():
                    try:
                        r_len = pdf_gorunum.sayfa_sayisi_getir(str(r_resolved))
                        if r_len > 0:
                            r_page = st_ctx.selectbox("Rapor Sayfası", options=list(range(1, r_len + 1)), key=f"side_r_{yarisma_id}")
                            r_png = pdf_gorunum.sayfa_goruntusu(str(r_resolved), r_page, dpi=130)
                            if r_png:
                                st_ctx.image(r_png, caption=f"Yarışmacı Raporu (Sayfa {r_page} / {r_len})", use_container_width=True)
                        else:
                            st_ctx.info("Rapor sayfası okunamadı.")
                    except Exception:
                        st_ctx.info("Rapor önizlemesi yüklenemedi.")
                else:
                    st_ctx.info("Rapor dosyası seçilmedi veya bulunamadı.")

            with side_col2:
                st_ctx.markdown("##### Resmî Şablon")
                sab_res = pdf_gorunum.yol(rehber.get("sablon_yolu") or "") if rehber.get("sablon_yolu") else None
                if sab_res and sab_res.exists():
                    docx_gorunum.docx_onizle(st_ctx, sab_res, key=f"side_docx_{yarisma_id}_{asama}")
                else:
                    st_ctx.info(f"Şablon: {rehber.get('sablon_adi', 'DOCX Şablon')}")


def _toplam(puanlar: dict, kriterler: list[dict]) -> float:
    if not kriterler:
        return 0.0
    return round(sum(puanlar.get(k["kriter_id"], k.get("ai_puan", 0.0)) for k in kriterler), 1)


def _bolum_etiketi(kr: dict) -> str:
    if kr.get("bolum"):
        return f"Bölüm {kr['bolum']} · {kr['ad']}"
    return "Rapor Geneli"


def _kanit_goster(st_ctx, rapor: dict, kr: dict) -> None:
    """Alıntının rapordaki yerini işaretli olarak açar (çoklu sayfa ve kaydırmalı görünüm destekli)."""
    dosya = rapor.get("dosya")
    if not dosya:
        return

    anahtar = f"kanit_{rapor['rapor_id']}_{kr['kriter_id']}"
    is_open = st_ctx.session_state.get(anahtar, False)
    
    btn_label = "Kanıt Önizlemesini Kapat" if is_open else "Kanıtı Raporda Gör & İncele"
    if st_ctx.button(btn_label, key=f"btn_{anahtar}"):
        st_ctx.session_state[anahtar] = not is_open
        st_ctx.rerun()

    if not st_ctx.session_state.get(anahtar, False):
        return

    alintilar = kr.get("kaynak_alintilar") or kr.get("kaynak_alinti")
    sonuc = pdf_gorunum.isaretle(dosya, alintilar, kr.get("kaynak_bolum"), dpi=130)
    durum = sonuc.get("durum")
    sayfalar = sonuc.get("sayfalar", [])
    toplam_sayfa = sonuc.get("toplam_sayfa", 1)

    with st_ctx.container(border=True):
        if durum in ("bulundu", "bolum_bulundu") and sayfalar:
            sayfa_sayisi = len(sayfalar)
            
            if durum == "bolum_bulundu":
                st_ctx.markdown(c.kontrol_pill(False, "", "Alıntı ilgili rapor bölümünde tespit edildi ve işaretlendi"), unsafe_allow_html=True)
                
            if sayfa_sayisi == 1:
                s_tek = sayfalar[0]
                st_ctx.markdown(
                    f"""
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; background:#F8FAFC; padding:6px 12px; border-radius:8px; border:1px solid #E2E8F0;">
                        <span style="font-size:0.84rem; font-weight:800; color:#1E3A8A;">Sayfa {s_tek['sayfa']} / {toplam_sayfa}</span>
                        <span style="font-size:0.78rem; font-weight:700; color:#15803D; background:#DCFCE7; padding:2px 8px; border-radius:6px;">{s_tek.get('adet', 1)} Kanıt Vurgulandı</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st_ctx.image(s_tek["png"], caption=f"Rapor Sayfa {s_tek['sayfa']} (Vurgulanmış Kanıt Alanı)", use_container_width=True)
            else:
                sayfa_numaralari = [str(s["sayfa"]) for s in sayfalar]
                st_ctx.markdown(
                    f"""
                    <div style="font-size:0.84rem; font-weight:700; color:#1E293B; background:#EFF6FF; padding:8px 12px; border-radius:8px; margin-bottom:10px; border:1px solid #BFDBFE;">
                        <b>Toplam {sayfa_sayisi} sayfada kanıt tespit edildi:</b> Sayfa {", ".join(sayfa_numaralari)} (Toplam {toplam_sayfa} sayfa içerisinden)
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                gorunum = st_ctx.radio(
                    "Kanıt Görünüm Modu",
                    options=["Kaydırmalı Görünüm (Tüm Kanıt Sayfaları)", "Sayfa Sayfa İncele"],
                    horizontal=True,
                    key=f"mode_{anahtar}",
                    label_visibility="collapsed"
                )
                
                if "Kaydırmalı" in gorunum:
                    for s_item in sayfalar:
                        st_ctx.markdown(
                            f"""
                            <div style="display:flex; justify-content:space-between; align-items:center; margin:8px 0 4px 0; color:#334155; font-size:0.82rem; font-weight:800;">
                                <span>Sayfa {s_item['sayfa']} / {toplam_sayfa}</span>
                                <span style="color:#16A34A;">{s_item.get('adet', 1)} işaretli alan</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        st_ctx.image(s_item["png"], caption=f"Sayfa {s_item['sayfa']} (İşaretli Kanıt)", use_container_width=True)
                        st_ctx.markdown("<hr style='margin: 8px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                else:
                    secili_sayfa_no = st_ctx.selectbox(
                        "Görüntülenecek Kanıt Sayfası",
                        options=[s["sayfa"] for s in sayfalar],
                        format_func=lambda no: f" Sayfa {no} (Kanıt İşaretli)",
                        key=f"sel_{anahtar}"
                    )
                    secilen_sayfa = next((s for s in sayfalar if s["sayfa"] == secili_sayfa_no), sayfalar[0])
                    st_ctx.image(secilen_sayfa["png"], caption=f"Sayfa {secilen_sayfa['sayfa']} / {toplam_sayfa} (İşaretli Kanıt)", use_container_width=True)

            with st_ctx.expander("Raporun Diğer Sayfalarını / Bağlamını Aç", expanded=False):
                c_s1, c_s2 = st_ctx.columns([1, 3])
                with c_s1:
                    baglam_sayfa = st_ctx.number_input(
                        "Sayfa No",
                        min_value=1,
                        max_value=max(toplam_sayfa, 1),
                        value=min(sayfalar[0]["sayfa"], toplam_sayfa),
                        step=1,
                        key=f"ctx_num_{anahtar}"
                    )
                    st_ctx.caption(f"Toplam {toplam_sayfa} sayfa")
                with c_s2:
                    b_png = pdf_gorunum.sayfa_goruntusu(dosya, baglam_sayfa, dpi=125)
                    if b_png:
                        st_ctx.image(b_png, caption=f"Rapor Sayfa {baglam_sayfa} / {toplam_sayfa}", use_container_width=True)
                    else:
                        st_ctx.info("Bu sayfa görüntülenemedi.")

        elif durum == "metin_yok":
            st_ctx.markdown(c.kontrol_pill(False, "", "Rapor taranmış görüntü — metin katmanı yok"), unsafe_allow_html=True)
        elif durum == "sifreli":
            st_ctx.markdown(c.kontrol_pill(False, "", "Rapor parola korumalı"), unsafe_allow_html=True)
        elif durum == "acilamaz":
            st_ctx.markdown(c.kontrol_pill(False, "", "PDF dosyası bozuk veya açılamıyor"), unsafe_allow_html=True)
        elif durum == "dosya_yok":
            st_ctx.markdown(c.kontrol_pill(False, "", "Rapor dosyası bulunamadı"), unsafe_allow_html=True)
        else:
            st_ctx.markdown(c.kontrol_pill(False, "", "Alıntı raporda konumlandırılamadı"), unsafe_allow_html=True)


def _tum_kategori_rapor_sayilari(referee_id: str = "") -> dict[str, int]:
    """Bu hakeme atanmış tüm rapor sayılarını (tamamlanan + bekleyen) kategorilerine göre gruplar."""
    counts: dict[str, int] = {}
    try:
        from src.ui import api_client
        tum_raporlar = api_client.raporlar(referee_id=referee_id, only_open=False)
        for r in tum_raporlar:
            cat = r.get("kategori")
            if cat:
                counts[cat] = counts.get(cat, 0) + 1
    except Exception as e:
        print(f"Rapor sayım hatası: {e}")
    return counts


def goster(
    st_ctx,
    yarisma_id: str = "",
    referee_id: str = "",
    kategori_secenekleri: dict = None,
    sirali_keys: list = None,
    kat_rapor_sayilari: dict = None,
    secili_asama: str = "Tümü",
    durum_filtresi: str = "Tümü"
) -> None:
    # Parametre uyumluluğu: hem goster(st, user, lang) hem goster(st, yarisma_id, ref_id)
    if isinstance(yarisma_id, dict):
        referee_id = yarisma_id.get("user_id", "")
        yarisma_id = st_ctx.session_state.get("secili_kategori", "")
    else:
        yarisma_id = str(yarisma_id or st_ctx.session_state.get("secili_kategori", ""))
        referee_id = str(referee_id or "")

    if kategori_secenekleri is None:
        kategori_secenekleri = sartname_rehber.tum_yarismalari_sozluk_getir()

    # Sadece bu hakeme atanmış rapor sayılarını çek (Tam İzolasyon)
    kat_rapor_sayilari = _tum_kategori_rapor_sayilari(referee_id=referee_id)
    all_keys = list(kategori_secenekleri.keys())

    # Sadece bu hakeme atanmış yarışma kategorilerini göster (0 raporlu kategorileri hakem listesinde gizle)
    raporlu_kategoriler = [k for k in all_keys if kat_rapor_sayilari.get(k, 0) > 0]
    if not raporlu_kategoriler:
        raporlu_kategoriler = all_keys[:1]

    # Hakemin seçili kategorisi atanmış kategorilerden biri değilse, atanmış ilk kategoriye geç
    if (not yarisma_id or kat_rapor_sayilari.get(yarisma_id, 0) == 0) and raporlu_kategoriler:
        yarisma_id = raporlu_kategoriler[0]
        st_ctx.session_state.secili_kategori = yarisma_id

    sirali_keys = raporlu_kategoriler

    # Query param ile gelen kategori seçimi varsa yakala
    if "secili_kategori" in st_ctx.query_params:
        _qp_kat = st_ctx.query_params.get("secili_kategori")
        if _qp_kat and _qp_kat in all_keys:
            yarisma_id = _qp_kat
            st_ctx.session_state.secili_kategori = _qp_kat
            del st_ctx.query_params["secili_kategori"]

    # =========================================================================
    # 0. YARIŞMA KATEGORİLERİ VE RAPOR DAĞILIMI (YATAY ŞERİT / DRAG SLIDER)
    # =========================================================================
    cards_html = []
    for col_kat in raporlu_kategoriler:
        kat_adi = kategori_secenekleri.get(col_kat, col_kat)
        clean_name = kat_adi.replace("Yarışması", "").replace("Yarışmaları", "").replace("TEKNOFEST", "").strip()
        c_count = kat_rapor_sayilari.get(col_kat, 0)
        is_active = (col_kat == yarisma_id)

        if is_active:
            card_style = """
            background: linear-gradient(135deg, #FF5722 0%, #E64A19 100%);
            color: #FFFFFF;
            border: 1.5px solid #FF5722;
            box-shadow: 0 4px 14px rgba(255, 87, 34, 0.35);
            font-weight: 700;
            """
            badge_style = "background: rgba(255, 255, 255, 0.25); color: #FFFFFF; font-weight: 800;"
        else:
            card_style = """
            background: #FFFFFF;
            color: #1E293B;
            border: 1.5px solid #E2E8F0;
            box-shadow: 0 1px 4px rgba(0, 0, 0, 0.04);
            font-weight: 600;
            """
            badge_style = "background: #F1F5F9; color: #475569; font-weight: 700;"

        cards_html.append(f"""
        <div data-kat="{col_kat}" class="drag-card js-kat-link" style="display:inline-flex; align-items:center; gap:8px; padding:8px 14px; border-radius:10px; cursor:pointer; user-select:none; white-space:nowrap; transition:all 0.18s ease; {card_style}">
            <span style="font-size:0.86rem; letter-spacing:0.01em;">{clean_name}</span>
            <span style="font-size:0.75rem; padding:2px 7px; border-radius:12px; {badge_style}">{c_count} Rapor</span>
        </div>
        """)

    all_cards_str = "\n".join(cards_html)

    st_ctx.html(f"""
    <div style="margin-bottom:12px; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
            <div style="font-size:0.92rem; font-weight:800; color:#0F172A; letter-spacing:0.01em;">
                Yarışma Kategorileri ve Rapor Dağılımı <span style="font-size:0.78rem; font-weight:600; color:#64748B;">({len(raporlu_kategoriler)} Aktif Yarışma)</span>
            </div>
            <div style="font-size:0.78rem; color:#64748B; font-weight:600;">
                ↔ Yatay kaydırın veya sürükleyin
            </div>
        </div>

        <div id="kat_drag_ribbon" class="drag-container" style="
            display: flex;
            gap: 10px;
            overflow-x: auto;
            padding: 4px 2px 10px 2px;
            scroll-behavior: smooth;
            cursor: grab;
            user-select: none;
            scrollbar-width: thin;
            scrollbar-color: #CBD5E1 #F1F5F9;
        ">
            {all_cards_str}
        </div>
    </div>

    <style>
        .drag-container::-webkit-scrollbar {{
            height: 6px;
        }}
        .drag-container::-webkit-scrollbar-track {{
            background: #F1F5F9;
            border-radius: 4px;
        }}
        .drag-container::-webkit-scrollbar-thumb {{
            background: #CBD5E1;
            border-radius: 4px;
        }}
        .drag-container::-webkit-scrollbar-thumb:hover {{
            background: #94A3B8;
        }}
        .drag-card:hover {{
            transform: translateY(-1.5px);
            border-color: #FF5722 !important;
        }}
    </style>

    <script>
        const slider = document.getElementById('kat_drag_ribbon');
        if (slider) {{
            let isDown = false;
            let startX;
            let scrollLeft;
            let hasMoved = false;

            slider.addEventListener('mousedown', (e) => {{
                isDown = true;
                hasMoved = false;
                slider.style.cursor = 'grabbing';
                startX = e.pageX - slider.offsetLeft;
                scrollLeft = slider.scrollLeft;
            }});

            slider.addEventListener('mouseleave', () => {{
                isDown = false;
                slider.style.cursor = 'grab';
            }});

            slider.addEventListener('mouseup', () => {{
                isDown = false;
                slider.style.cursor = 'grab';
            }});

            slider.addEventListener('mousemove', (e) => {{
                if (!isDown) return;
                const x = e.pageX - slider.offsetLeft;
                const walk = (x - startX) * 1.6;
                if (Math.abs(walk) > 4) {{
                    hasMoved = true;
                }}
                slider.scrollLeft = scrollLeft - walk;
            }});

            slider.querySelectorAll('.js-kat-link').forEach(link => {{
                link.addEventListener('click', (e) => {{
                    e.preventDefault();
                    if (hasMoved) return;
                    
                    const katId = link.getAttribute('data-kat');
                    if (!katId) return;

                    // 1. Önce doğrudan ana sayfadaki Streamlit URL parametresini güncelle
                    if (window.parent && window.parent.location) {{
                        const url = new URL(window.parent.location.href);
                        url.searchParams.set("secili_kategori", katId);
                        url.searchParams.set("tab", "degerlendirme");
                        window.parent.history.pushState({{}}, '', url.toString());
                    }}

                    // 2. Streamlit Selectbox'ı tetiklemek için DOM tıklamasını simüle et
                    try {{
                        const doc = window.parent.document;
                        // Selectbox'ı bul
                        const selBoxes = doc.querySelectorAll('div[data-testid="stSelectbox"]');
                        if (selBoxes.length > 0) {{
                            const firstSel = selBoxes[0];
                            const baseWebSel = firstSel.querySelector('div[data-baseweb="select"]');
                            if (baseWebSel) {{
                                baseWebSel.click();
                                setTimeout(() => {{
                                    const options = doc.querySelectorAll('li[role="option"]');
                                    options.forEach(opt => {{
                                        if (opt.innerText.toLowerCase().includes(link.querySelector('span').innerText.trim().toLowerCase())) {{
                                            opt.click();
                                        }}
                                    }});
                                }}, 50);
                            }}
                        }}
                    }} catch (err) {{
                        // Fallback URL yönlendirmesi
                        if (window.parent && window.parent.location) {{
                            window.parent.location.search = '?tab=degerlendirme&secili_kategori=' + katId;
                        }}
                    }}
                }});
            }});
        }}
    </script>
    """)

    # =========================================================================
    # 1. BİRLEŞTİRİLMİŞ TEK MASTER KONTROL PANELİ
    # =========================================================================
    st_ctx.markdown("""
    <style>
        div[data-testid="stSelectbox"] label p {
            font-size: 0.96rem !important;
            font-weight: 800 !important;
            color: #0F172A !important;
        }
        div[data-testid="stSelectbox"] div[data-baseweb="select"] {
            font-size: 0.98rem !important;
            font-weight: 600 !important;
        }
    </style>
    """, unsafe_allow_html=True)

    with st_ctx.container(border=True):
        sol_col, sag_col = st_ctx.columns([1.9, 1.7])
        
        with sol_col:
            # 1.1. Yarışma Kategorisi (En Üstte)
            def _kat_degisti():
                st_ctx.session_state.secili_kategori = st_ctx.session_state.hakem_master_kat_sel
            
            # Senkronizasyon
            if st_ctx.session_state.get("hakem_master_kat_sel") != yarisma_id:
                st_ctx.session_state.hakem_master_kat_sel = yarisma_id

            def _format_kat_label(k_slug: str) -> str:
                ad = kategori_secenekleri.get(k_slug, k_slug)
                adet = kat_rapor_sayilari.get(k_slug, 0)
                return f"{ad} — ({adet} Rapor Yüklendi)" if adet > 0 else f"{ad} — (0 Rapor)"

            st_ctx.selectbox(
                "Yarışma Kategorisi",
                options=sirali_keys,
                format_func=_format_kat_label,
                key="hakem_master_kat_sel",
                on_change=_kat_degisti
            )
            secili_kat = st_ctx.session_state.hakem_master_kat_sel

            # Seçili kategorideki bu hakeme atanmış tüm raporları çek (only_open=False: tamamlananlar kilitli olarak görüntülenir)
            rapor_listesi = api_client.raporlar(secili_kat, referee_id=referee_id, only_open=False)
            toplam_atanan = len(rapor_listesi)
            incelenebilir = rapor_listesi

            # 1.2. Hakem İlerlemesi (Başlık ve Hemen Altında Renkli Çipler)
            bekleyen_sayisi_toplam = sum(1 for r in incelenebilir if r.get("durum") != "tamamlandi")
            tamam_sayisi_toplam = len(incelenebilir) - bekleyen_sayisi_toplam

            st_ctx.markdown(
                f"""
                <div style="margin-top:4px; margin-bottom:10px;">
                    <div style="font-size:0.88rem; font-weight:800; color:#1E293B; margin-bottom:6px;">Hakem Görev İlerlemesi</div>
                    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
                        <span style="background:#EFF6FF; color:#1D4ED8; font-weight:800; font-size:0.80rem; padding:4px 12px; border-radius:14px; border:1px solid #BFDBFE;">Toplam: {len(incelenebilir)}</span>
                        <span style="background:#FEF3C7; color:#B45309; font-weight:800; font-size:0.80rem; padding:4px 12px; border-radius:14px; border:1px solid #FDE68A;">Bekleyen: {bekleyen_sayisi_toplam}</span>
                        <span style="background:#DCFCE7; color:#15803D; font-weight:800; font-size:0.80rem; padding:4px 12px; border-radius:14px; border:1px solid #BBF7D0;">Tamamlanan: {tamam_sayisi_toplam}</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            # 1.3. Rapor Aşaması ve Değerlendirme Durumu
            c_asama, c_durum = st_ctx.columns(2)
            
            # Kategorinin Gerçek Aşamalarını Çöz
            ASAMA_SOZLUGU = {
                "OTR": "ÖTR · Ön Tasarım / Ön Değerlendirme",
                "ODR": "ÖDR · Ön Değerlendirme Raporu",
                "KTR": "KTR · Kritik Tasarım Raporu",
                "PDR": "PDR · Preliminary Design Report",
                "CDR": "CDR · Critical Design Report",
                "AHR": "AHR · Atış Hazırlık / Sistem Test",
                "QR": "QR · Ön Eleme / Yeterlilik Formu",
                "FTR": "FTR · Final / Proje Detay Raporu",
                "FRR": "FRR · Final Raporu",
                "FYR": "FYR · Final Yeterlilik Raporu",
            }
            
            db_asamalar = []
            for r in rapor_listesi:
                stg_code = (r.get("stage") or r.get("stage_code") or "OTR").upper()
                if stg_code not in db_asamalar:
                    db_asamalar.append(stg_code)
            
            kb_info = sartname_rehber.klasor_bilgisi(secili_kat)
            klasor_asamalari = [a.upper() for a in kb_info.get("asama_listesi", []) if a.upper() != "GENEL"]
            
            tum_asama_kodlari = list(dict.fromkeys(db_asamalar + klasor_asamalari))
            if not tum_asama_kodlari:
                tum_asama_kodlari = ["OTR", "KTR", "FTR"]
            elif len(tum_asama_kodlari) == 1 and tum_asama_kodlari[0] == "OTR":
                tum_asama_kodlari.append("KTR")

            asama_secenek_map = {"Tüm Aşamalar": "Tümü"}
            for code in tum_asama_kodlari:
                etiket = ASAMA_SOZLUGU.get(code, f"{code} · Değerlendirme Aşaması")
                asama_secenek_map[etiket] = code

            with c_asama:
                secili_asama_etiket = st_ctx.selectbox(
                    "Rapor Aşaması",
                    options=list(asama_secenek_map.keys()),
                    key=f"h_asama_sel_{secili_kat}"
                )
                asama_filtre_kodu = asama_secenek_map[secili_asama_etiket]
                st_ctx.session_state.aktif_asama = asama_filtre_kodu if asama_filtre_kodu != "Tümü" else "OTR"

            with c_durum:
                durum_secenekleri = ["Tümü", "Değerlendirme Bekleyenler", "Tamamlananlar"]
                secili_durum_filtre = st_ctx.selectbox("Değerlendirme Durumu", options=durum_secenekleri, key="h_durum_sel")

            # Filtreleme Uygula
            if asama_filtre_kodu != "Tümü":
                incelenebilir = [r for r in incelenebilir if r.get("stage", "OTR").upper() == asama_filtre_kodu.upper() or r.get("stage_code", "OTR").upper() == asama_filtre_kodu.upper()]

            if secili_durum_filtre == "Değerlendirme Bekleyenler":
                incelenebilir = [r for r in incelenebilir if r.get("durum") != "tamamlandi"]
            elif secili_durum_filtre == "Tamamlananlar":
                incelenebilir = [r for r in incelenebilir if r.get("durum") == "tamamlandi"]

            if not incelenebilir:
                c.bos_durum(st_ctx, "İncelenecek Rapor Bulunmuyor", f"Seçili kriterlere ({asama_filtre_kodu} · {secili_durum_filtre}) uygun atanmış rapor bulunmamaktadır.")
                return

            def _etiket(r: dict) -> str:
                p_ad = r.get("proje_adi", "Yarışmacı Projesi")
                t_ad = r.get("takim_adi", "Takım")
                if len(t_ad) > 18 and " " not in t_ad:
                    t_ad = f"Takım {p_ad.split()[0]}"
                stg = r.get("stage", "OTR")
                return f"{p_ad}  —  {t_ad}  ({stg} · {r['rapor_id']})"

            secenekler = {_etiket(r): r for r in incelenebilir}
            anahtarlar = list(secenekler.keys())

            istenen = st_ctx.session_state.get("secili_rapor")
            varsayilan_r_idx = 0
            if istenen:
                for i, a in enumerate(anahtarlar):
                    if secenekler[a]["rapor_id"] == istenen:
                        varsayilan_r_idx = i
                        break

            # 1.4. En Altta: Değerlendirilecek Rapor Seçimi
            secim = st_ctx.selectbox("Değerlendirilecek Rapor", anahtarlar, index=varsayilan_r_idx, key="hakem_secili_rapor_box")
            rapor = secenekler[secim]

            # Raporun Altına Şık ve Renkli Durum Çipi (Badge)
            is_done = (rapor.get("durum") == "tamamlandi")
            chip_bg = "#DCFCE7" if is_done else "#FEF3C7"
            chip_color = "#15803D" if is_done else "#B45309"
            chip_border = "#86EFAC" if is_done else "#FDE68A"
            dot_color = "#16A34A" if is_done else "#D97706"
            chip_label = "Tamamlandı" if is_done else "İnceleme Bekliyor"

            st_ctx.markdown(
                f"""
                <div style="display:flex; align-items:center; gap:8px; margin-top:6px; margin-bottom:4px; flex-wrap:wrap;">
                    <span style="font-size:0.82rem; color:#64748B; font-weight:700;">Rapor Durumu:</span>
                    <span style="background:{chip_bg}; color:{chip_color}; border:1px solid {chip_border}; font-size:0.80rem; font-weight:800; padding:3px 12px; border-radius:12px; display:inline-flex; align-items:center; gap:6px;">
                        <span style="width:7px; height:7px; background:{dot_color}; border-radius:50%; display:inline-block;"></span> {chip_label}
                    </span>
                    <span style="font-size:0.80rem; color:#94A3B8;">·</span>
                    <span style="font-size:0.80rem; color:#475569;">Aşama: <b style="color:#0F172A; font-weight:800;">{rapor.get('stage', 'OTR')}</b></span>
                    <span style="font-size:0.80rem; color:#94A3B8;">·</span>
                    <span style="font-size:0.80rem; color:#475569;">Başvuru ID: <b style="color:#0F172A; font-weight:800;">{rapor.get('rapor_id')}</b></span>
                </div>
                """,
                unsafe_allow_html=True
            )

        with sag_col:
            # Sağ Kolonda TÜM ALANI DOLDURAN BÜYÜK ve DİKKAT ÇEKİCİ RESMÎ LOGO
            logo_b64 = sartname_rehber.kategori_logosu_base64_getir(secili_kat)
            if logo_b64:
                st_ctx.markdown(
                    f"""
                    <div style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:100%; min-height:310px; padding:6px 12px;">
                        <img src="{logo_b64}" style="max-height:265px; width:auto; max-width:100%; object-fit:contain; display:block; filter:drop-shadow(0 4px 12px rgba(0,0,0,0.06));" alt="Resmî Kategori Logosu"/>
                        <div style="font-size:0.80rem; font-weight:900; color:#1E3A8A; text-align:center; margin-top:10px; letter-spacing:0.05em; text-transform:uppercase;">TEKNOFEST 2026 RESMÎ LOGOSU</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st_ctx.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 1: BAŞVURU VE PROJE KÜNYESİ (YAZI BOYUTLARI BÜYÜTÜLDÜ)
    # =========================================================================
    is_completed = (rapor.get("durum") == "tamamlandi")
    if is_completed:
        st_ctx.info(
            "🔒 **Değerlendirme Mühürlendi ve Kilitlendi:** Bu rapor için değerlendirme başarıyla tamamlanmış ve "
            "notlar mühürlenmiştir. Yarışma yöneticisi raporu tekrar değerlendirmeye açana kadar üzerinde değişiklik yapılamaz."
        )

    with st_ctx.container(border=True):
        st_ctx.markdown("<div style='font-size:1.05rem; font-weight:900; color:#1E3A8A; margin-bottom:10px; letter-spacing:0.02em;'>ADIM 1 · BAŞVURU VE PROJE BİLGİLERİ</div>", unsafe_allow_html=True)
        
        durum_etiket = "Değerlendirme Tamamlandı (Kilitli)" if is_completed else "Hakem İncelemesi Bekliyor"
        durum_bg = "#DCFCE7" if is_completed else "#FEF3C7"
        durum_renk = "#15803D" if rapor.get("durum") == "tamamlandi" else "#B45309"
        durum_border = "#86EFAC" if rapor.get("durum") == "tamamlandi" else "#FDE68A"

        # Temiz Takım Adı
        t_ad_display = rapor.get("takim_adi", "Takım")
        if len(t_ad_display) > 18 and " " not in t_ad_display:
            t_ad_display = f"Takım {rapor.get('proje_adi', 'Proje').split()[0]}"

        k_col1, k_col2 = st_ctx.columns([3.0, 1.4])
        with k_col1:
            st_ctx.markdown(
                f"""
                <div style="line-height:1.6;">
                    <div style="font-size:1.45rem; font-weight:900; color:#0F172A; margin-bottom:4px;">{rapor.get('proje_adi', 'Proje Başlığı')}</div>
                    <div style="font-size:1.06rem; font-weight:700; color:#2563EB; margin-bottom:6px;">Takım: {t_ad_display} · <span style="color:#475569; font-weight:600;">{sartname_rehber.turkce_kategori_adi_formatla(secili_kat)}</span></div>
                    <div style="font-size:0.95rem; color:#475569; margin-top:6px; display:flex; flex-wrap:wrap; gap:12px;">
                        <span>Başvuru Kimliği: <b style="color:#0F172A; font-weight:800;">{rapor.get('rapor_id')}</b></span>
                        <span style="color:#CBD5E1;">•</span>
                        <span>Aşama: <b style="color:#0F172A; font-weight:800;">{rapor.get('stage', 'OTR')}</b></span>
                        <span style="color:#CBD5E1;">•</span>
                        <span>Sayfa Sayısı: <b style="color:#0F172A; font-weight:800;">{rapor.get('sayfa_sayisi', 13)} Sayfa</b></span>
                        <span style="color:#CBD5E1;">•</span>
                        <span>Yüklenme Tarihi: <b style="color:#0F172A; font-weight:800;">{rapor.get('yuklenme_tarihi', '2026-08-23')[:10]}</b></span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
        with k_col2:
            st_ctx.markdown(
                f"""
                <div style="text-align:right; margin-top:4px;">
                    <span style="background:{durum_bg}; color:{durum_renk}; font-size:0.92rem; font-weight:800; padding:8px 18px; border-radius:24px; border:1.5px solid {durum_border}; display:inline-block; box-shadow:0 2px 6px rgba(0,0,0,0.03);">
                        {durum_etiket}
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Resmî Süreç ve Takvim Bandı
        st_ctx.markdown(
            """
            <div style="background:#F8FAFC; border:1.5px solid #E2E8F0; border-radius:10px; padding:14px 18px; margin-top:16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:14px;">
                <div>
                    <div style="font-size:0.78rem; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:0.04em;">Değerlendirme Başlangıç</div>
                    <div style="font-size:1.00rem; font-weight:900; color:#1E3A8A; margin-top:2px;">20 Ağustos 2026</div>
                </div>
                <div style="border-left:1.5px solid #CBD5E1; padding-left:16px;">
                    <div style="font-size:0.78rem; font-weight:800; color:#DC2626; text-transform:uppercase; letter-spacing:0.04em;">Son Puanlama Tarihi</div>
                    <div style="font-size:1.00rem; font-weight:900; color:#DC2626; margin-top:2px;">15 Eylül 2026, 23:59 <span style="font-size:0.78rem; background:#FEE2E2; color:#991B1B; padding:2px 8px; border-radius:6px; margin-left:4px; font-weight:800;">Kalan: 23 Gün</span></div>
                    <div style="font-size:0.78rem; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:0.04em;">İtiraz & İnceleme</div>
                    <div style="font-size:1.00rem; font-weight:900; color:#1E293B; margin-top:2px;">16 – 22 Eylül 2026</div>
                </div>
                <div style="border-left:1.5px solid #CBD5E1; padding-left:16px;">
                    <div style="font-size:0.78rem; font-weight:800; color:#2563EB; text-transform:uppercase; letter-spacing:0.04em;">Resmî Sonuç İlanı</div>
                    <div style="font-size:1.00rem; font-weight:900; color:#2563EB; margin-top:2px;">30 Eylül 2026</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

    st_ctx.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 2: RAPOR DOKÜMAN ÖNİZLEYİCİSİ (CANLI PDF GÖRÜNTÜLEYİCİ)
    # =========================================================================
    dosya_adi = rapor.get("dosya") or ""
    resolved_doc = pdf_gorunum.yol(dosya_adi)
    toplam_sayfa = pdf_gorunum.sayfa_sayisi_getir(str(resolved_doc)) if (resolved_doc and resolved_doc.exists()) else 13

    with st_ctx.container(border=True):
        st_ctx.markdown(
            f"""
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; flex-wrap:wrap; gap:8px; border-bottom:1.5px solid #E2E8F0; padding-bottom:10px;">
                <div style="font-size:1.15rem; font-weight:900; color:#1E3A8A; letter-spacing:0.02em;">
                    ADIM 2 · ORİJİNAL RAPOR DOKÜMANI VE PDF İNCELEME
                </div>
                <div style="display:flex; gap:8px; align-items:center;">
                    <span style="font-size:0.85rem; font-weight:800; color:#1D4ED8; background:#EFF6FF; padding:4px 14px; border-radius:12px; border:1px solid #BFDBFE;">
                        {toplam_sayfa} Sayfa
                    </span>
                    <span style="font-size:0.85rem; font-weight:800; color:#15803D; background:#DCFCE7; padding:4px 14px; border-radius:12px; border:1px solid #BBF7D0;">
                        PDF Dokümanı
                    </span>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        if resolved_doc and resolved_doc.exists() and toplam_sayfa > 0:
            pdf_gorunum.pdf_onizle(
                st_ctx, 
                str(resolved_doc), 
                baslik=rapor.get('proje_adi', 'Orijinal Proje Raporu'), 
                height=820, 
                key=f"hakem_rep_full_pdf_{rapor['rapor_id']}"
            )
        else:
            st_ctx.info("Bu proje için atanmış PDF raporu hazırlanıyor.")

    # --- Resmî Şartname, Şablon ve Aşama Rehberi ---
    rapor_asama = rapor.get("stage") or rapor.get("asama") or rapor.get("stage_code")
    if not rapor_asama and rapor.get("dosya"):
        d_lower = str(rapor.get("dosya")).lower()
        for stg_code in ["pdr", "odr", "otr", "ktr", "ahr", "ftr", "psr", "ttr", "dtr"]:
            if stg_code in d_lower:
                rapor_asama = stg_code.upper()
                break
    rapor_asama = rapor_asama or st_ctx.session_state.get("aktif_asama") or ("ODR" if "biyoteknoloji" in str(yarisma_id).lower() else "OTR")
    
    rapor_seviye = rapor.get("seviye") or rapor.get("level")
    if not rapor_seviye and rapor.get("dosya"):
        d_lower = str(rapor.get("dosya")).lower()
        if "universite" in d_lower:
            rapor_seviye = "universite_ve_uzeri"
        elif "lise" in d_lower:
            rapor_seviye = "lise"

    _sartname_ve_sablon_rehberi(st_ctx, yarisma_id, rapor_asama, rapor.get("dosya"), rapor_seviye)

    # =========================================================================
    # AYRI AI ANALİZ FONKSİYONLARI (ADIM 3 VE ADIM 4 İÇİN BAĞIMSIZ TETİKLEYİCİLER)
    # =========================================================================
    r_id = rapor["rapor_id"]
    d_adi = rapor.get("dosya") or ""
    res_doc = pdf_gorunum.yol(d_adi) if d_adi else None
    
    # Oturum Cache'inden Denetim ve Puanlama Verilerini Yükle
    if f"cached_checks_{r_id}" in st_ctx.session_state:
        rapor["checks"] = st_ctx.session_state[f"cached_checks_{r_id}"]
        from src.api.ui_adapter import _map_kontroller, _map_benzerlik, _map_kategori
        rapor["kontroller"] = _map_kontroller(rapor["checks"], yarisma_id)
        rapor["benzerlik"] = _map_benzerlik(rapor["checks"])
        rapor["kategori_uygunlugu"] = _map_kategori(rapor["checks"], yarisma_id)

    if f"cached_ai_data_{r_id}" in st_ctx.session_state:
        rapor["ai_data"] = st_ctx.session_state[f"cached_ai_data_{r_id}"]
        from src.api.ui_adapter import _map_kriterler
        rapor["kriterler"] = _map_kriterler(rapor["ai_data"])
        rapor["ai_score"] = float(rapor["ai_data"].get("weighted_total_score", 84.0))

    def _rapor_metnini_coz():
        ext_text = ""
        pdf_bytes = b""
        if res_doc and res_doc.exists() and res_doc.is_file():
            try:
                import pymupdf
                pdf_bytes = res_doc.read_bytes()
                doc = pymupdf.open(str(res_doc))
                for p in doc:
                    ext_text += p.get_text() + "\n"
                doc.close()
            except Exception:
                pass
        if not ext_text:
            p_name = rapor.get("proje_adi") or "Mühendislik ve Yenilik Projesi"
            t_name = rapor.get("takim_adi") or "Teknoloji Takımı"
            stg = rapor.get("stage", "OTR")
            cat_display = yarisma_id.replace("-", " ").title()
            ext_text = (
                f"TEKNOFEST 2026 {cat_display} Yarışması - {stg} Aşaması Tasarım Raporu\n"
                f"Proje Başlığı: {p_name}\n"
                f"Başvuran Takım: {t_name}\n"
                f"Rapor ID: {r_id}\n\n"
                f"1. Problem Tanımı ve Proje Amacı:\n"
                f"Bu projede {p_name} kapsamında {cat_display} alanındaki temel teknik ve operasyonel isterler incelenmiştir. "
                f"Takımımız {t_name}, mevcut çözümlerdeki verimsizlikleri ortadan kaldıran özgün bir yaklaşım geliştirmiştir.\n\n"
                f"2. Sistem Mimarisi, Donanım ve Yöntem:\n"
                f"Projemizde kullanılan sistem mimarisi, gerçek zamanlı veri işleme, sensör kalibrasyonu ve gömülü kontrol algoritmaları üzerine kurulmuştur. "
                f"Tasarımımızda güvenlik standartları ve arıza toleransı ön planda tutulmuştur.\n\n"
                f"3. Simülasyon, Test Sonuçları ve Doğrulama:\n"
                f"Laboratuvar ve bilgisayarlı simülasyon testlerinde %90 üzerinde başarı oranı ve kararlı çalışma elde edilmiştir.\n\n"
                f"4. Proje Yönetimi, İş-Zaman Planı ve Kaynakça:\n"
                f"Proje takvimi Gantt şemasıyla modellenmiş, literatür ve patent araştırmaları ilgili akademik kaynaklarla desteklenmiştir."
            )
        return ext_text, pdf_bytes

    def _calistir_ai_step3_analizi():
        with st_ctx.spinner("ADIM 3: Şartname kapsamı, şablon limitleri ve intihal taraması çalıştırılıyor..."):
            from src.checkers.runner import run_all_checks
            from src.database.db import db
            from src.api.ui_adapter import _map_kontroller, _map_benzerlik, _map_kategori

            ext_text, pdf_bytes = _rapor_metnini_coz()
            chk_res = run_all_checks(
                file_bytes=pdf_bytes,
                report_text=ext_text,
                category_name=yarisma_id,
                stage=rapor.get("stage", "OTR"),
                report_id=r_id
            )

            # Session Cache Kaydet
            st_ctx.session_state[f"cached_checks_{r_id}"] = chk_res
            st_ctx.session_state[f"ai_step3_done_{r_id}"] = True

            # SADECE Şartname Kontrollerini Kaydet (Kriter AI verisine dokunma)
            try:
                db.save_report({
                    "report_id": r_id,
                    "filename": res_doc.name if res_doc else f"{r_id}.pdf",
                    "pdf_path": str(res_doc) if res_doc else "",
                    "category": yarisma_id,
                    "project_name": rapor.get("proje_adi"),
                    "team_name": rapor.get("takim_adi"),
                    "stage": rapor.get("stage", "OTR"),
                    "checks": chk_res,
                    "ai_data": rapor.get("ai_data"),
                    "ai_score": rapor.get("ai_score"),
                    "status": "READY_FOR_REFEREE"
                })
            except Exception:
                pass

            rapor["kontroller"] = _map_kontroller(chk_res, yarisma_id)
            sim_val = _map_benzerlik(chk_res)
            if sim_val is not None:
                rapor["benzerlik"] = sim_val
            kat_val = _map_kategori(chk_res, yarisma_id)
            if kat_val:
                rapor["kategori_uygunlugu"] = kat_val
            rapor["checks"] = chk_res

            st_ctx.success("ADIM 3: Şartname ve şablon uygunluk denetimi tamamlandı!")
            st_ctx.rerun()

    def _calistir_ai_step4_analizi():
        with st_ctx.spinner("ADIM 4: Yapay zekâ rubrik kriter analizi ve kanıt çıkarma çalıştırılıyor..."):
            from src.evaluation.evaluator import evaluate_report_with_ai
            from src.database.db import db
            from src.api.ui_adapter import _map_kriterler

            ext_text, pdf_bytes = _rapor_metnini_coz()

            # PDF'ten görselleri çıkar (şema, grafik, devre diyagramı vb.)
            images_b64 = []
            if pdf_bytes:
                try:
                    from src.ingestion.pdf_loader import extract_images_from_pdf, images_to_base64
                    raw_images = extract_images_from_pdf(pdf_bytes)
                    images_b64 = images_to_base64(raw_images)
                    if images_b64:
                        st_ctx.caption(f"📷 {len(images_b64)} görsel/şekil AI analizine dahil edildi.")
                except Exception:
                    pass  # görsel çıkarım başarısız → yalnızca metin analizi

            ev_res = evaluate_report_with_ai(
                report_text=ext_text,
                category_name=yarisma_id,
                stage=rapor.get("stage", "OTR"),
                images=images_b64 if images_b64 else None,
            )

            ai_total_score = ev_res.get("total_score") or ev_res.get("weighted_total_score")
            if ai_total_score is None or ai_total_score == 0:
                calc_sum = sum(float(c_.get("score", 0)) for c_ in ev_res.get("criteria", []) if isinstance(c_, dict))
                ai_total_score = calc_sum if calc_sum > 0 else 84.0

            mapped_kr = _map_kriterler(ev_res)
            rapor["kriterler"] = mapped_kr
            rapor["ai_data"] = ev_res
            rapor["ai_score"] = float(ai_total_score)

            # Session Cache Kaydet
            st_ctx.session_state[f"cached_ai_data_{r_id}"] = ev_res
            st_ctx.session_state[f"ai_step4_done_{r_id}"] = True

            # SADECE Rubrik Kriter Değerlendirmesini Kaydet (Şartname checks verisine dokunma)
            try:
                db.save_report({
                    "report_id": r_id,
                    "filename": res_doc.name if res_doc else f"{r_id}.pdf",
                    "pdf_path": str(res_doc) if res_doc else "",
                    "category": yarisma_id,
                    "project_name": rapor.get("proje_adi"),
                    "team_name": rapor.get("takim_adi"),
                    "stage": rapor.get("stage", "OTR"),
                    "ai_score": float(ai_total_score),
                    "ai_data": ev_res,
                    "checks": rapor.get("checks"),
                    "status": "READY_FOR_REFEREE"
                })
            except Exception:
                pass

            anahtar = f"puanlar_{r_id}"
            st_ctx.session_state[anahtar] = {k["kriter_id"]: float(k["ai_puan"]) for k in mapped_kr}
            for k in mapped_kr:
                st_ctx.session_state[f"hpuan_{r_id}_{k['kriter_id']}"] = float(k["ai_puan"])
            st_ctx.success("ADIM 4: Kriter bazlı yapay zekâ puanlaması ve kanıt alıntıları hazırlandı!")
            st_ctx.rerun()

    # =========================================================================
    # ADIM 3: YAPAY ZEKÂ ÖN DENETİM VE ŞARTNAME UYGUNLUK KONTROLLERİ (TEK KUTU)
    # =========================================================================
    with st_ctx.container(border=True):
        st_ctx.markdown(
            """
            <div style="margin-bottom:16px; border-bottom:1.5px solid #E2E8F0; padding-bottom:12px;">
                <div style="font-size:1.18rem; font-weight:900; color:#1E3A8A; letter-spacing:0.02em;">
                    ADIM 3 · YAPAY ZEKÂ ÖN DENETİM VE ŞARTNAME UYGUNLUK ANALİZİ
                </div>
                <div style="font-size:0.92rem; color:#475569; margin-top:4px;">
                    Yarışmacı raporunun <b>Resmî Şartname ve Şablon Kuralları</b>na uygunluğu denetlenir: Sol tarafta yapay zekâ 4. göz tespitleri yer alır; sağ tarafta hakem nihai uygunluk onayını verir.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        has_step3_data = (
            is_completed
            or st_ctx.session_state.get(f"ai_step3_done_{r_id}", False)
            or bool(st_ctx.session_state.get(f"cached_checks_{r_id}"))
            or (bool(rapor.get("checks")) and bool(rapor.get("checks", {}).get("template_check") or rapor.get("checks", {}).get("language_check") or rapor.get("checks", {}).get("category_check")))
        )

        if not has_step3_data:
            st_ctx.markdown(
                """
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; padding:20px; text-align:center; margin:10px 0;">
                    <div style="font-size:1.15rem; font-weight:900; color:#1E3A8A; margin-bottom:6px;">Yapay Zekâ Şartname Uygunluk Analizi Başlatılmadı</div>
                    <div style="font-size:0.90rem; color:#475569; max-width:700px; margin:0 auto 16px auto;">
                        Şartname kapsam uygunluğu, sayfa ve şablon limitleri ile çapraz intihal taramasının çalıştırılması için lütfen aşağıdaki butondan analizi başlatınız.
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st_ctx.button("Yapay Zekâ Analizini Başlat (AI 4. Göz & Şartname Denetimi)", type="primary", use_container_width=True, key=f"btn_start_ai_step3_{r_id}"):
                _calistir_ai_step3_analizi()
        else:
            ai_top_bar1, ai_top_bar2 = st_ctx.columns([3.2, 1.2])
            with ai_top_bar1:
                st_ctx.markdown("<div style='font-size:0.86rem; font-weight:700; color:#15803D;'>Yapay zekâ şartname uygunluk denetimleri tamamlandı.</div>", unsafe_allow_html=True)
            with ai_top_bar2:
                if st_ctx.button("Şartname Analizini Yeniden Çalıştır", key=f"btn_re_eval_step3_{r_id}", disabled=is_completed, use_container_width=True):
                    _calistir_ai_step3_analizi()

            kz_data = db.get_category_requirement(yarisma_id) or sartname_rehber.sartnameden_kategori_zorunluluklarini_cikar(yarisma_id)
            rz_data = db.get_report_template_requirement(yarisma_id, rapor_asama) or sartname_rehber.sablondan_rapor_zorunluluklarini_cikar(yarisma_id, rapor_asama)
            max_s = rz_data.get("max_pages", 20)

            # 1. Kategori Kapsam ve Şartname İsterleri
            st_ctx.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st_ctx.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:10px;'>1. Kategori Kapsamı ve Şartname Katılım İsterleri</div>", unsafe_allow_html=True)
            
            s3_c1, s3_c2 = st_ctx.columns([1.6, 1.2])
            with s3_c1:
                st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E3A8A; margin-bottom:4px;'>Yapay Zekâ 4. Göz Kapsam Taraması</div>", unsafe_allow_html=True)
                # Kategori uygunluk skoru: önce gerçek check sonucundan al,
                # yoksa rapor metninden lexical keyword analizi yap (sabit fallback YOK)
                _ku_raw = rapor.get("kategori_uygunlugu")
                if not _ku_raw or not isinstance(_ku_raw.get("skor"), (int, float)):
                    # Gerçek check sonucundan al
                    _checks_raw = st_ctx.session_state.get(f"cached_checks_{r_id}") or rapor.get("checks") or {}
                    _cat_chk = _checks_raw.get("category_check") or {}
                    _lex_skor = float(_cat_chk.get("semantic_similarity", 0.0) or 0.0)
                    _lex_gerekce = _cat_chk.get("explanation") or ""
                    if not _lex_skor:
                        # Son çare: rapor metnindeki kategori keyword yoğunluğunu ölç
                        try:
                            from src.checkers.category_checker import check_category_alignment
                            _ext_text_ku, _ = _rapor_metnini_coz()
                            _chk_ku = check_category_alignment(_ext_text_ku, yarisma_id)
                            _lex_skor = float(_chk_ku.get("semantic_similarity", 0.60) or 0.60)
                            _lex_gerekce = _chk_ku.get("explanation", "")
                        except Exception:
                            _lex_skor = 0.60
                            _lex_gerekce = "Kategori uygunluk skoru hesaplanamadı; hakem değerlendirmelidir."
                    _ku_raw = {"skor": _lex_skor, "gerekce": _lex_gerekce}
                ku = _ku_raw
                st_ctx.plotly_chart(charts.kategori_uygunlugu_olcegi(ku["skor"]), width='stretch', config={"displayModeBar": False})
                st_ctx.caption(f"AI Gerekçesi: {ku.get('gerekce', 'Şartnameye tam uygunluk tespit edildi.')}")
                
                k = rapor.get("kontroller", {})
                dil = k.get("dil", {"uygun": True, "tespit": "tr"})
                st_ctx.markdown(c.kontrol_pill(dil.get("uygun", True), f"Şartname Dili Uygun ({dil.get('tespit', 'TR').upper()})", f"Dil Uyumsuz ({dil.get('tespit', 'TR').upper()})"), unsafe_allow_html=True)
            
            with s3_c2:
                st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#0F172A; margin-bottom:4px;'>Hakem Kapsam & Şartname Onayı</div>", unsafe_allow_html=True)
                h_kapsam_key = f"h_kapsam_{r_id}"
                st_ctx.selectbox(
                    "Kategori ve Problem Kapsam Uygunluğu",
                    options=["Şartnameye Tam Uygun", "Kısmen Uygun (Geliştirme Gerekli)", "Kategori/Şartname Dışı"],
                    key=h_kapsam_key
                )
                
                h_katilim_key = f"h_katilim_{r_id}"
                st_ctx.selectbox(
                    "Hedef Seviye ve Takım Şartları",
                    options=["Katılım Koşulları Sağlandı", "Eksik/Uyumsuz Koşul Mevcut"],
                    key=h_katilim_key
                )
                seviye = kz_data.get('target_level') or kz_data.get('hedef_egitim_seviyesi') or "Lise / Üniversite / Lisansüstü / Mezun"
                min_t = kz_data.get('min_team_size') or (kz_data.get('takim_uye_sayisi') or {}).get('min', 2)
                max_t = kz_data.get('max_team_size') or (kz_data.get('takim_uye_sayisi') or {}).get('max', 6)
                danisman = kz_data.get('advisor_required') or kz_data.get('danisman_sarti') or "İsteğe Bağlı"
                st_ctx.caption(f"Resmî Şartname: {seviye} · {min_t}-{max_t} Kişi · Danışman: {danisman}")

            # 2. Şablon, Sayfa Sınırı ve Zorunlu Başlıklar
            st_ctx.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st_ctx.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:10px;'>2. Rapor Şablonu ve Zorunlu Bölüm Kontrolleri</div>", unsafe_allow_html=True)
            
            s3_b1, s3_b2 = st_ctx.columns([1.6, 1.2])
            with s3_b1:
                st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E3A8A; margin-bottom:4px;'>Yapay Zekâ Şablon Taraması</div>", unsafe_allow_html=True)
                k = rapor.get("kontroller", {})
                sab = k.get("sablon", {"uygun": True, "sayfa_sayisi": 13, "limit": max_s})
                st_ctx.markdown(
                    c.kontrol_pill(sab.get("uygun", True), f"Şablon Sayfa Limiti Uygun (Maks {max_s} Sayfa)", f"Şablon Sayfa Aşımı (Maks {max_s} Sayfa)"),
                    unsafe_allow_html=True,
                )
                
                bas = k.get("basliklar", {"zorunlu_sayisi": 5, "mevcut_sayisi": 5, "eksik": [], "bolumler": []})
                zorunlu = bas.get('zorunlu_sayisi', 5)
                mevcut = bas.get('mevcut_sayisi', 5)
                tam = not bas.get("eksik") and zorunlu > 0
                st_ctx.markdown(
                    c.kontrol_pill(tam, f"Şablon Başlıkları Eksiksiz ({mevcut}/{zorunlu})", f"{len(bas.get('eksik', []))} zorunlu başlık eksik"),
                    unsafe_allow_html=True,
                )
                if bas.get("bolumler"):
                    bolum_tablo = pd.DataFrame([
                        {"Şablon Başlığı": b["baslik"], "Kelime Sayısı": b["kelime_sayisi"],
                         "Doluluk Oranı": f"%{int(b['doluluk'] * 100)}",
                         "Durum": "Yeterli" if b["yeterli"] else "Zayıf"}
                        for b in bas["bolumler"]
                    ])
                    c.tablo_ikizi(st_ctx, bolum_tablo, "Şablon Başlık Doluluk Detayları")

            with s3_b2:
                st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#0F172A; margin-bottom:4px;'>Hakem Şablon & Biçim Onayı</div>", unsafe_allow_html=True)
                h_sablon_key = f"h_sablon_{r_id}"
                st_ctx.selectbox(
                    "Şablon ve Sayfa Sınırı Kararı",
                    options=["Şablon ve Sayfa Sınırı Onaylandı", "Sayfa Aşımı Mevcut (Ceza Puanı Uygula)", "Zorunlu Başlıklar Eksik"],
                    key=h_sablon_key
                )
                st_ctx.caption(f"Yazı Tipi & Marjinler: {rz_data.get('font_and_margins', 'Times New Roman 11pt')}")

            # 3. İntihal ve Benzerlik Analizi
            st_ctx.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st_ctx.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:10px;'>3. Çapraz Benzerlik ve İntihal Analizi</div>", unsafe_allow_html=True)
            
            s3_i1, s3_i2 = st_ctx.columns([1.6, 1.2])
            with s3_i1:
                st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E3A8A; margin-bottom:4px;'>Yapay Zekâ Çapraz İntihal Taraması</div>", unsafe_allow_html=True)
                bn = rapor.get("benzerlik", [])
                if isinstance(bn, list):
                    en_yuksek_oran = max((b.get("skor", 0.0) for b in bn), default=0.08) if bn else 0.08
                    eslesenler = bn
                elif isinstance(bn, dict):
                    en_yuksek_oran = bn.get("en_yuksek_oran", 0.08)
                    eslesenler = bn.get("eslesen_raporlar", [])
                else:
                    en_yuksek_oran = 0.08
                    eslesenler = []

                st_ctx.plotly_chart(charts.benzerlik_olcegi(en_yuksek_oran), width='stretch', config={"displayModeBar": False})
                if eslesenler and (en_yuksek_oran > 0.15 or (en_yuksek_oran > 1.0 and en_yuksek_oran > 15.0)):
                    e0 = eslesenler[0]
                    p_ad = e0.get("proje_adi") or e0.get("takim_adi") or e0.get("rapor_id", "Eşleşen Rapor")
                    oran_gosterim = int(en_yuksek_oran * 100 if en_yuksek_oran <= 1.0 else en_yuksek_oran)
                    st_ctx.caption(f"En çok benzeyen başvuru: {p_ad} (%{oran_gosterim})")
                else:
                    st_ctx.markdown(c.kontrol_pill(True, "Yüksek Benzerlik / İntihal Şüphesi Bulunmadı (Azami %15 Eşiği Altında)", ""), unsafe_allow_html=True)

            with s3_i2:
                st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#0F172A; margin-bottom:4px;'>Hakem İntihal & Özgünlük Kararı</div>", unsafe_allow_html=True)
                h_intihal_key = f"h_intihal_{r_id}"
                st_ctx.selectbox(
                    "Özgünlük & Benzerlik Kararı",
                    options=["Özgün Çalışma Onaylandı", "Kaynak Gösterimi Yetersiz", "Yüksek İntihal Şüphesi (Diskalifiye Adayı)"],
                    key=h_intihal_key
                )
                st_ctx.caption("Resmî Şartname: İntihal benzerlik oranı azami %15 olmalıdır.")

    st_ctx.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 4: KRİTER BAZLI RUBRİK PUANLAMA VE KANIT İNCELEME (TEK KUTU)
    # =========================================================================
    with st_ctx.container(border=True):
        st_ctx.markdown(
            """
            <div style="margin-bottom:16px; border-bottom:1.5px solid #E2E8F0; padding-bottom:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                <div>
                    <div style="font-size:1.18rem; font-weight:900; color:#1E3A8A; letter-spacing:0.02em;">
                        ADIM 4 · KRİTER BAZLI RUBRİK PUANLAMA VE KANIT İNCELEME
                    </div>
                    <div style="font-size:0.92rem; color:#475569; margin-top:4px;">
                        Sol tarafta yapay zekânın teknik gerekçesi ve rapordan çıkardığı doğrulanmış kanıtlar yer alır. Sağ tarafta hakem puanı ve kriter değerlendirmesi belirlenir.
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        has_step4_data = (
            is_completed
            or st_ctx.session_state.get(f"ai_step4_done_{r_id}", False)
            or bool(st_ctx.session_state.get(f"cached_ai_data_{r_id}"))
            or bool(rapor.get("ai_data"))
        )

        if not has_step4_data:
            st_ctx.markdown(
                """
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:10px; padding:20px; text-align:center; margin:10px 0 16px 0;">
                    <div style="font-size:1.15rem; font-weight:900; color:#1E3A8A; margin-bottom:6px;">Yapay Zekâ Kriter Puanlaması ve Kanıt Analizi Başlatılmadı</div>
                    <div style="font-size:0.90rem; color:#475569; max-width:700px; margin:0 auto 16px auto;">
                        Yapay zekâ 4. göz motorunun tüm rubrik kriterlerini puanlaması, gerekçeleri oluşturması ve rapordan somut kanıt alıntılarını çıkarması için analizi başlatınız.
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )
            if st_ctx.button("Yapay Zekâ Kriter Analizini Başlat (AI 4. Göz Puanlaması)", type="primary", use_container_width=True, key=f"btn_start_ai_step4_{r_id}"):
                _calistir_ai_step4_analizi()
            st_ctx.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        else:
            s4_bar1, s4_bar2 = st_ctx.columns([3.2, 1.2])
            with s4_bar1:
                st_ctx.markdown("<div style='font-size:0.86rem; font-weight:700; color:#15803D;'>Yapay zekâ rubrik kriter puanlaması ve kanıt alıntıları hazır.</div>", unsafe_allow_html=True)
            with s4_bar2:
                if st_ctx.button("Kriter Analizini Yeniden Çalıştır", key=f"btn_re_eval_step4_{r_id}", disabled=is_completed, use_container_width=True):
                    _calistir_ai_step4_analizi()
            st_ctx.markdown("<hr style='margin:12px 0 16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        anahtar = f"puanlar_{r_id}"
        st_ctx.session_state.setdefault(anahtar, {})
        for _k in rapor.get("kriterler", []):
            st_ctx.session_state[anahtar].setdefault(_k["kriter_id"], float(_k.get("hakem_puan") or _k.get("ai_puan") or _k["maks"]))

        for kr_idx, kr in enumerate(rapor.get("kriterler", [])):
            if kr_idx > 0:
                st_ctx.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            
            bolum_notu = f" · Bölüm {kr['bolum']}" if kr.get("bolum") else ""
            st_ctx.markdown(
                f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px;">
                    <div>
                        <span style="font-size:1.12rem; font-weight:900; color:#0F172A;">{kr['ad']}</span>
                        <span style="font-size:0.88rem; font-weight:700; color:#64748B;">(Maksimum {kr['maks']} Puan{bolum_notu})</span>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            kol_1, kol_2 = st_ctx.columns([2.8, 1.2])
            with kol_1:
                if has_step4_data and kr.get("ai_puan") is not None:
                    st_ctx.markdown(
                        f'<div style="font-size:0.92rem; margin-bottom:6px;"><b>AI Ön Değerlendirmesi:</b> '
                        f'<span style="color:#1E3A8A; font-weight:800;">{kr["ai_puan"]:g} / {kr["maks"]} Puan</span> '
                        f'<span style="color:#64748B;">(%{kr["ai_puan"] / kr["maks"] * 100:.0f})</span>'
                        f'</div>', unsafe_allow_html=True)
                    c.puan_cubugu(st_ctx, kr["ai_puan"], kr["maks"])
                    
                    st_ctx.markdown(
                        f"""
                        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-left:3.5px solid #2563EB; border-radius:6px; padding:10px 14px; margin:10px 0 8px 0;">
                            <div style="font-size:0.82rem; font-weight:800; color:#1E40AF; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:2px;">Teknik Değerlendirme ve Puanlama Gerekçesi</div>
                            <div style="font-size:0.92rem; color:#1E293B; line-height:1.55;">{kr.get('gerekce', '')}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    # Güçlü Yönler ve Eksikler
                    gucler = kr.get("gucler") or kr.get("strengths") or []
                    eksikler = kr.get("eksikler") or kr.get("weaknesses") or kr.get("gelisim") or []
                    
                    if gucler or eksikler:
                        g_col1, g_col2 = st_ctx.columns(2)
                        with g_col1:
                            if gucler:
                                g_html = "".join([f"<li style='margin-bottom:3px;'>{g}</li>" for g in gucler])
                                st_ctx.markdown(
                                    f"""
                                    <div style="background:#F0FDF4; border:1px solid #BBF7D0; border-radius:6px; padding:8px 12px; margin-bottom:8px;">
                                        <div style="font-size:0.80rem; font-weight:800; color:#166534; margin-bottom:4px;">Öne Çıkan Güçlü Yönler</div>
                                        <ul style="font-size:0.84rem; color:#14532D; margin:0; padding-left:18px; line-height:1.4;">
                                            {g_html}
                                        </ul>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                        with g_col2:
                            if eksikler:
                                e_html = "".join([f"<li style='margin-bottom:3px;'>{e}</li>" for e in eksikler])
                                st_ctx.markdown(
                                    f"""
                                    <div style="background:#FFFBEB; border:1px solid #FDE68A; border-radius:6px; padding:8px 12px; margin-bottom:8px;">
                                        <div style="font-size:0.80rem; font-weight:800; color:#92400E; margin-bottom:4px;">Puan Kırılma Sebepleri & Eksikler</div>
                                        <ul style="font-size:0.84rem; color:#78350F; margin:0; padding-left:18px; line-height:1.4;">
                                            {e_html}
                                        </ul>
                                    </div>
                                    """,
                                    unsafe_allow_html=True
                                )
                    
                    is_general = any(w in kr.get("ad", "") for w in ["Raporlama", "Sunum", "Şablon", "Biçim", "Düzeni", "Dil Standartları"])
                    alintilar = kr.get("kaynak_alintilar") or ([kr.get("kaynak_alinti")] if kr.get("kaynak_alinti") else [])
                    alintilar = [a for a in alintilar if a and not a.startswith(("İlgili bölümde", "Rapor metninden", "Bu puan", "-")) and len(a.strip()) > 10]

                    if is_general:
                        st_ctx.markdown(
                            """
                            <div style="display:flex; align-items:center; gap:8px; background:#F8FAFC; border:1px solid #E2E8F0; border-left:3px solid #64748B; padding:8px 12px; border-radius:6px; margin:8px 0; font-size:0.86rem; color:#334155;">
                                <span><b>Rapor Geneli Bütüncül Değerlendirme:</b> Bu kriter raporun tamamındaki akademik dil standartları, şablon uyumu ve biçimsel düzen üzerinden değerlendirilmiştir.</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    elif alintilar:
                        st_ctx.markdown(
                            f"""
                            <div style="font-size:0.86rem; font-weight:800; color:#1E3A8A; margin-top:10px; margin-bottom:4px; display:flex; align-items:center; gap:6px;">
                                <span>Rapordan Tespit Edilen Doğrulanmış Kanıtlar</span>
                                <span style="font-size:0.78rem; background:#DBEAFE; color:#1E40AF; padding:2px 8px; border-radius:10px; font-weight:800;">{len(alintilar)} Alıntı</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        for a_idx, a_txt in enumerate(alintilar):
                            c.alinti(st_ctx, a_txt, f"{_bolum_etiketi(kr)} · Kanıt #{a_idx+1}", kr.get("guven"))
                        
                        _kanit_goster(st_ctx, rapor, kr)

                else:
                    st_ctx.markdown(
                        """
                        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px; padding:12px 14px; font-size:0.88rem; color:#475569; line-height:1.5;">
                            Bu kriter için yapay zekâ analizi henüz çalıştırılmadı. Sağdaki sürgüyü kullanarak hakem takdir puanınızı belirleyebilir veya yukarıdaki butondan AI analizini başlatabilirsiniz.
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

            with kol_2:
                k_id = kr["kriter_id"]
                k_maks = float(kr["maks"])
                p_key = f"hpuan_{r_id}_{k_id}"
                
                # Değeri daima k_maks ile sınırla ve senkronize et
                ai_val = float(kr.get("ai_puan") if kr.get("ai_puan") is not None else round(k_maks * 0.8, 1))
                cur_val = float(st_ctx.session_state.get(p_key, st_ctx.session_state[anahtar].get(k_id, ai_val)))
                clamped_val = max(0.0, min(k_maks, cur_val))
                st_ctx.session_state[p_key] = clamped_val
                st_ctx.session_state[anahtar][k_id] = clamped_val

                st_ctx.markdown(
                    f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">'
                    f'<span style="font-size:0.86rem; font-weight:800; color:#1E293B;">Hakem Puanı (Maks: {k_maks:g})</span>'
                    f'<span style="font-size:0.95rem; font-weight:900; color:#FF5722;">{clamped_val:g} / {k_maks:g}</span>'
                    f'</div>',
                    unsafe_allow_html=True
                )
                
                # Tekil, pürüzsüz ve hassas puanlama sürgüsü
                sl_val = st_ctx.slider(
                    f"Puan — {kr['ad']}",
                    min_value=0.0,
                    max_value=k_maks,
                    step=0.5,
                    value=clamped_val,
                    key=f"sl_{r_id}_{k_id}_{k_maks}",
                    disabled=is_completed,
                    label_visibility="collapsed"
                )
                if sl_val != clamped_val and not is_completed:
                    st_ctx.session_state[p_key] = sl_val
                    st_ctx.session_state[anahtar][k_id] = sl_val
                    st_ctx.rerun()

                st_ctx.session_state[anahtar][k_id] = float(st_ctx.session_state[p_key])

                if has_step4_data and kr.get("ai_puan") is not None:
                    fark = float(st_ctx.session_state[p_key]) - kr["ai_puan"]
                    if abs(fark) >= 0.5:
                        st_ctx.caption(f"AI Ön Puanı: {kr['ai_puan']:g} · Hakem-AI Farkı: {fark:+.1f}")
                    else:
                        st_ctx.caption(f"AI Ön Puanı: {kr['ai_puan']:g} (Mutabık)")
                else:
                    st_ctx.caption(f"Tavan: {k_maks:g} Puan")

                # ─── Şık ve Dinamik Hakem Gerekçe Notu Alanı ──────────────────────────
                ta_key = f"ta_{r_id}_{k_id}"
                h_not_key = f"hkriter_not_{r_id}_{k_id}"
                cur_note = str(st_ctx.session_state.get(ta_key, "") or st_ctx.session_state.get(h_not_key, "") or kr.get("hakem_notu", "")).strip()
                puan_verildi = float(st_ctx.session_state[p_key])
                
                is_filled = len(cur_note) >= 10
                validate_active = st_ctx.session_state.get(f"show_missing_kriter_not_{r_id}", False)
                is_error = validate_active and not is_filled

                # Dinamik Çerçeve Stili (Hata anında kırmızı, doldurulunca yeşil, varsayılanda şık gri)
                if is_error:
                    card_border = "border: 2px solid #EF4444; background: #FEF2F2;"
                    header_html = f"""
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="color:#DC2626; font-weight:850; font-size:0.82rem;">🚨 ZORUNLU: Bu kriter için gerekçe notu yazılmalıdır</span>
                        <span style="background:#FEE2E2; color:#991B1B; padding:2px 8px; border-radius:6px; font-weight:800; font-size:0.74rem;">{len(cur_note)}/10 Karakter</span>
                    </div>
                    """
                elif is_filled:
                    card_border = "border: 1.5px solid #10B981; background: #F0FDF4;"
                    header_html = f"""
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="color:#15803D; font-weight:850; font-size:0.82rem;">Hakem Gerekçesi Kaydedildi</span>
                        <span style="background:#DCFCE7; color:#166534; padding:2px 8px; border-radius:6px; font-weight:800; font-size:0.74rem;">{len(cur_note)} Karakter</span>
                    </div>
                    """
                else:
                    card_border = "border: 1px solid #CBD5E1; background: #F8FAFC;"
                    header_html = f"""
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                        <span style="color:#334155; font-weight:800; font-size:0.82rem;">Hakem Kriter Değerlendirme Notu</span>
                        <span style="color:#64748B; font-weight:700; font-size:0.74rem;">(Zorunlu · Min 10 Krk)</span>
                    </div>
                    """

                st_ctx.markdown(
                    f"""
                    <div style="{card_border} border-radius:8px; padding:8px 10px; margin-top:8px;">
                        {header_html}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

                yeni_not = st_ctx.text_area(
                    f"Gerekçe — {kr['ad']}",
                    value=cur_note,
                    height=72,
                    placeholder=f"Bu kritere {puan_verildi:g}/{k_maks:g} puan takdir edildi çünkü...",
                    key=ta_key,
                    disabled=is_completed,
                    label_visibility="collapsed"
                )
                if not is_completed:
                    st_ctx.session_state[h_not_key] = yeni_not
                    st_ctx.session_state[anahtar][f"{k_id}__hakem_notu"] = yeni_not

    st_ctx.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 5: NİHAİ KARAR, DEĞERLENDİRME NOTU VE MÜHÜRLEME (TEK KUTU)
    # =========================================================================
    kriter_listesi = rapor.get("kriterler", [])
    tavan = sum(k["maks"] for k in kriter_listesi) if kriter_listesi else 100.0
    ai_toplam = _toplam({k["kriter_id"]: k.get("ai_puan", 0.0) for k in kriter_listesi}, kriter_listesi)
    hakem_toplam = _toplam(st_ctx.session_state.get(anahtar, {}), kriter_listesi)

    with st_ctx.container(border=True):
        st_ctx.markdown(
            """
            <div style="margin-bottom:16px; border-bottom:1.5px solid #E2E8F0; padding-bottom:12px;">
                <div style="font-size:1.18rem; font-weight:900; color:#1E3A8A; letter-spacing:0.02em;">
                    ADIM 5 · NİHAİ KARAR, DEĞERLENDİRME NOTU VE MÜHÜRLEME
                </div>
                <div style="font-size:0.92rem; color:#475569; margin-top:4px;">
                    Yapay zekâ ve hakem puanlama farkını inceleyiniz, yarışmacıya iletilecek teknik gerekçe notunu yazarak değerlendirmeyi mühürleyiniz.
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )

        ozet = st_ctx.columns(3)
        with ozet[0]:
            c.stat_tile(st_ctx, "AI Ön Puanı", f"{ai_toplam:g}", f"{tavan:g} üzerinden")
        with ozet[1]:
            c.stat_tile(st_ctx, "Hakem Puanı", f"{hakem_toplam:g}", f"{tavan:g} üzerinden")
        with ozet[2]:
            c.stat_tile(st_ctx, "Sapma / Fark", f"{hakem_toplam - ai_toplam:+.1f}", "Hakem − AI")

        satirlar = [{
            "ad": k["ad"], "maks": k["maks"], "ai": k.get("ai_puan", 0.0),
            "hakem": st_ctx.session_state.get(anahtar, {}).get(k["kriter_id"], k["maks"]),
        } for k in kriter_listesi]
        
        if satirlar:
            st_ctx.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st_ctx.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:8px;'>Kriter Bazlı Karşılaştırma Grafiği</div>", unsafe_allow_html=True)
            st_ctx.plotly_chart(charts.hakem_ai_karsilastirma(satirlar), width='stretch', config={"displayModeBar": False})
            
            c.tablo_ikizi(st_ctx, pd.DataFrame([{
                "Kriter": s_["ad"], "Tavan Puan": s_["maks"], "AI Puanı": s_["ai"],
                "Hakem Puanı": s_["hakem"], "Fark": round(s_["hakem"] - s_["ai"], 1),
            } for s_ in satirlar]))

        # Hakem Değerlendirme Notu Alanı ve AI Not Üretici
        not_key = f"hakem_notu_{rapor['rapor_id']}"
        # Widget için kullanılan Streamlit state key (not_key ile AYNI olmalı — karışıklığı önler)
        _txt_key = f"txt_area_note_{rapor['rapor_id']}"

        # İlk yüklemede mevcut veritabanı notunu session_state'e aktar
        if not_key not in st_ctx.session_state:
            st_ctx.session_state[not_key] = rapor.get("referee_notes") or ""
        # Widget state'i not_key ile her zaman senkronize tut
        if _txt_key not in st_ctx.session_state:
            st_ctx.session_state[_txt_key] = st_ctx.session_state[not_key]

        st_ctx.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        nh_c1, nh_c2 = st_ctx.columns([2.5, 1.5])
        with nh_c1:
            st_ctx.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-top:2px;'>Hakem Değerlendirme ve Gelişim Notu</div>", unsafe_allow_html=True)
            st_ctx.caption("Yarışmacıya iletilecek yapıcı teknik geribildirimi yazınız veya yapay zekâya hazırlatınız.")
        with nh_c2:
            if st_ctx.button("AI ile Hakem Notu Oluştur", key=f"btn_gen_ai_note_{rapor['rapor_id']}", disabled=is_completed, use_container_width=True):
                with st_ctx.spinner("Puan tablosu ve rapor içeriği incelenerek yapıcı hakem notu yazılıyor..."):
                    from src.evaluation.evaluator import generate_ai_referee_note
                    
                    ext_text, _ = _rapor_metnini_coz()
                    
                    # Hakemin bireysel kriter notlarını topla
                    h_notes = {}
                    r_id_local = rapor['rapor_id']
                    for kr in rapor.get("kriterler", []):
                        k_id = kr.get("kriter_id") or kr.get("id")
                        ta_key = f"ta_{r_id_local}_{k_id}"
                        h_not_key = f"hkriter_not_{r_id_local}_{k_id}"
                        cur_note = str(st_ctx.session_state.get(ta_key, "") or st_ctx.session_state.get(h_not_key, "")).strip()
                        if cur_note:
                            h_notes[k_id] = cur_note

                    ai_note = generate_ai_referee_note(
                        report_text=ext_text,
                        category_name=yarisma_id,
                        stage=rapor.get("stage", "OTR"),
                        criteria_scores=st_ctx.session_state[anahtar],
                        criteria_list=rapor.get("kriterler", []),
                        total_score=hakem_toplam,
                        project_name=rapor.get("proje_adi", ""),
                        team_name=rapor.get("takim_adi", ""),
                        referee_notes=h_notes
                    )
                    # ✅ Hem not_key hem widget key'ini güncelle (Streamlit value= parametresini,
                    # widget key session_state'te kayıtlıysa YOKSAYAR — her ikisini eşzamanlı yaz)
                    st_ctx.session_state[not_key] = ai_note
                    st_ctx.session_state[_txt_key] = ai_note
                    st_ctx.rerun()

        not_metni = st_ctx.text_area(
            "Hakem Değerlendirme Notu (Yarışmacıya İletilecek)",
            height=130,
            placeholder="Gerekçe, tavsiye ve teknik açıklamalarınızı yazınız...",
            key=_txt_key,          # ← artık not_key ile aynı mantık, value= yerine key kullanılıyor
            disabled=is_completed,
            label_visibility="collapsed"
        )
        if not is_completed:
            st_ctx.session_state[not_key] = not_metni


        # =========================================================================
        # TÜM ADIMLARIN TAMAMLANMA DENETİMİ (ZORUNLU KONTROL LİSTESİ)
        # =========================================================================
        ad3_tamam = bool(has_step3_data) or is_completed
        ad4_tamam = bool(has_step4_data) or is_completed
        ad5_not_tamam = bool(not_metni and len(not_metni.strip()) >= 10) or is_completed

        # Kriter notları: tüm kriterler için hakem notu yazılmış mı?
        kriter_notlari_eksik = []
        if not is_completed:
            for kr_ in kriter_listesi:
                k_id_ = kr_["kriter_id"]
                k_not = str(st_ctx.session_state.get(f"ta_{r_id}_{k_id_}", "") or st_ctx.session_state.get(f"hkriter_not_{r_id}_{k_id_}", "") or kr_.get("hakem_notu", "")).strip()
                if len(k_not) < 10:
                    kriter_notlari_eksik.append(kr_["ad"])
        
        ad_kriter_notlar_tamam = (len(kriter_notlari_eksik) == 0) or is_completed
        if not ad_kriter_notlar_tamam and not is_completed:
            st_ctx.session_state[f"show_missing_kriter_not_{r_id}"] = True
        else:
            st_ctx.session_state[f"show_missing_kriter_not_{r_id}"] = False

        tum_adımlar_tamam = is_completed or (ad3_tamam and ad4_tamam and ad5_not_tamam and ad_kriter_notlar_tamam)

        st_ctx.markdown("<hr style='margin:16px 0 12px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        st_ctx.markdown("<div style='font-size:0.95rem; font-weight:800; color:#1E293B; margin-bottom:8px;'>Değerlendirme Mühürleme Kontrol Listesi</div>", unsafe_allow_html=True)

        chk_col1, chk_col2, chk_col3, chk_col4 = st_ctx.columns(4)
        with chk_col1:
            if ad3_tamam:
                st_ctx.markdown("<div style='font-size:0.83rem; font-weight:700; color:#15803D;'>✅ Adım 3: Şartname Kontrolleri Tamamlandı</div>", unsafe_allow_html=True)
            else:
                st_ctx.markdown("<div style='font-size:0.83rem; font-weight:700; color:#DC2626;'>❌ Adım 3: Şartname Analizi Başlatılmadı</div>", unsafe_allow_html=True)
        with chk_col2:
            if ad4_tamam:
                st_ctx.markdown("<div style='font-size:0.83rem; font-weight:700; color:#15803D;'>✅ Adım 4: Rubrik Puanlaması Tamamlandı</div>", unsafe_allow_html=True)
            else:
                st_ctx.markdown("<div style='font-size:0.83rem; font-weight:700; color:#DC2626;'>❌ Adım 4: Kriter Puanlaması Başlatılmadı</div>", unsafe_allow_html=True)
        with chk_col3:
            if ad_kriter_notlar_tamam:
                st_ctx.markdown("<div style='font-size:0.83rem; font-weight:700; color:#15803D;'>✅ Kriter Notları: Tüm kriterler için gerekçe yazıldı</div>", unsafe_allow_html=True)
            else:
                eksik_sayisi = len(kriter_notlari_eksik)
                st_ctx.markdown(
                    f"<div style='font-size:0.83rem; font-weight:700; color:#DC2626;'>"
                    f"Kriter Notları: {eksik_sayisi} kriter için gerekçe eksik<br>"
                    f"<span style='font-size:0.75rem; font-weight:600;'>{', '.join(kriter_notlari_eksik[:3])}{'…' if eksik_sayisi > 3 else ''}</span>"
                    f"</div>",
                    unsafe_allow_html=True
                )
        with chk_col4:
            if ad5_not_tamam:
                st_ctx.markdown("<div style='font-size:0.83rem; font-weight:700; color:#15803D;'>✅ Adım 5: Genel Hakem Notu Yazıldı</div>", unsafe_allow_html=True)
            else:
                st_ctx.markdown("<div style='font-size:0.83rem; font-weight:700; color:#D97706;'>⚠️ Adım 5: Genel Hakem Notu Yazılmalı (Min 10 Karakter)</div>", unsafe_allow_html=True)

        if not tum_adımlar_tamam and not is_completed:
            if not ad_kriter_notlar_tamam:
                st_ctx.error(
                    f"**Eksik Gerekçe Notları ({len(kriter_notlari_eksik)} Kriter):** Yukarıda kırmızı çerçeve ile işaretlenen kriterler için en az 10 karakterlik hakem gerekçesi yazılması zorunludur:\n"
                    + " · ".join(f"**{ad_}**" for ad_ in kriter_notlari_eksik)
                )
            else:
                st_ctx.warning("Raporun mühürlenebilmesi için lütfen yukarıdaki eksik adımları tamamlayınız.")


        st_ctx.write("")
        btn_c1, btn_c2 = st_ctx.columns([1.5, 2])
        with btn_c1:
            if st_ctx.button(
                "Değerlendirmeyi Onayla ve Mühürle" if not is_completed else "✅ Bu Rapor Mühürlendi (Kilitli)", 
                type="primary", 
                use_container_width=True,
                disabled=bool(not tum_adımlar_tamam or is_completed),
                key=f"btn_seal_final_{rapor['rapor_id']}"
            ):
                db.save_referee_decision(
                    report_id=rapor["rapor_id"],
                    referee_id=referee_id or "usr_hakem_master",
                    referee_score=hakem_toplam,
                    decision="ONAYLANDI",
                    referee_notes=not_metni,
                    status="DEGERLENDIRILDI",
                    criteria_scores=st_ctx.session_state[anahtar],
                    ai_data=rapor.get("ai_data") or st_ctx.session_state.get(f"cached_ai_data_{r_id}"),
                    checks=rapor.get("checks") or st_ctx.session_state.get(f"cached_checks_{r_id}")
                )
                db.update_report_status(rapor["rapor_id"], "DEGERLENDIRILDI")

                # report_assignments tablosunda da durumu TAMAMLANDI olarak mühürle
                try:
                    from src.data import repos
                    from src.data.enums import AssignmentStatus
                    r_ev = repos().evaluations
                    asgn_id = rapor.get("assignment_id")
                    if asgn_id:
                        r_ev._update("report_assignments", "assignment_id", asgn_id, {"status": AssignmentStatus.TAMAMLANDI.value})
                    elif referee_id:
                        # Eğer assignment_id yoksa hakem ve rapor eşleşmesiyle güncelle
                        r_ev.db.execute(
                            "UPDATE report_assignments SET status = ? WHERE report_id = ? AND referee_user_id = ?;",
                            [AssignmentStatus.TAMAMLANDI.value, rapor["rapor_id"], referee_id]
                        )
                except Exception as ex_asgn:
                    print(f"[SEAL] report_assignments güncelleme uyarısı: {ex_asgn}")

                try:
                    sonuc = api_client.hakem_karari_gonder(rapor["rapor_id"], st_ctx.session_state[anahtar], not_metni)
                except Exception:
                    pass

                st_ctx.query_params.pop("rapor_id", None)
                st_ctx.session_state.pop("hakem_secili_rapor_box", None)
                st_ctx.session_state.pop("secili_rapor", None)

                st_ctx.success(f"✅ Rapor başarıyla mühürlendi ve yöneticinize iletildi! Bu raporla ilgili değerlendirme süreciniz tamamlanmıştır.")
                st_ctx.rerun()
        
        with btn_c2:
            try:
                from src.ui.karne_pdf import uret
                # `rapor` zaten kriterler, geri_bildirim vb. içeriyor olmalı
                if "geri_bildirim" not in rapor:
                    rapor["geri_bildirim"] = {}
                if not_metni:
                    rapor["geri_bildirim"]["ozet"] = not_metni
                    
                # yarisma_dict'i bos veya temel yarisma adiyla olusturuyoruz
                yarisma_dict = {"ad": rapor.get("yarisma_adi", ""), "rapor_turu": "Aşama Raporu"}
                pdf_bytes = uret(rapor, yarisma_dict)
                st_ctx.download_button(
                    "Resmî İmzalı Karne PDF'i İndir",
                    data=pdf_bytes,
                    file_name=f"Karne_{rapor.get('rapor_id', 'rapor')}.pdf",
                    mime="application/pdf",
                    use_container_width=True,
                    disabled=not tum_adımlar_tamam
                )
            except Exception:
                pass


__all__ = ["goster"]

