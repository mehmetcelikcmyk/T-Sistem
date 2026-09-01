"""T-Sistem · YARISMA YONETICISI (ADMIN) PANELI.

Kullanicinin dort kez birebir tekrarladigi ister:
    "yarisma olusturmayi duzenlemeyi sartnameleri yarisma asamalari olusturmayi
     duzenlemeyi seviyeleri falan hepsini yapan yarisma yoneticisi bunlari
     yapmaya DUZENLEMEYE SILMEYE EKLEMEYE TAM YETKILI olmali. hakem havuzu,
     rapor havuzu ve rapor yonlendirme adimlari da olmali."

ESKI KODUN DUZELTILEN HATALARI
------------------------------
1.  `upsert_competition` semayla uyusmuyordu (`levels`, `logo_url`,
    `sartname_url` kolonlari yoktu, `ON CONFLICT(slug)` hedefi yoktu,
    `sub_category NOT NULL` doldurulmuyordu). Hicbir yazma diske ulasmiyor,
    hata `except Exception: pass` ile yutuluyor, UI "basarili" diyordu.
2.  `competition_requirements` ve `report_assignments` tablolari HIC
    yaratilmiyordu; sartname kurallari ve hakem atamalari kayboluyordu.
3.  Hakem havuzu `SELECT email, name, surname FROM auth_users` yuzunden HER
    ZAMAN bostu (`surname` kolonu yoktu).
4.  Rapor havuzu `file_name` / `filename` uyusmazligi yuzunden HER ZAMAN bostu.
5.  Kural editorunde `selectbox(..., index=0)` sabitti; her kayitta tum
    kurallarin `rule_type` degeri sifirlaniyordu.
6.  Rubrik toplam puani, silinmek uzere isaretlenen kriterleri de sayiyordu.
7.  Sartname yukleme `domain` / `levels` / `description` alanlarini
    varsayilana donduruyordu (veri kaybi). Artik KISMI guncelleme yapilir.
8.  `sonuc_tarihi` her takvim guncellemesinde siliniyordu. Artik takvim
    birlestirilerek guncellenir.
9.  Word -> PDF donusumu Linux'ta hep basarisizdi ama UI "basariyla
    donusturuldu" diyordu. Artik basarisizlik ACIK HATA olarak gosterilir.
10. Modul ici rol kontrolu yoktu.
11. Sifir adet `t()` cagrisi vardi; ekran %100 Turkce sabitti.
12. Otomatik kayit vardi; kullanici "admin isi bitince KAYDET gibi bir tusla
    yapsin, kaydi daha guvenli olur" dedi. Artik her tabloda acik Kaydet butonu.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Callable, Sequence

from src.data import (
    DataError,
    DuplicateRecord,
    Keys,
    RecordNotFound,
    StorageError,
    repos,
    slugify,
)
from src.data.enums import (
    ApplicationStatus,
    AssignmentStatus,
    PublishStatus,
    ReportStatus,
    RubricStatus,
    RuleType,
    SpecStatus,
)
from src.data.models import (
    Competition,
    CompetitionSpec,
    Requirement,
    RubricCriterion,
    Stage,
    now_iso,
)
from src.ui.i18n_yonetici import t

_DATE_FORMATS = ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y")

DOMAIN_SUGGESTIONS = [
    "Havacilik ve Uzay", "Yapay Zeka", "Saglik Teknolojileri", "Enerji",
    "Dijital Teknolojiler", "Denizcilik", "Robotik ve Mekatronik",
    "Elektronik ve Yari Iletken", "Egitim Teknolojileri", "Mesleki Teknolojiler",
    "Cevre ve Surdurulebilirlik", "Teknoloji",
]
LEVEL_OPTIONS = ["Ortaokul", "Lise", "Universite", "Mezun", "Genel"]

_PUBLISH_BADGE = {
    PublishStatus.TASLAK: ("badge_publish_taslak", "t3-badge-info"),
    PublishStatus.YAYINDA: ("badge_publish_yayinda", "t3-badge-aktif"),
    PublishStatus.KAPALI: ("badge_publish_kapali", "t3-badge-pasif"),
}
_SPEC_BADGE = {
    SpecStatus.BEKLENIYOR: ("badge_spec_bekleniyor", "t3-badge-turuncu"),
    SpecStatus.YUKLENDI: ("badge_spec_yuklendi", "t3-badge-info"),
    SpecStatus.ANALIZ_EDILDI: ("badge_spec_analiz_edildi", "t3-badge-info"),
    SpecStatus.ONAYLANDI: ("badge_spec_onaylandi", "t3-badge-aktif"),
}
_RUBRIC_BADGE = {
    RubricStatus.BEKLENIYOR: ("badge_rubric_bekleniyor", "t3-badge-turuncu"),
    RubricStatus.CIKARILDI: ("badge_rubric_cikarildi", "t3-badge-info"),
    RubricStatus.ONAYLANDI: ("badge_rubric_onaylandi", "t3-badge-aktif"),
}


# ═══════════════════════════════════════════════════════════════════════════
# Yardimcilar
# ═══════════════════════════════════════════════════════════════════════════
def _e(value: Any) -> str:
    """HTML kacisi — kullanici metinleri dogrudan HTML'e basilmaz."""
    return (str(value or "")
            .replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _badge(label: str, css: str) -> str:
    return f'<span class="{css}">{_e(label)}</span>'


def _card_open(st_ctx, title: str, subtitle: str = "") -> None:
    sub = f'<div class="t3-card-sub">{_e(subtitle)}</div>' if subtitle else ""
    st_ctx.markdown(
        f'<div class="t3-content-card"><div class="t3-card-title">{_e(title)}</div>{sub}</div>',
        unsafe_allow_html=True,
    )


def _section(st_ctx, title: str) -> None:
    st_ctx.markdown(f'<div class="t3-form-section">{_e(title)}</div>', unsafe_allow_html=True)


def _sep(st_ctx) -> None:
    st_ctx.markdown('<hr class="t3-sep">', unsafe_allow_html=True)


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(value).strip(), fmt).date()
        except ValueError:
            continue
    return None


def _fmt_date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value else ""


def _guard(st_ctx, lang: str, fn: Callable[[], Any], default: Any = None) -> Any:
    """Veri/dosya hatalarini yakalar ve KULLANICIYA GOSTERIR.

    Eski kodda bu hatalar `except Exception: pass` ile yutuluyordu.
    """
    try:
        return fn()
    except (RecordNotFound, DuplicateRecord) as exc:
        st_ctx.error(f"{t('adm_data_error', lang)}: {exc}")
    except DataError as exc:
        st_ctx.error(f"{t('adm_data_error', lang)}: {exc}")
    except StorageError as exc:
        st_ctx.error(f"{t('adm_storage_error', lang)}: {exc}")
    except ValueError as exc:
        st_ctx.error(str(exc))
    return default


def _schedule_of(comp: Competition) -> dict[str, str]:
    if not comp.schedule_json:
        return {}
    try:
        data = json.loads(comp.schedule_json)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _rows_to_records(editor_value: Any) -> list[dict[str, Any]]:
    """`st.data_editor` ciktisini (DataFrame veya list) sozluk listesine cevirir."""
    if editor_value is None:
        return []
    if isinstance(editor_value, list):
        return [dict(r) for r in editor_value]
    to_dict = getattr(editor_value, "to_dict", None)
    if callable(to_dict):
        return list(to_dict("records"))
    return []


def _as_int(value: Any) -> int | None:
    if value in (None, "", "None"):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ═══════════════════════════════════════════════════════════════════════════
# Giris noktasi
# ═══════════════════════════════════════════════════════════════════════════
def goster(st_ctx, current_user: dict | None = None, lang: str = "tr") -> None:
    """Admin panelini render eder. Rol guard MODUL ICINDE uygulanir."""
    user = current_user or {}
    role = str(user.get("role", "")).lower()
    actor = str(user.get("user_id") or "")

    if not actor:
        st_ctx.error(t("adm_session_invalid", lang))
        return
    if role not in ("admin", "yonetici"):
        st_ctx.error(t("adm_no_permission", lang))
        return

    _card_open(st_ctx, t("adm_title", lang), t("adm_subtitle", lang))

    # URL'den alt sekmeyi ve seçili yarışmayı oku (Geri / İleri desteği)
    _y_subtab = st_ctx.query_params.get("subtab", "")
    if "yonetici_active_subtab" not in st_ctx.session_state:
        if _y_subtab in ("competitions", "pool", "calibration"):
            st_ctx.session_state.yonetici_active_subtab = _y_subtab
        else:
            st_ctx.session_state.yonetici_active_subtab = "competitions"
    elif _y_subtab in ("competitions", "pool", "calibration") and _y_subtab != st_ctx.session_state.yonetici_active_subtab:
        st_ctx.session_state.yonetici_active_subtab = _y_subtab

    _y_comp_id = st_ctx.query_params.get("comp_id", "")
    if _y_comp_id and st_ctx.session_state.get("adm_selected_comp") != _y_comp_id:
        st_ctx.session_state["adm_selected_comp"] = _y_comp_id
    elif not _y_comp_id and "adm_selected_comp" in st_ctx.session_state and not _y_subtab:
        st_ctx.session_state.pop("adm_selected_comp", None)

    y_cur = st_ctx.session_state.yonetici_active_subtab

    y_sw1, y_sw2, y_sw3 = st_ctx.columns(3)
    with y_sw1:
        y_b1 = "primary" if y_cur == "competitions" else "secondary"
        if st_ctx.button(t("tab_competitions", lang), key="sw_adm_comp", use_container_width=True, type=y_b1):
            st_ctx.session_state.yonetici_active_subtab = "competitions"
            st_ctx.query_params["subtab"] = "competitions"
            st_ctx.session_state.pop("adm_selected_comp", None)
            if "comp_id" in st_ctx.query_params:
                del st_ctx.query_params["comp_id"]
            st_ctx.rerun()
    with y_sw2:
        y_b2 = "primary" if y_cur == "pool" else "secondary"
        if st_ctx.button(t("tab_pool", lang), key="sw_adm_pool", use_container_width=True, type=y_b2):
            st_ctx.session_state.yonetici_active_subtab = "pool"
            st_ctx.query_params["subtab"] = "pool"
            st_ctx.session_state.pop("adm_selected_comp", None)
            if "comp_id" in st_ctx.query_params:
                del st_ctx.query_params["comp_id"]
            st_ctx.rerun()
    with y_sw3:
        y_b3 = "primary" if y_cur == "calibration" else "secondary"
        if st_ctx.button(t("tab_calibration", lang), key="sw_adm_cal", use_container_width=True, type=y_b3):
            st_ctx.session_state.yonetici_active_subtab = "calibration"
            st_ctx.query_params["subtab"] = "calibration"
            st_ctx.session_state.pop("adm_selected_comp", None)
            if "comp_id" in st_ctx.query_params:
                del st_ctx.query_params["comp_id"]
            st_ctx.rerun()

    st_ctx.markdown("<div style='margin-bottom: 14px;'></div>", unsafe_allow_html=True)

    if y_cur == "competitions":
        selected = st_ctx.session_state.get("adm_selected_comp")
        if selected:
            _render_detail(st_ctx, actor, lang, selected)
        else:
            _render_list(st_ctx, actor, lang)
    elif y_cur == "pool":
        _render_pool(st_ctx, actor, lang)
    elif y_cur == "calibration":
        _render_calibration(st_ctx, actor, lang)
    else:
        _render_list(st_ctx, actor, lang)


def render_announcements_view(st_ctx, current_user: dict | None = None, lang: str = "tr") -> None:
    """Yarışma yöneticisi ve admin için özel müstakil Duyuru Yönetimi ekranı."""
    user = current_user or {}
    actor = str(user.get("user_id") or "yonetici")
    _render_announcements(st_ctx, actor, lang)


# ═══════════════════════════════════════════════════════════════════════════
# A · Liste modu
# ═══════════════════════════════════════════════════════════════════════════
def _render_list(st_ctx, actor: str, lang: str) -> None:
    repo = repos().competitions

    if st_ctx.button(
        t("btn_close_form", lang) if st_ctx.session_state.get("adm_new_form")
        else t("btn_new_competition", lang),
        type="primary", key="adm_toggle_new",
    ):
        st_ctx.session_state["adm_new_form"] = not st_ctx.session_state.get("adm_new_form")
        st_ctx.rerun()

    if st_ctx.session_state.get("adm_new_form"):
        _render_create_form(st_ctx, actor, lang)

    _sep(st_ctx)

    col_a, col_b, col_c, col_d = st_ctx.columns([2.2, 1.3, 1.3, 1.3])
    search = col_a.text_input(t("lbl_search", lang), placeholder=t("ph_search", lang),
                              key="adm_search")
    domains = _guard(st_ctx, lang, repo.domains, []) or []
    levels = _guard(st_ctx, lang, repo.levels, []) or []
    domain = col_b.selectbox(t("lbl_filter_domain", lang),
                             [t("opt_all", lang)] + domains, key="adm_f_domain")
    level = col_c.selectbox(t("lbl_filter_level", lang),
                            [t("opt_all", lang)] + levels, key="adm_f_level")
    publish = col_d.selectbox(
        t("lbl_filter_publish", lang),
        [t("opt_all", lang)] + [t(_PUBLISH_BADGE[p][0], lang) for p in PublishStatus],
        key="adm_f_publish",
    )

    publish_value = None
    for status in PublishStatus:
        if publish == t(_PUBLISH_BADGE[status][0], lang):
            publish_value = status

    competitions = _guard(st_ctx, lang, lambda: repo.list(
        search=search or "",
        domain=None if domain == t("opt_all", lang) else domain,
        level=None if level == t("opt_all", lang) else level,
        publish_status=publish_value,
    ), []) or []

    st_ctx.caption(f"{t('lbl_result_count', lang)}: {len(competitions)}")
    if not competitions:
        st_ctx.info(t("msg_no_competition", lang))
        return

    for comp in competitions:
        _render_list_row(st_ctx, lang, comp)


