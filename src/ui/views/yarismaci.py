"""T-Sistem · Yarışmacı (Üye) Portalı — repos() Veri Katmanı.

app.py bu modülden 3 ayrı fonksiyon çağırır:
  render_vitrin(st_ctx, current_user, lang)     → Ana Sayfa: Yarışma Vitrini
  render_basvurular(st_ctx, current_user, lang) → Başvurularım & Karne
  render_takimlar(st_ctx, current_user, lang)   → Takımlarım
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from html import escape as _esc
from typing import Any, Dict, List

import streamlit as st

from src.data import (
    DataError,
    DuplicateRecord,
    Keys,
    RecordNotFound,
    StorageError,
    days_left,
    repos,
)
from src.ui.i18n import t
try:
    from src.ui import sartname_rehber
except ImportError:
    import sartname_rehber


# ─── Yardımcılar ─────────────────────────────────────────────────────────────

def _attr(obj: Any, key: str, default: Any = "") -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _schedule(comp: Any) -> Dict[str, str]:
    raw = _attr(comp, "schedule_json", None) or _attr(comp, "schedule", None)
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    return {}


def _days_badge(date_str: str, lang: str) -> str:
    if not date_str or date_str == "—":
        return ""
    n = days_left(date_str)
    if n is None:
        return ""
    if n <= 0:
        color, label = "#DC2626", t("badge_expired", lang)
    elif n <= 7:
        color, label = "#F04823", f"{n} {t('badge_days_left', lang)}"
    else:
        color, label = "#16A34A", f"{n} {t('badge_days_left', lang)}"
    return (
        f"<span style='font-size:.75rem;font-weight:700;color:{color};"
        f"background:{color}22;padding:2px 8px;border-radius:6px;'>{label}</span>"
    )


def _status_badge(status: str, lang: str) -> str:
    s = str(status).lower()
    if any(w in s for w in ("tamamlan", "değerlendirildi", "degerlendirildi", "done", "complete", "başarılı", "basarili", "gecti", "geçti", "onaylandı")):
        cls, lbl = "t3-badge-aktif", t("status_done", lang)
    elif any(w in s for w in ("hakem", "atand", "assigned", "review")):
        cls, lbl = "t3-badge-aktif", t("status_assigned", lang)
    elif any(w in s for w in ("ret", "reddedil", "reject", "başarısız", "basarisiz", "kaldi")):
        cls, lbl = "t3-badge-ret", t("status_rejected", lang)
    else:
        cls, lbl = "t3-badge-turuncu", t("status_waiting", lang)
    return f"<span class='{cls}'>{lbl}</span>"


@st.cache_data(ttl=300, show_spinner=False)
def _all_competitions() -> List[Any]:
    try:
        return repos().competitions.list() or []
    except Exception:
        return []


@st.cache_data(ttl=300, show_spinner=False)
def _get_competition_details_cached(slug: str) -> Dict[str, Any]:
    """Sadece 'Detaylar' tıklandığında Cloudflare D1'den şartname ve aşamaları çeker (Lazy Load)."""
    r = repos()
    comp = r.competitions.get(slug)
    specs = r.competitions.list_specs(slug)
    stages = r.competitions.list_stages(slug)
    
    # Kriter sayıları
    stage_info = []
    for stg in stages:
        crits = r.competitions.list_rubric(slug, stg.stage_code)
        sablon_url = r.storage.url_for(stg.sablon_docx_r2_key) if stg.sablon_docx_r2_key else ""
        stage_info.append({
            "code": stg.stage_code,
            "name": stg.stage_name or stg.stage_code,
            "max_pages": stg.max_pages,
            "max_score": stg.max_score,
            "criteria_count": len(crits),
            "sablon_url": sablon_url,
            "sablon_name": stg.sablon_docx_r2_key.split('/')[-1] if stg.sablon_docx_r2_key else ""
        })
        
    spec_info = []
    for sp in specs:
        s_url = r.storage.url_for(sp.r2_key) if sp.r2_key else ""
        spec_info.append({
            "title": sp.title or sp.original_name or "Şartname",
            "url": s_url,
            "branch": sp.branch_code
        })
        
    return {
        "comp": comp,
        "specs": spec_info,
        "stages": stage_info
    }


def _team_id(team: Any) -> str:
    return str(_attr(team, "team_id", _attr(team, "id", "")))


def _team_code(team: Any) -> str:
    return str(_attr(team, "team_code", _attr(team, "kod", _attr(team, "code", ""))))


def _team_year(team: Any) -> str:
    raw = str(_attr(team, "created_at", "") or "")
    if len(raw) >= 4 and raw[:4].isdigit():
        return raw[:4]
    y = str(_attr(team, "founded_year", "") or "")
    return y[:4] if y else str(datetime.date.today().year)


