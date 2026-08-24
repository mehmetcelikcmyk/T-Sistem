"""
T-Sistem · Süper Yetkili Yarışma Yöneticisi (Admin) Paneli.

- 1. Üstte "+ Yeni Yarışma Oluştur" butonu, altta dinamik arama & filtreleme özellikli yarışmalar tablosu.
- 2. Tıklanınca açılan kapsamlı Yarışma Detay & Yönetim Ekranı:
     * Bağımsız Yarışma Takvimi (Son Başvuru, Aşama Teslim ve Final Tarihleri)
     * Şartname Yükleme (R2) + AI Kural Çıkarıcı + Canlı Düzenlenebilir Kural Tablosu
     * Aşama Ekleme + Word (.docx) / PDF Şablon Yükleme + Otomatik PDF Üretimi
     * AI 0-100 Puanlama Rubriği Çıkarıcı + Canlı Düzenlenebilir Kriter Formu
- 3. Hakem Havuzu, Rapor Havuzu ve Hakem Yönlendirme (Routing) İstasyonu.
- 4. %100 Cloudflare D1 & R2 Senkronize Çalışma ve Admin Full-CRUD (Ekle / Düzenle / Sil).
"""

from __future__ import annotations

import os
import io
import json
import re
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
import streamlit as st

from src.database.db import db
from src.services.r2_service import r2_service
from src.services.doc_converter import docx_to_pdf
from src.ai.spec_analyzer import spec_analyzer
from src.ai.template_analyzer import template_analyzer
import pdf_gorunum

DOMAINS = [
    "Havacılık, Uzay ve Savunma",
    "Yapay Zekâ, Bilişim ve Yazılım",
    "Otonom Sistemler ve Robotik",
    "Sağlık, Biyoteknoloji ve Çevre",
    "Enerji, Ulaşım ve İklim",
    "İnsanlık ve Toplum Odaklı Teknolojiler"
]

ALL_LEVELS = [
    "İlkokul",
    "Ortaokul",
    "Lise",
    "Ön Lisans / Lisans",
    "Yüksek Lisans / Doktora",
    "Mezun / Serbest Girişimci"
]