def _render_list_row(st_ctx, lang: str, comp: Competition) -> None:
    repo = repos().competitions
    stages = _guard(st_ctx, lang, lambda: repo.list_stages(comp.competition_id), []) or []
    specs = _guard(st_ctx, lang, lambda: repo.list_specs(comp.competition_id), []) or []
    apps = _guard(st_ctx, lang,
                  lambda: repos().applications.count_for_competition(comp.competition_id), 0) or 0

    pub_key, pub_css = _PUBLISH_BADGE[comp.publish_status]
    spec_key, spec_css = _SPEC_BADGE[comp.spec_status]

    with st_ctx.container(border=True):
        head, action = st_ctx.columns([5.0, 1.2])
        stage_chip = f'<span style="background-color:#E0F2FE; color:#0369A1; padding:4px 10px; border-radius:999px; font-size:0.75rem; font-weight:700; margin-right:6px; display:inline-flex; align-items:center; gap:4px; border:1px solid #0369A130;">{len(stages)} Aşama</span>'
        spec_chip = f'<span style="background-color:#FEF3C7; color:#B45309; padding:4px 10px; border-radius:999px; font-size:0.75rem; font-weight:700; margin-right:6px; display:inline-flex; align-items:center; gap:4px; border:1px solid #B4530930;">{len(specs)} Şartname</span>'
        app_chip = f'<span style="background-color:#DCFCE7; color:#15803D; padding:4px 10px; border-radius:999px; font-size:0.75rem; font-weight:700; margin-right:6px; display:inline-flex; align-items:center; gap:4px; border:1px solid #15803D30;">{apps} Başvuru</span>'
        
        pub_bg, pub_fg, pub_icon = ("#F1F5F9", "#475569", "")
        if "aktif" in pub_css: pub_bg, pub_fg, pub_icon = ("#EFF6FF", "#1D4ED8", "")
        elif "pasif" in pub_css: pub_bg, pub_fg, pub_icon = ("#FEF2F2", "#B91C1C", "")
        pub_chip = f'<span style="background-color:{pub_bg}; color:{pub_fg}; padding:4px 10px; border-radius:999px; font-size:0.75rem; font-weight:700; margin-right:6px; display:inline-flex; align-items:center; gap:4px; border:1px solid {pub_fg}30;">{pub_icon} {t(pub_key, lang)}</span>'
        
        spec_bg, spec_fg, spec_icon = ("#F1F5F9", "#475569", "")
        if "aktif" in spec_css: spec_bg, spec_fg, spec_icon = ("#ECFEFF", "#0E7490", "")
        elif "turuncu" in spec_css: spec_bg, spec_fg, spec_icon = ("#FFF7ED", "#C2410C", "")
        spec_status_chip = f'<span style="background-color:{spec_bg}; color:{spec_fg}; padding:4px 10px; border-radius:999px; font-size:0.75rem; font-weight:700; margin-right:6px; display:inline-flex; align-items:center; gap:4px; border:1px solid {spec_fg}30;">{spec_icon} {t(spec_key, lang)}</span>'
        
        levels_text = _e(comp.levels or "-")
        head.markdown(
            f'<div class="t3-card-title" style="font-size:1.15rem; font-weight:800; color:#0F172A; margin-bottom:4px;">{_e(comp.name)}</div>'
            f'<div class="t3-card-sub" style="font-size:0.85rem; color:#64748B; margin-bottom:12px;">{_e(comp.domain)} - {levels_text}</div>'
            f'<div style="display:flex; flex-wrap:wrap; margin-bottom:8px;">'
            f'{pub_chip}{spec_status_chip}{stage_chip}{spec_chip}{app_chip}</div>',
            unsafe_allow_html=True,
        )
        if action.button(t("btn_manage", lang), key=f"adm_open_{comp.competition_id}",
                         type="primary", use_container_width=True):
            st_ctx.session_state["adm_selected_comp"] = comp.competition_id
            st_ctx.query_params["comp_id"] = comp.competition_id
            st_ctx.rerun()


def _render_create_form(st_ctx, actor: str, lang: str) -> None:
    repo = repos().competitions
    with st_ctx.form("adm_form_new_comp"):
        _section(st_ctx, t("frm_new_title", lang))
        col1, col2 = st_ctx.columns(2)
        name = col1.text_input(t("lbl_name", lang), placeholder=t("ph_name", lang))
        domain = col2.selectbox(t("lbl_domain_new", lang), DOMAIN_SUGGESTIONS)
        col3, col4 = st_ctx.columns(2)
        sub_category = col3.text_input(t("lbl_sub_category", lang))
        levels = col4.multiselect(t("lbl_levels", lang), LEVEL_OPTIONS, default=["Lise", "Universite"])
        description = st_ctx.text_area(t("lbl_description", lang),
                                       placeholder=t("ph_description", lang), height=90)

        _sep(st_ctx)
        _section(st_ctx, t("sec_schedule", lang))
        d1, d2, d3 = st_ctx.columns(3)
        apply_on = d1.date_input(t("lbl_deadline_apply", lang), value=None, format="DD.MM.YYYY")
        race_on = d2.date_input(t("lbl_date_competition", lang), value=None, format="DD.MM.YYYY")
        result_on = d3.date_input(t("lbl_date_result", lang), value=None, format="DD.MM.YYYY")

        slug_preview = slugify(name) if name else ""
        st_ctx.caption(f"{t('lbl_slug', lang)}: `{slug_preview or '-'}` · {t('help_slug', lang)}")

        if st_ctx.form_submit_button(t("btn_create", lang), type="primary"):
            if not name.strip():
                st_ctx.error(t("err_name_required", lang))
                return
            if not domain:
                st_ctx.error(t("err_domain_required", lang))
                return
            slug = slugify(name)
            schedule = {k: _fmt_date(v) for k, v in (
                ("son_basvuru", apply_on), ("yarisma_tarihi", race_on), ("sonuc_tarihi", result_on),
            ) if v}
            comp = Competition(
                competition_id=slug, name=name.strip(), slug=slug, domain=domain,
                sub_category=sub_category.strip() or None,
                levels=", ".join(levels) if levels else None,
                description=description.strip() or None,
                schedule_json=json.dumps(schedule, ensure_ascii=False) if schedule else None,
                publish_status=PublishStatus.TASLAK,
            )
            created = _guard(st_ctx, lang, lambda: repo.create(comp, actor=actor))
            if created:
                st_ctx.success(t("succ_created", lang))
                st_ctx.session_state["adm_new_form"] = False
                st_ctx.session_state["adm_selected_comp"] = created.competition_id
                st_ctx.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# B · Yarisma detayi
# ═══════════════════════════════════════════════════════════════════════════
def _render_detail(st_ctx, actor: str, lang: str, competition_id: str) -> None:
    repo = repos().competitions
    comp = _guard(st_ctx, lang, lambda: repo.get(competition_id))
    if comp is None:
        st_ctx.error(t("msg_no_competition", lang))
        if st_ctx.button(t("btn_back_to_list", lang), key="adm_back_missing"):
            st_ctx.session_state.pop("adm_selected_comp", None)
            st_ctx.rerun()
        return

    back, title = st_ctx.columns([1.2, 5.0])
    if back.button(t("btn_back_to_list", lang), key="adm_back"):
        st_ctx.session_state.pop("adm_selected_comp", None)
        if "comp_id" in st_ctx.query_params:
            del st_ctx.query_params["comp_id"]
        st_ctx.rerun()
    pub_key, pub_css = _PUBLISH_BADGE[comp.publish_status]
    title.markdown(
        f'<div class="t3-card-title">{_e(comp.name)}</div>'
        f'<div class="t3-card-sub">{_e(comp.domain)}</div>'
        f'<div style="margin-top:6px;">{_badge(t(pub_key, lang), pub_css)}</div>',
        unsafe_allow_html=True,
    )

    tabs = st_ctx.tabs([
        t("tab_general", lang), t("tab_spec", lang), t("tab_stage", lang),
        t("tab_apps", lang), t("tab_delete", lang),
    ])
    with tabs[0]:
        _render_general(st_ctx, actor, lang, comp)
    with tabs[1]:
        _render_specs(st_ctx, actor, lang, comp)
    with tabs[2]:
        _render_stages(st_ctx, actor, lang, comp)
    with tabs[3]:
        _render_applications(st_ctx, actor, lang, comp)
    with tabs[4]:
        _render_delete(st_ctx, actor, lang, comp)


# ── B1 · Genel bilgiler ve bagimsiz takvim ────────────────────────────────
def _render_general(st_ctx, actor: str, lang: str, comp: Competition) -> None:
    repo = repos().competitions
    schedule = _schedule_of(comp)
    st_ctx.info(t("info_no_autosave", lang))

    with st_ctx.form(f"adm_general_{comp.competition_id}"):
        _section(st_ctx, t("frm_general_title", lang))
        col1, col2 = st_ctx.columns(2)
        name = col1.text_input(t("lbl_name", lang), value=comp.name)
        domain_options = DOMAIN_SUGGESTIONS + ([comp.domain] if comp.domain not in DOMAIN_SUGGESTIONS else [])
        domain = col2.selectbox(t("lbl_domain", lang), domain_options,
                                index=domain_options.index(comp.domain) if comp.domain in domain_options else 0)
        col3, col4 = st_ctx.columns(2)
        sub_category = col3.text_input(t("lbl_sub_category", lang), value=comp.sub_category or "")
        current_levels = [lv for lv in (comp.levels or "").split(",") if lv.strip()]
        levels = col4.multiselect(t("lbl_levels", lang), LEVEL_OPTIONS,
                                  default=[lv.strip() for lv in current_levels if lv.strip() in LEVEL_OPTIONS])
        description = st_ctx.text_area(t("lbl_description", lang),
                                       value=comp.description or "", height=110)
        publish = st_ctx.selectbox(
            t("lbl_publish_status", lang),
            list(PublishStatus),
            index=list(PublishStatus).index(comp.publish_status),
            format_func=lambda p: t(_PUBLISH_BADGE[p][0], lang),
        )

        _sep(st_ctx)
        _section(st_ctx, t("sec_schedule", lang))
        st_ctx.caption(t("info_schedule_partial", lang))
        d1, d2, d3 = st_ctx.columns(3)
        apply_on = d1.date_input(t("lbl_deadline_apply", lang),
                                 value=_parse_date(schedule.get("son_basvuru")), format="DD.MM.YYYY")
        race_on = d2.date_input(t("lbl_date_competition", lang),
                                value=_parse_date(schedule.get("yarisma_tarihi")), format="DD.MM.YYYY")
        result_on = d3.date_input(t("lbl_date_result", lang),
                                  value=_parse_date(schedule.get("sonuc_tarihi")), format="DD.MM.YYYY")

        if st_ctx.form_submit_button(t("btn_save_general", lang), type="primary"):
            if not name.strip():
                st_ctx.error(t("err_name_required", lang))
                return
            changes: dict[str, Any] = {
                "name": name.strip(),
                "domain": domain,
                "sub_category": sub_category.strip() or None,
                "levels": ", ".join(levels) if levels else None,
                "description": description.strip() or None,
                "publish_status": publish.value,
            }
            updated = _guard(st_ctx, lang,
                             lambda: repo.update(comp.competition_id, changes, actor=actor))
            if updated is None:
                return
            new_schedule = {k: _fmt_date(v) for k, v in (
                ("son_basvuru", apply_on), ("yarisma_tarihi", race_on), ("sonuc_tarihi", result_on),
            ) if v}
            if new_schedule:
                _guard(st_ctx, lang,
                       lambda: repo.set_schedule(comp.competition_id, new_schedule, actor=actor))
            st_ctx.success(t("succ_general_saved", lang))
            st_ctx.rerun()


# ── B2 · Sartname ve AI kural cikarici ────────────────────────────────────
def _render_specs(st_ctx, actor: str, lang: str, comp: Competition) -> None:
    repo = repos().competitions
    storage = repos().storage
    specs = _guard(st_ctx, lang, lambda: repo.list_specs(comp.competition_id), []) or []

    _section(st_ctx, t("sec_spec_upload", lang))
    with st_ctx.form(f"adm_spec_upload_{comp.competition_id}", clear_on_submit=True):
        col1, col2 = st_ctx.columns(2)
        title = col1.text_input(t("lbl_spec_title", lang))
        branch_code = col2.text_input(t("lbl_branch_code", lang),
                                      help=t("help_branch_code", lang))
        branch_name = st_ctx.text_input(t("lbl_branch_name", lang))
        is_primary = st_ctx.checkbox(t("chk_primary", lang), value=not specs)
        upload = st_ctx.file_uploader(t("lbl_spec_file", lang), type=["pdf"])

        if st_ctx.form_submit_button(t("btn_upload_spec", lang), type="primary"):
            if upload is None:
                st_ctx.error(t("err_spec_file_required", lang))
                return
            if not title.strip():
                st_ctx.error(t("err_spec_title_required", lang))
                return
            code = slugify(branch_code) if branch_code.strip() else None
            key = Keys.spec(comp.slug, code)

            def _do() -> CompetitionSpec:
                storage.upload(upload.getvalue(), key, "application/pdf")
                spec = CompetitionSpec(
                    competition_id=comp.competition_id, title=title.strip(),
                    branch_code=code, branch_name=branch_name.strip() or None,
                    r2_key=key, original_name=upload.name, is_primary=is_primary,
                )
                return repo.add_spec(spec, actor=actor)

            if _guard(st_ctx, lang, _do):
                st_ctx.success(t("succ_spec_uploaded", lang))
                st_ctx.rerun()

    _sep(st_ctx)
    _section(st_ctx, t("sec_spec_list", lang))
    if not specs:
        st_ctx.info(t("msg_no_spec", lang))
        return

    for spec in specs:
        with st_ctx.container(border=True):
            info, act = st_ctx.columns([4.5, 1.6])
            label = spec.branch_name or spec.branch_code or t("opt_branch_none", lang)
            info.markdown(
                f'<div class="t3-form-section">{_e(spec.title)}</div>'
                f'<div class="ts-muted">{_e(t("col_branch", lang))}: {_e(label)}</div>'
                f'<div class="ts-muted">{_e(t("lbl_spec_key", lang))}: <code>{_e(spec.r2_key)}</code></div>',
                unsafe_allow_html=True,
            )
            url = _guard(st_ctx, lang, lambda: storage.url_for(spec.r2_key))
            if url:
                act.link_button(t("btn_open_file", lang), url, use_container_width=True)
            if act.button(t("btn_delete_spec", lang), key=f"adm_del_spec_{spec.spec_id}",
                          use_container_width=True):
                _guard(st_ctx, lang, lambda: repo.delete_spec(spec.spec_id, actor=actor))
                st_ctx.success(t("succ_spec_deleted", lang))
                st_ctx.rerun()

            if st_ctx.button(t("btn_extract_rules", lang),
                             key=f"adm_ai_spec_{spec.spec_id}", type="primary"):
                _run_spec_analysis(st_ctx, actor, lang, comp, spec)

        _render_rules_editor(st_ctx, actor, lang, comp, spec.branch_code)


