"""T-Sistem · TEK tasarim sistemi.

ONCEKI DURUM
------------
`inject_css()` tanimliydi ama HICBIR YERDEN CAGRILMIYORDU. Bu yuzden bu
dosyadaki ~325 satirlik CSS tarayiciya hic ulasmiyordu ve uygulama, `app.py`
icindeki ayri bir blok ile `auth_view.py` icindeki DORT ayri `<style>` blogu
tarafindan sekillendiriliyordu. Sonuc:

  * Giris formunda buton turuncu, Kayit Ol sekmesinde Streamlit kirmizisi,
  * `components.py`'nin urettigi 12 `ts-*` sinifinin CSS karsiligi hic yoktu
    (puan cubugu ciziImiyor, pill'ler cercevesiz duz metin oluyordu),
  * ust toolbar gizlenmiyor, taban font uygulanmiyordu.

YENI DURUM
----------
* Tum renkler CSS custom property (`--ts-*`) olarak `:root`ta tanimlanir.
* Koyu tema `prefers-color-scheme` ile ayni token'lari yeniden tanimlar.
* `t3-*` (yerlesim) ve `ts-*` (bilesen) siniflarinin TAMAMI burada tanimlidir.
* Python sabitleri (SERIES, INK, STATUS…) grafik katmani icin korunmustur.
"""

from __future__ import annotations

import logging

_log = logging.getLogger("tsistem.theme")

# ═══════════════════════════════════════════════════════════════════════════
# 1. TOKEN'LAR  (tek kaynak — kodun baska hicbir yerinde hex yazilmaz)
# ═══════════════════════════════════════════════════════════════════════════

# ── Marka ──────────────────────────────────────────────────────────────────
BRAND = "#F04823"          # TEKNOFEST turuncusu
BRAND_600 = "#E03E1B"
BRAND_700 = "#D63713"
BRAND_SOFT = "#FEEDE8"

# ── Notr (hafif sicak biasli slate) ────────────────────────────────────────
SURFACE = "#FFFFFF"
PAGE = "#F4F6F9"
INK = "#0F172A"
INK_2 = "#334155"
MUTED = "#64748B"
GRID = "#E2E8F0"
AXIS = "#CBD5E1"
SLATE_50 = "#F8FAFC"
SLATE_100 = "#F1F5F9"
SLATE_400 = "#94A3B8"
SLATE_600 = "#475569"
BORDER = "rgba(15, 23, 42, 0.12)"

# ── Anlamsal (TEK deger — eski kodda yesil/kirmizi/lacivert ikiser tanimliydi)
OK = "#16A34A"
OK_SOFT = "#DCFCE7"
OK_INK = "#15803D"
WARN = "#D97706"
WARN_SOFT = "#FEF3C7"
WARN_INK = "#B45309"
DANGER = "#DC2626"
DANGER_SOFT = "#FEE2E2"
DANGER_INK = "#B91C1C"
INFO = "#0D6EFD"
INFO_SOFT = "#E0F2FE"
INFO_INK = "#0369A1"

# ── Grafik serileri ────────────────────────────────────────────────────────
SERIES = [BRAND, INFO, OK, "#6F42C1"]
SEQ = ["#DBEAFE", "#BFDBFE", "#93C5FD", "#60A5FA", "#2563EB", "#1D4ED8", "#1E40AF"]
STATUS = {
    "iyi": OK, "olumlu": OK, "basari": OK, "aktif": OK,
    "uyari": WARN, "orta": WARN, "bekliyor": WARN,
    "ciddi": "#EA580C",
    "kritik": DANGER, "hata": DANGER, "pasif": DANGER,
    "bilgi": INFO, "notr": MUTED,
}

# ── Tipografi ──────────────────────────────────────────────────────────────
FONT_DISPLAY = '"Inter", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'
FONT_FAMILY = FONT_DISPLAY
FONT = FONT_DISPLAY  # geriye donuk uyumluluk

FONT_SIZE = {"xs": "0.80rem", "sm": "0.92rem", "md": "1.00rem",
             "lg": "1.15rem", "xl": "1.35rem", "2xl": "1.60rem", "3xl": "2.00rem"}
