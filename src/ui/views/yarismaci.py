"""
T-Sistem · Yarışmacı (Üye) Portalı (%100 Cloudflare D1 & R2 Bağlantılı).

- 1. TEKNOFEST Resmî Kart Tasarımı ile Tüm Yarışmalar Vitrini
- 2. Anlık Arama ve Alan / Seviye Filtreleme Motoru
- 3. Takım Seçimi, Yarışma Başvurusu ve Aşama Raporu Yükleme (R2)
- 4. Başvuru Durumları, Rapor Havuzu Takibi ve Hakem Değerlendirme Karnesi
"""

from __future__ import annotations

import os
import io
import json
import re
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import streamlit as st
import pandas as pd

from src.database.db import db
from src.services.r2_service import r2_service
import sartname_rehber
import charts
import karne_pdf


def goster(st_ctx=None, default_yarisma_id: str = "") -> None:
    """Yarışmacı Portalı Ana Ekranı."""
    if st_ctx is None:
        st_ctx = st

    st_ctx.markdown(
        """
        <div class="t3-content-card">
            <div class="t3-card-title">TEKNOFEST Yarışmacı Portalı & Başvuru İstasyonu</div>
            <div class="t3-card-sub">Yarışmaları inceleyin, takımınızla başvuru yapın, aşama raporlarınızı yükleyin ve değerlendirme sonuçlarınızı anlık takip edin.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_vitrin, tab_basvuru, tab_karnem = st_ctx.tabs([
        "1. Yarışma Vitrini & Başvuru",
        "2. Aşama Raporu Yükle",
        "3. Başvurularım & Değerlendirme Karnesi"
    ])

    tum_yarismalar = db.list_all_competitions()

    # -------------------------------------------------------------------------
    # TAB 1: TEKNOFEST KARTLI YARIŞMA VİTRİNİ & ARAMA / FİLTRELEME
    # -------------------------------------------------------------------------
    with tab_vitrin:
        st_ctx.markdown("##### TEKNOFEST 2026 Yarışma Kategorileri")
        st_ctx.caption("İncelemek ve başvurmak istediğiniz yarışmayı arayın ve seçin.")

        f_c1, f_c2, f_c3 = st_ctx.columns([2, 1.5, 1.5])
        with f_c1:
            y_arama = st_ctx.text_input("Yarışma Ara", placeholder="Yarışma adı ile filtreleyin...", key="yarismaci_arama_bar", label_visibility="collapsed")
        with f_c2:
            y_alan_filtre = st_ctx.selectbox("Alan Filtresi", ["Tüm Alanlar", "Havacılık, Uzay ve Savunma", "Yapay Zekâ, Bilişim ve Yazılım", "Otonom Sistemler ve Robotik", "Sağlık, Biyoteknoloji ve Çevre", "Enerji, Ulaşım ve İklim", "İnsanlık ve Toplum Odaklı Teknolojiler"], key="yarismaci_alan_filtre", label_visibility="collapsed")
        with f_c3:
            y_seviye_filtre = st_ctx.selectbox("Seviye Filtresi", ["Tüm Seviyeler", "İlkokul", "Ortaokul", "Lise", "Ön Lisans / Lisans", "Yüksek Lisans / Doktora", "Mezun / Serbest Girişimci"], key="yarismaci_seviye_filtre", label_visibility="collapsed")

        # Filtreleme
        gosterilecek_yarismalar = []
        for comp in tum_yarismalar:
            c_name = comp.get("name", "")
            c_dom = comp.get("domain", "")
            c_lev = comp.get("levels", "")

            if y_arama and y_arama.lower() not in c_name.lower():
                continue
            if y_alan_filtre != "Tüm Alanlar" and y_alan_filtre != c_dom:
                continue
            if y_seviye_filtre != "Tüm Seviyeler" and y_seviye_filtre not in c_lev:
                continue
            gosterilecek_yarismalar.append(comp)

        st_ctx.markdown(f"**Toplam {len(gosterilecek_yarismalar)} Yarışma Listeleniyor**")

        # 3'lü Grid Kart Düzeni (TEKNOFEST Kurumsal Tasarımı)
        cols_per_row = 3
        for i in range(0, len(gosterilecek_yarismalar), cols_per_row):
            row_comps = gosterilecek_yarismalar[i:i+cols_per_row]
            c_cols = st_ctx.columns(cols_per_row)
            for c_idx, comp in enumerate(row_comps):
                with c_cols[c_idx]:
                    c_slug = comp.get("slug", "")
                    c_name = comp.get("name", "")
                    c_dom = comp.get("domain", "Teknoloji")
                    c_levels = comp.get("levels", "Genel")
                    
                    try:
                        c_sched = json.loads(comp.get("schedule_json") or "{}")
                    except Exception:
                        c_sched = {}
                    son_basvuru = c_sched.get("son_basvuru", "28.02.2026")

                    # Logo Çek
                    logo_b64 = sartname_rehber.kategori_logosu_base64_getir(c_slug)
                    logo_img = f'<img src="{logo_b64}" style="width:52px; height:52px; object-fit:contain; border-radius:10px; background:#FFFFFF; padding:3px; box-shadow:0 2px 8px rgba(0,0,0,0.15);" alt="Logo"/>' if logo_b64 else '<div style="width:52px; height:52px; border-radius:10px; background:rgba(255,255,255,0.2); display:flex; align-items:center; justify-content:center; font-weight:900; color:#FFFFFF;">TF</div>'

                    # Kart Tasarımı
                    st_ctx.markdown(
                        f"""
                        <div class="t3-module-card" style="min-height: 275px; text-align:left; align-items:flex-start; justify-content:space-between;">
                            <div>
                                <div style="display:flex; justify-content:space-between; align-items:flex-start; width:100%; margin-bottom:12px;">
                                    {logo_img}
                                    <span style="background:rgba(255,255,255,0.22); font-size:0.75rem; font-weight:800; padding:4px 10px; border-radius:8px; color:#FFFFFF; text-transform:uppercase; letter-spacing:0.02em;">{c_dom}</span>
                                </div>
                                <div class="t3-module-title" style="margin-top:4px; font-size:1.18rem; line-height:1.35;">{c_name}</div>
                                <div class="t3-module-desc" style="font-size:0.86rem; color:rgba(255,255,255,0.90); margin-top:6px;">Seviyeler: {c_levels}</div>
                            </div>
                            <div style="width:100%; display:flex; justify-content:space-between; align-items:center; border-top:1px solid rgba(255,255,255,0.22); padding-top:10px; margin-top:10px;">
                                <span style="font-size:0.80rem; font-weight:750; color:#FFFFFF;">Son Başvuru: {son_basvuru}</span>
                            </div>
                        </div>
                        """,
                        unsafe_allow_html=True
                    )
                    if st_ctx.button("Bu Yarışmaya Rapor Yükle", key=f"btn_apply_card_{c_slug}", use_container_width=True, type="primary"):
                        st_ctx.session_state.selected_apply_comp = c_slug
                        st_ctx.rerun()

    # -------------------------------------------------------------------------
    # TAB 2: AŞAMA RAPORU YÜKLEME (%100 R2 & D1)
    # -------------------------------------------------------------------------
    with tab_basvuru:
        st_ctx.markdown("##### Takım Aşama Raporu Yükleme")
        st_ctx.caption("Aşama raporunuzu (PDF formatında) yükleyin. Raporunuz Cloudflare R2 deposuna aktarılır ve değerlendirme havuzuna eklenir.")

        my_teams = st_ctx.session_state.get("takim_verileri", [])
        team_options = [t.get("takim") for t in my_teams] if my_teams else ["Bireysel Başvuru"]

        comp_slug_list = [c.get("slug") for c in tum_yarismalar]
        comp_name_map = {c.get("slug"): c.get("name") for c in tum_yarismalar}

        default_comp = st_ctx.session_state.get("selected_apply_comp")
        default_index = comp_slug_list.index(default_comp) if default_comp in comp_slug_list else 0

        with st_ctx.form("form_submit_team_report"):
            u_c1, u_c2 = st_ctx.columns(2)
            with u_c1:
                secili_takim = st_ctx.selectbox("Başvuru Yapacak Takım *", team_options)
                secili_yarisma = st_ctx.selectbox(
                    "Yarışma Kategorisi *",
                    options=comp_slug_list,
                    index=default_index,
                    format_func=lambda x: comp_name_map.get(x, x)
                )
            with u_c2:
                # Yarışmanın aşamalarını D1'den çek
                comp_stages = db.list_competition_stages(secili_yarisma)
                stage_codes = [s.get("stage_code") for s in comp_stages] if comp_stages else ["OTR", "KTR", "FTR"]
                stage_names = {s.get("stage_code"): f"{s.get('stage_code')} - {s.get('stage_name')}" for s in comp_stages}
                
                secili_asama = st_ctx.selectbox(
                    "Rapor Aşaması *",
                    options=stage_codes,
                    format_func=lambda x: stage_names.get(x, x)
                )
                secili_seviye = st_ctx.selectbox("Eğitim Seviyesi *", ["Lise", "Ön Lisans / Lisans", "Yüksek Lisans / Doktora", "İlkokul / Ortaokul", "Mezun"])

            rapor_dosyasi = st_ctx.file_uploader("Resmî Aşama Raporu (.pdf formatında) *", type=["pdf"], key="yarismaci_pdf_upload_input")
            
            sub_report = st_ctx.form_submit_button("Raporumu R2'ye Yükle ve Değerlendirmeye Gönder", type="primary")
            if sub_report:
                if not rapor_dosyasi:
                    st_ctx.error("Lütfen rapor PDF dosyasını seçiniz.")
                else:
                    with st_ctx.spinner("Rapor Cloudflare R2'ye yükleniyor ve veritabanı kaydı oluşturuluyor..."):
                        file_bytes = rapor_dosyasi.getvalue()
                        clean_takim = r2_service.slugify(secili_takim)
                        clean_file_name = f"{clean_takim}_{secili_yarisma}_{secili_asama.lower()}_raporu.pdf"
                        
                        # 1. Cloudflare R2'ye yükle
                        app_id = f"APP-{abs(hash(secili_takim + secili_yarisma)) % 90000 + 10000}"
                        r2_key = f"raporlar/{app_id}/{secili_asama.lower()}/{clean_file_name}"
                        success, res_url = r2_service.upload_file(file_bytes, r2_key, "application/pdf")

                        # 2. Sayfa Sayısı Tespiti
                        p_count = 1
                        try:
                            import pymupdf
                            doc = pymupdf.open(stream=file_bytes, filetype="pdf")
                            p_count = len(doc)
                            doc.close()
                        except Exception:
                            pass

                        # 3. D1 Veritabanına Rapor Kaydı
                        rep_id = f"REP-{abs(hash(clean_file_name)) % 90000 + 10000}"
                        ins_sql = """
                        INSERT INTO reports (report_id, app_id, competition_id, stage_code, file_name, r2_url, page_count, status, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 'Beklemede', ?);
                        """
                        db.execute_d1(ins_sql, [
                            rep_id,
                            app_id,
                            secili_yarisma,
                            secili_asama.upper(),
                            clean_file_name,
                            res_url,
                            p_count,
                            datetime.datetime.now().isoformat()
                        ])

                        st_ctx.success("Raporunuz başarıyla yüklendi ve değerlendirme havuzuna eklendi! Durumu 'Başvurularım' sekmesinden takip edebilirsiniz.")

    # -------------------------------------------------------------------------
    # TAB 3: BAŞVURULARIM & DEĞERLENDİRME KARNESİ (YARIŞMA BAZLI HİYERARŞİ)
    # -------------------------------------------------------------------------
    with tab_karnem:
        st_ctx.markdown("##### Yarışma Başvurularım, Aşama Süreçleri ve Resmî Karnelerim")
        st_ctx.caption("Takımınızın kayıtlı olduğu yarışmaları, aşama rapor durumlarını inceleyin; sıradaki aşama için rapor yükleyin ve hakem karnelerinizi görüntüleyin.")

        my_teams = st_ctx.session_state.get("takim_verileri", [])
        team_names = [t.get("takim") for t in my_teams] if my_teams else ["Varsayılan Takım"]

        # Takım Seçici
        secili_izleme_takim = st_ctx.selectbox("İncelemek İstediğiniz Takımınız", team_names, key="sel_team_app_tracker")
        secili_takim_obj = next((t for t in my_teams if t.get("takim") == secili_izleme_takim), None) if my_teams else None
        team_id_val = secili_takim_obj.get("id", "100001") if secili_takim_obj else "100001"

        # D1'den bu takıma veya genel kullanıcıya ait tüm başvuruları çek
        user_apps = db.list_applications_for_team(team_id_val)
        
        # Eğer henüz başvuru yoksa ama yüklenmiş rapor varsa, raporlardan dinamik başvuru oluştur/göster
        user_reports = db.execute_d1("SELECT * FROM reports ORDER BY created_at DESC;") or []

        # Başvuruları grupla (Yarışma Bazında)
        comp_applications = {}
        for app in user_apps:
            c_slug = app.get("competition_id")
            comp_applications[c_slug] = app

        # Raporlardan da kategori tespiti yap
        for rep in user_reports:
            c_slug = rep.get("competition_id")
            if c_slug not in comp_applications:
                comp_info = db.get_competition_by_id(c_slug) or {}
                comp_applications[c_slug] = {
                    "app_id": rep.get("app_id", f"APP-{c_slug}"),
                    "team_id": team_id_val,
                    "competition_id": c_slug,
                    "competition_name": comp_info.get("name", c_slug),
                    "status": "Aktif",
                    "created_at": rep.get("created_at")
                }

        if not comp_applications:
            st_ctx.info("Takımınızın henüz aktif bir yarışma başvurusu bulunmamaktadır. 'Yarışma Vitrini' sekmesinden dilediğiniz yarışmaya başvurabilirsiniz.")
        else:
            for c_slug, app in comp_applications.items():
                c_name = app.get("competition_name") or c_slug
                app_id = app.get("app_id", "")
                
                comp_full = db.get_competition_by_id(c_slug) or {}
                try:
                    c_sched = json.loads(comp_full.get("schedule_json") or "{}")
                except Exception:
                    c_sched = {}

                # Yarışmanın tüm aşamalarını çek
                comp_stages = db.list_competition_stages(c_slug)
                if not comp_stages:
                    comp_stages = [
                        {"stage_code": "OTR", "stage_name": "Ön Tasarım Raporu", "deadline": "15.04.2026"},
                        {"stage_code": "KTR", "stage_name": "Kritik Tasarım Raporu", "deadline": "20.06.2026"},
                        {"stage_code": "FTR", "stage_name": "Final Tasarım Raporu", "deadline": "10.08.2026"}
                    ]

                # Bu yarışma için yüklenmiş raporları filtrele
                app_reports = [r for r in user_reports if r.get("competition_id") == c_slug]
                uploaded_stage_codes = {r.get("stage_code").upper(): r for r in app_reports}

                with st_ctx.container(border=True):
                    # Başlık Kartı
                    head_col1, head_col2 = st_ctx.columns([3, 1.5])
                    with head_col1:
                        st_ctx.markdown(f"### {c_name}")
                        st_ctx.caption(f"Başvuru No: `{app_id}` | Takım: **{secili_izleme_takim}** | Final: {c_sched.get('yarisma_tarihi', '15.09.2026 - 20.09.2026')}")
                    with head_col2:
                        st_ctx.markdown("<span class='t3-badge-aktif' style='font-size:0.90rem; margin-top:8px;'>Başvuru Aktif</span>", unsafe_allow_html=True)

                    st_ctx.markdown("<hr style='margin:12px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                    st_ctx.markdown("###### Aşama Rapor Süreçleri ve Değerlendirme Durumu")

                    # Aşama Süreçleri Akışı
                    for stg in comp_stages:
                        s_code = stg.get("stage_code", "OTR").upper()
                        s_name = stg.get("stage_name", "")
                        s_dead = stg.get("deadline", "—")
                        
                        has_report = uploaded_stage_codes.get(s_code)

                        with st_ctx.expander(f"Aşama: {s_code} - {s_name} (Son Teslim: {s_dead})", expanded=True if has_report else False):
                            st_col1, st_col2 = st_ctx.columns([2.5, 1.5])
                            
                            with st_col1:
                                if has_report:
                                    r_obj = has_report
                                    r_id = r_obj.get("report_id")
                                    r_status = r_obj.get("status", "Beklemede")
                                    r_fname = r_obj.get("file_name", "")
                                    r_pages = r_obj.get("page_count", 1)

                                    st_ctx.markdown(f"**Yüklenen Rapor:** `{r_fname}` ({r_pages} Sayfa)")
                                    st_ctx.caption(f"Yükleme Tarihi: {r_obj.get('created_at')}")

                                    if r_status == "Beklemede":
                                        st_ctx.markdown("<span class='t3-badge-turuncu'>Hakem Ataması Bekleniyor</span>", unsafe_allow_html=True)
                                    elif r_status == "Hakeme Atandı":
                                        st_ctx.markdown("<span class='t3-badge-aktif'>Hakem Değerlendirmesinde</span>", unsafe_allow_html=True)
                                    elif r_status == "Değerlendirildi":
                                        st_ctx.markdown("<span class='t3-badge-aktif'>Değerlendirme Tamamlandı</span>", unsafe_allow_html=True)

                                    # Hakem Değerlendirme Karnesi Çek
                                    eval_row = db.execute_d1("SELECT * FROM report_assignments WHERE report_id = ? LIMIT 1;", [r_id])
                                    if eval_row and eval_row[0].get("score") is not None:
                                        ev = eval_row[0]
                                        f_score = float(ev.get("score", 0.0))
                                        f_notes = ev.get("eval_json", "Değerlendirme tamamlandı.")

                                        st_ctx.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                                        k_box1, k_box2 = st_ctx.columns([1.5, 2.5])
                                        with k_box1:
                                            st_ctx.metric("Resmî Aşama Puanı", f"{f_score:.1f} / 100")
                                        with k_box2:
                                            st_ctx.markdown(f"**Hakem Değerlendirme Notu:**\n\n_{f_notes}_")
                                else:
                                    st_ctx.markdown(f"<span style='color:#DC2626; font-weight:750;'>Bu aşama için henüz rapor yüklenmedi.</span>", unsafe_allow_html=True)
                                    st_ctx.caption(f"Lütfen son teslim tarihine ({s_dead}) kadar resmî şablona uygun raporunuzu yükleyiniz.")

                            with st_col2:
                                if not has_report:
                                    st_ctx.markdown("**Bu Aşama İçin Rapor Yükle**")
                                    new_rep_file = st_ctx.file_uploader(f"{s_code} Raporu (PDF)", type=["pdf"], key=f"uploader_inline_{c_slug}_{s_code}")
                                    if new_rep_file is not None:
                                        if st_ctx.button(f"{s_code} Raporunu Gönder", key=f"btn_send_inline_{c_slug}_{s_code}", type="primary", use_container_width=True):
                                            with st_ctx.spinner("Rapor yükleniyor..."):
                                                f_bytes = new_rep_file.getvalue()
                                                clean_takim = r2_service.slugify(secili_izleme_takim)
                                                clean_f_name = f"{clean_takim}_{c_slug}_{s_code.lower()}_raporu.pdf"
                                                
                                                r2_key = f"raporlar/{app_id}/{s_code.lower()}/{clean_f_name}"
                                                r2_service.upload_file(f_bytes, r2_key, "application/pdf")

                                                p_cnt = 1
                                                try:
                                                    import pymupdf
                                                    doc = pymupdf.open(stream=f_bytes, filetype="pdf")
                                                    p_cnt = len(doc)
                                                    doc.close()
                                                except Exception:
                                                    pass

                                                new_r_id = f"REP-{abs(hash(clean_f_name)) % 90000 + 10000}"
                                                ins_sql = """
                                                INSERT INTO reports (report_id, app_id, competition_id, stage_code, file_name, r2_url, page_count, status, created_at)
                                                VALUES (?, ?, ?, ?, ?, ?, ?, 'Beklemede', ?);
                                                """
                                                db.execute_d1(ins_sql, [
                                                    new_r_id,
                                                    app_id,
                                                    c_slug,
                                                    s_code,
                                                    clean_f_name,
                                                    r2_key,
                                                    p_cnt,
                                                    datetime.datetime.now().isoformat()
                                                ])
                                                st_ctx.success(f"{s_code} raporunuz başarıyla yüklendi!")
                                                st_ctx.rerun()
                                else:
                                    st_ctx.markdown("<br>", unsafe_allow_html=True)
                                    st_ctx.button(f"{s_code} Raporunu İndir (PDF)", key=f"btn_dl_existing_{has_report.get('report_id')}", use_container_width=True)
