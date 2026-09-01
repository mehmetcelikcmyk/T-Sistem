"""Yeniden kullanılabilir arayüz bileşenleri.

Kural: renk asla tek başına anlam taşımaz — her durum göstergesi ikon + metinle
gelir. Her grafiğin bir "tabloyu gör" ikizi vardır.
"""

from __future__ import annotations

import html

import theme

DURUM_ETIKET = {
    "tamamlandi": ("Tamamlandı", theme.STATUS["iyi"], "✓"),
    "hakem_bekliyor": ("Hakem bekliyor", theme.STATUS["uyari"], "◔"),
    "ai_analiz_tamam": ("AI analizi tamam", theme.SERIES[0], "◍"),
    "kuyrukta": ("Kuyrukta", theme.MUTED, "◌"),
    "hatali": ("Hatalı", theme.STATUS["kritik"], "!"),
}


def _kacis(metin: str) -> str:
    return html.escape(str(metin))


def stat_tile(st, etiket: str, deger, alt: str = "") -> None:
    st.markdown(
        f"""<div class="ts-tile">
              <div class="ts-tile-label">{_kacis(etiket)}</div>
              <div class="ts-tile-value">{_kacis(deger)}</div>
              <div class="ts-tile-foot">{_kacis(alt)}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def durum_pill(durum: str) -> str:
    etiket, renk, ikon = DURUM_ETIKET.get(durum, (durum, theme.MUTED, "•"))
    return (
        f'<span class="ts-pill"><span class="ts-dot" style="background:{renk}"></span>'
        f"{ikon} {_kacis(etiket)}</span>"
    )


def kontrol_pill(uygun: bool, etiket_uygun: str, etiket_uygunsuz: str) -> str:
    if uygun:
        renk, ikon, etiket = theme.STATUS["iyi"], "✓", etiket_uygun
    else:
        renk, ikon, etiket = theme.STATUS["kritik"], "✕", etiket_uygunsuz
    return (
        f'<span class="ts-pill"><span class="ts-dot" style="background:{renk}"></span>'
        f"{ikon} {_kacis(etiket)}</span>"
    )


def kart_basi(st, baslik: str, alt: str = "") -> None:
    alt_html = f'<div class="ts-sub">{_kacis(alt)}</div>' if alt else ""
    st.markdown(f"### {baslik}\n{alt_html}", unsafe_allow_html=True)


def alinti(st, metin: str, bolum: str, guven: float | None = None) -> None:
    guven_html = ""
    if guven is not None:
        guven_html = f" · Model güveni %{int(guven * 100)}"
    st.markdown(
        f"""<div class="ts-quote">“{_kacis(metin)}”
              <div class="ts-quote-src">Kaynak: {_kacis(bolum)}{guven_html}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def puan_cubugu(st, puan: float, maks: float = 5) -> None:
    oran = max(0.0, min(1.0, puan / maks)) * 100
    st.markdown(
        f"""<div class="ts-track"><div class="ts-fill" style="width:{oran:.1f}%"></div></div>""",
        unsafe_allow_html=True,
    )


def tablo_ikizi(st, veri, etiket: str = "Tabloyu gör") -> None:
    """Her grafiğin erişilebilir ikizi — değerler renkten bağımsız okunabilir."""
    with st.expander(etiket):
        st.dataframe(veri, width='stretch', hide_index=True)


def hata_karti(st, hata: dict, dosya: str | None = None) -> None:
    """İşlenemeyen rapor için tek ve net bir açıklama.

    Kural: hata mesajı ne olduğunu, neden olduğunu ve ne yapılacağını söyler.
    "Bir hata oluştu" yazan ekran, hakemi bilgisiz bırakır.
    """
    st.markdown(
        f"""<div class="ts-card" style="border-left:3px solid {theme.STATUS['kritik']};">
              <span class="ts-pill"><span class="ts-dot"
                style="background:{theme.STATUS['kritik']}"></span>! İşlenemedi</span>
              <div style="color:{theme.INK};font-weight:600;margin-top:10px;">
                {_kacis(hata['baslik'])}</div>
              <div class="ts-kv" style="margin-top:6px;">{_kacis(hata['aciklama'])}</div>
              <div class="ts-kv" style="margin-top:10px;">
                <b>Yapılması gereken:</b> {_kacis(hata['cozum'])}</div>
              <div class="ts-muted" style="margin-top:10px;">
                Hata kodu: {_kacis(hata['tur'])}{' · dosya: ' + _kacis(dosya) if dosya else ''}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def iskelet(st, satir: int = 3) -> None:
    """Veri beklenirken yer tutucu — düzen zıplamasın."""
    cubuklar = "".join(
        f'<div style="height:12px;border-radius:6px;background:{theme.GRID};'
        f'margin:8px 0;width:{w}%;"></div>' for w in (92, 78, 64)[:satir]
    )
    st.markdown(f'<div class="ts-card">{cubuklar}</div>', unsafe_allow_html=True)


def bos_durum(st, baslik: str, aciklama: str) -> None:
    st.markdown(
        f"""<div class="ts-card">
              <div style="color:{theme.INK};font-weight:600;">{_kacis(baslik)}</div>
              <div class="ts-sub" style="margin-top:6px;">{_kacis(aciklama)}</div>
            </div>""",
        unsafe_allow_html=True,
    )
