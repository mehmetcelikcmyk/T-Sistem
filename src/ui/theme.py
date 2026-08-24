"""T3 KYS & TEKNOFEST Birebir Kurumsal Tasarım Sistemi ve Teması.

- Giriş Yap / Kayıt Ol ekranındaki kurumsal renk paleti (Vibrant Orange #F04823, Deep Navy #0F172A, Soft Slate #F4F6F9) uygulama geneline eksiksiz yansıtıldı.
- Genel uygulama font boyutu büyütüldü (16.5px taban, net başlıklar, büyük ve okunaklı girdiler).
- Sekmeler (stTabs) belirgin, ferah ve modern Segmented Pill / Kart butonlarına dönüştürüldü.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio

# --- Zeminler ve mürekkep (Yüksek Kontrast & Belirgin Ayrım) ---
SURFACE = "#FFFFFF"   # kart / grafik / kutu zemini (saf beyaz)
PAGE = "#F4F6F9"      # sayfa zemini (ferah gri-mavi)
INK = "#0F172A"       # birincil metin (koyu lacivert-siyah)
INK_2 = "#334155"     # ikincil metin
MUTED = "#64748B"     # eksen / etiket
GRID = "#E2E8F0"      # ızgara
AXIS = "#CBD5E1"      # taban çizgisi
BORDER = "rgba(15, 23, 42, 0.12)"

# --- Kategorik seriler (Plotly ve grafikler) -------------
SERIES = ["#F04823", "#0D6EFD", "#16A34A", "#6F42C1"]

# --- Durum renkleri (başarı, uyarı, kritik) -----------------
STATUS = {
    "iyi": "#16A34A",
    "olumlu": "#16A34A",
    "basari": "#16A34A",
    "uyari": "#D97706",
    "ciddi": "#EA580C",
    "kritik": "#DC2626",
    "hata": "#DC2626",
}

# Sıralı mavi rampa
SEQ = ["#DBEAFE", "#BFDBFE", "#93C5FD", "#60A5FA", "#2563EB", "#1D4ED8", "#1E40AF"]
FONT = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif'

# --- T3 KYS & TEKNOFEST Resmî Renk Paleti ---
COLOR_BG = "#F4F6F9"               # Sayfa Zemin Rengi
COLOR_WHITE = "#FFFFFF"            # Saf Beyaz Zemin
COLOR_ORANGE_RED = "#F04823"       # T3 KYS Birincil Canlı Turuncu
COLOR_ORANGE_HOVER = "#D93815"     # Buton Hover Rengi
COLOR_BLUE_NAV = "#0D6EFD"         # İşlem Butonları Mavi
COLOR_NAVY_HEADING = "#1E293B"     # Koyu Başlık Rengi
COLOR_TEXT_MUTED = "#64748B"       # Açıklama ve İkincil Metinler
COLOR_BORDER = "#E2E8F0"           # İnce Kart & Çerçeve Rengi
COLOR_INPUT_BG = "#EEF2F6"         # Form Girdi Alanı Dolgu Rengi
COLOR_GREEN = "#198754"            # Aktif Durum Yeşili
COLOR_RED_ALERT = "#DC3545"        # Pasif / Hata Kırmızısı

FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'


def register_plotly_template() -> None:
    """Grafikler için T3 KYS uyumlu sade şablon."""
    tpl = go.layout.Template()
    tpl.layout = go.Layout(
        paper_bgcolor=COLOR_WHITE,
        plot_bgcolor=COLOR_WHITE,
        font=dict(family=FONT_FAMILY, size=13, color=COLOR_NAVY_HEADING),
        title=dict(font=dict(size=15, color=COLOR_NAVY_HEADING, family=FONT_FAMILY), x=0, xanchor="left", pad=dict(b=12)),
        margin=dict(l=10, r=16, t=40, b=10),
        colorway=[COLOR_ORANGE_RED, "#0D6EFD", COLOR_GREEN, "#6F42C1"],
        xaxis=dict(showgrid=True, gridcolor="#F1F5F9", zeroline=False, linecolor=COLOR_BORDER),
        yaxis=dict(showgrid=False, zeroline=False, linecolor=COLOR_BORDER),
    )
    pio.templates["t3kys_theme"] = tpl
    pio.templates.default = "t3kys_theme"


CSS = f"""
<style>
  /* 1. STREAMLIT ÜST ŞERİDİ, DEPLOY BUTONU, TOOLBAR VE 3 NOKTA MENÜSÜNÜ TAMAMEN GİZLE */
  header, [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stStatusWidget"], .stDeployButton, #MainMenu, footer, div[data-testid="stToolbarActions"], [data-testid="stToolbar"] > * {{
    display: none !important;
    visibility: hidden !important;
    height: 0px !important;
    width: 0px !important;
    opacity: 0 !important;
    pointer-events: none !important;
  }}

  div[data-testid="InputInstructions"] {{
    display: none !important;
    visibility: hidden !important;
    height: 0px !important;
  }}

  /* 2. SAYFA VE BOŞLUKLARI SIFIRLAYARAK TAM EKRAN WEBSİTESİ YAP & BÜYÜK FONT */
  .stApp {{
    background-color: {COLOR_BG} !important;
    font-family: {FONT_FAMILY} !important;
    font-size: 16.5px !important;
    color: {COLOR_NAVY_HEADING} !important;
    margin-top: 0px !important;
    padding-top: 0px !important;
  }}

  .block-container {{
    padding-top: 0.6rem !important;
    padding-bottom: 2rem !important;
    max-width: 1400px !important;
  }}

  /* Genel Tipografi Büyütmeleri */
  h1, h2, h3, h4, h5 {{
    font-family: {FONT_FAMILY} !important;
    font-weight: 800 !important;
    color: #0F172A !important;
  }}
  h1 {{ font-size: 1.85rem !important; }}
  h2 {{ font-size: 1.55rem !important; }}
  h3 {{ font-size: 1.35rem !important; }}
  h4 {{ font-size: 1.20rem !important; }}
  h5 {{ font-size: 1.10rem !important; }}

  /* T3 KYS Üst Navbar Tasarımı */
  .t3-navbar {{
    background: {COLOR_WHITE};
    border-radius: 14px;
    padding: 14px 28px;
    margin-bottom: 20px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    box-shadow: 0 2px 10px rgba(0, 0, 0, 0.04);
    border: 1px solid {COLOR_BORDER};
  }}

  /* T3 KYS Kırmızı/Turuncu Büyük Modül Kartları */
  .t3-module-card {{
    background: linear-gradient(135deg, #F04823 0%, #D93815 100%);
    border-radius: 16px;
    padding: 30px 24px;
    color: #FFFFFF;
    text-align: center;
    min-height: 270px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    align-items: center;
    box-shadow: 0 6px 20px rgba(240, 72, 35, 0.25);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
  }}

  .t3-module-card:hover {{
    transform: translateY(-4px);
    box-shadow: 0 10px 25px rgba(240, 72, 35, 0.35);
  }}

  .t3-module-title {{
    font-size: 1.25rem;
    font-weight: 800;
    text-transform: uppercase;
    letter-spacing: 0.03em;
    margin-bottom: 10px;
    color: #FFFFFF !important;
  }}

  .t3-module-desc {{
    font-size: 0.95rem;
    color: rgba(255, 255, 255, 0.92);
    line-height: 1.55;
    margin-bottom: 18px;
  }}

  /* T3 KYS Beyaz İçerik & Tablo Kartı */
  .t3-content-card {{
    background: {COLOR_WHITE};
    border-radius: 16px;
    padding: 26px 32px;
    margin-bottom: 22px;
    box-shadow: 0 3px 14px rgba(0, 0, 0, 0.04);
    border: 1px solid {COLOR_BORDER};
  }}

  .t3-card-title {{
    font-size: 1.45rem;
    font-weight: 800;
    color: #0F172A;
    margin-bottom: 6px;
    letter-spacing: -0.01em;
  }}

  .t3-card-sub {{
    font-size: 0.96rem;
    color: {COLOR_TEXT_MUTED};
    line-height: 1.5;
  }}

  /* 3. T3 KYS BİRİNCİL (PRIMARY) BUTONLAR - CANLI TURUNCU */
  button[data-testid="baseButton-primary"],
  button[data-testid="stBaseButton-primary"],
  button[kind="primary"],
  button[kind="primaryFormSubmit"],
  div[data-testid="stFormSubmitButton"] > button,
  div.stDownloadButton > button[kind="primary"] {{
    background-color: {COLOR_ORANGE_RED} !important;
    background-image: linear-gradient(135deg, #F04823 0%, #E03E1B 100%) !important;
    color: #FFFFFF !important;
    border: none !important;
    border-radius: 9px !important;
    font-weight: 800 !important;
    font-size: 1.02rem !important;
    padding: 12px 22px !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    box-shadow: 0 4px 14px rgba(240, 72, 35, 0.28) !important;
  }}

  button[data-testid="baseButton-primary"]:hover,
  button[data-testid="stBaseButton-primary"]:hover,
  button[kind="primary"]:hover,
  button[kind="primaryFormSubmit"]:hover,
  div[data-testid="stFormSubmitButton"] > button:hover,
  div.stDownloadButton > button[kind="primary"]:hover {{
    background-color: {COLOR_ORANGE_HOVER} !important;
    background-image: linear-gradient(135deg, #E03E1B 0%, #D63713 100%) !important;
    color: #FFFFFF !important;
    box-shadow: 0 6px 20px rgba(240, 72, 35, 0.42) !important;
    transform: translateY(-1px) !important;
  }}

  /* İKİNCİL (SECONDARY) & MENÜ BUTONLARI - BEYAZ / TEMİZ GRİ */
  button[data-testid="baseButton-secondary"],
  button[data-testid="stBaseButton-secondary"],
  button[kind="secondary"],
  button[kind="secondaryFormSubmit"],
  div.stDownloadButton > button[kind="secondary"] {{
    background: #FFFFFF !important;
    color: #1E293B !important;
    border: 1.5px solid #CBD5E1 !important;
    border-radius: 9px !important;
    font-weight: 750 !important;
    font-size: 1.00rem !important;
    padding: 10px 20px !important;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03) !important;
    transition: all 0.2s ease !important;
  }}

  button[data-testid="baseButton-secondary"]:hover,
  button[data-testid="stBaseButton-secondary"]:hover,
  button[kind="secondary"]:hover,
  button[kind="secondaryFormSubmit"]:hover,
  div.stDownloadButton > button[kind="secondary"]:hover {{
    background-color: #F8FAFC !important;
    border-color: #F04823 !important;
    color: #F04823 !important;
  }}

  /* 4. FORM ALANLARI VE GİRDİLER (INPUT & SELECTBOX) */
  div[data-testid="stWidgetLabel"] label, label {{
    font-weight: 750 !important;
    font-size: 1.02rem !important;
    color: #0F172A !important;
    margin-bottom: 6px !important;
  }}

  div[data-baseweb="input"],
  div[data-baseweb="base-input"],
  div[data-baseweb="select"] > div {{
    background-color: {COLOR_INPUT_BG} !important;
    border: 1.5px solid #CBD5E1 !important;
    border-radius: 9px !important;
    transition: all 0.2s ease-in-out !important;
  }}

  div[data-baseweb="input"]:hover,
  div[data-baseweb="base-input"]:hover,
  div[data-baseweb="select"] > div:hover {{
    border-color: #94A3B8 !important;
    background-color: #E2E8F0 !important;
  }}

  /* Focus Durumu (Parıltılı Turuncu Çerçeve) */
  div[data-baseweb="input"]:focus-within,
  div[data-baseweb="base-input"]:focus-within,
  div[data-baseweb="select"] > div:focus-within {{
    border-color: {COLOR_ORANGE_RED} !important;
    background-color: #FFFFFF !important;
    box-shadow: 0 0 0 3.5px rgba(240, 72, 35, 0.20), inset 0 1px 2px rgba(0, 0, 0, 0.02) !important;
  }}

  input[type="text"], input[type="password"], input[type="number"], textarea {{
    font-size: 1.00rem !important;
    color: #0F172A !important;
    font-weight: 600 !important;
    padding: 10px 14px !important;
    border: none !important;
    background: transparent !important;
  }}

  input::placeholder, textarea::placeholder {{
    color: #64748B !important;
    opacity: 0.85 !important;
  }}

  /* 5. STREAMLIT TABLAR (BELİRGİN VE MODERN SEGMENTED PILL BUTONLARI) */
  div[data-testid="stTabs"] {{
    margin-bottom: 24px !important;
  }}

  div[data-testid="stTabs"] > div:first-child {{
    background: #EEF2F6 !important;
    padding: 6px !important;
    border-radius: 12px !important;
    border: 1px solid #CBD5E1 !important;
    display: inline-flex !important;
    gap: 8px !important;
    margin-bottom: 12px !important;
  }}

  div[data-testid="stTabs"] button[role="tab"] {{
    background: transparent !important;
    border-radius: 8px !important;
    font-weight: 750 !important;
    font-size: 1.05rem !important;
    color: #475569 !important;
    padding: 10px 22px !important;
    border: none !important;
    transition: all 0.2s ease !important;
  }}

  div[data-testid="stTabs"] button[role="tab"]:hover {{
    background: rgba(255, 255, 255, 0.7) !important;
    color: #0F172A !important;
  }}

  div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
    background: #FFFFFF !important;
    color: {COLOR_ORANGE_RED} !important;
    box-shadow: 0 3px 12px rgba(0, 0, 0, 0.08) !important;
    border: 1px solid #CBD5E1 !important;
    border-bottom: 3.5px solid {COLOR_ORANGE_RED} !important;
    font-weight: 850 !important;
  }}

  /* 6. EXPANDER KUTULARI */
  div[data-testid="stExpander"] {{
    background: #FFFFFF !important;
    border: 1px solid {COLOR_BORDER} !important;
    border-radius: 12px !important;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.02) !important;
    margin-bottom: 12px !important;
  }}

  /* 7. CHECKBOX VE RADİO BUTONLARI */
  span[data-baseweb="checkbox"] span:first-child {{
    background-color: {COLOR_ORANGE_RED} !important;
    border-color: {COLOR_ORANGE_RED} !important;
  }}

  /* 8. SLIDER VE İLERLEME ÇUBUĞU (PROGRESS) */
  div[data-testid="stSlider"] div[data-testid="stThumbValue"] {{
    color: {COLOR_ORANGE_RED} !important;
    font-weight: 750 !important;
  }}
  div[data-testid="stSlider"] div[role="slider"] {{
    background-color: {COLOR_ORANGE_RED} !important;
    border-color: {COLOR_ORANGE_RED} !important;
  }}
  div[data-testid="stProgress"] > div > div > div > div {{
    background-color: {COLOR_ORANGE_RED} !important;
  }}

  /* 9. T3 KYS TABLO ROZETLERİ */
  .t3-badge-aktif {{
    background-color: #198754;
    color: #FFFFFF;
    font-size: 0.82rem;
    font-weight: 750;
    padding: 5px 14px;
    border-radius: 6px;
    display: inline-block;
  }}

  .t3-badge-pasif {{
    background-color: #DC3545;
    color: #FFFFFF;
    font-size: 0.82rem;
    font-weight: 750;
    padding: 5px 14px;
    border-radius: 6px;
    display: inline-block;
  }}

  .t3-badge-turuncu {{
    background-color: #F04823;
    color: #FFFFFF;
    font-size: 0.82rem;
    font-weight: 750;
    padding: 5px 14px;
    border-radius: 6px;
    display: inline-block;
  }}
</style>
"""


def inject_css(st) -> None:
    """CSS stillerini enjekte eder."""
    st.markdown(CSS, unsafe_allow_html=True)