def goster(st_ctx=None, yarisma_id: str = "") -> None:
    """Admin Yönetici Paneli Ana Görünümü."""
    if st_ctx is None:
        st_ctx = st

    st_ctx.markdown(
        """
        <div class="t3-content-card">
            <div class="t3-card-title">Yarışma Yönetim İstasyonu & AI Kurallar Motoru</div>
            <div class="t3-card-sub">Yarışmaları, bağımsız takvimleri, şartnameleri, aşama şablonlarını, 0-100 puanlama rubriklerini ve hakem atamalarını tam yetkiyle yönetin.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Detay modu kontrolü
    secili_comp_id = st_ctx.session_state.get("admin_selected_comp_id")

    if secili_comp_id:
        _yarisma_detay_gorunumu(st_ctx, secili_comp_id)
    else:
        _yarisma_liste_ve_olusturma_gorunumu(st_ctx)


def _yarisma_liste_ve_olusturma_gorunumu(st_ctx) -> None:
    """Üstte '+ Yeni Yarışma Oluştur' butonu, altta dinamik arama/filtreleme tablosu."""
    
    # 1. Üst Buton & Açılır Yeni Yarışma Formu
    c1, c2, _ = st_ctx.columns([1.5, 1.5, 2.5])
    with c1:
        if st_ctx.button("+ Yeni Yarışma Oluştur", type="primary", use_container_width=True):
            st_ctx.session_state.show_new_comp_form = not st_ctx.session_state.get("show_new_comp_form", False)
    with c2:
        if st_ctx.button("Hakem & Rapor Havuzu", use_container_width=True):
            st_ctx.session_state.show_hakem_havuzu = not st_ctx.session_state.get("show_hakem_havuzu", False)

    # Hakem & Rapor Yönlendirme Paneli
    if st_ctx.session_state.get("show_hakem_havuzu"):
        _hakem_yonlendirme_paneli(st_ctx)
        st_ctx.markdown("<hr style='margin:20px 0;'>", unsafe_allow_html=True)

    # Yeni Yarışma Oluşturma Formu
    if st_ctx.session_state.get("show_new_comp_form"):
        with st_ctx.form("form_create_competition"):
            st_ctx.markdown("#### Yeni Yarışma Tanımla")
            f1, f2 = st_ctx.columns(2)
            with f1:
                yeni_ad = st_ctx.text_input("Yarışma Adı *", placeholder="Örn: Havacılıkta Yapay Zekâ Yarışması")
                yeni_domain = st_ctx.selectbox("Ana Alan / Kategori *", DOMAINS)
            with f2:
                yeni_levels = st_ctx.multiselect("Hedef Seviyeler *", ALL_LEVELS, default=["Lise", "Ön Lisans / Lisans"])
                yeni_son_basvuru = st_ctx.date_input("Son Başvuru Tarihi", datetime.date(2026, 3, 15))

            yeni_aciklama = st_ctx.text_area("Yarışma Tanımı ve Kapsamı", placeholder="Yarışmanın amacı, isterleri ve hedeflediği problem...")
            
            sub_comp = st_ctx.form_submit_button("Yarışmayı Kaydet ve Detaylara Geç", type="primary")
            if sub_comp:
                if not yeni_ad.strip():
                    st_ctx.error("Yarışma adı zorunludur.")
                else:
                    clean_slug = r2_service.slugify(yeni_ad)
                    schedule_data = {
                        "son_basvuru": yeni_son_basvuru.strftime("%d.%m.%Y"),
                        "yarisma_tarihi": "15.09.2026 - 20.09.2026",
                        "sonuc_tarihi": "25.09.2026"
                    }
                    comp_data = {
                        "name": yeni_ad.strip(),
                        "slug": clean_slug,
                        "domain": yeni_domain,
                        "levels": ", ".join(yeni_levels),
                        "description": yeni_aciklama.strip(),
                        "schedule": schedule_data
                    }
                    db.upsert_competition(comp_data)
                    st_ctx.session_state.admin_selected_comp_id = clean_slug
                    st_ctx.session_state.show_new_comp_form = False
                    st_ctx.success("Yarışma başarıyla oluşturuldu! Detay sayfasına yönlendiriliyorsunuz...")
                    st_ctx.rerun()

    st_ctx.markdown("<hr style='margin:18px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

    # 2. Arama & Filtreleme Barı
    s_col1, s_col2, s_col3 = st_ctx.columns([2, 1.5, 1.5])
    with s_col1:
        arama_metni = st_ctx.text_input("Yarışma Ara", placeholder="Yarışma adı ile filtreleyin...", label_visibility="collapsed")
    with s_col2:
        secili_alan_filtre = st_ctx.selectbox("Alan Filtresi", ["Tüm Alanlar"] + DOMAINS, label_visibility="collapsed")
    with s_col3:
        secili_seviye_filtre = st_ctx.selectbox("Seviye Filtresi", ["Tüm Seviyeler"] + ALL_LEVELS, label_visibility="collapsed")

    # 3. Dinamik Yarışmalar Tablosu
    tum_yarismalar = db.list_all_competitions()

    # Filtreleme mantığı
    filtrelenmis = []
    for comp in tum_yarismalar:
        c_name = comp.get("name", "")
        c_domain = comp.get("domain", "")
        c_levels = comp.get("levels", "")

        if arama_metni and arama_metni.lower() not in c_name.lower():
            continue
        if secili_alan_filtre != "Tüm Alanlar" and secili_alan_filtre != c_domain:
            continue
        if secili_seviye_filtre != "Tüm Seviyeler" and secili_seviye_filtre not in c_levels:
            continue
        filtrelenmis.append(comp)

    st_ctx.markdown(f"##### Kayıtlı Yarışmalar ({len(filtrelenmis)} Adet)")

    if not filtrelenmis:
        st_ctx.info("Kriterlere uygun yarışma bulunamadı. Yeni bir yarışma oluşturabilirsiniz.")
        return

    # Modern Tablo Görünümü
    for idx, comp in enumerate(filtrelenmis, 1):
        c_slug = comp.get("slug", "")
        c_name = comp.get("name", "")
        c_domain = comp.get("domain", "Teknoloji")
        c_levels = comp.get("levels", "Genel")
        sartname_durum = "Yüklendi" if comp.get("sartname_url") else "Eksik"

        with st_ctx.container(border=True):
            r1, r2, r3, r4, r5 = st_ctx.columns([3, 2, 2, 1.2, 1.2])
            with r1:
                st_ctx.markdown(f"**{c_name}**")
                st_ctx.caption(f"Slug: `{c_slug}`")
            with r2:
                st_ctx.markdown(f"<span style='color:#64748B;'>{c_domain}</span>", unsafe_allow_html=True)
            with r3:
                st_ctx.markdown(f"<span style='font-size:0.88rem;'>{c_levels}</span>", unsafe_allow_html=True)
            with r4:
                if sartname_durum == "Yüklendi":
                    st_ctx.markdown("<span class='t3-badge-aktif'>Şartname Var</span>", unsafe_allow_html=True)
                else:
                    st_ctx.markdown("<span class='t3-badge-pasif'>Şartname Yok</span>", unsafe_allow_html=True)
            with r5:
                if st_ctx.button("Detay & Yönet", key=f"btn_manage_comp_{c_slug}", type="primary", use_container_width=True):
                    st_ctx.session_state.admin_selected_comp_id = c_slug
                    st_ctx.rerun()


def _yarisma_detay_gorunumu(st_ctx, comp_slug: str) -> None:
    """Yarışma Detay Sayfası: Takvim, Şartname AI Kural Çıkarıcı, Aşama & Şablon AI Puanlama Rubriği."""
    comp = db.get_competition_by_id(comp_slug)
    if not comp:
        st_ctx.error("Yarışma kaydı bulunamadı.")
        if st_ctx.button("Listeye Dön"):
            st_ctx.session_state.admin_selected_comp_id = None
            st_ctx.rerun()
        return

    comp_name = comp.get("name", "")
    
    # Geri Dön Butonu ve Başlık
    h_col1, h_col2 = st_ctx.columns([4, 1.2])
    with h_col1:
        st_ctx.markdown(f"### {comp_name}")
        st_ctx.caption(f"Yarışma Detay, Bağımsız Takvim, Şartname ve Aşama Rubrik Yönetim Merkezi")
    with h_col2:
        if st_ctx.button("← Yarışma Listesine Dön", use_container_width=True):
            st_ctx.session_state.admin_selected_comp_id = None
            st_ctx.rerun()

    tab_genel, tab_sartname, tab_asamalar, tab_sil = st_ctx.tabs([
        "1. Genel Bilgiler & Bağımsız Takvim",
        "2. Şartname & AI Kural Çıkarıcı",
        "3. Aşamalar & Şablon Rubrik Yönetimi",
        "4. Yarışmayı Sil"
    ])

    # -------------------------------------------------------------------------
    # TAB 1: GENEL BİLGİLER & BAĞIMSIZ TAKVİM
    # -------------------------------------------------------------------------
    with tab_genel:
        with st_ctx.form("form_update_comp_general"):
            st_ctx.markdown("##### Yarışma Bilgilerini ve Takvimini Güncelle")
            g1, g2 = st_ctx.columns(2)
            with g1:
                u_name = st_ctx.text_input("Yarışma Adı", value=comp.get("name", ""))
                u_domain = st_ctx.selectbox("Ana Alan", DOMAINS, index=DOMAINS.index(comp.get("domain")) if comp.get("domain") in DOMAINS else 0)
            with g2:
                mevcut_lev = [x.strip() for x in comp.get("levels", "").split(",") if x.strip() in ALL_LEVELS]
                u_levels = st_ctx.multiselect("Seviyeler", ALL_LEVELS, default=mevcut_lev or ["Lise", "Ön Lisans / Lisans"])
            
            u_desc = st_ctx.text_area("Açıklama", value=comp.get("description", ""))

            st_ctx.markdown("##### Bağımsız Yarışma Takvimi")
            t_col1, t_col2 = st_ctx.columns(2)
            
            # Mevcut takvim verisini çek
            try:
                cur_sched = json.loads(comp.get("schedule_json") or "{}")
            except Exception:
                cur_sched = {}

            with t_col1:
                u_son_basvuru = st_ctx.text_input("Son Başvuru Tarihi", value=cur_sched.get("son_basvuru", "28.02.2026"))
            with t_col2:
                u_yarisma_tarihi = st_ctx.text_input("Final / Yarışma Tarihleri", value=cur_sched.get("yarisma_tarihi", "15.09.2026 - 20.09.2026"))

            save_g = st_ctx.form_submit_button("Bilgileri ve Takvimi Kaydet", type="primary")
            if save_g:
                sched = {
                    "son_basvuru": u_son_basvuru.strip(),
                    "yarisma_tarihi": u_yarisma_tarihi.strip()
                }
                up_data = {
                    "competition_id": comp.get("competition_id"),
                    "name": u_name.strip(),
                    "slug": comp_slug,
                    "domain": u_domain,
                    "levels": ", ".join(u_levels),
                    "description": u_desc.strip(),
                    "schedule": sched
                }
                db.upsert_competition(up_data)
                st_ctx.success("Genel bilgiler ve bağımsız takvim başarıyla güncellendi!")
                st_ctx.rerun()

    # -------------------------------------------------------------------------
    # TAB 2: ŞARTNAME & AI KURAL ÇIKARICI
    # -------------------------------------------------------------------------
    with tab_sartname:
        st_ctx.markdown("##### Resmî Şartname Yükleme ve AI Kural Çıkarıcı")
        st_ctx.caption("Şartname PDF dosyasını yükleyin. AI kuralları otomatik çıkarır; kuralları canlı tablodan düzenleyebilir, silebilir veya yeni kural ekleyebilirsiniz.")

        sn_file = st_ctx.file_uploader("Şartname PDF Dosyası Yükle", type=["pdf"], key=f"uploader_sn_{comp_slug}")
        if sn_file is not None:
            if st_ctx.button("Şartnameyi R2'ye Yükle ve AI ile Analiz Et", type="primary"):
                with st_ctx.spinner("Şartname Cloudflare R2'ye yükleniyor ve AI kural analizi yapılıyor..."):
                    # 1. R2'ye anlaşılır isimle yükle
                    clean_file_name = f"{comp_slug}_sartnamesi.pdf"
                    r2_key = f"sartnameler/{comp_slug}/{clean_file_name}"
                    success, res_key = r2_service.upload_file(sn_file.getvalue(), r2_key, "application/pdf")

                    # 2. AI Kural Çıkarımı
                    temp_pdf = Path(f"data/temp_{clean_file_name}")
                    temp_pdf.parent.mkdir(parents=True, exist_ok=True)
                    temp_pdf.write_bytes(sn_file.getvalue())
                    
                    analysis = spec_analyzer.analyze_specification(str(temp_pdf), comp_name)
                    if temp_pdf.exists():
                        temp_pdf.unlink()

                    # 3. Veritabanını güncelle
                    db.upsert_competition({
                        "slug": comp_slug,
                        "name": comp_name,
                        "sartname_url": res_key,
                        "schedule": analysis.get("schedule", {})
                    })
                    db.save_competition_requirements_bulk(comp_slug, analysis.get("requirements", []))

                    st_ctx.success("Şartname başarıyla R2'ye yüklendi ve kurallar AI tarafından çıkarıldı!")
                    st_ctx.rerun()

        # Mevcut Kuralları Listele ve Form Üzerinden Güvenli Düzenleme
        mevcut_kurallar = db.list_competition_requirements(comp_slug)
        st_ctx.markdown(f"###### Şartnameden Çıkarılan ve Onaylanan Kurallar ({len(mevcut_kurallar)} Adet)")

        if mevcut_kurallar:
            with st_ctx.form(f"form_save_requirements_bulk_{comp_slug}"):
                kural_duzenleme_listesi = []
                for idx, req in enumerate(mevcut_kurallar, 1):
                    st_ctx.markdown(f"**Kural #{idx}**")
                    e_k1, e_k2, e_k3 = st_ctx.columns([2.5, 1.2, 0.8])
                    with e_k1:
                        k_title = st_ctx.text_input(f"Kural Başlığı", value=req.get("title", ""), key=f"req_title_{idx}_{comp_slug}")
                        k_desc = st_ctx.text_area(f"Kural Açıklaması", value=req.get("description", ""), key=f"req_desc_{idx}_{comp_slug}")
                    with e_k2:
                        k_type = st_ctx.selectbox(f"Kural Tipi", ["teknik_ister", "takim_yapisi", "danisman_kurali", "ozgunluk_ve_intihal", "diger"], index=0, key=f"req_type_{idx}_{comp_slug}")
                        k_min = st_ctx.number_input(f"Min Üye", min_value=1, max_value=20, value=int(req.get("min_team_size", 1)), key=f"req_min_{idx}_{comp_slug}")
                        k_max = st_ctx.number_input(f"Max Üye", min_value=1, max_value=20, value=int(req.get("max_team_size", 6)), key=f"req_max_{idx}_{comp_slug}")
                    with e_k3:
                        st_ctx.markdown("<br>", unsafe_allow_html=True)
                        k_sil = st_ctx.checkbox(f"Bu kuralı sil", key=f"req_del_{idx}_{comp_slug}")

                    st_ctx.markdown("<hr style='margin:10px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

                    if not k_sil:
                        kural_duzenleme_listesi.append({
                            "req_id": req.get("req_id"),
                            "rule_type": k_type,
                            "title": k_title.strip(),
                            "description": k_desc.strip(),
                            "min_team_size": k_min,
                            "max_team_size": k_max,
                            "advisor_required": 1 if k_type == "danisman_kurali" else 0,
                            "is_mandatory": 1
                        })

                btn_save_reqs = st_ctx.form_submit_button("Tüm Kural Değişikliklerini Kaydet", type="primary")
                if btn_save_reqs:
                    db.save_competition_requirements_bulk(comp_slug, kural_duzenleme_listesi)
                    st_ctx.success("Şartname kuralları başarıyla kaydedildi!")
                    st_ctx.rerun()

        # Yeni Kural Ekleme Formu
        with st_ctx.expander("+ Manuel Yeni Kural Ekle"):
            with st_ctx.form(f"form_add_custom_rule_{comp_slug}"):
                nr_title = st_ctx.text_input("Kural Başlığı", placeholder="Örn: Yerli Donanım Zorunluluğu")
                nr_type = st_ctx.selectbox("Kural Türü", ["teknik_ister", "takim_yapisi", "danisman_kurali", "ozgunluk_ve_intihal", "diger"])
                nr_desc = st_ctx.text_area("Kural Açıklaması", placeholder="Kuralın detaylı tanımı...")
                
                sub_nr = st_ctx.form_submit_button("Yeni Kuralı Ekle", type="primary")
                if sub_nr:
                    if nr_title:
                        mevcut_kurallar.append({
                            "rule_type": nr_type,
                            "title": nr_title.strip(),
                            "description": nr_desc.strip(),
                            "min_team_size": 1,
                            "max_team_size": 6,
                            "advisor_required": 0,
                            "is_mandatory": 1
                        })
                        db.save_competition_requirements_bulk(comp_slug, mevcut_kurallar)
                        st_ctx.success("Yeni kural eklendi!")
                        st_ctx.rerun()

    # -------------------------------------------------------------------------
    # TAB 3: AŞAMALAR & ŞABLON RUBRİK YÖNETİMİ
    # -------------------------------------------------------------------------
    with tab_asamalar:
        st_ctx.markdown("##### Aşamalar, Şablon Yükleme ve AI Puanlama Rubriği (0-100)")
        
        mevcut_asamalar = db.list_competition_stages(comp_slug)

        # Yeni Aşama Ekleme Butonu & Formu
        with st_ctx.expander("+ Bu Yarışmaya Yeni Aşama Ekle (ÖTR, KTR vb.)"):
            with st_ctx.form(f"form_add_stage_{comp_slug}"):
                as1, as2, as3 = st_ctx.columns(3)
                with as1:
                    new_stage_code = st_ctx.text_input("Aşama Kodu *", placeholder="Örn: OTR, KTR, FTR").upper().strip()
                with as2:
                    new_stage_name = st_ctx.text_input("Aşama Adı *", placeholder="Örn: Ön Tasarım Raporu")
                with as3:
                    new_stage_deadline = st_ctx.text_input("Son Teslim Tarihi", value="15.04.2026")

                sub_stg = st_ctx.form_submit_button("Aşamayı Oluştur", type="primary")
                if sub_stg:
                    if new_stage_code and new_stage_name:
                        db.upsert_competition_stage({
                            "competition_id": comp_slug,
                            "stage_code": new_stage_code,
                            "stage_name": new_stage_name,
                            "deadline": new_stage_deadline
                        })
                        st_ctx.success(f"{new_stage_code} aşaması oluşturuldu!")
                        st_ctx.rerun()

        if not mevcut_asamalar:
            st_ctx.info("Bu yarışma için henüz aşama tanımlanmamış. Yukarıdan yeni aşama ekleyebilirsiniz.")
        else:
            for stg in mevcut_asamalar:
                s_code = stg.get("stage_code", "OTR")
                s_name = stg.get("stage_name", "")
                s_dead = stg.get("deadline", "—")

                with st_ctx.container(border=True):
                    st_ctx.markdown(f"#### Aşama: **{s_code} - {s_name}** (Son Teslim: {s_dead})")
                    
                    col_u1, col_u2 = st_ctx.columns([2, 1])
                    with col_u1:
                        stg_file = st_ctx.file_uploader(
                            f"{s_code} Şablon Dosyası (.docx veya .pdf)",
                            type=["docx", "pdf"],
                            key=f"upl_stg_file_{comp_slug}_{s_code}"
                        )
                    with col_u2:
                        st_ctx.markdown("<br>", unsafe_allow_html=True)
                        if st_ctx.button(f"{s_code} Aşamayı Tamamen Sil", key=f"del_stg_btn_{comp_slug}_{s_code}"):
                            db.delete_competition_stage(comp_slug, s_code)
                            st_ctx.warning(f"{s_code} aşaması silindi.")
                            st_ctx.rerun()

                    if stg_file is not None:
                        if st_ctx.button(f"Şablonu Yükle, Word ➔ PDF Bas ve AI Rubrik Çıkar ({s_code})", type="primary", key=f"btn_proc_stg_{comp_slug}_{s_code}"):
                            with st_ctx.spinner("Word dosyası orijinal PDF'e dönüştürülüyor ve R2'ye yükleniyor..."):
                                file_bytes = stg_file.getvalue()
                                file_ext = Path(stg_file.name).suffix.lower()
                                base_clean_name = f"{comp_slug}_{s_code.lower()}_rapor_sablonu"
                                
                                temp_source = Path(f"data/temp_{base_clean_name}{file_ext}")
                                temp_source.parent.mkdir(parents=True, exist_ok=True)
                                temp_source.write_bytes(file_bytes)

                                docx_r2_key = ""
                                pdf_r2_key = ""

                                if file_ext == ".docx":
                                    # 1. DOCX'i R2'ye yükle
                                    r2_docx_name = f"sablonlar/{comp_slug}/{s_code.lower()}/{base_clean_name}.docx"
                                    r2_service.upload_file(file_bytes, r2_docx_name, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
                                    docx_r2_key = r2_docx_name

                                    # 2. %100 Orijinal PDF Üret
                                    pdf_path = docx_to_pdf(temp_source)
                                    if pdf_path and pdf_path.exists():
                                        r2_pdf_name = f"sablonlar/{comp_slug}/{s_code.lower()}/{base_clean_name}.pdf"
                                        r2_service.upload_file(pdf_path.read_bytes(), r2_pdf_name, "application/pdf")
                                        pdf_r2_key = r2_pdf_name
                                        if pdf_path.exists():
                                            pdf_path.unlink()
                                else:
                                    # PDF Yüklendiyse
                                    r2_pdf_name = f"sablonlar/{comp_slug}/{s_code.lower()}/{base_clean_name}.pdf"
                                    r2_service.upload_file(file_bytes, r2_pdf_name, "application/pdf")
                                    pdf_r2_key = r2_pdf_name

                                # 3. AI Rubrik Çıkarımı (0-100 Puan)
                                tpl_analysis = template_analyzer.analyze_template(str(temp_source), s_code)
                                if temp_source.exists():
                                    temp_source.unlink()

                                # 4. D1 Veritabanı Kaydı
                                db.upsert_competition_stage({
                                    "competition_id": comp_slug,
                                    "stage_code": s_code,
                                    "stage_name": s_name,
                                    "sablon_docx_url": docx_r2_key,
                                    "sablon_pdf_url": pdf_r2_key,
                                    "deadline": s_dead
                                })
                                db.save_competition_rubrics_bulk(comp_slug, s_code, tpl_analysis.get("rubrics", []))

                                st_ctx.success(f"{s_code} şablonu başarıyla PDF'e dönüştürüldü ve 0-100 rubrik kriterleri çıkarıldı!")
                                st_ctx.rerun()

                    # Aşama Puanlama Rubriği (0-100) Form Üzerinden Güvenli Düzenleme
                    mevcut_rubrik = db.list_competition_rubrics(comp_slug, s_code)
                    st_ctx.markdown(f"###### {s_code} Değerlendirme & Puanlama Rubriği (Toplam Puan: 100)")
                    
                    if mevcut_rubrik:
                        with st_ctx.form(f"form_rubric_editor_{comp_slug}_{s_code}"):
                            rub_duzenleme_listesi = []
                            toplam_puan = 0.0
                            for r_idx, rub in enumerate(mevcut_rubrik, 1):
                                r_col1, r_col2, r_col3 = st_ctx.columns([3, 1.2, 0.8])
                                with r_col1:
                                    r_name = st_ctx.text_input(f"Kriter Başlığı #{r_idx}", value=rub.get("criterion_name", ""), key=f"rub_name_{comp_slug}_{s_code}_{r_idx}")
                                    r_desc = st_ctx.text_input(f"Açıklama #{r_idx}", value=rub.get("description", ""), key=f"rub_desc_{comp_slug}_{s_code}_{r_idx}")
                                with r_col2:
                                    r_score = st_ctx.number_input(f"Puan Değeri #{r_idx}", min_value=1.0, max_value=100.0, value=float(rub.get("max_score", 20.0)), step=1.0, key=f"rub_score_{comp_slug}_{s_code}_{r_idx}")
                                    toplam_puan += r_score
                                with r_col3:
                                    st_ctx.markdown("<br>", unsafe_allow_html=True)
                                    r_sil = st_ctx.checkbox("Sil", key=f"rub_del_{comp_slug}_{s_code}_{r_idx}")

                                if not r_sil:
                                    rub_duzenleme_listesi.append({
                                        "criterion_code": rub.get("criterion_code") or f"C{r_idx}",
                                        "criterion_name": r_name.strip(),
                                        "description": r_desc.strip(),
                                        "max_score": r_score,
                                        "order_index": r_idx
                                    })

                            st_ctx.markdown("<hr style='margin:10px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                            if toplam_puan == 100.0:
                                st_ctx.markdown(f"<span style='color:#16A34A; font-weight:750;'>Toplam Puan: {toplam_puan} / 100 (Kusursuz)</span>", unsafe_allow_html=True)
                            else:
                                st_ctx.markdown(f"<span style='color:#DC2626; font-weight:750;'>Uyarı: Toplam Puan {toplam_puan} / 100 (Toplamın 100 olması önerilir)</span>", unsafe_allow_html=True)

                            btn_save_rubrics = st_ctx.form_submit_button(f"{s_code} Rubrik Değişikliklerini Kaydet", type="primary")
                            if btn_save_rubrics:
                                db.save_competition_rubrics_bulk(comp_slug, s_code, rub_duzenleme_listesi)
                                st_ctx.success(f"{s_code} rubrik kriterleri başarıyla kaydedildi!")
                                st_ctx.rerun()

    # -------------------------------------------------------------------------
    # TAB 4: YARIŞMAYI SİL
    # -------------------------------------------------------------------------
    with tab_sil:
        st_ctx.markdown("##### Yarışmayı Tamamen Sil")
        st_ctx.warning(f"Dikkat: '{comp_name}' yarışmasını ve bağlı tüm şartname, aşama, şablon ve kurallarını silmek üzeresiniz. Bu işlem geri alınamaz!")
        if st_ctx.button(f"Evet, '{comp_name}' Yarışmasını Tamamen Sil", type="primary"):
            db.delete_competition(comp_slug)
            st_ctx.session_state.admin_selected_comp_id = None
            st_ctx.success("Yarışma başarıyla silindi.")
            st_ctx.rerun()


def _hakem_yonlendirme_paneli(st_ctx) -> None:
    """Hakem Havuzu, Rapor Havuzu ve Rapor Yönlendirme Paneli."""
    st_ctx.markdown("#### Hakem & Rapor Havuzu Yönlendirme İstasyonu")
    
    # Raporlar ve Hakemleri Listele
    tum_raporlar = db.execute_d1("SELECT * FROM reports ORDER BY created_at DESC;") or []
    tum_hakemler = db.execute_d1("SELECT email, name, surname FROM auth_users WHERE role = 'referee' OR role = 'hakem';") or []

    if not tum_raporlar:
        st_ctx.info("Sistemde henüz yarışmacılar tarafından yüklenmiş bir rapor bulunmamaktadır.")
        return

    st_ctx.markdown(f"##### Gelen Raporlar Havuzu ({len(tum_raporlar)} Adet)")
    
    for rep in tum_raporlar:
        rep_id = rep.get("report_id", "")
        c_id = rep.get("competition_id", "")
        stg_c = rep.get("stage_code", "")
        f_name = rep.get("file_name", "")
        durum = rep.get("status", "Beklemede")

        with st_ctx.container(border=True):
            col_rp1, col_rp2, col_rp3 = st_ctx.columns([3, 2, 1.5])
            with col_rp1:
                st_ctx.markdown(f"**{f_name}**")
                st_ctx.caption(f"Yarışma: `{c_id}` | Aşama: `{stg_c}`")
            with col_rp2:
                st_ctx.markdown(f"Durum: **{durum}**")
            with col_rp3:
                if tum_hakemler:
                    secili_hakem = st_ctx.selectbox("Hakem Ata", [f"{h['name']} {h['surname']} ({h['email']})" for h in tum_hakemler], key=f"sel_ref_{rep_id}")
                    if st_ctx.button("Hakeme Yönlendir", key=f"btn_assign_{rep_id}", type="primary", use_container_width=True):
                        ref_email = secili_hakem.split("(")[-1].rstrip(")")
                        db.assign_report_to_referee(rep_id, ref_email)
                        st_ctx.success("Rapor başarıyla hakeme atandı!")
                        st_ctx.rerun()
                else:
                    st_ctx.caption("Kayıtlı hakem bulunamadı.")