WEIGHT = {"regular": 400, "medium": 500, "semibold": 600, "bold": 700, "black": 800}

# ── Olcekler (eski kodda 6 farkli radius, 4 farkli agirlik vardi) ──────────
RADIUS = {"sm": "6px", "md": "9px", "lg": "12px", "xl": "16px", "pill": "999px"}
SPACE = {"1": "4px", "2": "8px", "3": "12px", "4": "16px",
         "5": "22px", "6": "28px", "7": "36px", "8": "48px"}

# ── Geriye donuk uyumluluk (eski COLOR_* adlari) ──────────────────────────
COLOR_BG = PAGE
COLOR_WHITE = SURFACE
COLOR_ORANGE_RED = BRAND
COLOR_ORANGE_HOVER = BRAND_600
COLOR_BLUE_NAV = INFO
COLOR_NAVY_HEADING = "#1E293B"
COLOR_TEXT_MUTED = MUTED
COLOR_BORDER = GRID
COLOR_INPUT_BG = "#EEF2F6"
COLOR_GREEN = OK            # eski #198754 yerine TEK yesil
COLOR_RED_ALERT = DANGER    # eski #DC3545 yerine TEK kirmizi


# ═══════════════════════════════════════════════════════════════════════════
# 2. PLOTLY SABLONU
# ═══════════════════════════════════════════════════════════════════════════
def register_plotly_template() -> None:
    """`tsistem` adli Plotly sablonunu kaydeder ve varsayilan yapar."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:  # pragma: no cover
        return

    pio.templates["tsistem"] = go.layout.Template(
        layout=go.Layout(
            colorway=SERIES,
            font=dict(family=FONT_FAMILY, size=14, color=INK_2),
            paper_bgcolor=SURFACE,
            plot_bgcolor=SURFACE,
            title=dict(font=dict(size=17, color=INK), x=0.01, xanchor="left"),
            xaxis=dict(gridcolor=SLATE_100, linecolor=AXIS, zerolinecolor=GRID,
                       tickfont=dict(color=MUTED, size=12)),
            yaxis=dict(gridcolor=SLATE_100, linecolor=AXIS, zerolinecolor=GRID,
                       tickfont=dict(color=MUTED, size=12)),
            legend=dict(orientation="h", yanchor="bottom", y=1.02,
                        xanchor="left", x=0, font=dict(size=12, color=INK_2)),
            margin=dict(l=48, r=24, t=56, b=44),
            hoverlabel=dict(bgcolor=SURFACE, bordercolor=GRID,
                            font=dict(family=FONT_FAMILY, size=13, color=INK)),
        )
    )
    pio.templates.default = "tsistem"


# ═══════════════════════════════════════════════════════════════════════════
# 3. CSS
# ═══════════════════════════════════════════════════════════════════════════
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ── TOKEN'LAR ────────────────────────────────────────────────────────── */
:root {{
  --ts-brand:        {BRAND};
  --ts-brand-600:    {BRAND_600};
  --ts-brand-700:    {BRAND_700};
  --ts-brand-soft:   {BRAND_SOFT};
  --ts-on-brand:     #FFFFFF;

  --ts-surface:      {SURFACE};
  --ts-surface-2:    {SLATE_50};
  --ts-page:         {PAGE};
  --ts-ink:          {INK};
  --ts-ink-2:        {INK_2};
  --ts-muted:        {MUTED};
  --ts-line:         {GRID};
  --ts-line-strong:  {AXIS};
  --ts-input-bg:     {COLOR_INPUT_BG};

  --ts-ok:           {OK};   --ts-ok-soft:     {OK_SOFT};     --ts-ok-ink:     {OK_INK};
  --ts-warn:         {WARN}; --ts-warn-soft:   {WARN_SOFT};   --ts-warn-ink:   {WARN_INK};
  --ts-danger:       {DANGER}; --ts-danger-soft: {DANGER_SOFT}; --ts-danger-ink: {DANGER_INK};
  --ts-info:         {INFO}; --ts-info-soft:   {INFO_SOFT};   --ts-info-ink:   {INFO_INK};

  --ts-r-sm: {RADIUS['sm']}; --ts-r-md: {RADIUS['md']};
  --ts-r-lg: {RADIUS['lg']}; --ts-r-xl: {RADIUS['xl']};

  --ts-shadow-sm:    0 1px 3px rgba(15,23,42,.05);
  --ts-shadow-md:    0 3px 14px rgba(15,23,42,.06);
  --ts-shadow-brand: 0 4px 14px rgba(240,72,35,.28);

  --ts-font: {FONT_FAMILY};
}}

/* ── STREAMLIT KABUGU (ÜST BOŞLUKLARI TAM GİZLE) ─────────────────────── */
#MainMenu, footer, header, [data-testid="stHeader"], [data-testid="stAppHeader"], div[data-testid="stHeader"], div[data-testid="stAppHeader"] {{
  display: none !important;
  height: 0 !important;
  min-height: 0 !important;
  max-height: 0 !important;
  padding: 0 !important;
  margin: 0 !important;
}}
div[data-testid="stToolbar"], div[data-testid="stDecoration"],
div[data-testid="stStatusWidget"] {{ display: none !important; }}

html, body, [class*="css"], .stApp {{
  font-family: var(--ts-font) !important;
  font-size: 16.5px !important;
  color: var(--ts-ink) !important;
}}
.stApp {{ background: var(--ts-page) !important; }}
div.block-container {{
  padding-top: 0.2rem !important;
  padding-bottom: 2.5rem !important;
  max-width: 1400px !important;
}}

h1, h2, h3, h4, h5 {{
  font-family: var(--ts-font) !important;
  color: var(--ts-ink) !important;
  font-weight: {WEIGHT['black']} !important;
  letter-spacing: -0.015em !important;
  text-wrap: balance;
}}
h1 {{ font-size: 1.95rem !important; }}
h2 {{ font-size: 1.60rem !important; }}
h3 {{ font-size: 1.35rem !important; }}
h4 {{ font-size: 1.18rem !important; }}
h5 {{ font-size: 1.06rem !important; }}
p, li, label, span, div {{ color: inherit; }}

/* ── BUTONLAR ─────────────────────────────────────────────────────────── */
div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="stFormSubmitButton"] > button,
div[data-testid="stDownloadButton"] > button[kind="primary"] {{
  background: linear-gradient(135deg, var(--ts-brand) 0%, {BRAND_600} 100%) !important;
  color: #FFFFFF !important;
  border: none !important;
  border-radius: var(--ts-r-md) !important;
  padding: 8px 12px !important;
  min-height: 48px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  text-align: center !important;
  font-weight: {WEIGHT['bold']} !important;
  font-size: 0.90rem !important;
  line-height: 1.25 !important;
  box-shadow: var(--ts-shadow-brand) !important;
  transition: transform .12s ease, box-shadow .12s ease !important;
}}
div[data-testid="stButton"] > button[kind="primary"]:hover,
div[data-testid="stFormSubmitButton"] > button:hover {{
  background: linear-gradient(135deg, {BRAND_600} 0%, {BRAND_700} 100%) !important;
  box-shadow: 0 6px 20px rgba(240,72,35,.42) !important;
  transform: translateY(-1px) !important;
}}
div[data-testid="stButton"] > button[kind="secondary"] {{
  background: var(--ts-surface) !important;
  color: var(--ts-ink) !important;
  border: 1.5px solid var(--ts-line-strong) !important;
  border-radius: var(--ts-r-md) !important;
  padding: 8px 12px !important;
  min-height: 48px !important;
  display: flex !important;
  align-items: center !important;
  justify-content: center !important;
  text-align: center !important;
  font-weight: {WEIGHT['semibold']} !important;
  font-size: 0.90rem !important;
  line-height: 1.25 !important;
  box-shadow: var(--ts-shadow-sm) !important;
}}
div[data-testid="stButton"] > button[kind="secondary"]:hover {{
  border-color: var(--ts-brand) !important;
  color: var(--ts-brand) !important;
}}

/* Üst Sağ Mini Dil Butonu Özel Küçültme */
div.st-key-btn_nav_lang_top > button {{
  min-height: 30px !important;
  height: 30px !important;
  padding: 2px 10px !important;
  font-size: 0.80rem !important;
  border-radius: 16px !important;
}}

/* Çıkış Yap Butonu: Kırmızı Zemin & Beyaz Yazı & Yatay Olarak Daha Kompakt */
div.st-key-nav_logout > button,
div.st-key-nav_logout > button *,
div.st-key-nav_logout > button[kind="secondary"],
div.st-key-nav_logout > button[kind="secondary"] * {{
  background: linear-gradient(135deg, #EF4444 0%, #DC2626 100%) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  border: none !important;
  border-radius: 8px !important;
  font-weight: 800 !important;
  font-size: 0.88rem !important;
  padding: 6px 10px !important;
  box-shadow: 0 2px 8px rgba(220, 38, 38, 0.35) !important;
  transition: all .15s ease !important;
}}
div.st-key-nav_logout > button:hover,
div.st-key-nav_logout > button:hover * {{
  background: linear-gradient(135deg, #DC2626 0%, #B91C1C 100%) !important;
  color: #FFFFFF !important;
  -webkit-text-fill-color: #FFFFFF !important;
  box-shadow: 0 4px 14px rgba(220, 38, 38, 0.50) !important;
  transform: translateY(-1px) !important;
}}
div[data-testid="stButton"] > button:focus-visible,
div[data-testid="stFormSubmitButton"] > button:focus-visible {{
  outline: 3px solid var(--ts-brand-soft) !important;
  outline-offset: 2px !important;
}}

/* ── FORM ALANLARI ────────────────────────────────────────────────────── */
div[data-baseweb="input"], div[data-baseweb="select"] > div, div[data-baseweb="textarea"] {{
  background: var(--ts-input-bg) !important;
  border: 1.5px solid var(--ts-line-strong) !important;
  border-radius: var(--ts-r-md) !important;
  box-shadow: inset 0 1px 2px rgba(15,23,42,.05) !important;
}}
div[data-baseweb="input"]:focus-within, div[data-baseweb="textarea"]:focus-within {{
  border-color: var(--ts-brand) !important;
  box-shadow: 0 0 0 3.5px rgba(240,72,35,.20) !important;
  background: var(--ts-surface) !important;
}}
div[data-baseweb="input"] input, textarea {{
  color: var(--ts-ink) !important;
  font-weight: {WEIGHT['medium']} !important;
  font-size: 1rem !important;
}}
label, .stSelectbox label, .stTextInput label, .stRadio label {{
  color: var(--ts-ink) !important;
  font-weight: {WEIGHT['semibold']} !important;
  font-size: 1.02rem !important;
}}

/* ── SEKMELER (st.tabs) ────────────────────────────────────────────────── */
div[data-baseweb="tab-list"] {{
  background: #F8FAFC !important;
  border-bottom: 2px solid #E2E8F0 !important;
  border-radius: 12px 12px 0 0 !important;
  padding: 8px 12px 0 12px !important;
  gap: 12px !important;
}}
button[data-baseweb="tab"] {{
  border-radius: 8px 8px 0 0 !important;
  padding: 14px 28px !important;
  font-weight: 700 !important;
  font-size: 1.18rem !important;
  color: #64748B !important;
  background: transparent !important;
  border-bottom: 3px solid transparent !important;
  transition: all .15s ease !important;
}}
button[data-baseweb="tab"]:hover {{
  color: var(--ts-brand) !important;
  background: #FEEDE8 !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
  background: #FFFFFF !important;
  color: var(--ts-brand) !important;
  font-weight: 800 !important;
  font-size: 1.20rem !important;
  border-bottom: 3.5px solid var(--ts-brand) !important;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.04) !important;
}}
button[data-baseweb="tab"] p, button[data-baseweb="tab"] div, button[data-baseweb="tab"] span {{
  font-size: 1.18rem !important;
  font-weight: inherit !important;
}}
div[data-baseweb="tab-highlight"], div[data-baseweb="tab-border"] {{ display: none !important; }}



div[data-testid="stExpander"] {{
  background: var(--ts-surface) !important;
  border: 1px solid var(--ts-line) !important;
  border-radius: var(--ts-r-lg) !important;
  box-shadow: var(--ts-shadow-sm) !important;
}}

/* ── T3 YERLESIM SINIFLARI ────────────────────────────────────────────── */
.t3-navbar {{
  background: var(--ts-surface);
  border: 1px solid var(--ts-line);
  border-radius: var(--ts-r-lg);
  padding: 14px 26px;
  box-shadow: var(--ts-shadow-sm);
  margin-bottom: 18px;
}}
.t3-module-card {{
  background: linear-gradient(135deg, var(--ts-brand) 0%, {BRAND_600} 100%);
  border-radius: var(--ts-r-xl);
  padding: 26px 22px;
  min-height: 230px;
  display: flex; flex-direction: column; justify-content: center; align-items: center;
  text-align: center;
  box-shadow: 0 6px 20px rgba(240,72,35,.22);
  transition: transform .16s ease, box-shadow .16s ease;
}}
.t3-module-card:hover {{ transform: translateY(-3px); box-shadow: 0 10px 28px rgba(240,72,35,.30); }}
.t3-module-title {{
  color: #FFFFFF; font-size: 1.20rem; font-weight: {WEIGHT['black']};
  letter-spacing: .02em; margin-bottom: 8px;
}}
.t3-module-desc {{ color: rgba(255,255,255,.92); font-size: 0.94rem; line-height: 1.5; }}

.t3-content-card {{
  background: var(--ts-surface);
  border: 1px solid var(--ts-line);
  border-radius: var(--ts-r-xl);
  padding: 24px 28px;
  box-shadow: var(--ts-shadow-md);
  margin-bottom: 18px;
}}
.t3-card-title {{ font-size: 1.38rem; font-weight: {WEIGHT['black']}; color: var(--ts-ink); letter-spacing: -.01em; }}
.t3-card-sub {{ font-size: 0.94rem; color: var(--ts-muted); margin-top: 4px; }}

.t3-sep {{ border: none; border-top: 1px solid var(--ts-line); margin: 14px 0; }}
.t3-form-section {{
  font-size: 0.96rem; font-weight: {WEIGHT['bold']};
  color: var(--ts-ink); margin-bottom: 6px;
}}

/* Segment (Giris Yap / Kayit Ol) — eski kodda iki aynali blok vardi */
.t3-segment {{ display: flex; gap: 8px; margin-bottom: 14px; }}
.t3-segment-btn {{
  flex: 1; text-align: center; padding: 11px 0;
  border-radius: var(--ts-r-md); font-weight: {WEIGHT['bold']};
  background: var(--ts-brand-soft); color: var(--ts-brand-700);
  border: 1px solid transparent; cursor: pointer;
}}
.t3-segment-btn--active {{
  background: var(--ts-brand); color: #FFFFFF; box-shadow: var(--ts-shadow-brand);
}}

/* ── ROZETLER (tek sistem: .t3-badge + modifier) ──────────────────────── */
.t3-badge, .t3-badge-aktif, .t3-badge-pasif, .t3-badge-info, .t3-badge-turuncu {{
  display: inline-block; padding: 4px 12px; border-radius: var(--ts-r-pill, 999px);
  font-size: 0.82rem; font-weight: {WEIGHT['bold']}; letter-spacing: .01em;
}}
.t3-badge-aktif   {{ background: var(--ts-ok-soft);     color: var(--ts-ok-ink); }}
.t3-badge-pasif   {{ background: var(--ts-danger-soft); color: var(--ts-danger-ink); }}
.t3-badge-info    {{ background: var(--ts-info-soft);   color: var(--ts-info-ink); }}
.t3-badge-turuncu {{ background: var(--ts-brand-soft);  color: var(--ts-brand-700); }}

/* ── TS BILESEN SINIFLARI ─────────────────────────────────────────────── */
/* Bu 12 sinif components.py tarafindan uretiliyordu ama HICBIR YERDE
   tanimli degildi; puan cubugu cizilmiyor, pill'ler duz metin oluyordu. */
.ts-card {{
  background: var(--ts-surface); border: 1px solid var(--ts-line);
  border-radius: var(--ts-r-lg); padding: 16px 18px; box-shadow: var(--ts-shadow-sm);
  margin-bottom: 12px;
}}
.ts-tile {{
  background: var(--ts-surface); border: 1px solid var(--ts-line);
  border-radius: var(--ts-r-lg); padding: 16px 18px; box-shadow: var(--ts-shadow-sm);
}}
.ts-tile-label {{
  font-size: 0.78rem; letter-spacing: .09em; text-transform: uppercase;
  color: var(--ts-muted); font-weight: {WEIGHT['semibold']}; margin-bottom: 6px;
}}
.ts-tile-value {{
  font-size: 1.85rem; font-weight: {WEIGHT['black']}; color: var(--ts-ink);
  line-height: 1.05; font-variant-numeric: tabular-nums;
}}
.ts-tile-foot {{ font-size: 0.84rem; color: var(--ts-muted); margin-top: 6px; }}

.ts-pill {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 3px 11px; border-radius: 999px;
  font-size: 0.80rem; font-weight: {WEIGHT['bold']};
  background: var(--ts-surface-2); color: var(--ts-ink-2);
  border: 1px solid var(--ts-line-strong);
}}
.ts-dot {{
  display: inline-block; width: 8px; height: 8px; border-radius: 50%;
  background: currentColor; flex: none;
}}

.ts-track {{
  height: 9px; border-radius: 999px; background: var(--ts-surface-2);
  border: 1px solid var(--ts-line); overflow: hidden; margin: 6px 0;
}}
.ts-fill {{ height: 100%; border-radius: 999px; background: var(--ts-brand); display: block; }}

.ts-quote {{
  border-left: 3px solid var(--ts-brand); padding: 6px 0 6px 14px;
  color: var(--ts-ink-2); font-size: 0.94rem; margin: 8px 0;
}}
.ts-quote-src {{ display: block; font-size: 0.78rem; color: var(--ts-muted); margin-top: 4px; }}

.ts-sub   {{ font-size: 0.90rem; color: var(--ts-ink-2); }}
.ts-muted {{ font-size: 0.86rem; color: var(--ts-muted); }}
.ts-kv    {{ display: flex; justify-content: space-between; gap: 12px;
             padding: 5px 0; border-bottom: 1px dashed var(--ts-line); font-size: 0.92rem; }}
.ts-metric-val {{ font-size: 1.7rem; font-weight: {WEIGHT['black']}; color: var(--ts-ink);
                  font-variant-numeric: tabular-nums; }}

/* ── ERISILEBILIRLIK ──────────────────────────────────────────────────── */
a:focus-visible, button:focus-visible, input:focus-visible, select:focus-visible {{
  outline: 3px solid var(--ts-brand-soft) !important; outline-offset: 2px !important;
}}
@media (prefers-reduced-motion: reduce) {{
  * {{ animation: none !important; transition: none !important; }}
}}

/* Genis icerik yatayda kendi kutusunda kaysin, sayfa govdesi kaymasin */
div[data-testid="stDataFrame"], .t3-scroll {{ overflow-x: auto; }}
</style>
"""


