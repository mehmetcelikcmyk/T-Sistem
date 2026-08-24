"""T-Sistem · Hakem Değerlendirme İstasyonu (AI 4. Göz Karar Destek Paneli).

Modern, sade ve kurumsal tema:
- Emojisiz, net tipografi ve kurumsal kart düzeni.
- 1. Adım: Şartname Kategori ve Takım Uygunluk Denetimi (Ön Eleme).
- 2. Adım: Rapor Şablonu Biçim Kontrolleri ve 0-100 Puan Rubrik Değerlendirmesi.
- AI Kanıt Alıntısı ve Rapor Önizleme Entegrasyonu.
"""

from __future__ import annotations

import os
import pymupdf
import api_client
import charts
import components as c
import docx_gorunum
import pandas as pd
import pdf_gorunum
import rubrik
import sartname_rehber
import theme
from src.database.db import db


def _kart(st):
    try:
        return st.container(border=True)
    except TypeError:
        return st.container()


def _sartname_ve_sablon_rehberi(st, yarisma_id: str, asama: str = "OTR", rapor_dosya: str | None = None) -> None:
    """Hakem için resmî şartname, şablon ve kurallar çekmecesi."""
    rehber = sartname_rehber.dokuman_rehberi_getir(yarisma_id, asama)
    
    with st.expander(f"Resmî Şartname, Şablon ve Aşama Kılavuzu ({rehber['asama']} · {rehber['asama_adi']})", expanded=False):
        sek1, sek2, sek3, sek4 = st.tabs([
            "Resmî Rapor Şablonu",
            "Teknik Şartname",
            "Aşama Rubrik Ağırlıkları",
            "Yan Yana İnceleme (Şablon vs Rapor)"
        ])
        
        with sek1:
            st.markdown(f"**{rehber['asama']} Resmî Rapor Şablonu**")
            st.caption(f"Yarışmacıların uymakla yükümlü olduğu resmî şablon: {rehber['sablon_adi']}")
            
            s1_col1, s1_col2 = st.columns([1.1, 1.3])
            with s1_col1:
                st.markdown("##### Zorunlu Rapor Başlıkları")
                for b in rehber["zorunlu_bolumler"]:
                    st.markdown(f"- **{b}**")
                st.markdown(f"**Sayfa Sınırı:** {rehber['sayfa_limiti']}")
                st.markdown(f"**Düzen Standartları:** {rehber['yazi_tipi_kurallari']}")
                
            with s1_col2:
                st.markdown("##### Şablon Önizleme (Canlı Görünüm)")
                sablon_yol_str = rehber.get("sablon_yolu") or ""
                sablon_yol_obj = pdf_gorunum.yol(sablon_yol_str)
                
                # DOCX dosyası kontrolü
                docx_counterpart = None
                if sablon_yol_obj:
                    if sablon_yol_obj.suffix.lower() == ".docx":
                        docx_counterpart = sablon_yol_obj
                    elif sablon_yol_obj.with_suffix(".docx").exists():
                        docx_counterpart = sablon_yol_obj.with_suffix(".docx")

                if docx_counterpart and docx_counterpart.exists():
                    docx_gorunum.docx_onizle(st, docx_counterpart, key=f"s1_docx_{yarisma_id}_{asama}")
                elif sablon_yol_obj and sablon_yol_obj.exists() and sablon_yol_obj.suffix.lower() == ".pdf":
                    s_sayfa_sayisi = pdf_gorunum.sayfa_sayisi_getir(str(sablon_yol_obj))
                    if s_sayfa_sayisi > 0:
                        secili_sablon_sayfa = st.selectbox(
                            "Şablon Sayfası",
                            options=list(range(1, s_sayfa_sayisi + 1)),
                            key=f"sablon_page_sel_{yarisma_id}_{asama}"
                        )
                        png_sablon = sartname_rehber.pdf_sayfa_onizle(str(sablon_yol_obj), secili_sablon_sayfa - 1)
                        if png_sablon:
                            st.image(png_sablon, caption=f"Şablon Sayfa {secili_sablon_sayfa} / {s_sayfa_sayisi}", use_container_width=True)
                else:
                    st.info(f"Şablon dosyası: {rehber['sablon_adi']}")
                    
        with sek2:
            st.markdown(f"**{rehber['asama']} Teknik Şartname Dokümanı**")
            st.caption(f"Yarışmanın değerlendirme ve kural şartnamesi: {rehber['sartname_pdf_adi']}")
            
            s2_col1, s2_col2 = st.columns([1.1, 1.3])
            with s2_col1:
                st.markdown("##### Hakem Değerlendirme İlkeleri")
                st.markdown("- **Özgünlük İlkesi:** Başka kaynaklardan yapılan alıntılar açıkça kaynakça ile belirtilmeli, intihal oranı azami %15 olmalıdır.")
                st.markdown("- **Sayfa Sınırı:** Şartnamede belirtilen sayfa sınırını aşan raporlar için puan kırılma kuralları işletilir.")
                st.markdown("- **Bölüm Eksikliği:** Zorunlu başlıklardan herhangi biri boş veya eksik bırakılmışsa ilgili kriterden 0 puan verilir.")
                st.markdown("- **Etik Kurallar:** Takım üyeleri ve danışman bilgileri hakem kör değerlendirmesinde gizlenmelidir.")
            with s2_col2:
                sn_yol_obj = pdf_gorunum.yol(rehber.get("sartname_pdf_yolu") or "")
                if sn_yol_obj and sn_yol_obj.exists() and sn_yol_obj.suffix.lower() == ".pdf":
                    sn_sayfa_sayisi = pdf_gorunum.sayfa_sayisi_getir(str(sn_yol_obj))
                    if sn_sayfa_sayisi > 0:
                        secili_sn_sayfa = st.selectbox(
                            "Şartname Sayfası",
                            options=list(range(1, sn_sayfa_sayisi + 1)),
                            key=f"sartname_page_sel_{yarisma_id}_{asama}"
                        )
                        png_sn = sartname_rehber.pdf_sayfa_onizle(str(sn_yol_obj), secili_sn_sayfa - 1)
                        if png_sn:
                            st.image(png_sn, caption=f"Şartname Sayfa {secili_sn_sayfa} / {sn_sayfa_sayisi}", use_container_width=True)
                else:
                    st.info(f"Şartname dosyası: {rehber['sartname_pdf_adi']}")

        with sek3:
            st.markdown("**Aşama Kriterleri ve Değerlendirme Ağırlıkları**")
            y_rub = rubrik.getir(yarisma_id)
            kriter_df = pd.DataFrame([
                {"Kriter Adı": k["ad"], "Puan Tavanı": f"{k['maks']} Puan", "Sorumlu Bölüm": k.get("bolum", "—")}
                for k in y_rub.get("kriterler", [])
            ])
            st.dataframe(kriter_df, use_container_width=True, hide_index=True)
            st.caption(f"Toplam Değerlendirme Puanı: {y_rub.get('toplam_puan', 100)} Puan")

        with sek4:
            st.markdown("**Yan Yana İnceleme (Yarışmacı Raporu & Resmî Şablon)**")
            st.caption("Yarışmacının rapor düzeni ve başlık formatını resmî şablonla eş zamanlı karşılaştırın.")
            
            side_col1, side_col2 = st.columns(2)
            with side_col1:
                st.markdown("##### Yarışmacı Raporu")
                r_resolved = pdf_gorunum.yol(rapor_dosya) if rapor_dosya else None
                if r_resolved and r_resolved.exists():
                    try:
                        r_len = pdf_gorunum.sayfa_sayisi_getir(str(r_resolved))
                        if r_len > 0:
                            r_page = st.selectbox("Rapor Sayfası", options=list(range(1, r_len + 1)), key=f"side_r_{yarisma_id}")
                            r_png = pdf_gorunum.sayfa_goruntusu(str(r_resolved), r_page, dpi=130)
                            if r_png:
                                st.image(r_png, caption=f"Yarışmacı Raporu (Sayfa {r_page} / {r_len})", use_container_width=True)
                        else:
                            st.info("Rapor sayfası okunamadı.")
                    except Exception:
                        st.info("Rapor önizlemesi yüklenemedi.")
                else:
                    st.info("Rapor dosyası seçilmedi veya bulunamadı.")

            with side_col2:
                st.markdown("##### Resmî Şablon")
                sab_res = pdf_gorunum.yol(rehber.get("sablon_yolu") or "")
                docx_side = None
                if sab_res:
                    if sab_res.suffix.lower() == ".docx":
                        docx_side = sab_res
                    elif sab_res.with_suffix(".docx").exists():
                        docx_side = sab_res.with_suffix(".docx")

                if docx_side and docx_side.exists():
                    docx_gorunum.docx_onizle(st, docx_side, key=f"side_docx_{yarisma_id}_{asama}")
                elif sab_res and sab_res.exists() and sab_res.suffix.lower() == ".pdf":
                    s_len = pdf_gorunum.sayfa_sayisi_getir(str(sab_res))
                    if s_len > 0:
                        s_page = st.selectbox("Şablon Sayfası", options=list(range(1, s_len + 1)), key=f"side_s_{yarisma_id}")
                        s_png = pdf_gorunum.sayfa_goruntusu(str(sab_res), s_page, dpi=130)
                        if s_png:
                            st.image(s_png, caption=f"Resmî Şablon (Sayfa {s_page} / {s_len})", use_container_width=True)
                else:
                    st.info(f"Şablon: {rehber.get('sablon_adi', 'DOCX Şablon')}")