def _run_spec_analysis(st_ctx, actor: str, lang: str,
                       comp: Competition, spec: CompetitionSpec) -> None:
    """Sartnameyi GERCEK LLM ile analiz eder. LLM yoksa acik hata gosterir."""
    from src.ai.spec_analyzer import LLMUnavailable, analyze_specification

    storage = repos().storage
    with st_ctx.spinner(t("msg_ai_running", lang)):
        try:
            data = storage.download_bytes(spec.r2_key)
            analysis = analyze_specification(
                data,
                competition_id=comp.competition_id,
                competition_name=comp.name,
                branch_code=spec.branch_code,
                branch_name=spec.branch_name,
                spec_id=spec.spec_id,
            )
        except LLMUnavailable as exc:
            st_ctx.error(f"{t('adm_ai_error', lang)}: {exc}")
            return
        except (StorageError, RuntimeError, ValueError) as exc:
            st_ctx.error(f"{t('adm_ai_error', lang)}: {exc}")
            return

    st_ctx.session_state[f"adm_rules_{comp.competition_id}_{spec.branch_code or ''}"] = [
        _requirement_to_row(r) for r in analysis.requirements
    ]
    _guard(st_ctx, lang, lambda: repos().competitions.update(
        comp.competition_id, {"spec_status": SpecStatus.ANALIZ_EDILDI.value}, actor=actor))
    if analysis.schedule:
        _guard(st_ctx, lang, lambda: repos().competitions.set_schedule(
            comp.competition_id, analysis.schedule, actor=actor))
    for warning in analysis.warnings:
        st_ctx.warning(f"{t('warn_ai', lang)}: {warning}")
    st_ctx.success(f"{t('succ_rules_extracted', lang)} ({len(analysis.requirements)})")
    st_ctx.rerun()


def _requirement_to_row(req: Requirement) -> dict[str, Any]:
    return {
        "rule_type": req.rule_type.value,
        "title": req.title,
        "description": req.description or "",
        "min_team_size": req.min_team_size,
        "max_team_size": req.max_team_size,
        "advisor_required": bool(req.advisor_required),
        "target_level": req.target_level or "",
        "is_mandatory": bool(req.is_mandatory),
        "source_quote": req.source_quote or "",
        "sil": False,
    }


def _render_rules_editor(st_ctx, actor: str, lang: str,
                         comp: Competition, branch_code: str | None) -> None:
    """Canli duzenlenebilir kural tablosu + acik KAYDET butonu."""
    repo = repos().competitions
    state_key = f"adm_rules_{comp.competition_id}_{branch_code or ''}"

    if state_key not in st_ctx.session_state:
        existing = _guard(st_ctx, lang,
                          lambda: repo.list_requirements(comp.competition_id, branch_code), []) or []
        if not existing:
            try:
                import sartname_rehber
                zk = sartname_rehber.sartnameden_kategori_zorunluluklarini_cikar(comp.competition_id)
                min_t = zk.get("takim_uye_sayisi", {}).get("min", 2)
                max_t = zk.get("takim_uye_sayisi", {}).get("max", 6)
                lvl = zk.get("hedef_egitim_seviyesi", "Lise / Üniversite / Lisansüstü")
                adv_req = "zorunlu" in zk.get("danisman_sarti", "").lower()
                existing = [
                    Requirement(
                        competition_id=comp.competition_id,
                        rule_type=RuleType.TAKIM,
                        title="Takım Üye Sayısı Sınırı",
                        description=f"Takımlar en az {min_t}, en fazla {max_t} kişiden oluşmalıdır.",
                        min_team_size=min_t,
                        max_team_size=max_t,
                        advisor_required=adv_req,
                        target_level=lvl,
                        is_mandatory=True,
                        approved_by_admin=True,
                        order_index=1,
                        source_quote="Şartname Katılım ve Takım Koşulları",
                    ),
                    Requirement(
                        competition_id=comp.competition_id,
                        rule_type=RuleType.KATILIM,
                        title="Hedef Eğitim Seviyesi ve Katılım Koşulu",
                        description=f"Bu yarışmaya {lvl} seviyesindeki öğrenciler başvurabilir.",
                        min_team_size=min_t,
                        max_team_size=max_t,
                        advisor_required=adv_req,
                        target_level=lvl,
                        is_mandatory=True,
                        approved_by_admin=True,
                        order_index=2,
                        source_quote="Şartname Hedef Seviye",
                    ),
                    Requirement(
                        competition_id=comp.competition_id,
                        rule_type=RuleType.DANISMAN,
                        title="Danışman Şartı",
                        description=zk.get("danisman_sarti", "Lise seviyesi için zorunlu, üniversite için isteğe bağlıdır."),
                        advisor_required=adv_req,
                        target_level=lvl,
                        is_mandatory=adv_req,
                        approved_by_admin=True,
                        order_index=3,
                        source_quote="Şartname Danışman İlkeleri",
                    ),
                    Requirement(
                        competition_id=comp.competition_id,
                        rule_type=RuleType.DIL,
                        title="Raporlama ve Sunum Dili",
                        description="Rapor ve sunumlar resmî olarak Türkçe hazırlanmalıdır.",
                        is_mandatory=True,
                        approved_by_admin=True,
                        order_index=4,
                        source_quote="Şartname Dil Standartları",
                    ),
                    Requirement(
                        competition_id=comp.competition_id,
                        rule_type=RuleType.TEKNIK,
                        title="Özgünlük ve İntihal Sınırı",
                        description="Raporlardaki intihal ve benzerlik oranı azami %15 olmalıdır.",
                        is_mandatory=True,
                        approved_by_admin=True,
                        order_index=5,
                        source_quote="Şartname Etik ve Özgünlük İlkeleri",
                    ),
                ]
            except Exception:
                pass
        st_ctx.session_state[state_key] = [_requirement_to_row(r) for r in existing]

    rows = st_ctx.session_state[state_key]
    active_rules = len([r for r in rows if not r.get("sil")])
    _section(st_ctx, t("sec_rules", lang) + f" ({active_rules})")
    if not rows:
        st_ctx.info(t("msg_no_rules", lang))

    edited = st_ctx.data_editor(
        rows,
        key=f"{state_key}_editor",
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "rule_type": st_ctx.column_config.SelectboxColumn(
                t("col_rule_type", lang), options=[r.value for r in RuleType], required=True),
            "title": st_ctx.column_config.TextColumn(t("col_title", lang), required=True),
            "description": st_ctx.column_config.TextColumn(t("col_description", lang)),
            "min_team_size": st_ctx.column_config.NumberColumn(t("col_min_team", lang), min_value=1),
            "max_team_size": st_ctx.column_config.NumberColumn(t("col_max_team", lang), min_value=1),
            "advisor_required": st_ctx.column_config.CheckboxColumn(t("col_advisor", lang)),
            "target_level": st_ctx.column_config.TextColumn(t("col_target_level", lang)),
            "is_mandatory": st_ctx.column_config.CheckboxColumn(t("col_mandatory", lang)),
            "source_quote": st_ctx.column_config.TextColumn(t("col_source_quote", lang), disabled=True),
            "sil": st_ctx.column_config.CheckboxColumn(t("chk_delete_file_too", lang)),
        },
    )

    col_save, col_approve = st_ctx.columns(2)
    if col_save.button(t("btn_save_rules", lang), key=f"{state_key}_save",
                       type="primary", use_container_width=True):
        records = [r for r in _rows_to_records(edited) if not r.get("sil")]
        requirements: list[Requirement] = []
        for record in records:
            title = str(record.get("title") or "").strip()
            if not title:
                st_ctx.error(t("err_rule_title_required", lang))
                return
            try:
                rule_type = RuleType(str(record.get("rule_type") or "diger"))
            except ValueError:
                rule_type = RuleType.DIGER
            requirements.append(Requirement(
                competition_id=comp.competition_id, branch_code=branch_code,
                rule_type=rule_type, title=title,
                description=str(record.get("description") or "").strip() or None,
                min_team_size=_as_int(record.get("min_team_size")),
                max_team_size=_as_int(record.get("max_team_size")),
                advisor_required=bool(record.get("advisor_required")),
                target_level=str(record.get("target_level") or "").strip() or None,
                is_mandatory=bool(record.get("is_mandatory", True)),
                source_quote=str(record.get("source_quote") or "").strip() or None,
            ))
        saved = _guard(st_ctx, lang, lambda: repo.replace_requirements(
            comp.competition_id, requirements, branch_code=branch_code, actor=actor))
        if saved is not None:
            st_ctx.session_state[state_key] = [_requirement_to_row(r) for r in requirements]
            st_ctx.success(t("succ_rules_saved", lang))
            st_ctx.rerun()

    if col_approve.button(t("btn_approve_rules", lang), key=f"{state_key}_approve",
                          use_container_width=True):
        _guard(st_ctx, lang, lambda: repo.approve_requirements(comp.competition_id, actor=actor))
        st_ctx.success(t("succ_rules_approved", lang))
        st_ctx.rerun()


# ── B3 · Asamalar, sablon ve AI rubrik ────────────────────────────────────
def _render_stages(st_ctx, actor: str, lang: str, comp: Competition) -> None:
    repo = repos().competitions
    stages = _guard(st_ctx, lang, lambda: repo.list_stages(comp.competition_id), []) or []

    _section(st_ctx, t("sec_stage_add", lang))
    with st_ctx.form(f"adm_stage_add_{comp.competition_id}", clear_on_submit=True):
        col1, col2, col3 = st_ctx.columns([1.0, 2.0, 1.2])
        stage_code = col1.text_input(t("lbl_stage_code", lang), help=t("help_stage_code", lang))
        stage_name = col2.text_input(t("lbl_stage_name", lang))
        level = col3.selectbox(t("lbl_level", lang), LEVEL_OPTIONS,
                               index=LEVEL_OPTIONS.index("Genel"))
        col4, col5, col6 = st_ctx.columns(3)
        max_pages = col4.number_input(t("lbl_max_pages", lang), min_value=1, max_value=200, value=25)
        deadline = col5.date_input(t("lbl_deadline_stage", lang), value=None, format="DD.MM.YYYY")
        order_index = col6.number_input(t("lbl_order", lang), min_value=0, max_value=50, value=len(stages))

        if st_ctx.form_submit_button(t("btn_add_stage", lang), type="primary"):
            if not stage_code.strip():
                st_ctx.error(t("err_stage_code_required", lang))
                return
            stage = Stage(
                competition_id=comp.competition_id, stage_code=stage_code.strip().upper(),
                stage_name=stage_name.strip() or stage_code.strip().upper(),
                level=level, max_pages=int(max_pages),
                deadline=_fmt_date(deadline) or None, order_index=int(order_index),
            )
            if _guard(st_ctx, lang, lambda: repo.add_stage(stage, actor=actor)):
                st_ctx.success(t("succ_stage_added", lang))
                st_ctx.rerun()

    _sep(st_ctx)
    if not stages:
        st_ctx.info(t("msg_no_stage", lang))
        return

    for stage in stages:
        _render_stage_card(st_ctx, actor, lang, comp, stage)