def _avatar(name: str, size: int = 36) -> str:
    name = str(name or "?").strip()
    parts = name.split()
    if len(parts) >= 2:
        ini = (parts[0][0] + parts[1][0]).upper()
    elif len(name) >= 2:
        ini = name[:2].upper()
    else:
        ini = name.upper()
    palette = ["#EF4444", "#3B82F6", "#8B5CF6", "#0EA5E9", "#D97706", "#DB2777", "#10B981"]
    col = palette[sum(ord(c) for c in name) % len(palette)]
    fs = max(11, size // 3)
    return (
        f'<div style="display:inline-flex;align-items:center;justify-content:center;'
        f'width:{size}px;height:{size}px;border-radius:50%;background:{col};'
        f'color:#FFF;font-size:{fs}px;font-weight:800;flex-shrink:0;">'
        f'{_esc(ini)}</div>'
    )


def _pill(label: str, tone: str = "primary") -> str:
    colors = {
        "primary": ("#F04823", "#FFF"),
        "blue": ("#2563EB", "#FFF"),
        "green": ("#16A34A", "#FFF"),
        "gray": ("#64748B", "#FFF"),
    }
    bg, fg = colors.get(tone, colors["gray"])
    return (
        f'<span style="display:inline-flex;align-items:center;padding:3px 12px;'
        f'border-radius:999px;font-size:.76rem;font-weight:800;background:{bg};'
        f'color:{fg};">{_esc(label)}</span>'
    )


def _sep(st_ctx) -> None:
    st_ctx.markdown('<div style="border-bottom:1px solid #E2E8F0;margin:8px 0;"></div>', unsafe_allow_html=True)


def _send_advisor_email(
    st_ctx,
    team: Any,
    team_name: str,
    team_code: str,
    adv_name: str,
    adv_email: str,
    captain_name: str,
) -> None:
    """Danışmana takım davet maili gönderir — auth_service SMTP üzerinden."""
    if not adv_email or "@" not in adv_email:
        return
    ok, msg = auth_service.send_team_advisor_email(
        advisor_email=adv_email,
        advisor_name=adv_name or "Danışman",
        team_name=team_name,
        team_code=team_code,
        captain_name=captain_name,
    )
    if ok:
        st_ctx.info(f"Danışman daveti **{adv_email}** adresine gönderildi.")
    else:
        st_ctx.caption(
            f"Mail gönderilemedi ({msg}). "
            f"Danışmana davet kodunu ({team_code}) kendiniz iletebilirsiniz."
        )


def _send_mail(st_ctx, to: str, subject: str, html_body: str, silent: bool = False) -> bool:
    """Genel amaçlı mail yardımcısı — auth_service SMTP altyapısını kullanır."""
    if not to or "@" not in to:
        return False
    ok, msg = auth_service._send_smtp(to, subject, html_body)
    if not ok and not silent:
        st_ctx.warning(f"Mail uyarısı: {msg}")
    return ok


# ─── 1. render_vitrin ────────────────────────────────────────────────────────

def render_yarisma_detay_sayfasi(st_ctx, detail_slug: str, current_user: dict, lang: str = "tr") -> None:
    """Seçili yarışmaya ait tam sayfa resmî şartname, aşamalar, şablonlar ve başvuru portalı."""
    from src.ui.views import competition_detail_view
    competition_detail_view.render_competition_detail_page(detail_slug, is_authenticated=True)


def render_vitrin(st_ctx, current_user: dict, lang: str = "tr") -> None:
    """TEKNOFEST yarışma vitrini — arama/filtre + kart grid veya tam sayfa detay."""

    # Eğer bir yarışmanın detayları istendiyse -> DEDİKATED TAM SAYFA AÇ
    detail_slug = st_ctx.session_state.get("view_detail_slug") or (st_ctx.query_params.get("slug") if st_ctx.query_params.get("view") == "comp" else None)
    if detail_slug:
        render_yarisma_detay_sayfasi(st_ctx, detail_slug, current_user, lang)
        return

    st_ctx.markdown(f"##### {t('yar_vitrin_title', lang)}")
    st_ctx.caption(t("yar_vitrin_cap", lang))

    f1, f2, f3 = st_ctx.columns([2, 1.5, 1.5])
    with f1:
        arama = st_ctx.text_input(
            t("yar_search_lbl", lang),
            placeholder=t("yar_search_ph", lang),
            key="yarismaci_arama_bar",
            label_visibility="collapsed",
        )
    with f2:
        alan_opts = [
            t("yar_filter_all_domains", lang),
            t("yar_domain_hava", lang), t("yar_domain_yapay", lang),
            t("yar_domain_otonom", lang), t("yar_domain_saglik", lang),
            t("yar_domain_enerji", lang), t("yar_domain_insanlik", lang),
        ]
        y_alan = st_ctx.selectbox(t("yar_filter_domain", lang), alan_opts,
                                   key="yarismaci_alan_filtre", label_visibility="collapsed")
    with f3:
        sev_opts = [
            t("yar_filter_all_levels", lang),
            t("yar_level_ilkokul", lang), t("yar_level_ortaokul", lang),
            t("yar_level_lise", lang), t("yar_level_lisans", lang),
            t("yar_level_yuksek", lang), t("yar_level_mezun", lang),
        ]
        y_sev = st_ctx.selectbox(t("yar_filter_level", lang), sev_opts,
                                  key="yarismaci_seviye_filtre", label_visibility="collapsed")

    all_comps = _all_competitions()
    gosterilecek = [
        c for c in all_comps
        if (not arama or arama.lower() in _attr(c, "name", "").lower())
        and (y_alan == alan_opts[0] or y_alan == _attr(c, "domain", ""))
        and (y_sev == sev_opts[0] or y_sev in (_attr(c, "levels", "") or ""))
    ]

    st_ctx.markdown(f"**{t('yar_count_prefix', lang)} {len(gosterilecek)} {t('yar_count_suffix', lang)}**")

    # 3'lü Grid Tasarımı — Hızlı Yükleme & Buton Kartın İçinde Bütünleşik Tasarım
    st_ctx.markdown("""
    <style>
        .ts-comp-card {
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
            padding: 20px 18px 16px 18px;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: space-between;
            min-height: 335px;
            position: relative;
            margin-bottom: 20px;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }
        .ts-comp-card:hover {
            transform: translateY(-3px);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.09);
        }
        .ts-corner-ribbon {
            position: absolute;
            top: 0;
            right: 18px;
            background: #991B1B;
            color: #FFFFFF;
            padding: 4px 10px;
            font-size: 0.70rem;
            font-weight: 800;
            border-radius: 0 0 6px 6px;
            text-align: center;
            box-shadow: 0 2px 6px rgba(153, 27, 27, 0.35);
        }
        .ts-comp-card-btn {
            width: 100%;
            background: linear-gradient(135deg, #F04823 0%, #D63713 100%);
            color: #FFFFFF !important;
            text-decoration: none !important;
            font-weight: 800;
            font-size: 0.88rem;
            padding: 10px 16px;
            border-radius: 8px;
            text-align: center;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 3px 12px rgba(240, 72, 35, 0.25);
            transition: all 0.18s ease;
            cursor: pointer;
            margin-top: 10px;
        }
        .ts-comp-card-btn:hover {
            background: linear-gradient(135deg, #FF5733 0%, #E03E1B 100%);
            transform: translateY(-1px);
            box-shadow: 0 5px 18px rgba(240, 72, 35, 0.4);
            color: #FFFFFF !important;
        }
    </style>
    """, unsafe_allow_html=True)

    for i in range(0, len(gosterilecek), 3):
        row = gosterilecek[i: i + 3]
        cols = st_ctx.columns(3)
        for idx, comp in enumerate(row):
            with cols[idx]:
                slug = _attr(comp, "slug", "")
                name = _attr(comp, "name", "")
                is_featured = (idx % 2 == 0)

                logo_b64 = sartname_rehber.kategori_logosu_base64_getir(slug)
                if logo_b64:
                    logo_html = f'<img src="{logo_b64}" style="max-height:115px; max-width:140px; object-fit:contain;" alt="{_esc(name)}"/>'
                else:
                    logo_html = (
                        '<div style="width:105px; height:105px; border-radius:16px;'
                        'background:linear-gradient(135deg, #F1F5F9, #E2E8F0); display:flex; align-items:center;'
                        'justify-content:center; font-weight:900; font-size:1.4rem; color:#64748B;">TF</div>'
                    )

                ribbon_html = '<div class="ts-corner-ribbon">★<br/>Yeni</div>' if is_featured else ''

                st_ctx.html(
                    f"""
                    <div class="ts-comp-card">
                        {ribbon_html}
                        <div style="height:120px; display:flex; align-items:center; justify-content:center; width:100%; margin-top:4px;">
                            {logo_html}
                        </div>
                        <div style="font-size:0.96rem; font-weight:800; color:#1E293B; text-align:center; line-height:1.35; min-height:46px; display:flex; align-items:center; justify-content:center; padding:0 4px; margin: 8px 0;">
                            {_esc(name)}
                        </div>
                        <a href="?view=comp&slug={slug}" class="ts-comp-card-btn">
                            › Şartname & Detaylar
                        </a>
                    </div>
                    """
                )


# ─── 2. _render_new_app_modal & render_basvurular ───────────────────────────

def _render_new_app_modal(st_ctx, current_user: dict, lang: str = "tr", preselected_slug: str | None = None) -> None:
    """Yeni yarışma başvurusu formu: Yarışma seçimi, takım seçimi/oluşturma ve Cloudflare D1 kaydı."""
    uid = str(current_user.get("user_id", ""))
    u_name = str(current_user.get("name", "Yarışmacı"))
    u_inst = str(current_user.get("institution", ""))

    all_comps = _all_competitions()
    if not all_comps:
        st_ctx.warning("Yarışma listesi yüklenemedi. Lütfen daha sonra tekrar deneyiniz.")
        return

    comp_map = {str(_attr(c, "slug", "")): c for c in all_comps}
    comp_names = {str(_attr(c, "slug", "")): str(_attr(c, "name", _attr(c, "slug", ""))) for c in all_comps}
    slug_list = list(comp_map.keys())

    # Varsayılan yarışma indeksi
    default_idx = 0
    if preselected_slug:
        if preselected_slug in slug_list:
            default_idx = slug_list.index(preselected_slug)
        else:
            for s_idx, s_val in enumerate(slug_list):
                if s_val.lower().replace("_", "-") == preselected_slug.lower().replace("_", "-"):
                    default_idx = s_idx
                    break
        st_ctx.session_state["sel_app_comp_slug"] = slug_list[default_idx]

    # Kullanıcının mevcut takımları
    user_teams = []
    try:
        user_teams = repos().teams.list_for_user(uid) or []
    except Exception:
        pass

    with st_ctx.container(border=True):
        st_ctx.markdown(
            """
            <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">
                <div style="font-size:1.15rem; font-weight:850; color:#0F172A;">
                    TEKNOFEST 2026 Yarışma Başvuru Formu
                </div>
                <span style="background:#DCFCE7; color:#15803D; font-weight:800; font-size:0.75rem; padding:3px 10px; border-radius:6px;">
                    Cloudflare D1 Canlı Kayıt
                </span>
            </div>
            """,
            unsafe_allow_html=True
        )

        with st_ctx.form("form_yeni_yarisma_basvurusu", clear_on_submit=False):
            # 1. Yarışma Seçimi
            sel_slug = st_ctx.selectbox(
                "Başvurulacak Yarışma Kategorisi *",
                options=slug_list,
                index=default_idx,
                format_func=lambda s: comp_names.get(s, s),
                key="sel_app_comp_slug"
            )
            selected_comp = comp_map.get(sel_slug)
            comp_name = _attr(selected_comp, "name", sel_slug)

            # 2. Takım Seçimi
            st_ctx.markdown("<hr style='margin:12px 0 8px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E293B; margin-bottom:6px;'>Takım Belirleme</div>", unsafe_allow_html=True)

            team_options = ["Yeni Takım Oluştur ve Başvur"]
            team_id_map = {}
            for tm in user_teams:
                t_id = str(_attr(tm, "team_id", _attr(tm, "id", "")))
                t_name = str(_attr(tm, "name", "Takım"))
                t_code = str(_attr(tm, "team_code", ""))
                opt_label = f"{t_name} (Kod: {t_code})"
                team_options.append(opt_label)
                team_id_map[opt_label] = t_id

            default_t_idx = 1 if len(team_options) > 1 else 0
            sel_team_opt = st_ctx.selectbox(
                "Başvuruda Kullanılacak Takım *",
                options=team_options,
                index=default_t_idx,
                key="sel_app_team_opt"
            )

            is_new_team = (sel_team_opt == "Yeni Takım Oluştur ve Başvur")
            new_team_name = ""
            new_team_level = "Lisans / Lisansüstü"
            new_adv_name = ""
            new_adv_email = ""

            if is_new_team:
                nc1, nc2 = st_ctx.columns(2)
                with nc1:
                    new_team_name = st_ctx.text_input("Yeni Takım Adı *", placeholder="Örn: Anka Teknoloji Takımı", key="inp_new_team_name")
                with nc2:
                    new_team_level = st_ctx.selectbox("Takım Seviyesi *", ["İlkokul", "Ortaokul", "Lise", "Lisans / Lisansüstü", "Mezun"], index=3, key="sel_new_team_level")

                ac1, ac2 = st_ctx.columns(2)
                with ac1:
                    new_adv_name = st_ctx.text_input("Danışman Adı & Soyadı (İsteğe Bağlı)", placeholder="Örn: Dr. Ahmet Yılmaz", key="inp_new_adv_name")
                with ac2:
                    new_adv_email = st_ctx.text_input("Danışman E-Postası (İsteğe Bağlı)", placeholder="danisman@universite.edu.tr", key="inp_new_adv_email")

            # 3. Proje Bilgileri
            st_ctx.markdown("<hr style='margin:12px 0 8px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
            st_ctx.markdown("<div style='font-size:0.92rem; font-weight:800; color:#1E293B; margin-bottom:6px;'>Proje Ön Bilgileri</div>", unsafe_allow_html=True)

            proj_c1, proj_c2 = st_ctx.columns([2, 1])
            with proj_c1:
                proje_adi = st_ctx.text_input("Proje Adı *", placeholder="Örn: 5G Destekli Otonom Yol ve Kavşak Güvenliği", key="inp_app_proj_name")
            with proj_c2:
                proje_dali = st_ctx.text_input("Yarışma Dalı / Kategori Kodu (Varsa)", placeholder="Örn: Genel Kategori", key="inp_app_branch_code")

            proje_ozeti = st_ctx.text_area("Proje Özeti (Kısa Açıklama)", placeholder="Projenizin hedeflerini, çözdüğü problemi ve kullanılacak ana teknolojileri kısaca özetleyiniz...", height=70, key="ta_app_proj_summary")

            st_ctx.write("")
            btn_col1, btn_col2 = st_ctx.columns([1.8, 1.2])
            with btn_col1:
                submit_app_btn = st_ctx.form_submit_button("Başvuruyu Tamamla ve Kaydet", type="primary", use_container_width=True)

            if submit_app_btn:
                if not proje_adi.strip():
                    st_ctx.error("Lütfen proje adını giriniz.")
                elif is_new_team and not new_team_name.strip():
                    st_ctx.error("Lütfen yeni takımınız için bir isim giriniz.")
                else:
                    try:
                        r = repos()
                        # 1. Takımı oluştur veya seç
                        if is_new_team:
                            created_team = r.teams.create(
                                name=new_team_name.strip(),
                                captain_user_id=uid,
                                level=new_team_level,
                                institution=u_inst or "Belirtilmedi",
                                advisor_name=new_adv_name.strip() or None,
                                advisor_email=new_adv_email.strip() or None
                            )
                            target_team_id = created_team.team_id
                            final_team_name = new_team_name.strip()
                        else:
                            target_team_id = team_id_map.get(sel_team_opt)
                            final_team_name = sel_team_opt.split(" (Kod:")[0]

                        # 2. Başvuruyu Cloudflare D1 ve SQLite'a kaydet
                        app_res = r.applications.apply(
                            team_id=target_team_id,
                            competition_id=sel_slug,
                            branch_code=proje_dali.strip() or None,
                            level=new_team_level if is_new_team else None,
                            actor=uid,
                            force=True
                        )

                        # 3. reports tablosuna taslak rapor kaydı oluştur (aşama yüklemeleri için)
                        try:
                            from src.database.db import db
                            init_rep_id = f"REP_{uuid.uuid4().hex[:8].upper()}"
                            db.insert_report(
                                report_id=init_rep_id,
                                filename=f"{final_team_name}_OTR_Raporu.pdf",
                                project_name=proje_adi.strip(),
                                category=sel_slug,
                                status="hakem_bekliyor",
                                team_name=final_team_name,
                                stage="OTR",
                                stage_code="OTR",
                                created_at=str(datetime.datetime.now())[:19]
                            )
                        except Exception:
                            pass

                        # Başarılı - state temizle ve yenile
                        st_ctx.session_state["selected_apply_comp"] = None
                        st_ctx.session_state["show_new_app_form"] = False
                        st_ctx.success(f"**{comp_name}** yarışmasına **{final_team_name}** takımı ile başvurunuz başarıyla kaydedildi!")
                        st_ctx.rerun()

                    except Exception as e:
                        st_ctx.error(f"Başvuru oluşturulurken hata oluştu: {e}")


# ─── 3. render_basvurular ────────────────────────────────────────────────────

def render_basvurular(st_ctx, current_user: dict, lang: str = "tr") -> None:
    """Başvurularım & Karne — başvuru listesi, rapor yükleme, hakem karnesı."""

    uid = str(current_user.get("user_id", ""))

    # Başlık ve Yeni Başvuru Butonu
    t_c1, t_c2 = st_ctx.columns([3.2, 1.2])
    with t_c1:
        st_ctx.markdown(
            '<div class="t3-content-card" style="margin-bottom:12px;">'
            '<div class="t3-card-title">Başvurularım &amp; Karne</div>'
            '<div class="t3-card-sub">Başvurduğunuz yarışmaları görüntüleyin, '
            'rapor yükleyin ve aşama karnenizi takip edin.</div></div>',
            unsafe_allow_html=True,
        )
    with t_c2:
        btn_yeni_lbl = "✕ Formu Kapat" if st_ctx.session_state.get("show_new_app_form") else "Yeni Başvuru Yap"
        if st_ctx.button(btn_yeni_lbl, key="btn_toggle_new_app_form", use_container_width=True, type="primary"):
            st_ctx.session_state["show_new_app_form"] = not st_ctx.session_state.get("show_new_app_form", False)
            if not st_ctx.session_state["show_new_app_form"]:
                st_ctx.session_state["selected_apply_comp"] = None
            st_ctx.rerun()

    # ─── YENİ BAŞVURU FORMU (Açıkken veya 'Bu Yarışmaya Başvur' Tıklandığında) ─────────
    preselected_slug = st_ctx.session_state.get("selected_apply_comp")
    is_form_open = st_ctx.session_state.get("show_new_app_form", False) or bool(preselected_slug)

    if is_form_open:
        _render_new_app_modal(st_ctx, current_user, lang, preselected_slug)

    # Başvuruları yükle
    all_apps: List[Any] = []
    try:
        raw_apps = repos().applications.list_for_user(uid) or []
        seen_apps = set()
        for app in raw_apps:
            app_id = str(_attr(app, "app_id", _attr(app, "application_id", _attr(app, "id", ""))))
            if app_id not in seen_apps:
                seen_apps.add(app_id)
                all_apps.append(app)
    except Exception as exc:
        st_ctx.error(f"Başvurular yüklenirken hata: {exc}")
        return

    if not all_apps:
        if not is_form_open:
            st_ctx.info("Henüz aktif bir başvurunuz bulunmamaktadır. Yukarıdaki **'Yeni Başvuru Yap'** butonuna tıklayarak istediğiniz yarışmaya takımınızla anında başvurabilirsiniz.")
        return

    # Takım adları
    user_teams: Dict[str, str] = {}
    try:
        for tm in (repos().teams.list_for_user(uid) or []):
            tm_id = str(_attr(tm, "team_id", _attr(tm, "id", "")))
            user_teams[tm_id] = str(_attr(tm, "name", ""))
    except Exception:
        pass

    # Yarışma cache
    comp_cache: Dict[str, Any] = {}
    for c in _all_competitions():
        comp_cache[str(_attr(c, "slug", ""))] = c
        comp_cache[str(_attr(c, "competition_id", _attr(c, "id", "")))] = c

    for idx, app in enumerate(all_apps):
        app_id = str(_attr(app, "app_id", _attr(app, "application_id", _attr(app, "id", ""))))
        comp_id = str(_attr(app, "competition_id", ""))
        team_id = str(_attr(app, "team_id", ""))
        branch_code = str(_attr(app, "branch_code", "") or "")
        app_status = str(_attr(app, "status", ""))
        created_at = str(_attr(app, "created_at", "") or "")

        team_name = user_teams.get(team_id, team_id or "—")
        comp = comp_cache.get(comp_id)
        comp_name = str(_attr(comp, "name", comp_id)) if comp else comp_id

        is_exp = st_ctx.session_state.get(f"_app_exp_{app_id}_{idx}", False)

        with st_ctx.container(border=True):
            hc1, hc3 = st_ctx.columns([5.0, 1.5])
            with hc1:
                st_ctx.markdown(f"#### {_esc(comp_name)}")
                meta = [f"Takım: **{_esc(team_name)}**"]
                if branch_code:
                    meta.append(f"Dal: {branch_code}")
                if created_at:
                    meta.append(f"Tarih: {created_at[:10]}")
                st_ctx.caption(" | ".join(meta))
            with hc3:
                lbl = "Kapat" if is_exp else "Detaylar"
                btn_t = "secondary" if is_exp else "primary"
                if st_ctx.button(lbl, key=f"_app_tog_{app_id}_{idx}",
                                  use_container_width=True, type=btn_t):
                    st_ctx.session_state[f"_app_exp_{app_id}_{idx}"] = not is_exp
                    st_ctx.rerun()

            if is_exp:
                _render_app_detail(st_ctx, uid, lang, app, team_name,
                                   comp_name, comp_id, team_id)


def _render_app_detail(
    st_ctx, uid: str, lang: str, app: Any,
    team_name: str, comp_name: str, comp_id: str, team_id: str,
) -> None:
    app_id = str(_attr(app, "app_id", _attr(app, "application_id", _attr(app, "id", ""))))

    _sep(st_ctx)
    st_ctx.markdown(f"##### Aşama Raporları — {_esc(comp_name)}")

    # Aşamaları getir
    stages: List[Any] = []
    try:
        stages = repos().competitions.list_stages(comp_id) or []
    except Exception:
        pass
    if not stages:
        stages = [
            {"stage_code": "OTR", "stage_name": "Ön Teknik Rapor", "deadline": "—"},
            {"stage_code": "KTR", "stage_name": "Kritik Tasarım Raporu", "deadline": "—"},
            {"stage_code": "FTR", "stage_name": "Final Teknik Raporu", "deadline": "—"},
        ]

    # Raporları getir
    app_reports: Dict[str, Any] = {}
    try:
        for rep in (repos().reports.list_for_application(app_id) or []):
            sc = str(_attr(rep, "stage_code", "")).upper()
            app_reports[sc] = rep
    except Exception:
        try:
            for rep in (repos().reports.list_for_user(uid) or []):
                if str(_attr(rep, "app_id", "")) == app_id:
                    sc = str(_attr(rep, "stage_code", "")).upper()
                    app_reports[sc] = rep
        except Exception:
            pass

    for stage in stages:
        s_code = str(_attr(stage, "stage_code", "")).upper()
        s_name = str(_attr(stage, "stage_name", s_code))
        s_dead = str(_attr(stage, "deadline", "—") or "—")
        has_rep = app_reports.get(s_code)

        with st_ctx.expander(
            f"{s_code} — {s_name}  |  Son: {s_dead}",
            expanded=bool(has_rep),
        ):
            if has_rep:
                r = has_rep
                r_id = str(_attr(r, "report_id", _attr(r, "id", "")))
                r_name = str(_attr(r, "file_name", "rapor.pdf"))
                r_pages = int(_attr(r, "page_count", 1) or 1)
                r_status = str(_attr(r, "status", ""))
                r_date = str(_attr(r, "created_at", "") or "")[:10]

                rc1, rc2 = st_ctx.columns([2, 1.5])
                with rc1:
                    st_ctx.markdown(
                        f"**{_esc(r_name)}** &nbsp;·&nbsp; {r_pages} sayfa &nbsp;·&nbsp; {r_date}",
                        unsafe_allow_html=True,
                    )
                    st_ctx.markdown(_status_badge(r_status, lang), unsafe_allow_html=True)
                with rc2:
                    r_key = str(_attr(r, "r2_key", _attr(r, "r2_url", "")) or "")
                    r_url = ""
                    if r_key:
                        try:
                            r_url = repos().storage.url_for(r_key)
                        except Exception:
                            r_url = r_key if r_key.startswith("http") else ""
                    if r_url:
                        st_ctx.link_button(f"{s_code} Raporunu İndir", r_url,
                                           use_container_width=True)

                # Karne
                r_status = str(_attr(r, "status", "")).upper()
                if r_status in ("COMPLETED", "TAMAMLANDI", "DEGERLENDIRILDI", "BAŞARILI", "BAŞARISIZ"):
                    score = float(_attr(r, "referee_score", _attr(r, "ai_score", 0)) or 0)
                    notes = str(_attr(r, "referee_notes", _attr(r, "decision", "")) or "")
                    
                    _sep(st_ctx)
                    st_ctx.markdown("#### 🏆 Değerlendirme Karnesi")
                    km1, km2 = st_ctx.columns([1, 2.5])
                    with km1:
                        # Puan dairesi / kartı tasarımı (Nötr / Kurumsal Renk)
                        color = "#3B82F6" # TEKNOFEST Mavi / Kurumsal nötr bir mavi
                        
                        st_ctx.markdown(
                            f"""
                            <div style="text-align:center; padding: 20px; background: white; border-radius: 12px; border: 2px solid {color}; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);">
                                <div style="font-size: 48px; font-weight: 800; color: {color};">{score:.1f}</div>
                                <div style="font-size: 14px; color: #64748b; margin-top: -5px; font-weight: 600;">100 ÜZERİNDEN</div>
                                <div style="margin-top: 15px; padding: 6px; background: {color}15; color: {color}; border-radius: 6px; font-weight: bold; font-size: 15px;">
                                    🏆 GENEL PUAN
                                </div>
                            </div>
                            """, unsafe_allow_html=True
                        )
                        st_ctx.markdown("<br>", unsafe_allow_html=True)
                    with km2:
                        if notes:
                            st_ctx.info(f"**Hakem Değerlendirme Özeti:**\n\n{_esc(notes)}", icon="💬")
                        else:
                            st_ctx.info("Henüz değerlendirme notu girilmemiş.", icon="⏳")

                    # YARIŞMACI İÇİN RESMİ PDF İNDİRME BUTONU
                    try:
                        from src.ui.karne_pdf import uret
                        
                        ai_data_str = _attr(r, "ai_data_json", "")
                        ai_data = {}
                        if ai_data_str and ai_data_str not in ("{}", "null", None):
                            import json
                            try: ai_data = json.loads(ai_data_str)
                            except: pass
                        
                        exact_report_dict = {
                            "rapor_id": r_id,
                            "proje_adi": team_name or "İsimsiz Proje",
                            "takim_adi": team_name or "İsimsiz Takım",
                            "kategori": comp_name,
                            "kriterler": []
                        }
                        
                        from src.api.ui_adapter import _map_kriterler
                        feedback_str = _attr(r, "feedback_json", "")
                        feedback_dict = {}
                        if feedback_str and feedback_str not in ("{}", "null", None):
                            try:
                                feedback_dict = json.loads(feedback_str) if isinstance(feedback_str, str) else feedback_str
                            except Exception:
                                pass

                        for k in exact_report_dict["kriterler"]:
                            k_id = k.get("kriter_id") or k.get("id")
                            if k_id and k_id in feedback_dict:
                                val = feedback_dict[k_id]
                                if isinstance(val, (int, float)):
                                    k["ai_puan"] = float(val)

                        if not exact_report_dict["kriterler"]:
                            exact_report_dict["kriterler"] = [{
                                "ad": "Genel Değerlendirme Puanı",
                                "maks": 100.0,
                                "ai_puan": score
                            }]
                            
                        exact_report_dict["geri_bildirim"] = {"ozet": notes}
                        
                        pdf_yarisma = {"ad": comp_name, "rapor_turu": f"{s_code} Karnesi"}
                        pdf_bytes = uret(exact_report_dict, pdf_yarisma)
                        
                        st_ctx.markdown("<br/>", unsafe_allow_html=True)
                        st_ctx.download_button(
                            "📄 Resmi İmzalı Karne PDF'ini İndir",
                            data=pdf_bytes,
                            file_name=f"Karne_{s_code}_{r_id}.pdf",
                            mime="application/pdf",
                            use_container_width=True, type='primary'
                        )
                    except Exception as e:
                        st_ctx.caption(f"PDF oluşturulamadı: {e}")
                elif r_status in ("REDDEDILDI", "REJECTED", "ELENDI"):
                    st_ctx.error("❌ Uygun görülemediği için reddedilmiştir.")
                elif r_status in ("DEGERLENDIRILIYOR", "INCELENIYOR", "IN_REVIEW"):
                    st_ctx.info("⏳ Raporunuz şu anda inceleme aşamasındadır.")
                elif r_status in ("REVIZYON_ISTENDI", "NEEDS_REVISION"):
                    st_ctx.warning("⚠️ Raporunuz için revizyon (düzeltme) talep edilmiştir.")
                    notes = str(_attr(r, "referee_notes", _attr(r, "decision", "")) or "")
                    if notes:
                        st_ctx.info(f"**Hakem / Yönetici Notu:** {notes}")
                    
                    st_ctx.markdown("Lütfen geri bildirimleri dikkate alarak raporunuzu güncelleyiniz. Eski raporunuzu silip yeni bir rapor yüklemek için aşağıdaki butonu kullanabilirsiniz.")
                    
                    if st_ctx.button("🔄 Raporu Sıfırla (Yeniden Yükle)", key=f"_reset_rep_{r_id}"):
                        try:
                            repos().reports.delete(r_id)
                            st_ctx.success("Eski raporunuz silindi. Şimdi yeni dosyanızı yükleyebilirsiniz.")
                            st_ctx.rerun()
                        except Exception as e:
                            st_ctx.error(f"Sıfırlama sırasında hata oluştu: {e}")
                else:
                    st_ctx.info("Bu aşama için henüz değerlendirme yapılmamış.")

            else:
                # Rapor yükleme
                wc1, wc2 = st_ctx.columns([1.5, 2])
                with wc1:
                    st_ctx.markdown(
                        f"<span style='color:#DC2626;font-weight:700;font-size:.9rem;'>"
                        f"⚠ {s_code} raporu henüz yüklenmedi</span>",
                        unsafe_allow_html=True,
                    )
                    badge = _days_badge(s_dead, lang)
                    if badge:
                        st_ctx.markdown(badge, unsafe_allow_html=True)
                with wc2:
                    inline_file = st_ctx.file_uploader(
                        f"{s_code} Raporu (PDF)", type=["pdf"],
                        key=f"_inline_{app_id}_{s_code}",
                        label_visibility="collapsed",
                    )
                    if inline_file is not None:
                        if st_ctx.button(
                            f"{s_code} Raporunu Gönder",
                            key=f"_send_{app_id}_{s_code}",
                            type="primary", use_container_width=True,
                        ):
                            with st_ctx.spinner("Rapor yükleniyor ve yapay zekâ ön şartname denetimi yapılıyor..."):
                                fbytes = inline_file.getvalue()
                                original_fn = inline_file.name
                                p_count = 1
                                extracted_text = ""
                                try:
                                    import pymupdf
                                    doc = pymupdf.open(stream=fbytes, filetype="pdf")
                                    p_count = len(doc)
                                    extracted_text = " ".join(page.get_text() for page in doc)
                                    doc.close()
                                except Exception:
                                    pass

                                # 1. Otomatik Yapay Zekâ Ön Denetimi ve Kriter Analizi
                                chk_res = {}
                                ev_res = {}
                                try:
                                    from src.checkers.runner import run_all_checks
                                    from src.evaluation.evaluator import evaluate_report_with_ai
                                    chk_res = run_all_checks(
                                        file_bytes=fbytes,
                                        report_text=extracted_text,
                                        category_name=comp_id,
                                        stage=s_code,
                                        report_id=app_id
                                    )
                                    ev_res = evaluate_report_with_ai(
                                        report_text=extracted_text,
                                        category_name=comp_id,
                                        stage=s_code
                                    )
                                except Exception as ex_ai:
                                    print(f"[AI Pre-check Warning]: {ex_ai}")

                                # 2. Standart R2 Depolama Yüklemesi
                                r2_key = Keys.report(
                                    competition_slug=comp_id,
                                    stage_code=s_code,
                                    app_id=app_id,
                                    team_name=team_name or "takim",
                                    version=1
                                )
                                try:
                                    repos().storage.upload(fbytes, r2_key, "application/pdf")
                                except StorageError as exc:
                                    st_ctx.warning(f"R2 uyarısı: {exc}")

                                # 3. Cloudflare D1 ve SQLite Veritabanına Mühürleme
                                try:
                                    created_rep = repos().reports.create(
                                        app_id=app_id,
                                        competition_id=comp_id,
                                        stage_code=s_code,
                                        file_name=original_fn,
                                        r2_key=r2_key,
                                        page_count=p_count,
                                        uploaded_by=uid,
                                    )
                                    rep_id = getattr(created_rep, "report_id", f"REP_{app_id}_{s_code}")
                                    
                                    from src.database.db import db
                                    if db:
                                        db.save_report({
                                            "report_id": rep_id,
                                            "app_id": app_id,
                                            "competition_id": comp_id,
                                            "stage_code": s_code,
                                            "stage": s_code,
                                            "file_name": original_fn,
                                            "filename": original_fn,
                                            "r2_key": r2_key,
                                            "r2_url": r2_key,
                                            "pdf_path": "",
                                            "category": comp_id,
                                            "project_name": team_name or "Yarışma Başvurusu",
                                            "team_name": team_name or "Yarışmacı Takım",
                                            "checks": chk_res,
                                            "ai_data": ev_res,
                                            "ai_score": ev_res.get("total_score") or ev_res.get("weighted_total_score"),
                                            "status": "READY_FOR_REFEREE",
                                            "uploaded_by": uid,
                                            "page_count": p_count
                                        })
                                    st_ctx.success(f"{s_code} raporunuz ({original_fn}) başarıyla yüklendi ve yapay zekâ ön denetimi tamamlandı!")
                                    st_ctx.rerun()
                                except DuplicateRecord:
                                    st_ctx.warning("Bu aşama için zaten bir rapor yüklenmiş.")
                                except DataError as exc:
                                    st_ctx.error(f"Veritabanı hatası: {exc}")


# ─── 3. render_takimlar ──────────────────────────────────────────────────────

def render_takimlar(st_ctx, current_user: dict, lang: str = "tr") -> None:
    """Takımlarım — ekran görüntüsündeki tablo tasarımıyla."""

    uid = str(current_user.get("user_id", ""))

    # Başlık
    st_ctx.markdown(
        '<div style="margin-bottom:16px;">'
        '<div style="font-size:1.25rem;font-weight:700;margin-bottom:4px;">Takımlarım</div>'
        '<div style="color:#64748B;font-size:.9rem;">'
        'Takım kurun, davet koduyla katılın, üyelerinizi ve kaptanlığı yönetin.</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    # Aksiyon butonları
    ac1, ac2 = st_ctx.columns([1, 1])
    with ac1:
        if st_ctx.button("Yeni Takım Oluştur", key="_t_btn_create", type="primary", use_container_width=True):
            st_ctx.session_state["_t_show_create"] = not st_ctx.session_state.get("_t_show_create", False)
            st_ctx.session_state["_t_show_join"] = False
    with ac2:
        if st_ctx.button("Davet Koduyla Katıl", key="_t_btn_join", use_container_width=True):
            st_ctx.session_state["_t_show_join"] = not st_ctx.session_state.get("_t_show_join", False)
            st_ctx.session_state["_t_show_create"] = False

    # Yeni takım formu
    if st_ctx.session_state.get("_t_show_create"):
        with st_ctx.container(border=True):
            st_ctx.markdown("**Yeni Takım Oluştur**")
            with st_ctx.form("_form_create_team"):
                fc1, fc2 = st_ctx.columns(2)
                with fc1:
                    new_name = st_ctx.text_input("Takım Adı *", placeholder="Örn: Bilig Yapay Zeka")
                    new_inst = st_ctx.text_input("Okul / Kurum", placeholder="Örn: İTÜ")
                with fc2:
                    new_level = st_ctx.selectbox(
                        "Eğitim Seviyesi",
                        ["Lise", "Ön Lisans / Lisans", "Yüksek Lisans / Doktora",
                         "Ortaokul", "İlkokul", "Mezun / Girişimci"],
                        index=1,
                    )
                adv_email = st_ctx.text_input("Danışman E-posta", placeholder="ornek@kurum.edu.tr")
                if st_ctx.form_submit_button("Takımı Oluştur", type="primary"):
                    if not (new_name or "").strip():
                        st_ctx.error("Takım adı zorunludur.")
                    else:
                        try:
                            # Danışman bilgilerini veritabanından otomatik çek
                            _fetched_adv_name = None
                            _fetched_adv_title = None
                            _adv_email_clean = (adv_email or "").strip()
                            if _adv_email_clean and "@" in _adv_email_clean:
                                try:
                                    _ar = auth_service.get_user_by_email(_adv_email_clean)
                                    if _ar:
                                        _fetched_adv_name = str(_ar.get("full_name", _ar.get("name", ""))).strip() or None
                                        _fetched_adv_title = (_ar.get("education_level") or "").strip() or None
                                except Exception:
                                    pass  # DB erişilemiyorsa boş bırak
                            team = repos().teams.create(
                                name=new_name,
                                captain_user_id=uid,
                                level=new_level,
                                institution=new_inst or None,
                                advisor_name=_fetched_adv_name or None,
                                advisor_email=adv_email or None,
                                advisor_title=_fetched_adv_title or None,
                            )
                            code = _team_code(team) or _attr(team, "team_code", "")
                            st_ctx.success(f"'{_attr(team, 'name', new_name)}' oluşturuldu! Davet kodu: {code}")

                            # Danışmana bilgilendirme / davet maili gönder
                            if (adv_email or "").strip():
                                captain_display = str(
                                    current_user.get("name",
                                    current_user.get("full_name",
                                    current_user.get("username", uid)))
                                )
                                _send_advisor_email(
                                    st_ctx,
                                    team=team,
                                    team_name=new_name,
                                    team_code=code,
                                    adv_name=_fetched_adv_name,
                                    adv_email=adv_email.strip(),
                                    captain_name=captain_display,
                                )

                            st_ctx.session_state["_t_show_create"] = False
                            st_ctx.rerun()
                        except DuplicateRecord:
                            st_ctx.warning("Bu isimde bir takım zaten mevcut.")
                        except (ValueError, DataError) as exc:
                            st_ctx.error(f"Hata: {exc}")

    # Katıl formu
    if st_ctx.session_state.get("_t_show_join"):
        with st_ctx.container(border=True):
            st_ctx.markdown("**Davet Koduyla Katıl**")
            with st_ctx.form("_form_join_team"):
                jcode = st_ctx.text_input("Davet Kodu", placeholder="Örn: 2QF3NX")
                if st_ctx.form_submit_button("Katıl", type="primary"):
                    if not (jcode or "").strip():
                        st_ctx.error("Lütfen bir davet kodu giriniz.")
                    else:
                        try:
                            team = repos().teams.join_by_code(jcode.strip().upper(), uid)
                            st_ctx.success(f"'{_attr(team, 'name', jcode)}' takımına katıldınız!")
                            st_ctx.session_state["_t_show_join"] = False
                            st_ctx.rerun()
                        except DuplicateRecord:
                            st_ctx.warning("Zaten bu takımın üyesisiniz.")
                        except RecordNotFound:
                            st_ctx.error("Bu davet kodu bulunamadı.")
                        except (ValueError, DataError) as exc:
                            st_ctx.error(f"Hata: {exc}")

    st_ctx.markdown("<br>", unsafe_allow_html=True)
    st_ctx.markdown("#### Kayıtlı Takımlarım")

    teams: List[Any] = []
    try:
        teams = repos().teams.list_for_user(uid) or []
    except Exception:
        pass

    if not teams:
        st_ctx.info("Henüz bir takımınız bulunmamaktadır.")
        return

    for team in teams:
        tid = _team_id(team)
        tcode = _team_code(team)
        tname = str(_attr(team, "name", ""))
        tyear = _team_year(team)
        is_cap = str(_attr(team, "captain_user_id", "")) == uid
        is_exp = st_ctx.session_state.get(f"_texp_{tid}", False)

        members: List[Any] = []
        try:
            members = repos().teams.members(tid) or []
        except Exception:
            pass

        with st_ctx.container(border=True):
            rc1, rc2, rc3, rc4, rc5 = st_ctx.columns([1.6, 2.4, 1.2, 1.2, 2.2], vertical_alignment="center")
            with rc1:
                st_ctx.markdown(
                    f'<div style="font-size:0.75rem; color:#64748b; font-weight:700;">TAKIM KODU</div>'
                    f'<span style="color:#F04823;font-weight:800;font-family:monospace;font-size:1.1rem; background-color:#F0482315; padding: 4px 8px; border-radius: 4px;">'
                    f'{_esc(tcode)}</span>',
                    unsafe_allow_html=True,
                )
            with rc2:
                st_ctx.markdown(f'<div style="font-size:0.75rem; color:#64748b; font-weight:700;">TAKIM ADI</div><div style="font-weight:700; font-size:1.1rem; color:#0F172A;">{_esc(tname)}</div>', unsafe_allow_html=True)
            with rc3:
                st_ctx.markdown(f'<div style="font-size:0.75rem; color:#64748b; font-weight:700;">YIL</div><span style="color:#475569; font-weight:600;">{tyear}</span>', unsafe_allow_html=True)
            with rc4:
                st_ctx.markdown(f'<div style="font-size:0.75rem; color:#64748b; font-weight:700;">ÜYE SAYISI</div><span style="color:#475569; font-weight:600;">{len(members)} Üye</span>', unsafe_allow_html=True)
            with rc5:
                if is_exp:
                    if st_ctx.button("Kapat", key=f"_tcls_{tid}", use_container_width=True):
                        st_ctx.session_state[f"_texp_{tid}"] = False
                        st_ctx.rerun()
                else:
                    btn_lbl = "Yönet" if is_cap else "İncele"
                    if st_ctx.button(btn_lbl, key=f"_topn_{tid}", type="primary" if is_cap else "secondary", use_container_width=True):
                        st_ctx.session_state[f"_texp_{tid}"] = True
                        st_ctx.rerun()

            if is_exp:
                st_ctx.markdown("<br>", unsafe_allow_html=True)
                _render_team_detail(st_ctx, uid, lang, team, members, is_cap, current_user)


def _render_team_detail(
    st_ctx, uid: str, lang: str,
    team: Any, members: List[Any], is_cap: bool,
    current_user: dict,
) -> None:
    """Takım detay paneli — screenshot tasarımına birebir uygun."""
    tid = _team_id(team)
    tname = str(_attr(team, "name", ""))
    tcode = _team_code(team)
    level = str(_attr(team, "level", "") or "")
    inst = str(_attr(team, "institution", "") or "")
    adv_name = str(_attr(team, "advisor_name", "") or "")
    adv_title = str(_attr(team, "advisor_title", "") or "")
    adv_email = str(_attr(team, "advisor_email", "") or "")
    status = str(_attr(team, "status", "Aktif") or "Aktif")

    with st_ctx.container(border=True):

        # Başlık + Durum
        dh1, dh2 = st_ctx.columns([4, 1])
        with dh1:
            st_ctx.markdown(
                f'<div style="font-size:1.05rem;font-weight:700;">'
                f'{_esc(tname)} Detayları</div>',
                unsafe_allow_html=True,
            )
            meta = []
            if level:
                meta.append(level)
            if inst:
                meta.append(f"Kurum: {inst}")
            if meta:
                st_ctx.markdown(
                    f'<div style="color:#64748B;font-size:.85rem;">'
                    f'{_esc(" · ".join(meta))}</div>',
                    unsafe_allow_html=True,
                )
        with dh2:
            is_aktif = "aktif" in status.lower()
            chip_bg      = "linear-gradient(135deg,#D1FAE5,#A7F3D0)" if is_aktif else "linear-gradient(135deg,#FEE2E2,#FECACA)"
            chip_color   = "#065F46" if is_aktif else "#991B1B"
            chip_border  = "#6EE7B7" if is_aktif else "#FCA5A5"
            chip_shadow  = "0 1px 4px rgba(16,185,129,.25)" if is_aktif else "0 1px 4px rgba(239,68,68,.20)"
            chip_icon    = "✓" if is_aktif else "✕"
            chip_label   = "AKTİF" if is_aktif else "PASİF"
            chip_dot_bg  = "#10B981" if is_aktif else "#EF4444"
            st_ctx.markdown(
                f'<div style="display:flex;justify-content:flex-end;margin-top:4px;">'
                f'<span style="display:inline-flex;align-items:center;gap:6px;'
                f'background:{chip_bg};color:{chip_color};'
                f'border:1.5px solid {chip_border};'
                f'box-shadow:{chip_shadow};'
                f'font-size:.72rem;font-weight:800;padding:5px 13px;'
                f'border-radius:999px;letter-spacing:.07em;white-space:nowrap;">'
                f'<span style="width:7px;height:7px;border-radius:50%;'
                f'background:{chip_dot_bg};flex-shrink:0;'
                f'box-shadow:0 0 0 2px {chip_border};"></span>'
                f'{chip_icon} {chip_label}</span></div>',
                unsafe_allow_html=True,
            )

        # Davet kodu + Danışman
        dc1, dc2 = st_ctx.columns(2)
        with dc1:
            st_ctx.markdown(
                '<div style="font-size:.8rem;font-weight:700;color:#64748B;'
                'margin:12px 0 4px 0;">Davet kodu</div>',
                unsafe_allow_html=True,
            )
            st_ctx.code(tcode, language=None)
            st_ctx.caption(
                "Bu kodu takım arkadaşlarınızla paylaşın; "
                "kod alanının sağındaki simgeyle kopyalayabilirsiniz."
            )
        with dc2:
            adv_parts = [p for p in [adv_name, adv_title, adv_email] if p]
            if adv_parts:
                st_ctx.markdown(
                    '<div style="font-size:.8rem;font-weight:700;color:#64748B;'
                    'margin:12px 0 4px 0;">Danışman</div>',
                    unsafe_allow_html=True,
                )
                st_ctx.markdown(
                    f'<div style="font-size:.9rem;">'
                    f'{_esc(" · ".join(adv_parts))}</div>',
                    unsafe_allow_html=True,
                )

        # Üyeler
        with st_ctx.expander("Takım üyeleri", expanded=True):
            if not members:
                st_ctx.caption("Üye listesi alınamadı.")
            else:
                for m_idx, item in enumerate(members):
                    if isinstance(item, (list, tuple)) and len(item) >= 2:
                        membership, user = item[0], item[1]
                    else:
                        membership, user = item, None

                    member_uid = str(_attr(membership, "user_id", ""))
                    role_raw = str(
                        _attr(membership, "role_in_team",
                              _attr(membership, "role", "uye")) or "uye"
                    ).lower()

                    if user:
                        display_name = str(_attr(user, "full_name", _attr(user, "name", member_uid)))
                        m_email = str(_attr(user, "email", "") or "")
                    else:
                        display_name = member_uid
                        m_email = ""

                    is_k = "kaptan" in role_raw or "captain" in role_raw
                    is_d = "danisman" in role_raw or "advisor" in role_raw
                    if is_k:
                        role_badge = _pill("KAPTAN", "primary")
                    elif is_d:
                        role_badge = _pill("DANIŞMAN", "secondary")
                    else:
                        role_badge = _pill("ÜYE", "blue")

                    # Kaptan ise ve bu üye kendisi/danışman değilse → Çıkar butonu göster
                    show_kick = is_cap and not is_k and not is_d and member_uid != uid
                    mcol1, mcol2 = st_ctx.columns([5, 1]) if show_kick else (st_ctx.container(), None)
                    with mcol1:
                        email_str = f'<div style="color:#64748B;font-size:.8rem;"> ' + _esc(m_email) + '</div>' if m_email else ""
                        st_ctx.markdown(
                            f'<div style="display:flex;align-items:center;gap:12px;padding:8px 0;border-bottom:1px solid rgba(0,0,0,.06);">'
                            f'{_avatar(display_name, 38)}'
                            f'<div style="flex:1;">'
                            f'<div style="font-weight:700;font-size:.9rem;">{_esc(display_name)}</div>'
                            f'{email_str}'
                            f'</div>{role_badge}</div>',
                            unsafe_allow_html=True,
                        )
                    if show_kick and mcol2 is not None:
                        with mcol2:
                            st_ctx.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
                            if st_ctx.button("Çıkar", key=f"_kick_{tid}_{m_idx}",
                                             help=f"{display_name} adlı üyeyi takımdan çıkar"):
                                try:
                                    repos().teams.remove_member(tid, member_uid, actor=uid)
                                    # Mail bildirimi — üyeye
                                    if m_email:
                                        cap_display = str(
                                            current_user.get("name",
                                            current_user.get("full_name",
                                            current_user.get("username", uid)))
                                        )
                                        auth_service.send_member_removed_email(
                                            to_email=m_email,
                                            member_name=display_name,
                                            team_name=tname,
                                            captain_name=cap_display,
                                        )
                                    st_ctx.success(f"✅ {display_name} takımdan çıkarıldı.")
                                    st_ctx.rerun()
                                except (RecordNotFound, ValueError, DataError) as exc:
                                    st_ctx.error(f"Hata: {exc}")

        _sep(st_ctx)

        # Kaptanlık devri + Ayrıl
        ac1, ac2 = st_ctx.columns(2)
        with ac1:
            if is_cap:
                other_members = []
                for item in members:
                    m = item[0] if isinstance(item, (list, tuple)) and len(item) >= 2 else item
                    u = item[1] if isinstance(item, (list, tuple)) and len(item) >= 2 else None
                    m_uid = str(_attr(m, "user_id", ""))
                    if m_uid != uid:
                        uname = str(_attr(u, "full_name", _attr(u, "name", "")) if u else "") or m_uid
                        other_members.append((m_uid, uname))

                st_ctx.markdown(
                    '<div style="font-size:.85rem;font-weight:600;margin-bottom:8px;">'
                    'Kaptanlığı devret</div>',
                    unsafe_allow_html=True,
                )
                if other_members:
                    opts = [x[0] for x in other_members]
                    fmt = {x[0]: x[1] for x in other_members}
                    new_cap = st_ctx.selectbox(
                        "Yeni kaptan seç", options=opts,
                        format_func=lambda x: fmt.get(x, x),
                        key=f"_new_cap_{tid}",
                        label_visibility="collapsed",
                    )
                    if st_ctx.button("Devret", key=f"_devret_{tid}"):
                        try:
                            repos().teams.transfer_captain(tid, new_cap, actor=uid)
                            st_ctx.success("Kaptanlık başarıyla devredildi.")
                            st_ctx.rerun()
                        except (RecordNotFound, ValueError, DataError) as exc:
                            st_ctx.error(f"Hata: {exc}")
                else:
                    st_ctx.caption("Devredebileceğiniz başka üye yok.")

        with ac2:
            st_ctx.markdown(
                '<div style="font-size:.85rem;font-weight:600;margin-bottom:8px;">'
                'Takımdan ayrıl</div>',
                unsafe_allow_html=True,
            )
            if st_ctx.button("Takımdan ayrıl", key=f"_leave_{tid}"):
                try:
                    repos().teams.remove_member(tid, uid, actor=uid)
                    # Danışmana bilgi maili
                    leaving_name = str(
                        current_user.get("name",
                        current_user.get("full_name",
                        current_user.get("username", uid)))
                    )
                    if adv_email:
                        auth_service.send_member_left_email(
                            to_email=adv_email,
                            recipient_name=adv_name or "Danışman",
                            member_name=leaving_name,
                            team_name=tname,
                        )
                    st_ctx.success("Takımdan ayrıldınız.")
                    st_ctx.session_state[f"_texp_{tid}"] = False
                    st_ctx.rerun()
                except (RecordNotFound, ValueError, DataError) as exc:
                    st_ctx.error(f"Hata: {exc}")

        # Takımı Düzenle / Sil (Kaptan)
        if is_cap:
            st_ctx.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
            _sep(st_ctx)
            with st_ctx.expander("⚙️ Takımı Yönet (Düzenle / Sil)", expanded=False):
                with st_ctx.form(f"_form_edit_{tid}"):
                    st_ctx.markdown("###### Takım Bilgilerini Güncelle")
                    en_name = st_ctx.text_input("Takım Adı", value=tname)
                    _levels = ["Lise", "Ön Lisans / Lisans", "Yüksek Lisans / Doktora", "Ortaokul", "İlkokul", "Mezun / Girişimci"]
                    en_level = st_ctx.selectbox(
                        "Eğitim Seviyesi",
                        _levels,
                        index=_levels.index(level) if level in _levels else 1
                    )
                    en_adv = st_ctx.text_input("Danışman E-posta", value=adv_email or "")
                    if st_ctx.form_submit_button("Güncelle", type="primary"):
                        try:
                            repos().teams.update(tid, {
                                "name": en_name,
                                "level": en_level,
                                "advisor_email": en_adv
                            }, actor=uid)
                            st_ctx.success("Takım güncellendi!")
                            st_ctx.rerun()
                        except Exception as exc:
                            st_ctx.error(f"Hata: {exc}")
                
                st_ctx.markdown("<br>", unsafe_allow_html=True)
                st_ctx.markdown("###### Takımı Sil")
                st_ctx.caption("Takımı silerseniz tüm üyelikler iptal edilir. **Eğer takımın aktif bir başvurusu varsa takım silinemez.**")
                if st_ctx.button("Takımı Kalıcı Olarak Sil", key=f"_del_team_{tid}"):
                    try:
                        repos().teams.delete(tid, actor=uid)
                        st_ctx.success("Takım silindi.")
                        st_ctx.rerun()
                    except ValueError as ve:
                        st_ctx.error(str(ve))
                    except Exception as exc:
                        st_ctx.error(f"Silinemedi: {exc}")

        # Kaptan — Üye davet et
        if is_cap:
            st_ctx.markdown('<div style="height:8px;"></div>', unsafe_allow_html=True)
            _sep(st_ctx)

            # Davet listesi session_state'te tutulur; repos destekliyorsa oradan da çekilir
            inv_key = f"_invites_{tid}"
            if inv_key not in st_ctx.session_state:
                pending: List[dict] = []
                try:
                    raw_inv = repos().teams.list_invitations(tid) or []
                    for inv in raw_inv:
                        pending.append({
                            "email": str(_attr(inv, "email", _attr(inv, "invited_email", ""))),
                            "status": str(_attr(inv, "status", "Beklemede")),
                            "date": str(_attr(inv, "created_at", "") or "")[:10],
                        })
                except Exception:
                    pending = []
                st_ctx.session_state[inv_key] = pending

            # Genişleyebilir davet paneli
            inv_count = len(st_ctx.session_state.get(inv_key, []))
            inv_label = (
                f"📨 Takıma Üye Davet Et"
                + (f"  ·  {inv_count} bekleyen davet" if inv_count else "")
            )
            with st_ctx.expander(inv_label, expanded=False):
                with st_ctx.form(f"_inv_form_{tid}"):
                    ic1, ic2 = st_ctx.columns([3, 1])
                    with ic1:
                        inv_email = st_ctx.text_input(
                            "E-posta adresi",
                            placeholder="üye@email.com",
                            label_visibility="collapsed",
                        )
                    with ic2:
                        send_inv = st_ctx.form_submit_button(
                            "Davet Gönder", type="primary", use_container_width=True
                        )
                    if send_inv:
                        em = (inv_email or "").strip().lower()
                        if not em or "@" not in em:
                            st_ctx.error("Geçerli bir e-posta adresi giriniz.")
                        elif any(x["email"].lower() == em
                                 for x in st_ctx.session_state[inv_key]):
                            st_ctx.warning(f"{em} zaten davet listesinde.")
                        else:
                            sent_ok = False
                            try:
                                repos().teams.invite_by_email(tid, em, actor=uid)
                                sent_ok = True
                            except AttributeError:
                                sent_ok = True  # API yok ama session'a kaydediyoruz
                            except (RecordNotFound, ValueError, DataError) as exc:
                                st_ctx.error(f"Hata: {exc}")
                            if sent_ok:
                                today = datetime.date.today().strftime("%Y-%m-%d")
                                st_ctx.session_state[inv_key].append({
                                    "email": em,
                                    "status": "Beklemede",
                                    "date": today,
                                })
                                # Davet maili gönder — token'lı accept linki ile
                                cap_display = str(
                                    current_user.get("name",
                                    current_user.get("full_name",
                                    current_user.get("username", uid)))
                                )
                                try:
                                    token = auth_service.create_team_invite_token(
                                        team_id=tid,
                                        team_name=tname,
                                        invited_email=em,
                                        invited_by_name=cap_display,
                                    )
                                    mail_ok, _ = auth_service.send_team_invite_email(
                                        to_email=em,
                                        team_name=tname,
                                        invited_by=cap_display,
                                        token=token,
                                    )
                                except Exception:
                                    mail_ok = False
                                if mail_ok:
                                    st_ctx.success(f"{em} adresine davet maili gönderildi.")
                                else:
                                    st_ctx.success(
                                        f"{em} davet listesine eklendi. "
                                        f"(Mail gönderilemedi — davet kodunu "
                                        f"**{tcode}** paylaşabilirsiniz.)"
                                    )

                # Davet listesi
                invites = st_ctx.session_state.get(inv_key, [])
                if invites:
                    st_ctx.markdown(
                        '<div style="font-size:.8rem;font-weight:700;color:#64748B;'
                        'margin:14px 0 6px 0;">Gönderilen Davetler</div>',
                        unsafe_allow_html=True,
                    )
                    # Başlık satırı
                    lh1, lh2, lh3, lh4 = st_ctx.columns([3, 1.5, 1.5, 1])
                    _LH = '<span style="font-size:.7rem;font-weight:800;color:#94A3B8;">'
                    with lh1: st_ctx.markdown(f"{_LH}E-POSTA</span>", unsafe_allow_html=True)
                    with lh2: st_ctx.markdown(f"{_LH}DURUM</span>", unsafe_allow_html=True)
                    with lh3: st_ctx.markdown(f"{_LH}TARİH</span>", unsafe_allow_html=True)
                    with lh4: st_ctx.markdown(f"{_LH}İŞLEM</span>", unsafe_allow_html=True)
                    st_ctx.markdown(
                        '<div style="border-bottom:1px solid #E2E8F0;margin-bottom:4px;"></div>',
                        unsafe_allow_html=True,
                    )
                    for i, inv in enumerate(invites):
                        dur = inv.get("status", "Beklemede")
                        # Inline-styled durum chip
                        if dur == "Kabul Edildi":
                            dur_style = (
                                "background:#D1FAE5;color:#065F46;border:1px solid #6EE7B7;"
                            )
                        else:
                            dur_style = (
                                "background:#FEF3C7;color:#92400E;border:1px solid #FCD34D;"
                            )
                        lc1, lc2, lc3, lc4 = st_ctx.columns([3, 1.5, 1.5, 1])
                        with lc1:
                            st_ctx.markdown(
                                f'<div style="font-size:.88rem;padding:4px 0;">'
                                f'{_esc(inv.get("email", ""))}</div>',
                                unsafe_allow_html=True,
                            )
                        with lc2:
                            st_ctx.markdown(
                                f'<span style="display:inline-block;font-size:.7rem;'
                                f'font-weight:700;padding:2px 8px;border-radius:999px;'
                                f'{dur_style}">{_esc(dur)}</span>',
                                unsafe_allow_html=True,
                            )
                        with lc3:
                            st_ctx.markdown(
                                f'<div style="font-size:.8rem;color:#64748B;">'
                                f'{inv.get("date", "")}</div>',
                                unsafe_allow_html=True,
                            )
                        with lc4:
                            if st_ctx.button("✕", key=f"_inv_del_{tid}_{i}",
                                             help="Daveti iptal et"):
                                try:
                                    repos().teams.cancel_invitation(
                                        tid, inv["email"], actor=uid
                                    )
                                except Exception:
                                    pass
                                st_ctx.session_state[inv_key].pop(i)
                                st_ctx.rerun()
                else:
                    st_ctx.caption("Henüz davet gönderilmedi.")


# ─── Geriye dönük uyumluluk ──────────────────────────────────────────────────

def goster(st_ctx, current_user: dict, lang: str = "tr") -> None:
    """Eski tek-fonksiyon API. 3 sekme çizer."""
    tab_v, tab_b, tab_t = st_ctx.tabs([
        t("yar_tab_vitrin", lang),
        t("yar_tab_basvuru", lang),
        t("yar_tab_takimlar", lang),
    ])
    with tab_v:
        render_vitrin(st_ctx, current_user, lang)
    with tab_b:
        render_basvurular(st_ctx, current_user, lang)
    with tab_t:
        render_takimlar(st_ctx, current_user, lang)