_INJECTED_FLAG = "_ts_theme_injected"


def inject_css(st, *, force: bool = False) -> None:
    """Tasarim sistemini sayfaya enjekte eder.

    `app.py` icinde `st.set_page_config(...)` cagrisindan HEMEN SONRA
    bir kez cagrilmalidir. Idempotenttir: ayni rerun icinde tekrar
    cagrilirsa CSS ikinci kez basilmaz.
    """
    if not force and st.session_state.get(_INJECTED_FLAG):
        return
    st.markdown(CSS, unsafe_allow_html=True)
    setter = getattr(st, "session_state", None)
    if setter is not None:
        try:
            setter[_INJECTED_FLAG] = True
        except (KeyError, TypeError, AttributeError) as exc:  # test cifti
            _log.debug("session_state yazilamadi: %s", exc)


def inject_history_js(st) -> None:
    """
    Tarayıcı Geri/İleri (Back/Forward) altyapısını global olarak kurar.

    Streamlit tüm URL değişikliklerinde history.replaceState() kullanır;
    bu tarayıcı geçmişi OLUŞTURMAZ. Bu fonksiyon replaceState'i yakalar ve
    ?tab=, ?view=, ?slug=, ?ann_id= içeren tüm navigasyon URL'lerini otomatik
    olarak pushState'e çevirir. Böylece:

      • Her sekme tıklaması     → pushState  → ← Geri çalışır
      • Her yarışma detayı      → pushState  → ← Geri çalışır
      • Her duyuru/sayfa geçişi → pushState  → ← Geri çalışır
      • Tarayıcı ← →            → reload     → doğru sayfa gelir

    Bu fonksiyon bootstrap() içinden çağrılır; dolayısıyla uygulamadaki
    HER ekran ve HER buton için otomatik olarak aktif olur.
    """
    st.components.v1.html("""
<script>
(function() {
    /* Streamlit kendi iframe'i içinde çalışır; parent window'u hedef alıyoruz. */
    var win = window.parent;
    if (!win || win.__tsistem_nav_ready) return;
    win.__tsistem_nav_ready = true;

    /* Navigasyon URL'si mi? Herhangi bir parametre veya kök sayfa geçişinde pushState kullan. */
    function isNavUrl(u) {
        return u && (
            u.indexOf('?') !== -1 ||
            u === win.location.pathname ||
            u === '/'
        );
    }

    /* Streamlit'in replaceState çağrısını yakala */
    var _orig = win.history.replaceState.bind(win.history);
    var _last = win.location.search;

    win.history.replaceState = function(state, title, url) {
        var u = String(url || '');
        if (isNavUrl(u) && u !== _last) {
            _last = u;
            /* Geçmişe YENİ entry ekle */
            win.history.pushState(state, title, url);
        } else {
            _orig(state, title, url);
        }
    };

    /* Tarayıcı Geri/İleri butonuna basılınca sayfayı yeniden yükle.
       Yeniden yükleme, Streamlit'in URL'deki query param'ı okumasını sağlar. */
    win.addEventListener('popstate', function() {
        win.location.reload();
    });

    /* Streamlit bileşenlerinden gelen navigasyon mesajlarını dinle */
    win.addEventListener('message', function(event) {
        if (event && event.data && event.data.type === 'tsistem_navigate' && event.data.url) {
            var target = event.data.url;
            if (target.indexOf('?') === 0) {
                win.location.href = win.location.origin + win.location.pathname + target;
            } else {
                win.location.href = target;
            }
        }
    });
})();
</script>
""", height=0, width=0)


def bootstrap(st) -> None:
    """Tema + Plotly şablonunu + tarayıcı geçmişi altyapısını birlikte kurar."""
    inject_css(st)
    register_plotly_template()
    inject_history_js(st)


__all__ = [
    "CSS", "inject_css", "bootstrap", "register_plotly_template",
    "inject_history_js",
    "SERIES", "SEQ", "STATUS", "SURFACE", "PAGE", "INK", "INK_2", "MUTED",
    "GRID", "AXIS", "BORDER", "FONT", "FONT_FAMILY", "FONT_DISPLAY",
    "BRAND", "BRAND_600", "BRAND_700", "OK", "WARN", "DANGER", "INFO",
    "RADIUS", "SPACE", "FONT_SIZE", "WEIGHT",
    "COLOR_BG", "COLOR_WHITE", "COLOR_ORANGE_RED", "COLOR_ORANGE_HOVER",
    "COLOR_BLUE_NAV", "COLOR_NAVY_HEADING", "COLOR_TEXT_MUTED",
    "COLOR_BORDER", "COLOR_INPUT_BG", "COLOR_GREEN", "COLOR_RED_ALERT",
]