def _render_stage_card(st_ctx, actor: str, lang: str, comp: Competition, stage: Stage) -> None:
    repo = repos().competitions
    storage = repos().storage
    rub_key, rub_css = _RUBRIC_BADGE[stage.rubric_status]

    with st_ctx.expander(f"{stage.stage_code} · {stage.stage_name} · {stage.level}", expanded=False):
        st_ctx.markdown(_badge(t(rub_key, lang), rub_css), unsafe_allow_html=True)
        if stage.is_auto_generated:
            st_ctx.caption(t("info_default_stage", lang))

        with st_ctx.form(f"adm_stage_edit_{stage.stage_id}"):
            col1, col2, col3 = st_ctx.columns([2.0, 1.0, 1.2])
            stage_name = col1.text_input(t("lbl_stage_name", lang), value=stage.stage_name)
            max_pages = col2.number_input(t("lbl_max_pages", lang), min_value=1, max_value=200,
                                          value=int(stage.max_pages or 25))
            deadline = col3.date_input(t("lbl_deadline_stage", lang),
                                       value=_parse_date(stage.deadline), format="DD.MM.YYYY")
            
            # --- BARAJ SİSTEMİ EKLENTİSİ ---
            _section(st_ctx, t("sec_stage_baraj", lang) if "sec_stage_baraj" in t.__globals__ else "Baraj ve Eleme Ayarları")
            b_col1, b_col2, b_col3 = st_ctx.columns(3)
            passing_score = b_col1.number_input("Geçme Barajı Puanı", min_value=0.0, max_value=100.0, value=float(stage.passing_score), step=1.0)
            revision_min_score = b_col2.number_input("Revizyon Alt Sınırı", min_value=0.0, max_value=100.0, value=float(stage.revision_min_score), step=1.0)
            quota_val = stage.quota_limit if stage.quota_limit is not None else 0
            quota_limit = b_col3.number_input("Kontenjan (Sıralama Sınırı)", min_value=0, value=quota_val, step=1, help="0 ise limitsiz")
            
            font_rules = st_ctx.text_input("Yazi tipi / marj", value=stage.font_and_margins or "")
            if st_ctx.form_submit_button(t("btn_save_stage", lang), type="primary"):
                changes = {
                    "stage_name": stage_name.strip() or stage.stage_code,
                    "max_pages": int(max_pages),
                    "deadline": _fmt_date(deadline) or None,
                    "font_and_margins": font_rules.strip() or None,
                    "passing_score": float(passing_score),
                    "revision_min_score": float(revision_min_score),
                    "quota_limit": int(quota_limit) if quota_limit > 0 else None,
                }
                if _guard(st_ctx, lang,
                          lambda: repo.update_stage(stage.stage_id, changes, actor=actor)):
                    st_ctx.success(t("succ_stage_saved", lang))
                    st_ctx.rerun()

        _sep(st_ctx)
        _section(st_ctx, t("sec_template", lang))
        upload = st_ctx.file_uploader(t("lbl_template_file", lang), type=["docx", "pdf"],
                                      key=f"adm_tpl_{stage.stage_id}")
        if upload is not None and st_ctx.button(t("btn_upload_template", lang),
                                                key=f"adm_tpl_btn_{stage.stage_id}", type="primary"):
            _upload_template(st_ctx, actor, lang, comp, stage, upload)

        if stage.sablon_docx_r2_key:
            url = _guard(st_ctx, lang, lambda: storage.url_for(stage.sablon_docx_r2_key))
            if url:
                st_ctx.link_button(t("btn_open_file", lang) + " (.docx)", url)
        if stage.sablon_pdf_r2_key:
            url = _guard(st_ctx, lang, lambda: storage.url_for(stage.sablon_pdf_r2_key))
            if url:
                st_ctx.link_button(t("btn_open_file", lang) + " (.pdf)", url)

        if stage.sablon_docx_r2_key or stage.sablon_pdf_r2_key:
            if st_ctx.button(t("btn_extract_rubric", lang),
                             key=f"adm_ai_tpl_{stage.stage_id}", type="primary"):
                _run_template_analysis(st_ctx, actor, lang, comp, stage)
        else:
            st_ctx.caption(t("err_no_template", lang))

        _render_rubric_editor(st_ctx, actor, lang, comp, stage)

        _sep(st_ctx)
        _render_stage_reports(st_ctx, actor, lang, comp, stage)

        _sep(st_ctx)
        _render_stage_calculations(st_ctx, actor, lang, comp, stage)

        _sep(st_ctx)
        if st_ctx.button(t("btn_delete_stage", lang), key=f"adm_del_stage_{stage.stage_id}"):
            _guard(st_ctx, lang, lambda: repo.delete_stage(stage.stage_id, actor=actor))
            st_ctx.success(t("succ_stage_deleted", lang))
            st_ctx.rerun()

def _render_stage_reports(st_ctx, actor: str, lang: str,
                          comp: Competition, stage: Stage) -> None:
    """Aşamaya ait rapor sonuçlarını listeler ve yöneticinin sonuç açıklaması yazmasını sağlar."""
    report_repo = repos().reports
    team_repo = repos().teams
    app_repo = repos().applications

    reports = _guard(st_ctx, lang,
                     lambda: report_repo.list_for_admin(
                         competition_id=comp.competition_id,
                         stage_code=stage.stage_code), []) or []

    _section(st_ctx, t("sec_stage_reports", lang) + f" ({len(reports)})")

    if not reports:
        st_ctx.info(t("msg_no_stage_report", lang))
        return

    # Raporları takım bilgileriyle eşleştir
    for report in reports:
        app = _guard(st_ctx, lang, lambda: app_repo.get(report.app_id))
        team = _guard(st_ctx, lang, lambda: team_repo.get(app.team_id)) if app else None
        team_label = team.name if team else (report.app_id[:8] if report.app_id else "?")

        # Durum rozeti
        status_label = report.status.label_tr if lang == "tr" else report.status.label_en
        tone_css = {
            "ok": "t3-badge-aktif", "warn": "t3-badge-turuncu",
            "info": "t3-badge-info", "crit": "t3-badge-kirmizi",
        }.get(report.status.tone, "t3-badge-info")
        status_chip = _badge(status_label, tone_css)

        # Puan rozeti
        score_text = ""
        if getattr(report, "referee_score", None) is not None:
            score_text += _badge(f"Hakem: {report.referee_score:.1f}", "t3-badge-aktif") + " "
        if getattr(report, "ai_score", None) is not None:
            score_text += _badge(f"AI: {report.ai_score:.1f}", "t3-badge-info")

        with st_ctx.container(border=True):
            st_ctx.markdown(f"** {_e(team_label)} · {report.file_name} · v{report.version}**")
            # Rapor özet bilgileri
            team_code_txt = _e(team.team_code if team else "-")
            level_txt = _e(app.level if app else "-")
            st_ctx.markdown(
                f'<div class="ts-kv">'
                f'<span>{_e(t("col_team_code", lang))}: <code>{team_code_txt}</code> · '
                f'{_e(t("col_level", lang))}: {level_txt}</span>'
                f'<span>{status_chip} {score_text}</span></div>',
                unsafe_allow_html=True,
            )

            # Yöneticinin not girme alanı iptal edildi (Hakemin notu direkt yarışmacıya gidecek)
            # Sadece durum güncelleme alanı bırakıldı
            
            # Durum güncelleme
            col_status, col_btn = st_ctx.columns([3, 1])
            new_status = col_status.selectbox(
                t("lbl_report_status", lang),
                list(ReportStatus),
                index=list(ReportStatus).index(report.status),
                format_func=lambda s: s.label_tr if lang == "tr" else s.label_en,
                key=f"adm_rpt_st_{stage.stage_id}_{report.report_id}",
            )

            if col_btn.button(
                t("btn_publish_result", lang),
                key=f"adm_rpt_pub_{stage.stage_id}_{report.report_id}",
                type="primary",
                use_container_width=True,
            ):
                changes = {}
                if new_status != report.status:
                    changes["status"] = new_status.value
                _guard(st_ctx, lang,
                       lambda: report_repo.update(report.report_id, changes, actor=actor))
                st_ctx.success(t("succ_result_published", lang))
                st_ctx.rerun()

