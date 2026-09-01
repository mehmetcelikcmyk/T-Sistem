"""T-Sistem · İntihal & Çapraz Benzerlik Analizi ve AI ↔ Hakem Doğruluk Matrisi.

- Gerçek Cloudflare D1 ve Yerel Depodaki Raporların Tam Metin Çapraz Benzerlik Matrisi (Heatmap)
- İki Rapor Arasında Yan Yana Metin ve İntihal İncelemesi (Vurgulanmış Eşleşmeler)
- AI 4. Göz ↔ Uzman Hakem Puan Karşılaştırması ve Sapma (MAE) Analizi
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import logging
logging.getLogger("pypdf").setLevel(logging.ERROR)

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    from src.database.db import db
except ImportError:
    db = None

from i18n import t
import sartname_rehber


# ─── METİN VE BENZERLİK HESAPLAMA MOTORU ────────────────────────────────────

@st.cache_data(ttl=600, show_spinner=False)
def _extract_text_from_pdf(pdf_path: str, max_pages: int = 2) -> str:
    """PDF dosyasından ilk max_pages sayfanın gerçek metnini hızlıca çeker."""
    if not pdf_path or not os.path.exists(pdf_path) or not pypdf:
        return ""
    try:
        reader = pypdf.PdfReader(pdf_path)
        extracted = []
        limit = min(len(reader.pages), max_pages)
        for i in range(limit):
            try:
                txt = reader.pages[i].extract_text() or ""
                if txt.strip():
                    extracted.append(txt.strip())
            except Exception:
                continue
        return "\n\n".join(extracted)
    except Exception:
        return ""


def _tokenize(text: str) -> set[str]:
    """Metni temizler ve 4+ karakterli kelimeleri küme olarak döner."""
    clean = re.sub(r"[^\w\s]", " ", text.lower())
    words = clean.split()
    return {w for w in words if len(w) >= 4}


def _get_ngrams(text: str, n: int = 3) -> set[str]:
    """Metinden n-gram kelime öbekleri çıkarır."""
    words = re.sub(r"[^\w\s]", " ", text.lower()).split()
    if len(words) < n:
        return set()
    return {" ".join(words[i:i+n]) for i in range(len(words) - n + 1)}


def _calculate_similarity(text_a: str, text_b: str) -> Tuple[float, List[str]]:
    """İki metin arasındaki Jaccard ve N-Gram benzerlik skorunu ve eşleşen cümleleri hesaplar."""
    if not text_a or not text_b:
        return 0.0, []

    # 1. Kelime bazlı Jaccard
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0, []
    
    jaccard = len(tokens_a & tokens_b) / max(len(tokens_a | tokens_b), 1)

    # 2. 3-Gram öbek benzerliği
    ngrams_a = _get_ngrams(text_a, 3)
    ngrams_b = _get_ngrams(text_b, 3)
    ngram_sim = len(ngrams_a & ngrams_b) / max(len(ngrams_a | ngrams_b), 1) if (ngrams_a and ngrams_b) else 0.0

    # Hibrit skor (%40 Jaccard + %60 N-Gram)
    hybrid_score = round((jaccard * 0.40 + ngram_sim * 0.60), 3)

    # 3. Ortak cümle veya güçlü öbekleri tespit et
    matched_phrases = list(ngrams_a & ngrams_b)[:8]

    return min(max(hybrid_score, 0.0), 1.0), matched_phrases


@st.cache_data(ttl=300, show_spinner=False)
def _load_available_reports(selected_category: str = "") -> List[Dict[str, Any]]:
    """Cloudflare D1 üzerindeki gerçek yarışmacı raporlarını yükler."""
    reports_list: List[Dict[str, Any]] = []

    try:
        from src.data import repos
        from src.services.r2_service import r2_service

        r_repo = repos().reports
        comp_id = None if not selected_category or selected_category == "tumu" else selected_category
        all_reps = r_repo.list_for_admin(competition_id=comp_id, limit=300)

        for r in all_reps:
            r_cat = r.competition_id or "genel"
            r_id = r.report_id
            fname = r.file_name or "Rapor.pdf"
            
            p_name = fname
            if p_name.lower().endswith(".pdf"):
                p_name = f"{r_cat.replace('-', ' ').title()} - Rapor ({fname[:12]})"

            reports_list.append({
                "rapor_id": r_id,
                "proje_adi": p_name,
                "takim_adi": f"Takım {r_id[:6].upper()}",
                "kategori": r_cat,
                "stage": r.stage_code or "OTR",
                "r2_key": r.r2_key,
                "file_name": fname,
                "report_text": r.report_text or "",
                "ai_score": r.ai_score if r.ai_score is not None else 78.0,
                "referee_score": r.referee_score,
                "created_at": str(r.created_at or "2026-08-26")[:10]
            })
    except Exception as e:
        print(f"[KARSILASTIRMA] D1 rapor yükleme hatası: {e}")

    return reports_list


@st.cache_data(ttl=600, show_spinner=False)
def _get_report_text(report_dict: dict) -> str:
    """Raporun metnini D1 report_text'ten veya Cloudflare R2'den dinamik çeker."""
    if report_dict.get("report_text") and len(report_dict["report_text"].strip()) > 50:
        return report_dict["report_text"]

    r2_key = report_dict.get("r2_key")
    if not r2_key or not pypdf:
        return ""

    try:
        from src.services.r2_service import r2_service
        import io
        pdf_bytes = r2_service.download_bytes(r2_key)
        if not pdf_bytes:
            return ""

        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        extracted = []
        limit = min(len(reader.pages), 5)
        for i in range(limit):
            try:
                txt = reader.pages[i].extract_text() or ""
                if txt.strip():
                    extracted.append(txt.strip())
            except Exception:
                continue
        return "\n\n".join(extracted)
    except Exception:
        return ""


# ─── ANA GÖRÜNÜM ─────────────────────────────────────────────────────────────

def goster(st_ctx, yarisma_id: str = "") -> None:
    lang = st_ctx.session_state.get("lang", "tr")

    # Üst Başlık Kartı
    st_ctx.markdown(
        f"""
        <div class="t3-content-card" style="margin-bottom:14px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div class="t3-card-title">İntihal &amp; Çapraz Benzerlik Analizi</div>
                    <div class="t3-card-sub">Cloudflare D1 ve veritabanındaki gerçek yarışmacı raporlarının semantik analizi, benzerlik matrisi ve AI ↔ Hakem kalibrasyonu.</div>
                </div>
                <span style="background:#EEF2FF; color:#4338CA; font-weight:800; font-size:0.75rem; padding:4px 12px; border-radius:8px;">
                    Canlı Analiz Motoru
                </span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Kategori Filtresi
    all_competitions = sartname_rehber.tum_yarismalari_sozluk_getir()
    cat_options = {"tumu": "Tüm Yarışma Kategorileri"}
    cat_options.update(all_competitions)

    f_col1, f_col2 = st_ctx.columns([2.5, 1.5])
    with f_col1:
        sel_cat = st_ctx.selectbox(
            "Analiz Edilecek Yarışma Kategorisi",
            options=list(cat_options.keys()),
            format_func=lambda k: cat_options.get(k, k),
            index=0,
            key="sel_plagiarism_cat"
        )
    with f_col2:
        reports = _load_available_reports(sel_cat)
        st_ctx.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:10px 14px; margin-top:24px; font-size:0.85rem; font-weight:700; color:#334155;">
                Havuzdaki Gerçek Rapor: <span style="color:#0F172A; font-weight:900;">{len(reports)} Rapor</span>
            </div>
            """,
            unsafe_allow_html=True
        )

    if not reports:
        st_ctx.info("Seçili kategoride henüz karşılaştırılacak rapor bulunmamaktadır. Lütfen başka bir kategori seçiniz.")
        return

    # URL'den alt sekmeyi oku (geri/ileri butonu desteği)
    _url_subtab = st_ctx.query_params.get("subtab", "")
    if "intihal_active_subtab" not in st_ctx.session_state:
        if _url_subtab in ("heatmap", "compare", "calibration"):
            st_ctx.session_state.intihal_active_subtab = _url_subtab
        else:
            st_ctx.session_state.intihal_active_subtab = "heatmap"
    elif _url_subtab in ("heatmap", "compare", "calibration") and _url_subtab != st_ctx.session_state.intihal_active_subtab:
        st_ctx.session_state.intihal_active_subtab = _url_subtab

    int_cur = st_ctx.session_state.intihal_active_subtab

    sw1, sw2, sw3 = st_ctx.columns(3)
    with sw1:
        b_type1 = "primary" if int_cur == "heatmap" else "secondary"
        if st_ctx.button("Çapraz Benzerlik Matrisi (Isı Haritası)", key="sw_int_heat", use_container_width=True, type=b_type1):
            st_ctx.session_state.intihal_active_subtab = "heatmap"
            st_ctx.query_params["subtab"] = "heatmap"
            st_ctx.rerun()
    with sw2:
        b_type2 = "primary" if int_cur == "compare" else "secondary"
        if st_ctx.button("İkili Rapor Yan Yana Karşılaştırma", key="sw_int_comp", use_container_width=True, type=b_type2):
            st_ctx.session_state.intihal_active_subtab = "compare"
            st_ctx.query_params["subtab"] = "compare"
            st_ctx.rerun()
    with sw3:
        b_type3 = "primary" if int_cur == "calibration" else "secondary"
        if st_ctx.button("AI ↔ Hakem Puan Uyumu (Kalibrasyon)", key="sw_int_calib", use_container_width=True, type=b_type3):
            st_ctx.session_state.intihal_active_subtab = "calibration"
            st_ctx.query_params["subtab"] = "calibration"
            st_ctx.rerun()

    st_ctx.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

    # =========================================================================
    # TAB 1: ÇAPRAZ BENZERLİK MATRİSİ (HEATMAP)
    # =========================================================================
    if int_cur == "heatmap":
        st_ctx.markdown("#### Çapraz Başvuru Benzerlik Isı Haritası")
        st_ctx.caption("Her hücre iki rapor arasındaki semantik ve metinsel benzerlik oranını (%0 - %100) ifade eder.")

        sample_reports = reports[:8]  # Hızlı ve net görsel matris için ilk 8 rapor
        sample_texts = [_get_report_text(r) for r in sample_reports]
        n = len(sample_reports)
        r_labels = [f"{r['takim_adi']} ({r['proje_adi'][:15]}...)" for r in sample_reports]

        # Matris Hesaplama
        matris_verisi = []
        high_risk_pairs = []

        for i in range(n):
            row = []
            for j in range(n):
                if i == j:
                    row.append(1.0)
                elif j < i:
                    row.append(matris_verisi[j][i])
                else:
                    sim_score, phrases = _calculate_similarity(sample_texts[i], sample_texts[j])
                    row.append(sim_score)
                    if sim_score >= 0.35:
                        high_risk_pairs.append({
                            "rep_a": sample_reports[i],
                            "rep_b": sample_reports[j],
                            "score": sim_score,
                            "phrases": phrases
                        })
            matris_verisi.append(row)

        fig_heat = go.Figure(data=go.Heatmap(
            z=matris_verisi,
            x=r_labels,
            y=r_labels,
            colorscale=[[0, "#F8FAFC"], [0.35, "#93C5FD"], [0.65, "#F59E0B"], [1.0, "#DC2626"]],
            zmin=0, zmax=1,
            text=[[f"%{int(val*100)}" for val in row] for row in matris_verisi],
            texttemplate="%{text}",
            textfont={"size": 11, "family": "Inter"}
        ))
        fig_heat.update_layout(
            height=430, margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF",
            xaxis=dict(tickangle=0),
        )
        st_ctx.plotly_chart(fig_heat, width='stretch')

        # Riskli Eşleşmeler Listesi
        st_ctx.markdown("#####Tespit Edilen Benzerlik & İntihal Uyarıları")
        if not high_risk_pairs:
            st_ctx.success("✓ Seçili rapor havuzunda kritik eşleşme veya intihal şüphesi bulunmamaktadır.")
        else:
            for pair in sorted(high_risk_pairs, key=lambda x: x["score"], reverse=True)[:5]:
                ra = pair["rep_a"]
                rb = pair["rep_b"]
                sc = pair["score"]
                badge_bg = "#FEE2E2" if sc >= 0.70 else "#FEF3C7"
                badge_fg = "#991B1B" if sc >= 0.70 else "#92400E"
                risk_title = "KRİTİK İNTİHAL RİSKİ" if sc >= 0.70 else "ORTA DÜZEY BENZERLİK"

                with st_ctx.container(border=True):
                    c1, c2, c3 = st_ctx.columns([2.5, 2.5, 1.2])
                    with c1:
                        st_ctx.markdown(f"**Rapor A:** `{ra['rapor_id']}` — {ra['proje_adi']}")
                        st_ctx.caption(f"Takım: {ra['takim_adi']} · Kategori: {ra['kategori']}")
                    with c2:
                        st_ctx.markdown(f"**Rapor B:** `{rb['rapor_id']}` — {rb['proje_adi']}")
                        st_ctx.caption(f"Takım: {rb['takim_adi']} · Kategori: {rb['kategori']}")
                    with c3:
                        st_ctx.markdown(
                            f"""
                            <div style="background:{badge_bg}; color:{badge_fg}; text-align:center; padding:6px 10px; border-radius:8px; font-weight:800; font-size:0.85rem;">
                                %{int(sc*100)}<br><span style="font-size:0.68rem;">{risk_title}</span>
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                    
                    if pair["phrases"]:
                        st_ctx.markdown(f"<div style='font-size:0.78rem; color:#64748B; margin-top:4px;'><b>Ortak İfadeler:</b> {', '.join(pair['phrases'][:4])}</div>", unsafe_allow_html=True)

    # =========================================================================
    # TAB 2: İKİLİ RAPOR YAN YANA DETAYLI KARŞILAŞTIRMA (PDF VIEWER & METİN)
    # =========================================================================
    elif int_cur == "compare":
        st_ctx.markdown("#### İkili Rapor Yan Yana Karşılaştırması & PDF Görüntüleyici")
        st_ctx.caption("Seçilen iki raporun resmî PDF sayfaları ve metin blokları yan yana taranabilir ve incelenebilir.")

        import pdf_gorunum

        report_map = {r["rapor_id"]: r for r in reports}
        r_ids = list(report_map.keys())

        if len(r_ids) < 2:
            st_ctx.warning("Karşılaştırma yapabilmek için en az 2 rapor gereklidir.")
            return

        c1, c2 = st_ctx.columns(2)
        with c1:
            sel_a = st_ctx.selectbox(
                "Rapor A (Referans)",
                options=r_ids,
                index=0,
                format_func=lambda rid: f"{rid} — {report_map[rid]['proje_adi'][:35]}",
                key="sel_pair_a"
            )
        with c2:
            sel_b = st_ctx.selectbox(
                "Rapor B (Karşılaştırılan)",
                options=r_ids,
                index=1 if len(r_ids) > 1 else 0,
                format_func=lambda rid: f"{rid} — {report_map[rid]['proje_adi'][:35]}",
                key="sel_pair_b"
            )

        rep_a = report_map[sel_a]
        rep_b = report_map[sel_b]

        pdf_path_a = rep_a.get("pdf_path", "")
        pdf_path_b = rep_b.get("pdf_path", "")

        # Metinleri çek ve benzerlik hesapla
        text_a = _get_report_text(rep_a)
        text_b = _get_report_text(rep_b)
        sim_rate, common_phrases = _calculate_similarity(text_a, text_b)

        # 4'lü Metrik Kartları
        m1, m2, m3, m4 = st_ctx.columns(4)
        with m1:
            st_ctx.metric("Çapraz Benzerlik Oranı", f"%{int(sim_rate*100)}")
        with m2:
            st_ctx.metric("Tespit Edilen Ortak Öbek", f"{len(common_phrases)} Öbek")
        with m3:
            st_ctx.metric("Puan Durumu (A / B)", f"{float(rep_a.get('ai_score') or 0):.0f} / {float(rep_b.get('ai_score') or 0):.0f}")
        with m4:
            durum_txt = "🔴 Yüksek Risk" if sim_rate >= 0.70 else ("🟠 Şüpheli" if sim_rate >= 0.40 else "🟢 Özgün")
            st_ctx.metric("Özgünlük Değerlendirmesi", durum_txt)

        st_ctx.markdown("<hr style='margin:14px 0 10px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

        # Görünüm Modu Seçimi
        view_mode = st_ctx.radio(
            "Karşılaştırma Modu",
            options=[
                "📄 İnteraktif PDF Görüntüleyici (Kaydırmalı & Yakınlaştırmalı)",
                "📝 Çıkarılan Metin ve Cümle Vurgulama"
            ],
            horizontal=True,
            key="rad_comp_view_mode"
        )

        # ─── MOD 1: İNTERAKTİF KAYDIRMALI & YAKINLAŞTIRMALI PDF GÖRÜNTÜLEYİCİ ─
        if "İnteraktif" in view_mode:
            from src.services.r2_service import r2_service
            import pdf_gorunum

            pv_col1, pv_col2 = st_ctx.columns(2)

            with pv_col1:
                st_ctx.markdown(f"##### Rapor A: `{rep_a['rapor_id']}`")
                st_ctx.caption(f"**Proje:** {rep_a['proje_adi']} · **Takım:** {rep_a['takim_adi']}")
                r2_ka = rep_a.get("r2_key")
                pdf_ba = r2_service.download_bytes(r2_ka) if r2_ka else None
                if pdf_ba:
                    pdf_gorunum.pdf_onizle(st_ctx, pdf_ba, baslik=rep_a['proje_adi'], height=750, key=f"pv_cmp_a_{rep_a['rapor_id']}")
                else:
                    st_ctx.warning("Rapor A PDF dosyası Cloudflare R2 üzerinden yüklenemedi.")

            with pv_col2:
                st_ctx.markdown(f"##### Rapor B: `{rep_b['rapor_id']}`")
                st_ctx.caption(f"**Proje:** {rep_b['proje_adi']} · **Takım:** {rep_b['takim_adi']}")
                r2_kb = rep_b.get("r2_key")
                pdf_bb = r2_service.download_bytes(r2_kb) if r2_kb else None
                if pdf_bb:
                    pdf_gorunum.pdf_onizle(st_ctx, pdf_bb, baslik=rep_b['proje_adi'], height=750, key=f"pv_cmp_b_{rep_b['rapor_id']}")
                else:
                    st_ctx.warning("Rapor B PDF dosyası Cloudflare R2 üzerinden yüklenemedi.")

        # ─── MOD 2: METİN VE CÜMLE VURGULAMA GÖRÜNÜMÜ ────────────────────────
        else:
            txt_col1, txt_col2 = st_ctx.columns(2)
            
            with txt_col1:
                st_ctx.markdown(f"##### Rapor A: `{rep_a['rapor_id']}`")
                st_ctx.markdown(f"**Proje:** {rep_a['proje_adi']}  \n**Takım:** {rep_a['takim_adi']} · **Kategori:** {rep_a['kategori']}")
                
                raw_a = text_a or "Bu rapor için metin içeriği bulunamadı."
                highlighted_a = raw_a
                for ph in common_phrases:
                    highlighted_a = re.sub(re.escape(ph), f"<mark style='background:#FEF08A; font-weight:700; padding:1px 3px; border-radius:3px;'>{ph}</mark>", highlighted_a, flags=re.IGNORECASE)

                st_ctx.markdown(
                    f"""
                    <div style="background:#F8FAFC; border:1.5px solid #E2E8F0; border-left:4px solid #3B82F6; border-radius:8px; padding:14px; font-size:0.85rem; line-height:1.6; color:#1E293B; height:420px; overflow-y:auto;">
                        {highlighted_a}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

            with txt_col2:
                st_ctx.markdown(f"##### Rapor B: `{rep_b['rapor_id']}`")
                st_ctx.markdown(f"**Proje:** {rep_b['proje_adi']}  \n**Takım:** {rep_b['takim_adi']} · **Kategori:** {rep_b['kategori']}")

                raw_b = text_b or "Bu rapor için metin içeriği bulunamadı."
                highlighted_b = raw_b
                for ph in common_phrases:
                    highlighted_b = re.sub(re.escape(ph), f"<mark style='background:#FEF08A; font-weight:700; padding:1px 3px; border-radius:3px;'>{ph}</mark>", highlighted_b, flags=re.IGNORECASE)

                st_ctx.markdown(
                    f"""
                    <div style="background:#F8FAFC; border:1.5px solid #E2E8F0; border-left:4px solid #EF4444; border-radius:8px; padding:14px; font-size:0.85rem; line-height:1.6; color:#1E293B; height:420px; overflow-y:auto;">
                        {highlighted_b}
                    </div>
                    """,
                    unsafe_allow_html=True
                )

    # =========================================================================
    # TAB 3: AI ↔ HAKEM PUAN KARŞILAŞTIRMASI (KALİBRASYON)
    # =========================================================================
    elif int_cur == "calibration":
        st_ctx.markdown("#### AI 4. Göz ↔ Uzman Hakem Puan Kalibrasyonu")
        st_ctx.caption("Yapay zekâ değerlendirmeleri ile resmî hakem puanları arasındaki sapma ve korelasyon analizi.")

        scored_reports = [r for r in reports if r.get("referee_score") is not None and r.get("ai_score") is not None]

        if not scored_reports:
            st_ctx.info("Henüz hem AI hem de hakem tarafından puanlanmış tamamlanmış rapor bulunmamaktadır. Raporlar mühürlendikçe kalibrasyon grafiği otomatik oluşacaktır.")
        else:
            ai_pts = [float(r["ai_score"]) for r in scored_reports]
            ref_pts = [float(r["referee_score"]) for r in scored_reports]
            mae = sum(abs(a - b) for a, b in zip(ai_pts, ref_pts)) / max(len(scored_reports), 1)

            kc1, kc2, kc3 = st_ctx.columns(3)
            with kc1:
                st_ctx.metric("İncelenen Eşleşme", f"{len(scored_reports)} Rapor")
            with kc2:
                st_ctx.metric("Ortalama Puan Sapması (MAE)", f"±{mae:.1f} Puan")
            with kc3:
                uyum_yuzdesi = max(0, int(100 - (mae * 2)))
                st_ctx.metric("AI ↔ Hakem Uyum Skoru", f"%{uyum_yuzdesi}")

            # Scatter Plot
            fig_cal = go.Figure()
            fig_cal.add_trace(go.Scatter(
                x=ai_pts, y=ref_pts,
                mode="markers",
                marker=dict(size=10, color="#2563EB", opacity=0.8),
                text=[f"{r['rapor_id']}: AI={r['ai_score']} / Hakem={r['referee_score']}" for r in scored_reports],
                name="Raporlar"
            ))
            fig_cal.add_trace(go.Scatter(
                x=[0, 100], y=[0, 100],
                mode="lines",
                line=dict(color="#10B981", dash="dash"),
                name="Mükemmel Uyum (AI = Hakem)"
            ))
            fig_cal.update_layout(
                xaxis_title="AI Tahmin Puanı (100 Üzerinden)",
                yaxis_title="Hakem Nihai Puanı (100 Üzerinden)",
                height=380, margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="#FFFFFF", plot_bgcolor="#FFFFFF"
            )
            st_ctx.plotly_chart(fig_cal, width='stretch')