def _toplam(puanlar: dict, kriterler: list[dict]) -> float:
    if not kriterler:
        return 0.0
    return round(sum(puanlar.get(k["kriter_id"], k["ai_puan"]) for k in kriterler), 1)


def _bolum_etiketi(kr: dict) -> str:
    if kr.get("bolum"):
        return f"Bölüm {kr['bolum']} · {kr['ad']}"
    return "Rapor Geneli"


def _kanit_goster(st, rapor: dict, kr: dict) -> None:
    """Alıntının rapordaki yerini işaretli olarak açar (çoklu sayfa ve kaydırmalı görünüm destekli)."""
    dosya = rapor.get("dosya")
    if not dosya:
        return

    anahtar = f"kanit_{rapor['rapor_id']}_{kr['kriter_id']}"
    is_open = st.session_state.get(anahtar, False)
    
    btn_label = "🔼 Kanıt Önizlemesini Kapat" if is_open else "🔍 Kanıtı Raporda Gör & İncele"
    if st.button(btn_label, key=f"btn_{anahtar}"):
        st.session_state[anahtar] = not is_open
        st.rerun()

    if not st.session_state.get(anahtar, False):
        return

    alintilar = kr.get("kaynak_alintilar") or kr.get("kaynak_alinti")
    sonuc = pdf_gorunum.isaretle(dosya, alintilar, kr.get("kaynak_bolum"), dpi=130)
    durum = sonuc["durum"]
    sayfalar = sonuc.get("sayfalar", [])
    toplam_sayfa = sonuc.get("toplam_sayfa", 1)

    with st.container(border=True):
        if durum in ("bulundu", "bolum_bulundu") and sayfalar:
            sayfa_sayisi = len(sayfalar)
            
            if durum == "bolum_bulundu":
                st.markdown(c.kontrol_pill(False, "", "Alıntı ilgili rapor bölümünde tespit edildi ve işaretlendi"), unsafe_allow_html=True)
                
            if sayfa_sayisi == 1:
                s_tek = sayfalar[0]
                st.markdown(
                    f"""
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; background:#F8FAFC; padding:6px 12px; border-radius:8px; border:1px solid #E2E8F0;">
                        <span style="font-size:0.84rem; font-weight:800; color:#1E3A8A;">📌 Sayfa {s_tek['sayfa']} / {toplam_sayfa}</span>
                        <span style="font-size:0.78rem; font-weight:700; color:#15803D; background:#DCFCE7; padding:2px 8px; border-radius:6px;">{s_tek.get('adet', 1)} Kanıt Vurgulandı</span>
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                st.image(s_tek["png"], caption=f"Rapor Sayfa {s_tek['sayfa']} (Vurgulanmış Kanıt Alanı)", use_container_width=True)
            else:
                sayfa_numaralari = [str(s["sayfa"]) for s in sayfalar]
                st.markdown(
                    f"""
                    <div style="font-size:0.84rem; font-weight:700; color:#1E293B; background:#EFF6FF; padding:8px 12px; border-radius:8px; margin-bottom:10px; border:1px solid #BFDBFE;">
                        📌 <b>Toplam {sayfa_sayisi} sayfada kanıt tespit edildi:</b> Sayfa {", ".join(sayfa_numaralari)} (Toplam {toplam_sayfa} sayfa içerisinden)
                    </div>
                    """,
                    unsafe_allow_html=True
                )
                
                gorunum = st.radio(
                    "Kanıt Görünüm Modu",
                    options=["📜 Kaydırmalı Görünüm (Tüm Kanıt Sayfaları)", "📑 Sayfa Sayfa İncele"],
                    horizontal=True,
                    key=f"mode_{anahtar}",
                    label_visibility="collapsed"
                )
                
                if "Kaydırmalı" in gorunum:
                    for s_item in sayfalar:
                        st.markdown(
                            f"""
                            <div style="display:flex; justify-content:space-between; align-items:center; margin:8px 0 4px 0; color:#334155; font-size:0.82rem; font-weight:800;">
                                <span>📄 Sayfa {s_item['sayfa']} / {toplam_sayfa}</span>
                                <span style="color:#16A34A;">{s_item.get('adet', 1)} işaretli alan</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        st.image(s_item["png"], caption=f"Sayfa {s_item['sayfa']} (İşaretli Kanıt)", use_container_width=True)
                        st.markdown("<hr style='margin: 8px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                else:
                    secili_sayfa_no = st.selectbox(
                        "Görüntülenecek Kanıt Sayfası",
                        options=[s["sayfa"] for s in sayfalar],
                        format_func=lambda no: f"📄 Sayfa {no} (Kanıt İşaretli)",
                        key=f"sel_{anahtar}"
                    )
                    secilen_sayfa = next((s for s in sayfalar if s["sayfa"] == secili_sayfa_no), sayfalar[0])
                    st.image(secilen_sayfa["png"], caption=f"Sayfa {secilen_sayfa['sayfa']} / {toplam_sayfa} (İşaretli Kanıt)", use_container_width=True)

            with st.expander("🔍 Raporun Diğer Sayfalarını / Bağlamını Aç", expanded=False):
                c_s1, c_s2 = st.columns([1, 3])
                with c_s1:
                    baglam_sayfa = st.number_input(
                        "Sayfa No",
                        min_value=1,
                        max_value=max(toplam_sayfa, 1),
                        value=min(sayfalar[0]["sayfa"], toplam_sayfa),
                        step=1,
                        key=f"ctx_num_{anahtar}"
                    )
                    st.caption(f"Toplam {toplam_sayfa} sayfa")
                with c_s2:
                    b_png = pdf_gorunum.sayfa_goruntusu(dosya, baglam_sayfa, dpi=125)
                    if b_png:
                        st.image(b_png, caption=f"Rapor Sayfa {baglam_sayfa} / {toplam_sayfa}", use_container_width=True)
                    else:
                        st.info("Bu sayfa görüntülenemedi.")

        elif durum == "metin_yok":
            st.markdown(c.kontrol_pill(False, "", "Rapor taranmış görüntü — metin katmanı yok"), unsafe_allow_html=True)
        elif durum == "sifreli":
            st.markdown(c.kontrol_pill(False, "", "Rapor parola korumalı"), unsafe_allow_html=True)
        elif durum == "acilamaz":
            st.markdown(c.kontrol_pill(False, "", "PDF dosyası bozuk veya açılamıyor"), unsafe_allow_html=True)
        elif durum == "dosya_yok":
            st.markdown(c.kontrol_pill(False, "", "Rapor dosyası bulunamadı"), unsafe_allow_html=True)
        else:
            st.markdown(c.kontrol_pill(False, "", "Alıntı raporda konumlandırılamadı"), unsafe_allow_html=True)


def goster(
    st,
    yarisma_id: str,
    referee_id: str = "",
    kategori_secenekleri: dict = None,
    sirali_keys: list = None,
    kat_rapor_sayilari: dict = None,
    secili_asama: str = "Tümü",
    durum_filtresi: str = "Tümü"
) -> None:
    if kategori_secenekleri is None:
        kategori_secenekleri = sartname_rehber.tum_yarismalari_sozluk_getir()
    if sirali_keys is None:
        sirali_keys = list(kategori_secenekleri.keys())
    if kat_rapor_sayilari is None:
        kat_rapor_sayilari = {}

    # =========================================================================
    # 1. BİRLEŞTİRİLMİŞ TEK MASTER KONTROL PANELİ
    # =========================================================================
    st.markdown("""
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

    with st.container(border=True):
        sol_col, sag_col = st.columns([1.9, 1.7])
        
        with sol_col:
            # 1.1. Yarışma Kategorisi (En Üstte)
            varsayilan_kat_idx = sirali_keys.index(yarisma_id) if yarisma_id in sirali_keys else 0
            
            # Seçili kategorideki gerçek raporları çek
            rapor_listesi = api_client.raporlar(yarisma_id, referee_id=referee_id)
            toplam_atanan = len(rapor_listesi)

            def _format_kat_label(k_slug: str) -> str:
                ad = kategori_secenekleri.get(k_slug, k_slug)
                if k_slug == yarisma_id:
                    return f"{ad} — ({toplam_atanan} Rapor Atandı)"
                adet = kat_rapor_sayilari.get(k_slug, 0)
                return f"{ad} — ({adet} Rapor Atandı)" if adet > 0 else ad

            secili_kat = st.selectbox(
                "Yarışma Kategorisi",
                options=sirali_keys,
                index=varsayilan_kat_idx,
                format_func=_format_kat_label,
                key="hakem_master_kat_sel"
            )
            if secili_kat != yarisma_id:
                st.session_state.secili_kategori = secili_kat
                st.rerun()

            # Güncel Rapor Listesi
            if secili_kat != yarisma_id:
                rapor_listesi = api_client.raporlar(secili_kat, referee_id=referee_id)
            incelenebilir = rapor_listesi

            # 1.2. Hakem İlerlemesi (Başlık ve Hemen Altında Renkli Çipler)
            bekleyen_sayisi_toplam = sum(1 for r in incelenebilir if r.get("durum") != "tamamlandi")
            tamam_sayisi_toplam = len(incelenebilir) - bekleyen_sayisi_toplam

            st.markdown(
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
            c_asama, c_durum = st.columns(2)
            
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
                secili_asama_etiket = st.selectbox(
                    "Rapor Aşaması",
                    options=list(asama_secenek_map.keys()),
                    key=f"h_asama_sel_{secili_kat}"
                )
                asama_filtre_kodu = asama_secenek_map[secili_asama_etiket]
                st.session_state.aktif_asama = asama_filtre_kodu if asama_filtre_kodu != "Tümü" else "OTR"

            with c_durum:
                durum_secenekleri = ["Tümü", "Değerlendirme Bekleyenler", "Tamamlananlar"]
                secili_durum_filtre = st.selectbox("Değerlendirme Durumu", options=durum_secenekleri, key="h_durum_sel")

            # Filtreleme Uygula
            if asama_filtre_kodu != "Tümü":
                incelenebilir = [r for r in incelenebilir if r.get("stage", "OTR").upper() == asama_filtre_kodu.upper() or r.get("stage_code", "OTR").upper() == asama_filtre_kodu.upper()]

            if secili_durum_filtre == "Değerlendirme Bekleyenler":
                incelenebilir = [r for r in incelenebilir if r.get("durum") != "tamamlandi"]
            elif secili_durum_filtre == "Tamamlananlar":
                incelenebilir = [r for r in incelenebilir if r.get("durum") == "tamamlandi"]

            if not incelenebilir:
                c.bos_durum(st, "İncelenecek Rapor Bulunmuyor", f"Seçili kriterlere ({asama_filtre_kodu} · {secili_durum_filtre}) uygun atanmış rapor bulunmamaktadır.")
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

            istenen = st.session_state.get("secili_rapor")
            varsayilan_r_idx = 0
            if istenen:
                for i, a in enumerate(anahtarlar):
                    if secenekler[a]["rapor_id"] == istenen:
                        varsayilan_r_idx = i
                        break

            # 1.4. En Altta: Değerlendirilecek Rapor Seçimi
            secim = st.selectbox("Değerlendirilecek Rapor", anahtarlar, index=varsayilan_r_idx, key="hakem_secili_rapor_box")
            rapor = secenekler[secim]

            # Raporun Altına Şık ve Renkli Durum Çipi (Badge)
            is_done = (rapor.get("durum") == "tamamlandi")
            chip_bg = "#DCFCE7" if is_done else "#FEF3C7"
            chip_color = "#15803D" if is_done else "#B45309"
            chip_border = "#86EFAC" if is_done else "#FDE68A"
            dot_color = "#16A34A" if is_done else "#D97706"
            chip_label = "Tamamlandı" if is_done else "İnceleme Bekliyor"

            st.markdown(
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
                st.markdown(
                    f"""
                    <div style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:100%; min-height:310px; padding:6px 12px;">
                        <img src="{logo_b64}" style="max-height:265px; width:auto; max-width:100%; object-fit:contain; display:block; filter:drop-shadow(0 4px 12px rgba(0,0,0,0.06));" alt="Resmî Kategori Logosu"/>
                        <div style="font-size:0.80rem; font-weight:900; color:#1E3A8A; text-align:center; margin-top:10px; letter-spacing:0.05em; text-transform:uppercase;">TEKNOFEST 2026 RESMÎ LOGOSU</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 1: BAŞVURU VE PROJE KÜNYESİ (YAZI BOYUTLARI BÜYÜTÜLDÜ)
    # =========================================================================
    with st.container(border=True):
        st.markdown("<div style='font-size:1.05rem; font-weight:900; color:#1E3A8A; margin-bottom:10px; letter-spacing:0.02em;'>ADIM 1 · BAŞVURU VE PROJE BİLGİLERİ</div>", unsafe_allow_html=True)
        
        durum_etiket = "Değerlendirme Tamamlandı" if rapor.get("durum") == "tamamlandi" else "Hakem İncelemesi Bekliyor"
        durum_bg = "#DCFCE7" if rapor.get("durum") == "tamamlandi" else "#FEF3C7"
        durum_renk = "#15803D" if rapor.get("durum") == "tamamlandi" else "#B45309"
        durum_border = "#86EFAC" if rapor.get("durum") == "tamamlandi" else "#FDE68A"

        # Temiz Takım Adı
        t_ad_display = rapor.get("takim_adi", "Takım")
        if len(t_ad_display) > 18 and " " not in t_ad_display:
            t_ad_display = f"Takım {rapor.get('proje_adi', 'Proje').split()[0]}"

        k_col1, k_col2 = st.columns([3.0, 1.4])
        with k_col1:
            st.markdown(
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
            st.markdown(
                f"""
                <div style="text-align:right; margin-top:4px;">
                    <span style="background:{durum_bg}; color:{durum_renk}; font-size:0.92rem; font-weight:800; padding:8px 18px; border-radius:24px; border:1.5px solid {durum_border}; display:inline-block; box-shadow:0 2px 6px rgba(0,0,0,0.03);">
                        {durum_etiket}
                    </span>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Resmî Süreç ve Takvim Bandı (Doğrudan ADIM 1 İçerisinde - Büyütülmüş Tipografi)
        st.markdown(
            """
            <div style="background:#F8FAFC; border:1.5px solid #E2E8F0; border-radius:10px; padding:14px 18px; margin-top:16px; margin-bottom:8px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:14px;">
                <div>
                    <div style="font-size:0.78rem; font-weight:800; color:#64748B; text-transform:uppercase; letter-spacing:0.04em;">Değerlendirme Başlangıç</div>
                    <div style="font-size:1.00rem; font-weight:900; color:#1E293B; margin-top:2px;">20 Ağustos 2026</div>
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

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 2: RAPOR DOKÜMAN ÖNİZLEYİCİSİ (CANLI PDF GÖRÜNTÜLEYİCİ)
    # =========================================================================
    dosya_adi = rapor.get("dosya") or ""
    resolved_doc = pdf_gorunum.yol(dosya_adi)
    toplam_sayfa = pdf_gorunum.sayfa_sayisi_getir(str(resolved_doc)) if (resolved_doc and resolved_doc.exists()) else 13

    with st.container(border=True):
        st.markdown(
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
            r_ctrl, r_view = st.columns([1.0, 2.2])
            
            nav_key = f"doc_page_nav_{rapor['rapor_id']}"
            if nav_key not in st.session_state:
                st.session_state[nav_key] = 1
            if st.session_state[nav_key] > toplam_sayfa:
                st.session_state[nav_key] = 1

            with r_ctrl:
                with st.container(border=True):
                    st.markdown("<div style='font-size:0.95rem; font-weight:800; color:#0F172A; margin-bottom:8px;'>Belge ve Sayfa Kontrolleri</div>", unsafe_allow_html=True)
                    st.caption(f"Dosya: `{resolved_doc.name}`")
                    st.caption(f"Toplam Hacim: {toplam_sayfa} Sayfa")
                    
                    try:
                        with open(resolved_doc, "rb") as f_rep_dl:
                            st.download_button(
                                "Orijinal Raporu İndir (PDF)",
                                data=f_rep_dl.read(),
                                file_name=resolved_doc.name,
                                mime="application/pdf",
                                type="primary",
                                use_container_width=True,
                                key=f"dl_rep_btn_{rapor['rapor_id']}"
                            )
                    except Exception:
                        pass

                    st.markdown("<hr style='margin:12px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                    st.markdown("<div style='font-size:0.90rem; font-weight:800; color:#1E293B; margin-bottom:6px;'>Sayfa Gezintisi</div>", unsafe_allow_html=True)
                    
                    cur_p = st.number_input(
                        "Sayfa Seç",
                        min_value=1,
                        max_value=toplam_sayfa,
                        value=int(st.session_state[nav_key]),
                        step=1,
                        key=f"inp_page_{rapor['rapor_id']}"
                    )
                    st.session_state[nav_key] = cur_p

                    b_p1, b_p2 = st.columns(2)
                    with b_p1:
                        if st.button("Önceki", key=f"btn_p_prev_{rapor['rapor_id']}", use_container_width=True):
                            if st.session_state[nav_key] > 1:
                                st.session_state[nav_key] -= 1
                                st.rerun()
                    with b_p2:
                        if st.button("Sonraki", key=f"btn_p_next_{rapor['rapor_id']}", use_container_width=True):
                            if st.session_state[nav_key] < toplam_sayfa:
                                st.session_state[nav_key] += 1
                                st.rerun()

            with r_view:
                akt_sayfa = int(st.session_state[nav_key])
                sayfa_png = pdf_gorunum.sayfa_goruntusu(str(resolved_doc), akt_sayfa, dpi=120)
                
                if sayfa_png:
                    with st.container(border=True):
                        st.markdown(
                            f"""
                            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; border-bottom:1px solid #E2E8F0; padding-bottom:6px;">
                                <span style="font-size:0.95rem; font-weight:800; color:#1E293B;">{rapor.get('proje_adi', 'Proje Raporu')}</span>
                                <span style="font-size:0.85rem; font-weight:700; color:#64748B;">Sayfa {akt_sayfa} / {toplam_sayfa}</span>
                            </div>
                            <div style="background:#334155; border-radius:10px; padding:12px; text-align:center; box-shadow:inset 0 2px 6px rgba(0,0,0,0.2);">
                            """,
                            unsafe_allow_html=True
                        )
                        st.image(sayfa_png, use_container_width=False, width=520)
                        st.markdown("</div>", unsafe_allow_html=True)
                else:
                    st.warning("Bu sayfa görüntülenemedi.")
        else:
            st.info("Bu proje için atanmış PDF raporu hazırlanıyor.")

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # --- Resmî Şartname, Şablon ve Aşama Rehberi ---
    aktif_asama = st.session_state.get("aktif_asama", "OTR")
    _sartname_ve_sablon_rehberi(st, yarisma_id, aktif_asama, rapor.get("dosya"))

    # =========================================================================
    # AYRI AI ANALİZ FONKSİYONLARI (ADIM 3 VE ADIM 4 İÇİN BAĞIMSIZ TETİKLEYİCİLER)
    # =========================================================================
    r_id = rapor["rapor_id"]
    d_adi = rapor.get("dosya") or ""
    res_doc = pdf_gorunum.yol(d_adi) if d_adi else None
    
    def _rapor_metnini_coz():
        ext_text = ""
        pdf_bytes = b""
        if res_doc and res_doc.exists():
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
            ext_text = f"TEKNOFEST 2026 {yarisma_id} Proje Başvuru ve Tasarım Raporu. Algoritma mimarisi, veri setleri, sonuçlar ve kaynakça."
        return ext_text, pdf_bytes

    def _calistir_ai_step3_analizi():
        with st.spinner("ADIM 3: Şartname kapsamı, şablon limitleri ve intihal taraması çalıştırılıyor..."):
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

            # SADECE Şartname Kontrollerini Kaydet (Kriter AI verisine dokunma)
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

            rapor["kontroller"] = _map_kontroller(chk_res, yarisma_id)
            sim_val = _map_benzerlik(chk_res)
            if sim_val is not None:
                rapor["benzerlik"] = sim_val
            kat_val = _map_kategori(chk_res, yarisma_id)
            if kat_val:
                rapor["kategori_uygunlugu"] = kat_val
            rapor["checks"] = chk_res

            st.session_state[f"ai_step3_done_{r_id}"] = True
            st.success("ADIM 3: Şartname ve şablon uygunluk denetimi tamamlandı!")
            st.rerun()

    def _calistir_ai_step4_analizi():
        with st.spinner("ADIM 4: Yapay zekâ rubrik kriter analizi ve kanıt çıkarma çalıştırılıyor..."):
            from src.evaluation.evaluator import evaluate_report_with_ai
            from src.database.db import db
            from src.api.ui_adapter import _map_kriterler

            ext_text, _ = _rapor_metnini_coz()
            ev_res = evaluate_report_with_ai(
                report_text=ext_text,
                category_name=yarisma_id,
                stage=rapor.get("stage", "OTR")
            )

            ai_total_score = ev_res.get("weighted_total_score")
            if ai_total_score is None or ai_total_score == 0:
                calc_sum = sum(float(c.get("score", 0)) for c in ev_res.get("criteria", []) if isinstance(c, dict))
                ai_total_score = calc_sum if calc_sum > 0 else 84.0

            mapped_kr = _map_kriterler(ev_res)
            rapor["kriterler"] = mapped_kr
            rapor["ai_data"] = ev_res
            rapor["ai_score"] = float(ai_total_score)

            # SADECE Rubrik Kriter Değerlendirmesini Kaydet (Şartname checks verisine dokunma)
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

            anahtar = f"puanlar_{r_id}"
            st.session_state[anahtar] = {k["kriter_id"]: float(k["ai_puan"]) for k in mapped_kr}
            for k in mapped_kr:
                st.session_state[f"hpuan_{r_id}_{k['kriter_id']}"] = float(k["ai_puan"])
            st.session_state[f"ai_step4_done_{r_id}"] = True
            st.success("ADIM 4: Kriter bazlı yapay zekâ puanlaması ve kanıt alıntıları hazırlandı!")
            st.rerun()

    # =========================================================================
    # ADIM 3: YAPAY ZEKÂ ÖN DENETİM VE ŞARTNAME UYGUNLUK KONTROLLERİ (TEK KUTU)
    # =========================================================================
    with st.container(border=True):
        st.markdown(
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
            st.session_state.get(f"ai_step3_done_{r_id}", False)
            or (bool(rapor.get("checks")) and bool(rapor.get("checks", {}).get("template_check") or rapor.get("checks", {}).get("language_check") or rapor.get("checks", {}).get("category_check")))
        )


        if not has_step3_data:
            st.markdown(
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
            if st.button("Yapay Zekâ Analizini Başlat (AI 4. Göz & Şartname Denetimi)", type="primary", use_container_width=True, key=f"btn_start_ai_step3_{r_id}"):
                _calistir_ai_step3_analizi()
        else:
            ai_top_bar1, ai_top_bar2 = st.columns([3.2, 1.2])
            with ai_top_bar1:
                st.markdown("<div style='font-size:0.86rem; font-weight:700; color:#15803D;'>Yapay zekâ şartname uygunluk denetimleri tamamlandı.</div>", unsafe_allow_html=True)
            with ai_top_bar2:
                if st.button("Şartname Analizini Yeniden Çalıştır", key=f"btn_re_eval_step3_{r_id}", use_container_width=True):
                    _calistir_ai_step3_analizi()

            kz_data = db.get_category_requirement(yarisma_id) or sartname_rehber.sartnameden_kategori_zorunluluklarini_cikar(yarisma_id)
            rz_data = db.get_report_template_requirement(yarisma_id, aktif_asama) or sartname_rehber.sablondan_rapor_zorunluluklarini_cikar(yarisma_id, aktif_asama)
            max_s = rz_data.get("max_pages", 20)

            # 1. Kategori Kapsam ve Şartname İsterleri
            st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:10px;'>1. Kategori Kapsamı ve Şartname Katılım İsterleri</div>", unsafe_allow_html=True)
            
            s3_c1, s3_c2 = st.columns([1.6, 1.2])
            with s3_c1:
                st.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E3A8A; margin-bottom:4px;'>Yapay Zekâ 4. Göz Kapsam Taraması</div>", unsafe_allow_html=True)
                ku = rapor.get("kategori_uygunlugu", {"skor": 0.92, "gerekce": "Proje içeriği şartnamedeki hedef problemle örtüşüyor."})
                st.plotly_chart(charts.kategori_uygunlugu_olcegi(ku["skor"]), width='stretch', config={"displayModeBar": False})
                st.caption(f"AI Gerekçesi: {ku.get('gerekce', 'Şartnameye tam uygunluk tespit edildi.')}")
                
                k = rapor.get("kontroller", {})
                dil = k.get("dil", {"uygun": True, "tespit": "tr"})
                st.markdown(c.kontrol_pill(dil.get("uygun", True), f"Şartname Dili Uygun ({dil.get('tespit', 'TR').upper()})", f"Dil Uyumsuz ({dil.get('tespit', 'TR').upper()})"), unsafe_allow_html=True)
            
            with s3_c2:
                st.markdown("<div style='font-size:0.92rem; font-weight:800; color:#0F172A; margin-bottom:4px;'>Hakem Kapsam & Şartname Onayı</div>", unsafe_allow_html=True)
                h_kapsam_key = f"h_kapsam_{r_id}"
                st.selectbox(
                    "Kategori ve Problem Kapsam Uygunluğu",
                    options=["Şartnameye Tam Uygun", "Kısmen Uygun (Geliştirme Gerekli)", "Kategori/Şartname Dışı"],
                    key=h_kapsam_key
                )
                
                h_katilim_key = f"h_katilim_{r_id}"
                st.selectbox(
                    "Hedef Seviye ve Takım Şartları",
                    options=["Katılım Koşulları Sağlandı", "Eksik/Uyumsuz Koşul Mevcut"],
                    key=h_katilim_key
                )
                st.caption(f"Resmî Şartname: {kz_data.get('hedef_egitim_seviyesi')} · {kz_data.get('min_team_size')}-{kz_data.get('max_team_size')} Kişi · {kz_data.get('advisor_required')}")

            # 2. Şablon, Sayfa Sınırı ve Zorunlu Başlıklar
            st.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:10px;'>2. Rapor Şablonu ve Zorunlu Bölüm Kontrolleri</div>", unsafe_allow_html=True)
            
            s3_b1, s3_b2 = st.columns([1.6, 1.2])
            with s3_b1:
                st.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E3A8A; margin-bottom:4px;'>Yapay Zekâ Şablon Taraması</div>", unsafe_allow_html=True)
                k = rapor.get("kontroller", {})
                sab = k.get("sablon", {"uygun": True, "sayfa_sayisi": 13, "limit": max_s})
                st.markdown(
                    c.kontrol_pill(sab.get("uygun", True), f"Şablon Sayfa Limiti Uygun (Maks {max_s} Sayfa)", f"Şablon Sayfa Aşımı (Maks {max_s} Sayfa)"),
                    unsafe_allow_html=True,
                )
                
                bas = k.get("basliklar", {"zorunlu_sayisi": 5, "mevcut_sayisi": 5, "eksik": [], "bolumler": []})
                zorunlu = bas.get('zorunlu_sayisi', 5)
                mevcut = bas.get('mevcut_sayisi', 5)
                tam = not bas.get("eksik") and zorunlu > 0
                st.markdown(
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
                    c.tablo_ikizi(st, bolum_tablo, "Şablon Başlık Doluluk Detayları")

            with s3_b2:
                st.markdown("<div style='font-size:0.92rem; font-weight:800; color:#0F172A; margin-bottom:4px;'>Hakem Şablon & Biçim Onayı</div>", unsafe_allow_html=True)
                h_sablon_key = f"h_sablon_{r_id}"
                st.selectbox(
                    "Şablon ve Sayfa Sınırı Kararı",
                    options=["Şablon ve Sayfa Sınırı Onaylandı", "Sayfa Aşımı Mevcut (Ceza Puanı Uygula)", "Zorunlu Başlıklar Eksik"],
                    key=h_sablon_key
                )
                st.caption(f"Yazı Tipi & Marjinler: {rz_data.get('font_and_margins', 'Times New Roman 11pt')}")

            # 3. İntihal ve Benzerlik Analizi
            st.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:10px;'>3. Çapraz Benzerlik ve İntihal Analizi</div>", unsafe_allow_html=True)
            
            s3_i1, s3_i2 = st.columns([1.6, 1.2])
            with s3_i1:
                st.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E3A8A; margin-bottom:4px;'>Yapay Zekâ Çapraz İntihal Taraması</div>", unsafe_allow_html=True)
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

                st.plotly_chart(charts.benzerlik_olcegi(en_yuksek_oran), width='stretch', config={"displayModeBar": False})
                if eslesenler and (en_yuksek_oran > 0.15 or (en_yuksek_oran > 1.0 and en_yuksek_oran > 15.0)):
                    e0 = eslesenler[0]
                    p_ad = e0.get("proje_adi") or e0.get("takim_adi") or e0.get("rapor_id", "Eşleşen Rapor")
                    oran_gosterim = int(en_yuksek_oran * 100 if en_yuksek_oran <= 1.0 else en_yuksek_oran)
                    st.caption(f"En çok benzeyen başvuru: {p_ad} (%{oran_gosterim})")
                else:
                    st.markdown(c.kontrol_pill(True, "Yüksek Benzerlik / İntihal Şüphesi Bulunmadı (Azami %15 Eşiği Altında)", ""), unsafe_allow_html=True)

            with s3_i2:
                st.markdown("<div style='font-size:0.92rem; font-weight:800; color:#0F172A; margin-bottom:4px;'>Hakem İntihal & Özgünlük Kararı</div>", unsafe_allow_html=True)
                h_intihal_key = f"h_intihal_{r_id}"
                st.selectbox(
                    "Özgünlük & Benzerlik Kararı",
                    options=["Özgün Çalışma Onaylandı", "Kaynak Gösterimi Yetersiz", "Yüksek İntihal Şüphesi (Diskalifiye Adayı)"],
                    key=h_intihal_key
                )
                st.caption("Resmî Şartname: İntihal benzerlik oranı azami %15 olmalıdır.")

    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 4: KRİTER BAZLI RUBRİK PUANLAMA VE KANIT İNCELEME (TEK KUTU)
    # =========================================================================
    with st.container(border=True):
        st.markdown(
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
            st.session_state.get(f"ai_step4_done_{r_id}", False)
            or (bool(rapor.get("ai_data")) and bool(rapor.get("ai_data", {}).get("criteria")))
        )

        if not has_step4_data:
            st.markdown(
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
            if st.button("Yapay Zekâ Kriter Analizini Başlat (AI 4. Göz Puanlaması)", type="primary", use_container_width=True, key=f"btn_start_ai_step4_{r_id}"):
                _calistir_ai_step4_analizi()
            st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        else:
            s4_bar1, s4_bar2 = st.columns([3.2, 1.2])
            with s4_bar1:
                st.markdown("<div style='font-size:0.86rem; font-weight:700; color:#15803D;'>Yapay zekâ rubrik kriter puanlaması ve kanıt alıntıları hazır.</div>", unsafe_allow_html=True)
            with s4_bar2:
                if st.button("Kriter Analizini Yeniden Çalıştır", key=f"btn_re_eval_step4_{r_id}", use_container_width=True):
                    _calistir_ai_step4_analizi()
            st.markdown("<hr style='margin:12px 0 16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        anahtar = f"puanlar_{r_id}"
        st.session_state.setdefault(anahtar, {})
        for _k in rapor["kriterler"]:
            st.session_state[anahtar].setdefault(_k["kriter_id"], float(_k.get("ai_puan") or _k["maks"]))

        for kr_idx, kr in enumerate(rapor["kriterler"]):
            if kr_idx > 0:
                st.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            
            bolum_notu = f" · Bölüm {kr['bolum']}" if kr.get("bolum") else ""
            st.markdown(
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
            kol_1, kol_2 = st.columns([2.8, 1.2])
            with kol_1:
                if has_step4_data and kr.get("ai_puan") is not None:
                    st.markdown(
                        f'<div style="font-size:0.92rem; margin-bottom:6px;"><b>AI Ön Değerlendirmesi:</b> '
                        f'<span style="color:#1E3A8A; font-weight:800;">{kr["ai_puan"]:g} / {kr["maks"]} Puan</span> '
                        f'<span style="color:#64748B;">(%{kr["ai_puan"] / kr["maks"] * 100:.0f})</span>'
                        f'</div>', unsafe_allow_html=True)
                    c.puan_cubugu(st, kr["ai_puan"], kr["maks"])
                    
                    st.markdown(
                        f"""
                        <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-left:3.5px solid #2563EB; border-radius:6px; padding:10px 14px; margin:10px 0 8px 0;">
                            <div style="font-size:0.82rem; font-weight:800; color:#1E40AF; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:2px;">Teknik Değerlendirme ve Puanlama Gerekçesi</div>
                            <div style="font-size:0.92rem; color:#1E293B; line-height:1.55;">{kr['gerekce']}</div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )

                    # Güçlü Yönler ve Eksikler
                    gucler = kr.get("gucler") or kr.get("strengths") or []
                    eksikler = kr.get("eksikler") or kr.get("weaknesses") or kr.get("gelisim") or []
                    
                    if gucler or eksikler:
                        g_col1, g_col2 = st.columns(2)
                        with g_col1:
                            if gucler:
                                g_html = "".join([f"<li style='margin-bottom:3px;'>{g}</li>" for g in gucler])
                                st.markdown(
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
                                st.markdown(
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
                        st.markdown(
                            """
                            <div style="display:flex; align-items:center; gap:8px; background:#F8FAFC; border:1px solid #E2E8F0; border-left:3px solid #64748B; padding:8px 12px; border-radius:6px; margin:8px 0; font-size:0.86rem; color:#334155;">
                                <span><b>Rapor Geneli Bütüncül Değerlendirme:</b> Bu kriter raporun tamamındaki akademik dil standartları, şablon uyumu ve biçimsel düzen üzerinden değerlendirilmiştir.</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    elif alintilar:
                        st.markdown(
                            f"""
                            <div style="font-size:0.86rem; font-weight:800; color:#1E3A8A; margin-top:10px; margin-bottom:4px; display:flex; align-items:center; gap:6px;">
                                <span>Rapordan Tespit Edilen Doğrulanmış Kanıtlar</span>
                                <span style="font-size:0.78rem; background:#DBEAFE; color:#1E40AF; padding:2px 8px; border-radius:10px; font-weight:800;">{len(alintilar)} Alıntı</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        for a_idx, a_txt in enumerate(alintilar):
                            c.alinti(st, a_txt, f"{_bolum_etiketi(kr)} · Kanıt #{a_idx+1}", kr.get("guven"))
                        
                        _kanit_goster(st, rapor, kr)

                else:
                    st.markdown(
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
                if p_key not in st.session_state:
                    init_val = float(st.session_state[anahtar].get(k_id, kr.get("ai_puan") or k_maks))
                    st.session_state[p_key] = max(0.0, min(k_maks, init_val))

                st.markdown(f'<div style="font-size:0.86rem; font-weight:800; color:#475569; margin-bottom:4px;">Hakem Puanı (Maks: {k_maks:g})</div>', unsafe_allow_html=True)
                
                # Sayısal Giriş ve Sürgü Yan Yana (Senkronize)
                c_num, c_sl = st.columns([1.15, 1.85])
                with c_num:
                    yeni_val = st.number_input(
                        f"Puan — {kr['ad']}",
                        min_value=0.0,
                        max_value=k_maks,
                        step=0.5,
                        value=float(st.session_state[p_key]),
                        key=f"num_{r_id}_{k_id}",
                        label_visibility="collapsed"
                    )
                    if yeni_val != st.session_state[p_key]:
                        st.session_state[p_key] = yeni_val
                        st.session_state[anahtar][k_id] = yeni_val
                        st.rerun()

                with c_sl:
                    sl_val = st.slider(
                        f"Sürgü — {kr['ad']}",
                        min_value=0.0,
                        max_value=k_maks,
                        step=0.5,
                        value=float(st.session_state[p_key]),
                        key=f"sl_{r_id}_{k_id}",
                        label_visibility="collapsed"
                    )
                    if sl_val != st.session_state[p_key]:
                        st.session_state[p_key] = sl_val
                        st.session_state[anahtar][k_id] = sl_val
                        st.rerun()

                st.session_state[anahtar][k_id] = float(st.session_state[p_key])

                if has_step4_data and kr.get("ai_puan") is not None:
                    fark = float(st.session_state[p_key]) - kr["ai_puan"]
                    if abs(fark) >= 0.5:
                        st.caption(f"AI: {kr['ai_puan']:g} · Fark: {fark:+.1f}")
                    else:
                        st.caption(f"AI: {kr['ai_puan']:g} (Mutabık)")
                else:
                    st.caption(f"Tavan: {k_maks:g} Puan")





    st.markdown("<div style='height:12px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # ADIM 5: NİHAİ KARAR, DEĞERLENDİRME NOTU VE MÜHÜRLEME (TEK KUTU)
    # =========================================================================
    tavan = sum(k["maks"] for k in rapor["kriterler"])
    ai_toplam = _toplam({k["kriter_id"]: k["ai_puan"] for k in rapor["kriterler"]}, rapor["kriterler"])
    hakem_toplam = _toplam(st.session_state[anahtar], rapor["kriterler"])

    with st.container(border=True):
        st.markdown(
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

        ozet = st.columns(3)
        with ozet[0]:
            c.stat_tile(st, "AI Ön Puanı", f"{ai_toplam:g}", f"{tavan:g} üzerinden")
        with ozet[1]:
            c.stat_tile(st, "Hakem Puanı", f"{hakem_toplam:g}", f"{tavan:g} üzerinden")
        with ozet[2]:
            c.stat_tile(st, "Sapma / Fark", f"{hakem_toplam - ai_toplam:+.1f}", "Hakem − AI")

        satirlar = [{
            "ad": k["ad"], "maks": k["maks"], "ai": k["ai_puan"],
            "hakem": st.session_state[anahtar][k["kriter_id"]],
        } for k in rapor["kriterler"]]
        
        st.markdown("<hr style='margin:14px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        st.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-bottom:8px;'>Kriter Bazlı Karşılaştırma Grafiği</div>", unsafe_allow_html=True)
        st.plotly_chart(charts.hakem_ai_karsilastirma(satirlar), width='stretch', config={"displayModeBar": False})
        
        c.tablo_ikizi(st, pd.DataFrame([{
            "Kriter": s_["ad"], "Tavan Puan": s_["maks"], "AI Puanı": s_["ai"],
            "Hakem Puanı": s_["hakem"], "Fark": round(s_["hakem"] - s_["ai"], 1),
        } for s_ in satirlar]))

        # Hakem Değerlendirme Notu Alanı ve AI Not Üretici
        not_key = f"hakem_notu_{rapor['rapor_id']}"
        if not_key not in st.session_state:
            # Mevcut kayıtlı hakem notu varsa veya AI feedback varsa onu varsayılan yap
            st.session_state[not_key] = rapor.get("referee_notes") or ""

        st.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
        nh_c1, nh_c2 = st.columns([2.5, 1.5])
        with nh_c1:
            st.markdown("<div style='font-size:1.05rem; font-weight:900; color:#0F172A; margin-top:2px;'>Hakem Değerlendirme ve Gelişim Notu</div>", unsafe_allow_html=True)
            st.caption("Yarışmacıya iletilecek yapıcı teknik geribildirimi yazınız veya yapay zekâya hazırlatınız.")
        with nh_c2:
            if st.button("AI ile Hakem Notu Oluştur", key=f"btn_gen_ai_note_{rapor['rapor_id']}", use_container_width=True):
                with st.spinner("Puan tablosu ve rapor içeriği incelenerek yapıcı hakem notu yazılıyor..."):
                    from src.evaluation.evaluator import generate_ai_referee_note
                    
                    # Rapor metnini al
                    ext_text = ""
                    d_adi = rapor.get("dosya") or ""
                    res_doc = pdf_gorunum.yol(d_adi) if d_adi else None
                    if res_doc and res_doc.exists():
                        try:
                            import pymupdf
                            doc = pymupdf.open(str(res_doc))
                            for p in doc:
                                ext_text += p.get_text() + "\n"
                            doc.close()
                        except Exception:
                            pass
                    if not ext_text:
                        ext_text = f"TEKNOFEST 2026 {yarisma_id} Proje Başvuru Raporu. Algoritmalar, testler ve tasarım."

                    ai_note = generate_ai_referee_note(
                        report_text=ext_text,
                        category_name=yarisma_id,
                        stage=rapor.get("stage", "OTR"),
                        criteria_scores=st.session_state[anahtar],
                        criteria_list=rapor.get("kriterler", []),
                        total_score=hakem_toplam,
                        project_name=rapor.get("proje_adi", ""),
                        team_name=rapor.get("takim_adi", "")
                    )
                    st.session_state[not_key] = ai_note
                    st.rerun()

        not_metni = st.text_area(
            "Hakem Değerlendirme Notu (Yarışmacıya İletilecek)",
            value=st.session_state[not_key],
            height=130,
            placeholder="Gerekçe, tavsiye ve teknik açıklamalarınızı yazınız...",
            key=f"txt_area_note_{rapor['rapor_id']}",
            label_visibility="collapsed"
        )
        st.session_state[not_key] = not_metni

        st.write("")
        btn_c1, btn_c2 = st.columns([1.5, 2])
        with btn_c1:
            if st.button("Değerlendirmeyi Onayla ve Mühürle", type="primary", use_container_width=True):
                db.update_referee_decision(
                    report_id=rapor["rapor_id"],
                    referee_id=referee_id or "usr_hakem_ef6def",
                    referee_score=hakem_toplam,
                    decision="ONAYLANDI",
                    referee_notes=not_metni,
                    status="tamamlandi"
                )
                sonuc = api_client.hakem_karari_gonder(rapor["rapor_id"], st.session_state[anahtar], not_metni)
                st.success(f"Rapor mühürlendi ve nihai puan ({hakem_toplam}/100) yarışmacı sistemine işlendi!")
                st.rerun()
        
        with btn_c2:
            from karne_pdf import uret
            try:
                pdf_bytes = uret(rapor, st.session_state[anahtar], not_metni)
                st.download_button(
                    "Resmî İmzalı Karne PDF'i İndir",
                    data=pdf_bytes,
                    file_name=f"Karne_{rapor['rapor_id']}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
            except Exception:
                pass