def _render_stage_calculations(st_ctx, actor: str, lang: str, comp: Competition, stage: Stage) -> None:
    """Aşama değerlendirme sonuçlarını hesaplar, sıralar ve ilan edilmesini sağlar."""
    import pandas as pd
    from io import BytesIO
    report_repo = repos().reports
    app_repo = repos().applications
    team_repo = repos().teams

    _section(st_ctx, "Sonuç Hesaplama & İlan İşlemleri")

    reports = _guard(st_ctx, lang, lambda: report_repo.list_for_admin(competition_id=comp.competition_id, stage_code=stage.stage_code), []) or []
    if not reports:
        st_ctx.info("Hesaplanacak rapor bulunamadı.")
        return

    # Sadece puanı olan raporları dahil et veya hepsini listele
    results = []
    for r in reports:
        app = _guard(st_ctx, lang, lambda: app_repo.get(r.app_id))
        team = _guard(st_ctx, lang, lambda: team_repo.get(app.team_id)) if app else None
        
        ref_score = getattr(r, "referee_score", None)
        ai_score = getattr(r, "ai_score", None)
        score = ref_score if ref_score is not None else (ai_score if ai_score is not None else 0.0)
        
        # Durum tespiti:
        if score >= stage.passing_score:
            status = " BAŞARILI"
        elif score >= stage.revision_min_score:
            status = " REVİZYON"
        else:
            status = " ELENDİ"
            
        results.append({
            "report_id": r.report_id,
            "team_name": team.name if team else "?",
            "team_code": team.team_code if team else "?",
            "score": score,
            "status": status,
            "level": app.level if app else "-",
            "current_decision": r.decision
        })

    # Skora göre azalan sıralama
    results.sort(key=lambda x: x["score"], reverse=True)
    
    # Kotaya göre eleme (eğer kontenjan limiti varsa)
    if stage.quota_limit and stage.quota_limit > 0:
        for i, res in enumerate(results):
            if i >= stage.quota_limit and res["status"] == " BAŞARILI":
                res["status"] = " KOTA ALTI (ELENDİ)"

    df = pd.DataFrame(results)
    df.index = df.index + 1
    
    st_ctx.dataframe(
        df[["team_name", "team_code", "level", "score", "status"]],
        use_container_width=True,
        column_config={
            "team_name": "Takım Adı",
            "team_code": "Takım Kodu",
            "level": "Seviye",
            "score": st_ctx.column_config.ProgressColumn("Puan", format="%.2f", min_value=0, max_value=100),
            "status": "Durum"
        }
    )

    col1, col2, col3 = st_ctx.columns(3)
    
    # Excel Dışa Aktar
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=True, sheet_name='Sonuclar')
    excel_data = output.getvalue()
    col1.download_button("Excel Olarak İndir", data=excel_data, file_name=f"{stage.stage_code}_sonuclar.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
    
    if col2.button("Sonuçları Hesapla & Kararları Uygula", use_container_width=True, type="secondary"):
        for res in results:
            decision_text = f"Otomatik Karar: {res['status']}"
            if res["current_decision"]:
                decision_text = res["current_decision"] # Mevcut notu ezme
            changes = {"decision": decision_text}
            # İsteğe bağlı olarak report status da güncellenebilir
            _guard(st_ctx, lang, lambda: report_repo.update(res["report_id"], changes, actor=actor))
        # Aşama durumunu HESAPLANDI yap
        _guard(st_ctx, lang, lambda: repos().competitions.update_stage(stage.stage_id, {"stage_status": "HESAPLANDI"}, actor=actor))
        st_ctx.success("Sonuçlar hesaplandı ve raporlara işlendi.")
        st_ctx.rerun()

    if stage.stage_status in ("HESAPLANDI", "ILAN_EDILDI"):
        btn_type = "primary" if stage.stage_status == "HESAPLANDI" else "secondary"
        btn_label = "Sonuçları Resmen İlan Et" if stage.stage_status == "HESAPLANDI" else "Sonuçlar İlan Edildi (Yeniden İlan Et)"
        if col3.button(btn_label, use_container_width=True, type=btn_type):
            _guard(st_ctx, lang, lambda: repos().competitions.update_stage(stage.stage_id, {"stage_status": "ILAN_EDILDI"}, actor=actor))
            st_ctx.success("Sonuçlar yarışmacı panellerinde duyuruldu!")
            st_ctx.rerun()


def _upload_template(st_ctx, actor: str, lang: str, comp: Competition,
                     stage: Stage, upload: Any) -> None:
    """Sablonu R2'ye yukler; DOCX ise PDF uretmeyi dener.

    Donusum basarisiz olursa ACIK HATA gosterilir — eski kod basarisiz
    donusumde bile "basariyla PDF'e donusturuldu" diyordu.
    """
    storage = repos().storage
    repo = repos().competitions
    data = upload.getvalue()
    is_docx = upload.name.lower().endswith(".docx")
    changes: dict[str, Any] = {}

    def _do_upload() -> bool:
        ext = "docx" if is_docx else "pdf"
        key = Keys.template(comp.slug, stage.stage_code, stage.level, ext, stage.branch_code)
        storage.upload(data, key, None)
        changes["sablon_docx_r2_key" if is_docx else "sablon_pdf_r2_key"] = key
        return True

    if _guard(st_ctx, lang, _do_upload) is None:
        return
    st_ctx.success(t("succ_template_uploaded", lang))

    if is_docx:
        try:
            from src.services.doc_converter import ConversionError, docx_to_pdf_bytes

            pdf_bytes = docx_to_pdf_bytes(data)
            pdf_key = Keys.template(comp.slug, stage.stage_code, stage.level, "pdf", stage.branch_code)
            storage.upload(pdf_bytes, pdf_key, "application/pdf")
            changes["sablon_pdf_r2_key"] = pdf_key
            st_ctx.success(t("succ_pdf_generated", lang))
        except ImportError:
            st_ctx.warning(t("err_pdf_failed", lang))
        except Exception as exc:  # ConversionError dahil — ACIK gosterilir
            st_ctx.warning(f"{t('err_pdf_failed', lang)}: {exc}")

    _guard(st_ctx, lang, lambda: repo.update_stage(stage.stage_id, changes, actor=actor))
    st_ctx.rerun()


def _run_template_analysis(st_ctx, actor: str, lang: str,
                           comp: Competition, stage: Stage) -> None:
    from src.ai.template_analyzer import LLMUnavailable, analyze_template

    storage = repos().storage
    key = stage.sablon_docx_r2_key or stage.sablon_pdf_r2_key
    with st_ctx.spinner(t("msg_rubric_running", lang)):
        try:
            data = storage.download_bytes(key)
            analysis = analyze_template(
                data,
                competition_id=comp.competition_id, competition_name=comp.name,
                stage_code=stage.stage_code, stage_name=stage.stage_name,
                level=stage.level, branch_code=stage.branch_code,
            )
        except LLMUnavailable as exc:
            st_ctx.error(f"{t('adm_ai_error', lang)}: {exc}")
            return
        except (StorageError, RuntimeError, ValueError) as exc:
            st_ctx.error(f"{t('adm_ai_error', lang)}: {exc}")
            return

    st_ctx.session_state[f"adm_rubric_{stage.stage_id}"] = [
        _criterion_to_row(c) for c in analysis.criteria
    ]
    if analysis.required_sections or analysis.max_pages or analysis.font_and_margins:
        changes: dict[str, Any] = {}
        if analysis.required_sections:
            changes["required_sections_json"] = json.dumps(analysis.required_sections,
                                                           ensure_ascii=False)
        if analysis.max_pages:
            changes["max_pages"] = analysis.max_pages
        if analysis.font_and_margins:
            changes["font_and_margins"] = analysis.font_and_margins
        _guard(st_ctx, lang,
               lambda: repos().competitions.update_stage(stage.stage_id, changes, actor=actor))
    for warning in analysis.warnings:
        st_ctx.warning(f"{t('warn_ai', lang)}: {warning}")
    st_ctx.success(f"{t('succ_rubric_extracted', lang)} ({len(analysis.criteria)})")
    st_ctx.rerun()


def _criterion_to_row(crit: RubricCriterion) -> dict[str, Any]:
    return {
        "criterion_code": crit.criterion_code,
        "criterion_name": crit.criterion_name,
        "description": crit.description or "",
        "max_score": float(crit.max_score),
        "parent_code": crit.parent_code or "",
        "source_quote": crit.source_quote or "",
        "sil": False,
    }


def _render_rubric_editor(st_ctx, actor: str, lang: str,
                          comp: Competition, stage: Stage) -> None:
    repo = repos().competitions
    state_key = f"adm_rubric_{stage.stage_id}"

    if state_key not in st_ctx.session_state:
        existing = _guard(st_ctx, lang, lambda: repo.list_rubric(
            comp.competition_id, stage.stage_code, stage.level), []) or []
        st_ctx.session_state[state_key] = [_criterion_to_row(c) for c in existing]

    rows = st_ctx.session_state[state_key]
    _section(st_ctx, t("sec_rubric", lang))
    if not rows:
        st_ctx.info(t("msg_no_rubric", lang))

    edited = st_ctx.data_editor(
        rows, key=f"{state_key}_editor", num_rows="dynamic", use_container_width=True,
        column_config={
            "criterion_code": st_ctx.column_config.TextColumn(t("col_criterion_code", lang), required=True),
            "criterion_name": st_ctx.column_config.TextColumn(t("col_criterion_name", lang), required=True),
            "description": st_ctx.column_config.TextColumn(t("col_description", lang)),
            "max_score": st_ctx.column_config.NumberColumn(t("col_max_score", lang),
                                                           min_value=0.0, max_value=100.0, step=0.5),
            "parent_code": st_ctx.column_config.TextColumn(t("col_parent", lang)),
            "source_quote": st_ctx.column_config.TextColumn(t("col_source_quote", lang), disabled=True),
            "sil": st_ctx.column_config.CheckboxColumn(t("chk_delete_file_too", lang)),
        },
    )

    # TOPLAM PUAN: silinecekler HARIC, yalnizca UST kriterler.
    # Eski kod silinenleri de sayiyor ve yanlis toplam gosteriyordu.
    records = [r for r in _rows_to_records(edited) if not r.get("sil")]
    total = round(sum(_as_float(r.get("max_score"))
                      for r in records if not str(r.get("parent_code") or "").strip()), 2)
    tone = "t3-badge-aktif" if abs(total - 100.0) < 0.01 else "t3-badge-turuncu"
    st_ctx.markdown(
        t("lbl_rubric_total", lang) + ": " + _badge(f"{total:g} / 100", tone),
        unsafe_allow_html=True,
    )

    col_save, col_approve = st_ctx.columns(2)
    if col_save.button(t("btn_save_rubric", lang), key=f"{state_key}_save",
                       type="primary", use_container_width=True):
        criteria: list[RubricCriterion] = []
        codes = {str(r.get("criterion_code") or "").strip() for r in records}
        for record in records:
            code = str(record.get("criterion_code") or "").strip()
            name = str(record.get("criterion_name") or "").strip()
            if not code or not name:
                st_ctx.error(t("err_criterion_required", lang))
                return
            score = _as_float(record.get("max_score"), -1.0)
            if score < 0:
                st_ctx.error(t("err_criterion_score", lang))
                return
            parent = str(record.get("parent_code") or "").strip() or None
            if parent and parent not in codes:
                st_ctx.warning(f"{t('warn_parent_unknown', lang)}: {parent}")
                parent = None
            criteria.append(RubricCriterion(
                competition_id=comp.competition_id, stage_code=stage.stage_code,
                level=stage.level, branch_code=stage.branch_code,
                criterion_code=code, criterion_name=name,
                description=str(record.get("description") or "").strip() or None,
                max_score=score, parent_code=parent,
                source_quote=str(record.get("source_quote") or "").strip() or None,
            ))
        saved = _guard(st_ctx, lang, lambda: repo.replace_rubric(
            comp.competition_id, stage.stage_code, criteria,
            level=stage.level, branch_code=stage.branch_code, actor=actor))
        if saved is not None:
            st_ctx.session_state[state_key] = [_criterion_to_row(c) for c in criteria]
            st_ctx.success(t("succ_rubric_saved", lang))
            st_ctx.rerun()

    if col_approve.button(t("btn_approve_rubric", lang), key=f"{state_key}_approve",
                          use_container_width=True):
        _guard(st_ctx, lang, lambda: repo.approve_rubric(
            comp.competition_id, stage.stage_code, actor=actor))
        st_ctx.success(t("succ_rubric_approved", lang))
        st_ctx.rerun()


# ── B4 · Basvurular ve raporlar ───────────────────────────────────────────
def _render_applications(st_ctx, actor: str, lang: str, comp: Competition) -> None:
    apps = _guard(st_ctx, lang,
                  lambda: repos().applications.list_for_competition(comp.competition_id), []) or []
    _section(st_ctx, t("sec_applications", lang) + f" ({len(apps)})")
    if not apps:
        st_ctx.info(t("msg_no_application", lang))
        return

    team_repo = repos().teams
    report_repo = repos().reports
    for app in apps:
        team = _guard(st_ctx, lang, lambda: team_repo.get(app.team_id))
        reports = _guard(st_ctx, lang, lambda: report_repo.list_for_application(app.app_id), []) or []
        label = team.name if team else app.team_id[:8]
        exp_label = f"{label} · {len(reports)} " + t("col_reports", lang)
        with st_ctx.expander(exp_label, expanded=False):
            st_ctx.markdown(
                f'<div class="ts-muted">{_e(t("col_team_code", lang))}: '
                f'<code>{_e(team.team_code if team else "-")}</code> · '
                f'{_e(t("col_level", lang))}: {_e(app.level or "-")} · '
                f'{_e(t("col_branch", lang))}: {_e(app.branch_code or "-")}</div>',
                unsafe_allow_html=True,
            )
            new_status = st_ctx.selectbox(
                t("lbl_change_app_status", lang), list(ApplicationStatus),
                index=list(ApplicationStatus).index(app.status),
                format_func=lambda s: s.value, key=f"adm_app_st_{app.app_id}",
            )
            if st_ctx.button(t("btn_apply_status", lang), key=f"adm_app_btn_{app.app_id}"):
                _guard(st_ctx, lang, lambda: repos().applications.set_status(
                    app.app_id, new_status, actor=actor))
                st_ctx.success(t("succ_app_status", lang))
                st_ctx.rerun()

            for report in reports:
                status_label = (report.status.label_tr if lang == "tr"
                                else report.status.label_en)
                status_chip = _badge(status_label, "t3-badge-info")
                st_ctx.markdown(
                    f'<div class="ts-kv"><span>{_e(report.stage_code)} v{report.version} · '
                    f'{_e(report.file_name)}</span>'
                    f'<span>{status_chip}</span></div>',
                    unsafe_allow_html=True,
                )


# ── B5 · Silme ────────────────────────────────────────────────────────────
def _render_delete(st_ctx, actor: str, lang: str, comp: Competition) -> None:
    st_ctx.warning(t("warn_delete", lang))
    confirm = st_ctx.text_input(t("lbl_delete_confirm", lang), key=f"adm_del_cfm_{comp.competition_id}")
    delete_files = st_ctx.checkbox(t("chk_delete_r2", lang), value=True,
                                   key=f"adm_del_r2_{comp.competition_id}")
    if st_ctx.button(t("btn_delete_competition", lang), key=f"adm_del_{comp.competition_id}"):
        if confirm.strip() != comp.slug:
            st_ctx.error(t("err_delete_confirm", lang))
            return
        if delete_files:
            removed = _guard(st_ctx, lang,
                             lambda: repos().storage.delete_prefix(f"yarismalar/{comp.slug}/"), 0)
            if removed:
                st_ctx.info(f"{t('succ_r2_deleted', lang)}: {removed}")
        if _guard(st_ctx, lang,
                  lambda: repos().competitions.delete(comp.competition_id, actor=actor)) is not None:
            st_ctx.success(t("succ_deleted", lang))
            st_ctx.session_state.pop("adm_selected_comp", None)
            st_ctx.rerun()


# ═══════════════════════════════════════════════════════════════════════════
# C · Hakem ve rapor havuzu, yonlendirme
# ═══════════════════════════════════════════════════════════════════════════
def _render_pool(st_ctx, actor: str, lang: str) -> None:
    ev_repo = repos().evaluations
    workload = _guard(st_ctx, lang, ev_repo.referee_workload, []) or []

    # 1. TÜM YARIŞMACI RAPORLARI VE HAKEM YÖNLENDİRME DETAYLI SORGU (Cloudflare D1 Canlı Bağlantı)
    try:
        raw_rows = repos().evaluations.db.query("""
            SELECT 
                r.report_id,
                r.file_name,
                r.stage_code,
                r.version,
                r.status as report_status,
                r.created_at,
                r.competition_id,
                COALESCE(c.name, r.competition_id) as competition_name,
                c.slug as competition_slug,
                a.app_id,
                t.name as team_name,
                ra.assignment_id,
                ra.status as assignment_status,
                ra.assigned_at,
                u.name as referee_name,
                u.surname as referee_surname,
                u.email as referee_email,
                COALESCE(e.total_score, r.referee_score) as total_score,
                COALESCE(e.decision, r.decision) as decision,
                r.referee_score
            FROM reports r
            LEFT JOIN applications a ON a.app_id = r.app_id
            LEFT JOIN teams t ON t.team_id = a.team_id
            LEFT JOIN competitions c ON c.competition_id = r.competition_id OR c.slug = r.competition_id
            LEFT JOIN report_assignments ra ON ra.report_id = r.report_id AND (ra.status IS NULL OR ra.status != 'IPTAL')
            LEFT JOIN auth_users u ON u.user_id = ra.referee_user_id
            LEFT JOIN evaluations e ON e.assignment_id = ra.assignment_id
            ORDER BY c.name ASC, r.stage_code ASC, r.created_at DESC;
        """) or []
    except Exception:
        raw_rows = []

    # URL QUERY PARAMS & SUB-SECTION SELECTION (TAM URL ENTEGRASYONU)
    pool_cur = st_ctx.query_params.get("pool_sec") or st_ctx.session_state.get("yonetici_pool_sec") or "routing"
    if pool_cur not in ("routing", "pool", "active", "evaluated"):
        pool_cur = "routing"

    # YUKARIDAKİ ANA BUTONLARLA BİREBİR AYNI TEMADA 4 ADET SUB-NAVIGATION BUTONU
    p_b1, p_b2, p_b3, p_b4 = st_ctx.columns(4)

    with p_b1:
        b1_type = "primary" if pool_cur == "routing" else "secondary"
        if st_ctx.button("Hakem Yönlendirme & Dağıtım", key="btn_psec_routing", use_container_width=True, type=b1_type):
            st_ctx.session_state.yonetici_pool_sec = "routing"
            st_ctx.query_params["pool_sec"] = "routing"
            st_ctx.rerun()

    with p_b2:
        b2_type = "primary" if pool_cur == "pool" else "secondary"
        if st_ctx.button("Kategori & Aşama Rapor Havuzu", key="btn_psec_pool", use_container_width=True, type=b2_type):
            st_ctx.session_state.yonetici_pool_sec = "pool"
            st_ctx.query_params["pool_sec"] = "pool"
            st_ctx.rerun()

    with p_b3:
        b3_type = "primary" if pool_cur == "active" else "secondary"
        if st_ctx.button("Aktif Atamalar (Havuza Geri Çek)", key="btn_psec_active", use_container_width=True, type=b3_type):
            st_ctx.session_state.yonetici_pool_sec = "active"
            st_ctx.query_params["pool_sec"] = "active"
            st_ctx.rerun()

    with p_b4:
        b4_type = "primary" if pool_cur == "evaluated" else "secondary"
        if st_ctx.button("Değerlendirilen Raporlar & Yeniden Atama", key="btn_psec_evaluated", use_container_width=True, type=b4_type):
            st_ctx.session_state.yonetici_pool_sec = "evaluated"
            st_ctx.query_params["pool_sec"] = "evaluated"
            st_ctx.rerun()

    st_ctx.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

    # ── MODÜL 1: HAKEM HAVUZU VE YENİ ATAMA YAPMA ──
    if pool_cur == "routing":
        _section(st_ctx, t("sec_referee_pool", lang))
        if not workload:
            st_ctx.info(t("msg_no_referee", lang))
        else:
            df_data = []
            for w in workload:
                total = int(w.get("toplam") or 0)
                done = int(w.get("tamamlanan") or 0)
                progress = int((done / total * 100)) if total > 0 else 0
                df_data.append({
                    t("col_referee", lang): f"{w.get('name', '')} {w.get('surname') or ''}".strip(),
                    t("col_email", lang): w.get("email", ""),
                    t("col_specialty", lang): w.get("specialty") or "-",
                    t("col_pending", lang): int(w.get("bekleyen") or 0),
                    t("col_done", lang): done,
                    t("col_total", lang): total,
                    "İlerleme": progress,
                })
            
            import streamlit as st
            st_ctx.dataframe(
                df_data,
                use_container_width=True, 
                hide_index=True,
                column_config={
                    t("col_pending", lang): st.column_config.NumberColumn(t("col_pending", lang), format="%d"),
                    t("col_done", lang): st.column_config.NumberColumn(t("col_done", lang), format="%d"),
                    t("col_total", lang): st.column_config.NumberColumn(t("col_total", lang), format="%d"),
                    "İlerleme": st.column_config.ProgressColumn(
                        "Tamamlama Oranı",
                        help="Hakemin tamamladığı raporların yüzdesi",
                        format="%d%%",
                        min_value=0,
                        max_value=100,
                    )
                }
            )

        _sep(st_ctx)
        _section(st_ctx, t("sec_routing", lang))
        st_ctx.caption("Henüz herhangi bir hakeme yönlendirilmemiş (atama bekleyen) yarışmacı raporlarını seçerek hakemlere yönlendirin.")

        # YALNIZCA KESİN OLARAK ATANMAMIŞ (BEKLEYEN) RAPORLARI FİLTRELE
        target_rows = [
            r for r in raw_rows
            if not r.get("assignment_id") and not r.get("referee_email") and r.get("report_status") not in ("HAKEME_ATANDI", "DEGERLENDIRILDI")
        ]

        labels = {
            f"{r.get('file_name')} — {r.get('stage_code')} v{r.get('version', 1)} ({r.get('competition_name', '')})": r.get("report_id")
            for r in target_rows if r.get("report_id")
        }

        referee_map = {
            f"{w.get('name', '')} {w.get('surname') or ''} ({w.get('email', '')})".strip(): w["user_id"]
            for w in workload
        }

        if not labels:
            st_ctx.success("Tebrikler! Atama bekleyen yeni yarışmacı raporu bulunmamaktadır. Tüm raporlar hakemlere yönlendirilmiştir.")
        elif referee_map:
            selected_reports = st_ctx.multiselect(t("lbl_select_reports", lang), list(labels), key="adm_route_reports")
            selected_referees = st_ctx.multiselect(t("lbl_select_referees", lang), list(referee_map), key="adm_route_referees")

            col_assign, col_auto = st_ctx.columns(2)
            if col_assign.button(t("btn_assign", lang), type="primary", use_container_width=True, key="adm_assign"):
                if not selected_reports:
                    st_ctx.error(t("err_select_report", lang))
                elif not selected_referees:
                    st_ctx.error(t("err_select_referee", lang))
                else:
                    done = 0
                    for report_label in selected_reports:
                        for referee_label in selected_referees:
                            result = _guard(st_ctx, lang, lambda rl=report_label, fl=referee_label:
                                            ev_repo.assign(labels[rl], referee_map[fl], assigned_by=actor))
                            if result is not None:
                                done += 1
                    if done:
                        st_ctx.success(f"{t('succ_assigned', lang)}: {done}")
                        st_ctx.rerun()

            if col_auto.button(t("btn_auto_distribute", lang), use_container_width=True, key="adm_auto"):
                target = [labels[r] for r in selected_reports] or list(labels.values())
                result = _guard(st_ctx, lang, lambda: ev_repo.auto_distribute(target, assigned_by=actor))
                if result:
                    st_ctx.success(f"{t('succ_assigned', lang)}: {len(result)}")
                    st_ctx.rerun()

    # ── MODÜL 2: KATEGORİ VE AŞAMA BAZLI KAPSAMLI RAPOR HAVUZU ──
    elif pool_cur == "pool":
        _section(st_ctx, t("sec_report_pool", lang))
        st_ctx.caption("Sisteme yüklenen tüm yarışmacı raporlarını kategorilere ve aşamalara göre inceleyin, hakem yönlendirmelerini ve puanlama durumlarını anlık takip edin.")

        tot_reports = len(raw_rows)
        tot_assigned = sum(1 for r in raw_rows if r.get("referee_email") or r.get("assignment_id") or r.get("report_status") in ("HAKEME_ATANDI", "DEGERLENDIRILIYOR", "DEGERLENDIRILDI"))
        tot_unassigned = tot_reports - tot_assigned
        tot_completed = sum(1 for r in raw_rows if r.get("report_status") == "DEGERLENDIRILDI" or r.get("total_score") is not None or r.get("referee_score") is not None or r.get("assignment_status") == "TAMAMLANDI")

        m1, m2, m3, m4 = st_ctx.columns(4)
        m1.markdown(f'''
        <div style="background: rgba(2, 28, 97, 0.75); border: 1px solid rgba(61, 211, 255, 0.35); border-radius: 10px; padding: 14px; text-align: center;">
            <div style="font-size: 0.82rem; color: #CBD5E1; font-weight: 700; text-transform: uppercase;">Toplam Yüklenen Rapor</div>
            <div style="font-size: 1.8rem; font-weight: 900; color: #FFFFFF; margin-top: 4px;">{tot_reports}</div>
        </div>
        ''', unsafe_allow_html=True)

        m2.markdown(f'''
        <div style="background: rgba(2, 28, 97, 0.75); border: 1px solid rgba(61, 211, 255, 0.35); border-radius: 10px; padding: 14px; text-align: center;">
            <div style="font-size: 0.82rem; color: #3DD3FF; font-weight: 700; text-transform: uppercase;">Hakeme Yönlendirilen</div>
            <div style="font-size: 1.8rem; font-weight: 900; color: #3DD3FF; margin-top: 4px;">{tot_assigned}</div>
        </div>
        ''', unsafe_allow_html=True)

        m3.markdown(f'''
        <div style="background: rgba(2, 28, 97, 0.75); border: 1px solid rgba(255, 180, 0, 0.45); border-radius: 10px; padding: 14px; text-align: center;">
            <div style="font-size: 0.82rem; color: #FFB400; font-weight: 700; text-transform: uppercase;">Atama Bekleyen</div>
            <div style="font-size: 1.8rem; font-weight: 900; color: #FFB400; margin-top: 4px;">{tot_unassigned}</div>
        </div>
        ''', unsafe_allow_html=True)

        m4.markdown(f'''
        <div style="background: rgba(2, 28, 97, 0.75); border: 1px solid rgba(0, 230, 120, 0.45); border-radius: 10px; padding: 14px; text-align: center;">
            <div style="font-size: 0.82rem; color: #00E678; font-weight: 700; text-transform: uppercase;">Tamamlanan Değerlendirme</div>
            <div style="font-size: 1.8rem; font-weight: 900; color: #00E678; margin-top: 4px;">{tot_completed}</div>
        </div>
        ''', unsafe_allow_html=True)

        st_ctx.markdown("<div style='height: 16px;'></div>", unsafe_allow_html=True)

        f_c1, f_c2, f_c3 = st_ctx.columns([1.5, 1.2, 1.5])
        all_cat_names = sorted(list({r.get("competition_name") or "Diğer / Tanımsız" for r in raw_rows})) if raw_rows else []
        sel_cat = f_c1.selectbox("Kategori Filtresi", ["Tüm Kategoriler"] + all_cat_names, key="adm_rep_cat_filter")

        all_stages = sorted(list({str(r.get("stage_code") or "GENEL").upper() for r in raw_rows})) if raw_rows else []
        sel_stage = f_c2.selectbox("Aşama Filtresi", ["Tüm Aşamalar"] + all_stages, key="adm_rep_stage_filter")

        sel_status_filter = f_c3.selectbox(
            "Atama & Hakem Durumu",
            ["Tüm Raporlar", "Yalnızca Hakeme Yönlendirilenler", "Yalnızca Atama Bekleyenler", "Tamamlanmış Değerlendirmeler"],
            key="adm_rep_status_filter"
        )

        filtered_rows = raw_rows
        if sel_cat != "Tüm Kategoriler":
            filtered_rows = [r for r in filtered_rows if (r.get("competition_name") or "Diğer / Tanımsız") == sel_cat]

        if sel_stage != "Tüm Aşamalar":
            filtered_rows = [r for r in filtered_rows if str(r.get("stage_code") or "").upper() == sel_stage]

        if sel_status_filter == "Yalnızca Hakeme Yönlendirilenler":
            filtered_rows = [r for r in filtered_rows if r.get("referee_email") or r.get("assignment_id")]
        elif sel_status_filter == "Yalnızca Atama Bekleyenler":
            filtered_rows = [r for r in filtered_rows if not r.get("referee_email") and not r.get("assignment_id")]
        elif sel_status_filter == "Tamamlanmış Değerlendirmeler":
            filtered_rows = [r for r in filtered_rows if r.get("report_status") == "DEGERLENDIRILDI" or r.get("total_score") is not None or r.get("referee_score") is not None]

        st_ctx.caption(f"Filtrelenen Rapor Sayısı: {len(filtered_rows)}")

        if not filtered_rows:
            st_ctx.info("Seçilen kriterlere uygun yarışmacı raporu bulunamadı.")
        else:
            cat_groups: dict[str, dict[str, list[dict]]] = {}
            for r in filtered_rows:
                cname = r.get("competition_name") or "Diğer / Genel Yarışmalar"
                scode = str(r.get("stage_code") or "GENEL").upper()
                if cname not in cat_groups:
                    cat_groups[cname] = {}
                if scode not in cat_groups[cname]:
                    cat_groups[cname][scode] = []
                cat_groups[cname][scode].append(r)

            for cat_name, stages_dict in cat_groups.items():
                cat_rep_count = sum(len(items) for items in stages_dict.values())
                with st_ctx.expander(f"KATEGORİ: {cat_name.upper()} ({cat_rep_count} Rapor)", expanded=True):
                    for stage_name, reports_list in stages_dict.items():
                        st_ctx.markdown(f"""
                        <div style="font-size: 1.05rem; font-weight: 850; color: #3DD3FF; border-bottom: 1.5px solid rgba(61, 211, 255, 0.35); padding-bottom: 4px; margin-top: 12px; margin-bottom: 10px;">
                            AŞAMA: {stage_name} ({len(reports_list)} Rapor)
                        </div>
                        """, unsafe_allow_html=True)

                        table_rows = []
                        for rp in reports_list:
                            team = rp.get("team_name") or rp.get("app_id") or "Bireysel / Takımsız"
                            fname = rp.get("file_name") or "dokuman.pdf"
                            ver = f"v{rp.get('version', 1)}"
                            cdate = (rp.get("created_at") or "")[:10]
                            
                            ref_name = f"{rp.get('referee_name', '')} {rp.get('referee_surname') or ''}".strip()
                            ref_email = rp.get("referee_email") or ""
                            
                            if ref_email:
                                ref_info = f"{ref_name} ({ref_email})"
                            else:
                                ref_info = "ATANMADI (Bekliyor)"

                            score = rp.get("total_score") if rp.get("total_score") is not None else rp.get("referee_score")
                            decision = rp.get("decision")
                            rep_st = rp.get("report_status")

                            if rep_st == "DEGERLENDIRILDI" or score is not None:
                                sc_str = f"Puan: {score:.1f}" if score is not None else ""
                                dec_str = f" - {decision}" if decision else ""
                                status_badge = f"TAMAMLANDI ({sc_str}{dec_str})".replace("()", "")
                            elif ref_email or rp.get("assignment_id"):
                                status_badge = "HAKEME YÖNLENDİRİLDİ"
                            else:
                                status_badge = "ATAMA BEKLİYOR"

                            table_rows.append({
                                "Takım / Yarışmacı": team,
                                "Rapor Dosyası": f"{fname} ({ver})",
                                "Yükleme Tarihi": cdate,
                                "Yönlendirilen Hakem": ref_info,
                                "Değerlendirme Durumu": status_badge,
                            })

                        import streamlit as st
                        st_ctx.dataframe(
                            table_rows,
                            use_container_width=True,
                            hide_index=True,
                            column_config={
                                "Takım / Yarışmacı": st.column_config.TextColumn("Takım / Yarışmacı"),
                                "Rapor Dosyası": st.column_config.TextColumn("Rapor Dosyası"),
                                "Yönlendirilen Hakem": st.column_config.TextColumn("Yönlendirilen Hakem"),
                                "Değerlendirme Durumu": st.column_config.TextColumn("Değerlendirme Durumu"),
                            }
                        )

    # ── MODÜL 3: AKTİF HAKEM ATAMALARI VE HAVUZA GERİ YÖNLENDİRME ──
    elif pool_cur == "active":
        _section(st_ctx, "Aktif Hakem Atamaları ve Havuza Geri Yönlendirme")
        st_ctx.caption("Hakemlere atanan raporları tarih, kategori ve hakem detaylarıyla görüntüleyin; dilediğiniz atamayı tek tıkla iptal edip havuza geri yönlendirin.")

        active_assignments = [r for r in raw_rows if r.get("assignment_id") and r.get("referee_email")]

        if not active_assignments:
            st_ctx.info("Henüz hakemlere atanmış aktif bir yarışmacı raporu bulunmamaktadır.")
        else:
            # Gelişmiş Filtreleme Çubuğu (Yarışma, Aşama ve Hakem Filtresi)
            af_col1, af_col2, af_col3 = st_ctx.columns([1.5, 1.2, 1.5])
            
            act_cat_names = sorted(list({r.get("competition_name") or "Diğer / Tanımsız" for r in active_assignments}))
            act_stage_codes = sorted(list({str(r.get("stage_code") or "GENEL").upper() for r in active_assignments}))
            act_ref_emails = sorted(list({f"{r.get('referee_name', '')} {r.get('referee_surname') or ''} ({r.get('referee_email', '')})".strip() for r in active_assignments if r.get("referee_email")}))

            sel_act_cat = af_col1.selectbox("Yarışma / Kategori Filtresi", ["Tüm Yarışmalar"] + act_cat_names, key="flt_act_cat")
            sel_act_stage = af_col2.selectbox("Aşama Filtresi", ["Tüm Aşamalar"] + act_stage_codes, key="flt_act_stage")
            sel_act_ref = af_col3.selectbox("Hakem Filtresi", ["Tüm Hakemler"] + act_ref_emails, key="flt_act_ref")

            filtered_active = active_assignments
            if sel_act_cat != "Tüm Yarışmalar":
                filtered_active = [r for r in filtered_active if (r.get("competition_name") or "Diğer / Tanımsız") == sel_act_cat]
            if sel_act_stage != "Tüm Aşamalar":
                filtered_active = [r for r in filtered_active if str(r.get("stage_code") or "").upper() == sel_act_stage]
            if sel_act_ref != "Tüm Hakemler":
                filtered_active = [r for r in filtered_active if f"{r.get('referee_name', '')} {r.get('referee_surname') or ''} ({r.get('referee_email', '')})".strip() == sel_act_ref]

            st_ctx.caption(f"Filtrelenen Aktif Atama Sayısı: {len(filtered_active)}")

            if not filtered_active:
                st_ctx.info("Seçilen kriterlere uygun aktif hakem ataması bulunamadı.")
            else:
                for asg in filtered_active:
                    asg_id = asg.get("assignment_id")
                    c_name = asg.get("competition_name") or "Yarışma Kategorisi"
                    s_code = asg.get("stage_code") or "ÖTR"
                    f_name = asg.get("file_name") or "dokuman.pdf"
                    t_name = asg.get("team_name") or "Takım"
                    ref_title = f"{asg.get('referee_name', '')} {asg.get('referee_surname', '')}".strip()
                    ref_mail = asg.get("referee_email") or ""
                    a_date = (asg.get("assigned_at") or asg.get("created_at") or "")[:16].replace("T", " ")

                    with st_ctx.container(border=True):
                        a_col1, a_col2 = st_ctx.columns([3.2, 1.2])
                        with a_col1:
                            st_ctx.markdown(f"**Kategori:** `{c_name}` &nbsp;|&nbsp; **Aşama:** `{s_code}` &nbsp;|&nbsp; **Takım:** `{t_name}`")
                            st_ctx.markdown(f"**Rapor:** {f_name} v{asg.get('version', 1)} &nbsp;|&nbsp; **Atanan Hakem:** <span style='color:#3DD3FF; font-weight:700;'>{ref_title} ({ref_mail})</span>", unsafe_allow_html=True)
                            st_ctx.caption(f"Atama Tarihi: {a_date} · Atama Durumu: {asg.get('assignment_status') or 'ATANDI'}")
                        with a_col2:
                            if st_ctx.button("Atamayı İptal Et & Havuza Gönder", key=f"btn_unassign_active_{asg_id}", type="secondary", use_container_width=True):
                                try:
                                    ev_repo.unassign(asg_id, actor=actor)
                                    st_ctx.success(f"Atama iptal edildi ve {f_name} raporu havuza geri gönderildi.")
                                    st_ctx.rerun()
                                except Exception as ex:
                                    st_ctx.error(f"Atama iptal edilirken hata oluştu: {ex}")

    # ── MODÜL 4: DEĞERLENDİRİLMİŞ RAPORLAR VE YENİDEN HAKEME ATAMA ──
    elif pool_cur == "evaluated":
        _section(st_ctx, "Değerlendirilmiş Raporlar ve Yeniden Hakeme Atama")
        st_ctx.caption("Hakemler tarafından puanlanmış ve değerlendirmesi tamamlanmış raporları inceleyin, gerekli durumlarda farklı bir hakeme yeniden atayarak revize değerlendirme sürecini başlatın.")

        completed_reports = [
            r for r in raw_rows
            if r.get("report_status") == "DEGERLENDIRILDI" or r.get("total_score") is not None or r.get("referee_score") is not None
        ]

        if not completed_reports:
            st_ctx.info("Henüz değerlendirilmesi tamamlanmış bir yarışmacı raporu bulunmamaktadır.")
        else:
            # Gelişmiş Filtreleme Çubuğu (Yarışma, Aşama ve Hakem Filtresi)
            cf_col1, cf_col2, cf_col3 = st_ctx.columns([1.5, 1.2, 1.5])
            
            comp_cat_names = sorted(list({r.get("competition_name") or "Diğer / Tanımsız" for r in completed_reports}))
            comp_stage_codes = sorted(list({str(r.get("stage_code") or "GENEL").upper() for r in completed_reports}))
            comp_ref_emails = sorted(list({f"{r.get('referee_name', '')} {r.get('referee_surname') or ''} ({r.get('referee_email', '')})".strip() for r in completed_reports if r.get("referee_email")}))

            sel_comp_cat = cf_col1.selectbox("Yarışma / Kategori Filtresi", ["Tüm Yarışmalar"] + comp_cat_names, key="flt_comp_cat")
            sel_comp_stage = cf_col2.selectbox("Aşama Filtresi", ["Tüm Aşamalar"] + comp_stage_codes, key="flt_comp_stage")
            sel_comp_ref = cf_col3.selectbox("Hakem Filtresi", ["Tüm Hakemler"] + comp_ref_emails, key="flt_comp_ref")

            filtered_completed = completed_reports
            if sel_comp_cat != "Tüm Yarışmalar":
                filtered_completed = [r for r in filtered_completed if (r.get("competition_name") or "Diğer / Tanımsız") == sel_comp_cat]
            if sel_comp_stage != "Tüm Aşamalar":
                filtered_completed = [r for r in filtered_completed if str(r.get("stage_code") or "").upper() == sel_comp_stage]
            if sel_comp_ref != "Tüm Hakemler":
                filtered_completed = [r for r in filtered_completed if f"{r.get('referee_name', '')} {r.get('referee_surname') or ''} ({r.get('referee_email', '')})".strip() == sel_comp_ref]

            st_ctx.caption(f"Filtrelenen Değerlendirilmiş Rapor Sayısı: {len(filtered_completed)}")

            if not filtered_completed:
                st_ctx.info("Seçilen kriterlere uygun değerlendirilmiş rapor bulunamadı.")
            else:
                for comp_rp in filtered_completed:
                    c_rep_id = comp_rp.get("report_id")
                    c_comp_name = comp_rp.get("competition_name") or "Yarışma Kategorisi"
                    c_stage_code = comp_rp.get("stage_code") or "ÖTR"
                    c_file_name = comp_rp.get("file_name") or "dokuman.pdf"
                    c_team_name = comp_rp.get("team_name") or "Takım"
                    c_ref_name = f"{comp_rp.get('referee_name', '')} {comp_rp.get('referee_surname', '')}".strip()
                    c_ref_mail = comp_rp.get("referee_email") or ""
                    c_score = comp_rp.get("total_score") if comp_rp.get("total_score") is not None else comp_rp.get("referee_score")
                    c_decision = comp_rp.get("decision") or "Değerlendirildi"

                    with st_ctx.container(border=True):
                        rc_col1, rc_col2 = st_ctx.columns([2.5, 1.8])
                        with rc_col1:
                            st_ctx.markdown(f"**Kategori:** `{c_comp_name}` &nbsp;|&nbsp; **Aşama:** `{c_stage_code}` &nbsp;|&nbsp; **Takım:** `{c_team_name}`")
                            st_ctx.markdown(f"**Rapor:** {c_file_name} v{comp_rp.get('version', 1)}")
                            score_txt = f"{c_score:.1f} Puan" if c_score is not None else "Puanlandı"
                            st_ctx.markdown(f"**Mevcut Değerlendirme:** <span style='color:#00E678; font-weight:800;'>{score_txt} - {c_decision}</span> (Hakem: {c_ref_name} - {c_ref_mail})", unsafe_allow_html=True)
                        
                        with rc_col2:
                            referee_map = {
                                f"{w.get('name', '')} {w.get('surname') or ''} ({w.get('email', '')})".strip(): w["user_id"]
                                for w in workload
                            }
                            if referee_map:
                                target_ref = st_ctx.selectbox(
                                    "Yeniden Atanacak Hakem",
                                    list(referee_map.keys()),
                                    key=f"sel_reassign_ref_{c_rep_id}"
                                )
                                if st_ctx.button("Yeniden Hakeme Ata", key=f"btn_reassign_{c_rep_id}", type="primary", use_container_width=True):
                                    try:
                                        new_ref_id = referee_map[target_ref]
                                        repos().reports.set_status(c_rep_id, ReportStatus.HAKEME_ATANDI, actor=actor)
                                        ev_repo.assign(c_rep_id, new_ref_id, assigned_by=actor)
                                        st_ctx.success(f"{c_file_name} raporu {target_ref} hakemine yeniden atandı ve değerlendirme sürecine alındı.")
                                        st_ctx.rerun()
                                    except Exception as ex:
                                        st_ctx.error(f"Yeniden atama yapılırken hata oluştu: {ex}")




# ═══════════════════════════════════════════════════════════════════════════
# D · Kalibrasyon
# ═══════════════════════════════════════════════════════════════════════════
# DUYURU YÖNETİMİ (ANNOUNCEMENTS CRUD)
# ═══════════════════════════════════════════════════════════════════════════
def _render_announcements(st_ctx, actor: str, lang: str) -> None:
    from src.database.db import db
    _section(st_ctx, "Resmî Duyuru & Bildirim Yönetimi")
    st_ctx.caption("Ana ekranda ve vitrinde yayınlanacak şartname güncellemeleri, yarışma bildirimleri ve genel duyuruları oluşturun ve yönetin.")

    # 1. Yeni Duyuru Oluşturma Kartı
    with st_ctx.expander("Yeni Resmî Duyuru Yayınla", expanded=False):
        with st_ctx.form("form_create_announcement"):
            a_title = st_ctx.text_input("Duyuru Başlığı", placeholder="Örn: 2026 Teknik Şartnameleri ve Aşama Şablonları Yayınlandı")
            c_cat, c_pin, c_auth = st_ctx.columns([1.5, 1, 1.5])
            with c_cat:
                a_cat = st_ctx.selectbox("Duyuru Kategorisi", ["GENEL", "ŞARTNAME", "HAKEM", "YARIŞMA", "SONUÇLAR", "ÖNEMLİ"])
            with c_pin:
                a_pin = st_ctx.checkbox("Başa Tuttur (Öne Çıkar)", value=False)
            with c_auth:
                a_auth = st_ctx.text_input("Yayınlayan / Birim", value="Yarışma Yönetimi")
            
            # Resim Yükleme (Sürükle & Bırak veya Mevcut Görsel)
            uploaded_ann_file = st_ctx.file_uploader(
                "Kapak Resmi Yükle (Sürükle & Bırak — PNG, JPG, JPEG, WEBP)",
                type=["png", "jpg", "jpeg", "webp"],
                key="ann_upload_new_img"
            )
            a_content = st_ctx.text_area("Duyuru Metni / Açıklama", height=120, placeholder="Duyuru içeriği, detaylar ve yarışmacılara iletilecek bildirim metni...")

            if st_ctx.form_submit_button("Duyuruyu Yayınla", type="primary", use_container_width=True):
                if a_title.strip() and a_content.strip():
                    try:
                        final_img_url = ""
                        if uploaded_ann_file is not None:
                            file_bytes = uploaded_ann_file.read()
                            # 1. Cloudflare R2'ye yüklemeyi dene
                            try:
                                from src.data.r2 import R2Client, slugify
                                r2 = R2Client()
                                if r2.is_configured:
                                    ext = Path(uploaded_ann_file.name).suffix.lower() or ".jpg"
                                    r2_key = f"announcements/{slugify(a_title[:30])}_{int(time.time())}{ext}"
                                    r2_obj = r2.upload(file_bytes, r2_key, content_type=uploaded_ann_file.type or "image/jpeg")
                                    final_img_url = r2_obj.url
                            except Exception as r2_err:
                                print(f"[R2 Announcement Upload Warning] {r2_err}")
                            
                            # 2. Eğer R2 yoksa veya hata verdiyse base64 data URI olarak kaydet
                            if not final_img_url:
                                import base64
                                b64 = base64.b64encode(file_bytes).decode()
                                mime = uploaded_ann_file.type or "image/jpeg"
                                final_img_url = f"data:{mime};base64,{b64}"

                        db.create_announcement(
                            title=a_title.strip(),
                            content=a_content.strip(),
                            category=a_cat,
                            author_name=a_auth.strip() or "Yarışma Yönetimi",
                            image_url=final_img_url,
                            is_pinned=a_pin
                        )
                        st_ctx.success("Duyuru başarıyla oluşturuldu ve ana ekranda yayına alındı!")
                        st_ctx.rerun()
                    except Exception as e:
                        st_ctx.error(f"Duyuru kaydedilirken hata oluştu: {e}")
                else:
                    st_ctx.warning("Lütfen başlık ve duyuru içeriğini eksiksiz doldurunuz.")

    # 2. Yayındaki Duyuruların Listesi ve Düzenleme / Silme
    st_ctx.markdown("<hr style='margin:16px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
    st_ctx.markdown("##### Yayındaki Duyurular")

    ann_list = db.list_announcements()
    if not ann_list:
        st_ctx.info("Henüz sistemde yayınlanmış bir duyuru bulunmuyor.")
        return

    for ann in ann_list:
        a_id = ann.get("announcement_id", "")
        title = ann.get("title", "")
        content = ann.get("content", "")
        cat = ann.get("category", "GENEL")
        author = ann.get("author_name", "Yarışma Yönetimi")
        img_url = ann.get("image_url", "")
        is_pin = bool(ann.get("is_pinned", 0))
        created = str(ann.get("created_at", ""))[:16]

        pin_badge = "<b style='color:#DC2626;'>SABİTLENDİ</b> · " if is_pin else ""
        
        with st_ctx.container(border=True):
            col_info, col_act = st_ctx.columns([3.5, 1])
            with col_info:
                st_ctx.markdown(f"#### {title}")
                st_ctx.markdown(f"<div style='font-size:0.80rem; color:#64748B; margin-top:-6px; margin-bottom:8px;'>{pin_badge}Kategori: <b>{cat}</b> &nbsp;|&nbsp; Yayınlayan: <b>{author}</b> &nbsp;|&nbsp; Tarih: {created}</div>", unsafe_allow_html=True)
                if img_url:
                    st_ctx.markdown(f"<div style='margin-bottom:8px;'><img src='{img_url}' style='height:80px; max-width:160px; object-fit:cover; border-radius:6px;'/></div>", unsafe_allow_html=True)
                st_ctx.markdown(f"<div style='font-size:0.92rem; color:#1E293B; line-height:1.55;'>{content}</div>", unsafe_allow_html=True)
            
            with col_act:
                with st_ctx.expander("Düzenle"):
                    with st_ctx.form(f"form_edit_ann_{a_id}"):
                        e_title = st_ctx.text_input("Başlık", value=title)
                        e_content = st_ctx.text_area("İçerik", value=content, height=90)
                        e_cat = st_ctx.selectbox("Kategori", ["GENEL", "ŞARTNAME", "HAKEM", "YARIŞMA", "SONUÇLAR", "ÖNEMLİ"], index=["GENEL", "ŞARTNAME", "HAKEM", "YARIŞMA", "SONUÇLAR", "ÖNEMLİ"].index(cat) if cat in ["GENEL", "ŞARTNAME", "HAKEM", "YARIŞMA", "SONUÇLAR", "ÖNEMLİ"] else 0)
                        e_uploaded_file = st_ctx.file_uploader("Kapak Resmini Değiştir (Sürükle & Bırak)", type=["png", "jpg", "jpeg", "webp"], key=f"edit_file_{a_id}")
                        e_pin = st_ctx.checkbox("Sabitlendi", value=is_pin, key=f"pin_edit_{a_id}")
                        
                        if st_ctx.form_submit_button("Güncelle", type="primary", use_container_width=True):
                            new_img_url = img_url
                            if e_uploaded_file is not None:
                                file_bytes = e_uploaded_file.read()
                                try:
                                    from src.data.r2 import R2Client, slugify
                                    r2 = R2Client()
                                    if r2.is_configured:
                                        ext = Path(e_uploaded_file.name).suffix.lower() or ".jpg"
                                        r2_key = f"announcements/{slugify(e_title[:30])}_{int(time.time())}{ext}"
                                        r2_obj = r2.upload(file_bytes, r2_key, content_type=e_uploaded_file.type or "image/jpeg")
                                        new_img_url = r2_obj.url
                                except Exception as r2_err:
                                    print(f"[R2 Announcement Edit Warning] {r2_err}")
                                
                                if new_img_url == img_url:
                                    import base64
                                    b64 = base64.b64encode(file_bytes).decode()
                                    mime = e_uploaded_file.type or "image/jpeg"
                                    new_img_url = f"data:{mime};base64,{b64}"

                            db.update_announcement(a_id, e_title, e_content, e_cat, new_img_url, e_pin)
                            st_ctx.success("Güncellendi!")
                            st_ctx.rerun()
                
                if st_ctx.button("Sil", key=f"btn_del_ann_{a_id}", use_container_width=True):
                    db.delete_announcement(a_id)
                    st_ctx.success("Duyuru silindi.")
                    st_ctx.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# D · Kalibrasyon (Yarışma Bazlı Özelleştirilebilir Kalibrasyon Paneli)
# ═══════════════════════════════════════════════════════════════════════════
def _render_calibration(st_ctx, actor: str, lang: str) -> None:
    client = repos().client
    _section(st_ctx, t("sec_calibration", lang))
    st_ctx.caption("Yarışma genelinde veya seçilen yarışma kategorisi bazında baraj puanlarını, kabul/red eşiklerini ve Yapay Zeka (AI) kalibrasyon katsayılarını özelleştirin.")

    # 1. YARIŞMALAR LİSTESİ (Cloudflare D1 / SQLite Canlı Çekim)
    try:
        comps = client.query("SELECT competition_id, name, slug FROM competitions WHERE name IS NOT NULL ORDER BY name;") or []
    except Exception:
        comps = []

    comp_options = ["Genel Sistem Varsayılanı (Tüm Yarışmalar İçin Fallback)"] + [
        f"{c.get('name')} [{c.get('slug')}]" for c in comps if c.get("name")
    ]

    selected_scope = st_ctx.selectbox(
        "Kalibrasyon Kapsamı ve Yarışma Seçimi",
        comp_options,
        key="adm_cal_scope_select"
    )

    is_global = "Genel Sistem Varsayılanı" in selected_scope
    selected_comp_slug = ""
    selected_comp_name = "Genel Sistem Varsayılanı"

    if not is_global:
        for c in comps:
            if f"{c.get('name')} [{c.get('slug')}]" == selected_scope:
                selected_comp_slug = c.get("slug") or ""
                selected_comp_name = c.get("name") or ""
                break

    desc_text = "Genel sistem kabul/red barajları ve varsayılan AI katsayıları düzenlenmektedir." if is_global else f"Yalnızca <b>{selected_comp_name}</b> yarışması için özel kabul/red baraj puanları ve AI katsayıları düzenlenmektedir."
    st_ctx.markdown(f"""
    <div style="background: #FFF5F5; border-left: 5px solid #FF1A00; border: 1px solid #FED7D7; border-radius: 8px; padding: 14px 18px; margin-bottom: 18px;">
        <span style="font-weight: 850; color: #C53030; font-size: 1.02rem;">Aktif Kalibrasyon Modu:</span> 
        <span style="color: #1A202C; font-weight: 800; font-size: 1.02rem;">{selected_comp_name}</span>
        <div style="font-size: 0.88rem; color: #4A5568; margin-top: 4px; font-weight: 500;">
            {desc_text}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. MEVCUT KALİBRASYON AYARLARINI OKU (Cloudflare D1 Canlı Çekim)
    base_rows = _guard(st_ctx, lang, lambda: client.query(
        "SELECT key, value, description FROM calibration_settings ORDER BY key;"), []) or []

    if not base_rows:
        st_ctx.info(t("msg_no_calibration", lang))
        if st_ctx.button(t("btn_seed_calibration", lang), key="adm_cal_seed", type="primary"):
            from src.data.migrate import seed_calibration
            _guard(st_ctx, lang, lambda: seed_calibration("sqlite" if not client.is_cloud else "d1"))
            st_ctx.success(t("succ_calibration_seeded", lang))
            st_ctx.rerun()
        return

    base_dict = {row["key"]: float(row["value"]) for row in base_rows}

    # 11 ADET KAPSAMLI KALİBRASYON PARAMETRESİ (3 KATEGORİYE AYRILMIŞ DETAYLI REHBERLİ)
    param_groups = [
        {
            "title": "1. Rapor Geçme, Elenme ve Revizyon Eşikleri",
            "desc": "Yarışmacı raporlarının kurul değerlendirmesinde KABUL (Geçti), REVİZYON (Düzeltme İste) veya RED (Elendi) kararı alması için gereken baraj puanları.",
            "params": [
                ("accept_threshold", "KABUL Kararı Alt Sınırı (Baraj Puanı)", base_dict.get("accept_threshold", 75.0),
                 "Raporun doğrudan ONAYLANIP bir sonraki aşamaya geçmesi için alması gereken minimum puandır. Örn: 75.00 girilirse 75 ve üzeri puan alan raporlar geçer."),
                ("revision_threshold", "REVİZYON Kararı Alt Sınırı (Düzeltme Eşiği)", base_dict.get("revision_threshold", 60.0),
                 "Raporun doğrudan elenmeyip yarışmacıya düzeltme / revizyon hakkı verileceği alt puandır. Örn: 60-74 puan arası alan raporlar revizyona yönlendirilir."),
                ("reject_threshold", "RED Kararı Üst Sınırı (Elenme Eşiği)", base_dict.get("reject_threshold", 50.0),
                 "Raporun kesin olarak ELENDİ kararı alması için belirlenen puan sınırıdır. Örn: 50.00 altı alan raporlar doğrudan elenir."),
                ("feedback_min_score_for_positive", "Olumlu Karne Geri Bildirimi Alt Sınırı", base_dict.get("feedback_min_score_for_positive", 70.0),
                 "Otomatik karne üreticide olumlu nesirler ve takdir ifadeleri oluşturulması için gereken minimum raporsal puan barajıdır."),
            ]
        },
        {
            "title": "2. Yapay Zeka (AI) ve Hakem Uyum Katsayıları",
            "desc": "Yapay Zeka ön değerlendirme puanlarının insan hakemlerinin puanlama çizgisine kalibre edilmesi ve sapma alarmlarının yönetimi.",
            "params": [
                ("ai_score_offset", "Yapay Zeka (AI) Puan Kaydırma (Offset)", base_dict.get("ai_score_offset", 0.0),
                 "Yapay zeka puanlarına uygulanan artı/eksi sabit değerdir. Örn: +5.00 girilirse AI'ın verdiği 70 puan otomatik 75 olarak güncellenir."),
                ("ai_score_slope", "Yapay Zeka (AI) Puan Çarpanı (Slope / Skala)", base_dict.get("ai_score_slope", 1.0),
                 "Yapay zeka puanlarının hassasiyet ve yayılım katsayısıdır. Örn: 1.15 girilirse AI puanları arasındaki makas açılarak iyi ve orta raporlar ayrıştırılır."),
                ("referee_ai_warning_delta", "Hakem - AI Puan Farkı Uyarı Eşiği", base_dict.get("referee_ai_warning_delta", 15.0),
                 "İnsan hakemi ile Yapay Zeka puanı arasındaki kabul edilebilir maksimum sapmadır. Örn: 15.0 puan üzeri fark oluşursa yöneticiye bayrak kaldırılır."),
            ]
        },
        {
            "title": "3. İntihal ve Benzerlik Analizi Güvenlik Eşikleri",
            "desc": "Raporlar arasındaki birebir metin kopyalama ve anlamsal (AI Vectorize) intihal tespitinde diskalifiye ve uyarı barajları.",
            "params": [
                ("similarity_high_threshold", "Yüksek İntihal Riski Eşiği (Birleşik Oran)", base_dict.get("similarity_high_threshold", 0.70),
                 "Raporun yüksek risk kategorisine alınıp diskalifiye incelemesine sevk edilmesi için gereken birleşik intihal oranı (0.70 = %70 benzerlik)."),
                ("similarity_medium_threshold", "Orta İntihal Riski Eşiği", base_dict.get("similarity_medium_threshold", 0.40),
                 "Hakem ekranında sarı uyarı bayrağı çıkarılması için gereken orta seviye benzerlik oranı (0.40 = %40 benzerlik)."),
                ("semantic_high_threshold", "Anlamsal (AI Vectorize) Benzerlik Risk Eşiği", base_dict.get("semantic_high_threshold", 0.82),
                 "Kelime kelime değiştirilse dahi konunun/fikrin başka bir rapordan kopyalandığını gösteren AI vektör benzerlik sınırı (0.82 = %82)."),
                ("literal_high_threshold", "Birebir Metin Kopyalama Riski Eşiği", base_dict.get("literal_high_threshold", 0.35),
                 "Metin içerisindeki cümle ve paragrafların birebir kopyala-yapıştır yapılma oranı (0.35 = %35 kopyalama)."),
            ]
        }
    ]

    with st_ctx.form(f"adm_calibration_form_{selected_comp_slug or 'global'}"):
        form_values: dict[str, float] = {}

        for group in param_groups:
            st_ctx.markdown(f"""
            <div style="font-size: 1.15rem; font-weight: 850; color: #D80000; border-bottom: 2px solid #FEB2B2; padding-bottom: 6px; margin-top: 22px; margin-bottom: 6px;">
                {group['title']}
            </div>
            <div style="font-size: 0.90rem; color: #4A5568; font-weight: 500; margin-bottom: 14px;">
                {group['desc']}
            </div>
            """, unsafe_allow_html=True)

            for std_key, std_label, default_val, std_help in group["params"]:
                target_key = std_key if is_global else f"{selected_comp_slug}_{std_key}"
                curr_val = base_dict.get(target_key, default_val)

                # Parametre Giriş Kutusu + Detaylı Açıklama Kutusu
                c_inp, c_help = st_ctx.columns([1.8, 2.2])
                with c_inp:
                    step_val = 0.05 if "similarity" in std_key or "semantic" in std_key or "literal" in std_key else (0.5 if "threshold" in std_key else 0.01)
                    fmt_val = "%.2f" if "threshold" in std_key or "delta" in std_key else "%.4f"
                    
                    form_values[target_key] = st_ctx.number_input(
                        f"{std_label} — (`{target_key}`)",
                        value=float(curr_val),
                        step=step_val,
                        format=fmt_val,
                        key=f"input_cal_{target_key}",
                    )
                with c_help:
                    st_ctx.markdown(f"""
                    <div style="background: #F7FAFC; border: 1px solid #CBD5E1; border-radius: 8px; padding: 10px 14px; font-size: 0.86rem; color: #1E293B; line-height: 1.5; margin-top: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.05);">
                        <strong style="color: #FF1A00; font-weight: 800;">Ne İşe Yarar?</strong> <span style="color: #334155;">{std_help}</span>
                    </div>
                    """, unsafe_allow_html=True)

        st_ctx.markdown("<div style='margin-bottom: 16px;'></div>", unsafe_allow_html=True)

        if st_ctx.form_submit_button("Kalibrasyon Ayarlarını Kaydet", type="primary", use_container_width=True):
            def _save_scope() -> None:
                for k, v in form_values.items():
                    client.query("""
                        INSERT INTO calibration_settings (key, value, description, updated_at)
                        VALUES (?, ?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
                    """, [k, v, f"{selected_comp_name} özel kalibrasyonu", now_iso()])

            if _guard(st_ctx, lang, _save_scope) is not None:
                st_ctx.success(f"{selected_comp_name} için tüm kalibrasyon ayarları başarıyla kaydedildi!")
                st_ctx.rerun()


__all__ = ["goster"]
