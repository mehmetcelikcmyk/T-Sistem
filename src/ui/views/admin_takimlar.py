"""T-Sistem · Admin Takım Yönetim Paneli.

Cloudflare D1 ve SQLite üzerindeki tüm takımları listeler, üyelerini,
kaptanlarını, seviyelerini görüntüler, düzenler ve yönetir.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from src.data import repos
from i18n import t


def render() -> None:
    """Admin Takım Yönetimi arayüzünü render eder."""
    lang = st.session_state.get("lang", "tr")

    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">Takım Yönetim Merkezi</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                Sistemde kayıtlı tüm takımları, takım kodlarını, kaptanları ve üyeleri görüntüleyin ve yönetin.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    try:
        r_teams = repos().teams
        all_teams = r_teams.list_all(include_disbanded=True)
    except Exception as e:
        st.error(f"Takımlar yüklenirken hata oluştu: {e}")
        all_teams = []

    toplam_takim = len(all_teams)
    aktif_takim = len([t for t in all_teams if getattr(t, "status", "aktif") != "dagitildi"])
    lise_takim = len([t for t in all_teams if "lise" in str(getattr(t, "level", "")).lower()])
    uni_takim = len([t for t in all_teams if "lisans" in str(getattr(t, "level", "")).lower() or "üniversite" in str(getattr(t, "level", "")).lower()])

    # Metrik Kartları
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Toplam Takım</div>
                <div class="ts-metric-val">{toplam_takim}</div>
                <div class="ts-metric-sub">Kayıtlı Tüm Takımlar</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Aktif Takım</div>
                <div class="ts-metric-val">{aktif_takim}</div>
                <div class="ts-metric-sub">Faal Takımlar</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Üniversite / Lisans</div>
                <div class="ts-metric-val">{uni_takim}</div>
                <div class="ts-metric-sub">Yükseköğretim</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Lise & Diğer</div>
                <div class="ts-metric-val">{lise_takim}</div>
                <div class="ts-metric-sub">Ortaöğretim & Mezun</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    if not all_teams:
        st.info("Sistemde henüz kayıtlı takım bulunmamaktadır.")
        return

    # Arama ve Filtre
    f_col1, f_col2 = st.columns([3, 1])
    with f_col1:
        search_query = st.text_input("🔍 Takım Adı veya Davet Kodu ile Ara", placeholder="Aramak için takım adı veya 6 haneli davet kodunu girin...").strip().lower()
    with f_col2:
        level_filter = st.selectbox("Seviye Filtresi", ["Tümü", "Ön Lisans / Lisans", "Lise", "Ortaokul", "İlkokul", "Mezun"])

    filtered_teams = all_teams
    if search_query:
        filtered_teams = [
            t for t in filtered_teams
            if search_query in str(getattr(t, "name", "")).lower()
            or search_query in str(getattr(t, "team_code", "")).lower()
            or search_query in str(getattr(t, "team_id", "")).lower()
        ]

    if level_filter != "Tümü":
        filtered_teams = [
            t for t in filtered_teams
            if level_filter.lower() in str(getattr(t, "level", "")).lower()
        ]

    tablo_verisi = []
    for tm in filtered_teams:
        tablo_verisi.append({
            "Takım ID": getattr(tm, "team_id", ""),
            "Takım Adı": getattr(tm, "name", ""),
            "Davet Kodu": getattr(tm, "team_code", ""),
            "Seviye": getattr(tm, "level", "Genel"),
            "Kurum": getattr(tm, "institution", "") or "-",
            "Danışman": getattr(tm, "advisor_name", "") or "-",
            "Durum": str(getattr(tm, "status", "aktif")).upper(),
            "Oluşturulma": str(getattr(tm, "created_at", ""))[:10] if getattr(tm, "created_at", "") else "-",
        })

    df = pd.DataFrame(tablo_verisi)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### Takım Detayları ve Üye Yönetimi")

    team_options = {f"{getattr(t, 'name', '')} (Kod: {getattr(t, 'team_code', '')}) · [{getattr(t, 'level', '')}]": t for t in filtered_teams}
    if team_options:
        secilen_etiket = st.selectbox("Detayını ve Üyelerini Görmek İstediğiniz Takımı Seçin", list(team_options.keys()))
        if secilen_etiket:
            secilen_team = team_options[secilen_etiket]
            team_id = getattr(secilen_team, "team_id", "")
            current_status = str(getattr(secilen_team, "status", "aktif")).lower()

            with st.container(border=True):
                head_col1, head_col2 = st.columns([3, 1.5])
                with head_col1:
                    st.markdown(f"### `{getattr(secilen_team, 'name', '')}`")
                    st.caption(f"Takım ID: `{team_id}` &nbsp;·&nbsp; Davet Kodu: **{getattr(secilen_team, 'team_code', '-')}** &nbsp;·&nbsp; Seviye: **{getattr(secilen_team, 'level', '-')}**")
                
                with head_col2:
                    st.markdown("**Takım Durumu / Faaliyet:**")
                    durum_opts = ["aktif", "pasif", "dagitildi"]
                    durum_labels = {"aktif": "🟢 AKTİF", "pasif": "🟡 PASİF / ASKIYA AL", "dagitildi": "🔴 DAĞITILDI"}
                    curr_idx = durum_opts.index(current_status) if current_status in durum_opts else 0
                    
                    yeni_durum = st.selectbox(
                        "Durum Seç",
                        durum_opts,
                        index=curr_idx,
                        format_func=lambda x: durum_labels.get(x, x.upper()),
                        key=f"team_stat_sel_{team_id}",
                        label_visibility="collapsed"
                    )
                    
                    if yeni_durum != current_status:
                        if st.button("Durumu Kaydet", key=f"btn_save_stat_{team_id}", type="primary", use_container_width=True):
                            try:
                                from src.data.enums import TeamStatus
                                repos().teams.update(team_id, {"status": TeamStatus(yeni_durum)})
                                st.success(f"Takım durumu '{durum_labels.get(yeni_durum)}' olarak güncellendi.")
                                st.rerun()
                            except Exception as ex_st:
                                st.error(f"Durum güncellenirken hata oluştu: {ex_st}")

                st.markdown("<hr style='margin:12px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)

                # TAB 1: ÜYE YÖNETİMİ & TAB 2: BAŞVURU VE RAPORLAR & TAB 3: BİLGİ DÜZENLE
                t_tab1, t_tab2, t_tab3 = st.tabs(["👥 Takım Üyeleri", "📄 Başvuru & Raporlar", "✏️ Takım Bilgilerini Düzenle"])

                with t_tab1:
                    try:
                        members = repos().teams.members(team_id)
                    except Exception as ex_m:
                        st.warning(f"Üyeler çekilemedi: {ex_m}")
                        members = []

                    st.markdown(f"##### Takım Kadrosu ({len(members)} Kişi)")
                    if members:
                        member_rows = []
                        for m, u in members:
                            member_rows.append({
                                "Rol": getattr(m, "role_in_team", "").upper(),
                                "Kullanıcı ID": getattr(m, "user_id", ""),
                                "Ad Soyad": getattr(u, "name", getattr(u, "full_name", "-")) if u else "-",
                                "E-Posta": getattr(u, "email", "-") if u else "-",
                                "Kurum": getattr(u, "institution", "-") if u else "-",
                                "Katılma Tarihi": str(getattr(m, "joined_at", ""))[:10] if getattr(m, "joined_at", "") else "-"
                            })
                        df_m = pd.DataFrame(member_rows)
                        st.dataframe(df_m, use_container_width=True, hide_index=True)

                        # Üye Çıkarma Yetkisi
                        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
                        with st.expander("⚠️ Takımdan Üye Çıkar"):
                            cikarilabilir_uyeler = {f"{getattr(u, 'full_name', getattr(u, 'name', m.user_id))} ({getattr(m, 'role_in_team', '')})": m.user_id for m, u in members if str(getattr(m, 'role_in_team', '')).lower() != "kaptan"}
                            if cikarilabilir_uyeler:
                                secili_u_etiket = st.selectbox("Çıkarılacak Üye", list(cikarilabilir_uyeler.keys()), key=f"sel_rem_u_{team_id}")
                                if st.button("Seçili Üyeyi Takımdan Çıkar", key=f"btn_rem_u_{team_id}", type="secondary"):
                                    u_id_to_rem = cikarilabilir_uyeler[secili_u_etiket]
                                    try:
                                        repos().teams.remove_member(team_id, u_id_to_rem)
                                        st.success("Üye takımdan çıkarıldı.")
                                        st.rerun()
                                    except Exception as ex_rem:
                                        st.error(f"Üye çıkarılırken hata oluştu: {ex_rem}")
                            else:
                                st.caption("Kaptan dışındaki üyeler takımdan çıkarılabilir.")
                    else:
                        st.info("Bu takıma kayıtlı üye bulunmuyor.")

                with t_tab2:
                    try:
                        apps = repos().applications.list_for_team(team_id) if hasattr(repos().applications, 'list_for_team') else []
                    except Exception:
                        apps = []

                    st.markdown(f"##### Takımın Yarışma Başvuruları ({len(apps)})")
                    if apps:
                        app_rows = []
                        for ap in apps:
                            app_rows.append({
                                "Başvuru ID": getattr(ap, "app_id", ""),
                                "Yarışma ID": getattr(ap, "competition_id", ""),
                                "Dal": getattr(ap, "branch_code", "-") or "-",
                                "Durum": str(getattr(ap, "status", "")).upper(),
                                "Tarih": str(getattr(ap, "created_at", ""))[:10] if getattr(ap, "created_at", "") else "-"
                            })
                        st.dataframe(pd.DataFrame(app_rows), use_container_width=True, hide_index=True)
                    else:
                        st.caption("Bu takımın henüz kayıtlı aktif yarışma başvurusu bulunmuyor.")

                with t_tab3:
                    st.markdown("##### Takım Bilgilerini Güncelle")
                    with st.form(f"form_edit_team_{team_id}"):
                        e_name = st.text_input("Takım Adı", value=getattr(secilen_team, "name", ""))
                        e_inst = st.text_input("Kurum / Okul", value=getattr(secilen_team, "institution", "") or "")
                        e_adv_name = st.text_input("Danışman Adı", value=getattr(secilen_team, "advisor_name", "") or "")
                        e_adv_email = st.text_input("Danışman E-Posta", value=getattr(secilen_team, "advisor_email", "") or "")
                        
                        if st.form_submit_button("Bilgileri Kaydet", type="primary"):
                            try:
                                repos().teams.update(team_id, {
                                    "name": e_name.strip(),
                                    "institution": e_inst.strip() or None,
                                    "advisor_name": e_adv_name.strip() or None,
                                    "advisor_email": e_adv_email.strip() or None,
                                })
                                st.success("Takım bilgileri başarıyla güncellendi.")
                                st.rerun()
                            except Exception as ex_edt:
                                st.error(f"Güncelleme başarısız: {ex_edt}")
