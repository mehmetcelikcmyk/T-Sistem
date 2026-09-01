"""Grafikler.

Kurallar (bilinçli tercihler, keyfi değil):
- Tek seri → tek renk (slot 1). Çubuk uzunluğunu ayrıca renkle kodlamıyoruz.
- Çift eksen yok, gökkuşağı rampa yok, her veri noktasına sayı basmıyoruz;
  değerler seçici doğrudan etiket + hover + tablo ikizi ile okunur.
- Izgara ve eksenler saç teli kalınlığında ve düz çizgi (kesikli değil).
"""

from __future__ import annotations

import plotly.graph_objects as go

import theme

HOVER = "<b>%{y}</b><br>%{x}<extra></extra>"


def _yatay_cubuk(etiketler, degerler, metinler, x_baslik, x_maks, yukseklik):
    fig = go.Figure(
        go.Bar(
            x=degerler,
            y=etiketler,
            orientation="h",
            marker=dict(color=theme.SERIES[0], line=dict(width=0)),
            text=metinler,
            textposition="outside",
            textfont=dict(color=theme.INK_2, size=12),
            cliponaxis=False,
            hovertemplate=HOVER,
        )
    )
    fig.update_layout(
        height=yukseklik,
        showlegend=False,
        xaxis=dict(title=dict(text=x_baslik, font=dict(color=theme.MUTED, size=12)),
                   range=[0, x_maks], showgrid=True, gridcolor=theme.GRID),
        yaxis=dict(autorange="reversed", showgrid=False),
        margin=dict(l=8, r=64, t=16, b=32),
        bargap=0.58,
    )
    return fig


def kriter_ortalamalari(kriter_ort: list[dict]):
    """Yarışma genelinde kriter bazlı ortalama — tavana göre oran.

    Kriterlerin tavanı farklı (30, 15, 10, 5) olduğu için ham puanı yan yana
    koymak yanıltır; oran karşılaştırılabilir tek ölçüdür.
    """
    etiketler = [f"{k['ad']} ({k['maks']}p)" for k in kriter_ort]
    degerler = [k.get("oran", 0) * 100 for k in kriter_ort]
    metinler = [f"%{d:.0f} · {k['ortalama']}/{k['maks']}"
                for d, k in zip(degerler, kriter_ort)]
    yukseklik = max(220, 46 * len(kriter_ort))
    return _yatay_cubuk(etiketler, degerler, metinler,
                        "Tavana göre ortalama (%)", 132, yukseklik)


def kriter_puanlari(kriterler: list[dict]):
    """Tek raporun kriter puanları — her kriterin kendi tavanı arka planda.

    Mermi (bullet) grafiği: açık gri iz kriterin tavanı, mavi dolgu alınan puan.
    Tavanlar farklı olduğu için ham puanı tek ölçekte göstermek ancak izle
    birlikte anlamlı olur.
    """
    etiketler = [k["ad"] for k in kriterler]
    tavanlar = [k["maks"] for k in kriterler]
    puanlar = [k["ai_puan"] for k in kriterler]
    metinler = [f"{k['ai_puan']:g}/{k['maks']}" for k in kriterler]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=tavanlar, y=etiketler, orientation="h", name="Tavan",
        marker=dict(color=theme.GRID, line=dict(width=0)),
        hoverinfo="skip", showlegend=False, width=0.52,
    ))
    fig.add_trace(go.Bar(
        x=puanlar, y=etiketler, orientation="h", name="Alınan puan",
        marker=dict(color=theme.SERIES[0], line=dict(width=0)),
        text=metinler, textposition="outside",
        textfont=dict(color=theme.INK_2, size=12), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>%{x} puan<extra></extra>",
        showlegend=False, width=0.30,
    ))
    fig.update_layout(
        barmode="overlay",
        height=max(230, 46 * len(kriterler)),
        xaxis=dict(title=dict(text="Puan (kriter tavanına göre)",
                              font=dict(color=theme.MUTED, size=12)),
                   range=[0, max(tavanlar) * 1.16], showgrid=True, gridcolor=theme.GRID),
        yaxis=dict(autorange="reversed", showgrid=False),
        margin=dict(l=8, r=70, t=16, b=32),
    )
    return fig


def hakem_ai_karsilastirma(satirlar: list[dict]):
    """Hakem puanı ile AI ön puanını kriter kriter yan yana gösterir.

    Kriter tavanları farklı (30, 15, 10, 5) olduğu için çubuk uzunluğu TAVANA
    GÖRE ORAN'dır; ham puan doğrudan etiket olarak yazılır. Ham puan çizilse
    "Sonuçlar 11,5" çubuğu, 30 üzerinden %38 olmasına rağmen uzun görünürdü.
    İki seri → gösterge zorunlu, ayrıca her çubuk doğrudan etiketli.
    """
    etiketler = [f"{s['ad']} ({s['maks']}p)" for s in satirlar]
    hakem_oran = [s["hakem"] / s["maks"] * 100 for s in satirlar]
    ai_oran = [s["ai"] / s["maks"] * 100 for s in satirlar]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=hakem_oran, y=etiketler, orientation="h", name="Hakem",
        marker=dict(color=theme.SERIES[0], line=dict(width=0)),
        text=[f"{s['hakem']:g}/{s['maks']}" for s in satirlar], textposition="outside",
        textfont=dict(color=theme.INK_2, size=11), cliponaxis=False,
        customdata=[[s["hakem"], s["maks"]] for s in satirlar],
        hovertemplate="<b>%{y}</b><br>Hakem: %{customdata[0]}/%{customdata[1]} "
                      "(%{x:.0f}%)<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=ai_oran, y=etiketler, orientation="h", name="AI 4. Göz",
        marker=dict(color=theme.SERIES[1], line=dict(width=0)),
        text=[f"{s['ai']:g}/{s['maks']}" for s in satirlar], textposition="outside",
        textfont=dict(color=theme.INK_2, size=11), cliponaxis=False,
        customdata=[[s["ai"], s["maks"]] for s in satirlar],
        hovertemplate="<b>%{y}</b><br>AI: %{customdata[0]}/%{customdata[1]} "
                      "(%{x:.0f}%)<extra></extra>",
    ))
    fig.update_layout(
        barmode="group",
        bargap=0.34,
        bargroupgap=0.12,
        height=max(300, 56 * len(satirlar)),
        xaxis=dict(title=dict(text="Kriter tavanına göre puan (%)",
                              font=dict(color=theme.MUTED, size=12)),
                   range=[0, 122], showgrid=True, gridcolor=theme.GRID),
        yaxis=dict(autorange="reversed", showgrid=False),
        margin=dict(l=8, r=62, t=44, b=32),
    )
    return fig


def _sapma_cubugu(etiketler, farklar, x_baslik="AI − Hakem (puan)"):
    """Ayrışan (diverging) çubuk: sıfırda nötr eksen, iki karşıt renk."""
    renkler = [theme.SERIES[0] if f >= 0 else "#d03b3b" for f in farklar]
    sinir = max(2.0, max(abs(f) for f in farklar) * 1.35)

    fig = go.Figure(go.Bar(
        x=farklar, y=etiketler, orientation="h",
        marker=dict(color=renkler, line=dict(width=0)),
        text=[f"{f:+.1f}" for f in farklar], textposition="outside",
        textfont=dict(color=theme.INK_2, size=11), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Fark: %{x:+.1f} puan<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color=theme.AXIS, width=1))
    fig.update_layout(
        height=max(260, 46 * len(etiketler)),
        showlegend=False,
        xaxis=dict(title=dict(text=x_baslik, font=dict(color=theme.MUTED, size=12)),
                   range=[-sinir, sinir], showgrid=True, gridcolor=theme.GRID),
        yaxis=dict(autorange="reversed", showgrid=False),
        margin=dict(l=8, r=52, t=16, b=32),
        bargap=0.5,
    )
    return fig


def sapma(satirlar: list[dict]):
    """Tek rapor için AI − Hakem farkı."""
    return _sapma_cubugu([s["ad"] for s in satirlar],
                         [s["ai"] - s["hakem"] for s in satirlar])


def kriter_sapmalari(satirlar: list[dict]):
    """Yarışma genelinde kriter bazlı ortalama AI − Hakem farkı."""
    return _sapma_cubugu([f"{s['ad']} ({s['maks']}p)" for s in satirlar],
                         [s["ortalama_fark"] for s in satirlar],
                         "Ortalama fark: AI − Hakem (puan)")


def uyum_trendi(trend: list[dict]):
    """Günlük AI–hakem sapması (MAE). Tek seri; düşmesi iyidir."""
    x = [_gun_etiketi(t["tarih"]) for t in trend]
    y = [t["mae"] for t in trend]
    n = [t["rapor"] for t in trend]

    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="lines+markers",
        line=dict(color=theme.SERIES[0], width=2),
        marker=dict(size=8, color=theme.SERIES[0],
                    line=dict(color=theme.SURFACE, width=2)),
        customdata=n,
        hovertemplate="<b>%{x}</b><br>Sapma: %{y:.2f} puan"
                      "<br>%{customdata} rapor<extra></extra>",
    ))
    if x:
        fig.add_annotation(x=x[-1], y=y[-1], text=f"<b>{y[-1]:.2f}</b>", showarrow=False,
                           xanchor="left", xshift=10,
                           font=dict(color=theme.INK, size=13))
    fig.update_layout(
        height=250, showlegend=False, hovermode="x unified",
        xaxis=dict(type="category", showgrid=False, linecolor=theme.AXIS),
        yaxis=dict(title=dict(text="Kriter başına ortalama sapma (puan)",
                              font=dict(color=theme.MUTED, size=12)),
                   showgrid=True, gridcolor=theme.GRID, rangemode="tozero"),
        margin=dict(l=8, r=52, t=16, b=32),
    )
    return fig


def hakem_yuku(yuku: list[dict]):
    """Hakem başına iş yükü — tamamlanan ve bekleyen üst üste.

    Yığın seçildi çünkü sorulan şey toplam yük; segmentler arasında 2px zemin
    boşluğu bırakılır, çerçeve çizilmez.
    """
    etiketler = [h["hakem"] for h in yuku]
    tamam = [h["tamamlanan"] for h in yuku]
    bekleyen = [h["bekleyen"] for h in yuku]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=tamam, y=etiketler, orientation="h", name="Tamamlanan",
        marker=dict(color=theme.SERIES[0],
                    line=dict(color=theme.SURFACE, width=2)),
        hovertemplate="<b>%{y}</b><br>Tamamlanan: %{x}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=bekleyen, y=etiketler, orientation="h", name="Bekleyen",
        marker=dict(color=theme.SERIES[1],
                    line=dict(color=theme.SURFACE, width=2)),
        text=[f"{h['atanan']}" for h in yuku], textposition="outside",
        textfont=dict(color=theme.INK_2, size=11), cliponaxis=False,
        hovertemplate="<b>%{y}</b><br>Bekleyen: %{x}<extra></extra>",
    ))
    en_cok = max((h["atanan"] for h in yuku), default=1)
    fig.update_layout(
        barmode="stack",
        height=max(250, 52 * len(yuku)),
        xaxis=dict(title=dict(text="Atanan rapor sayısı",
                              font=dict(color=theme.MUTED, size=12)),
                   range=[0, en_cok * 1.18], showgrid=True, gridcolor=theme.GRID),
        yaxis=dict(autorange="reversed", showgrid=False),
        margin=dict(l=8, r=48, t=44, b=32),
        bargap=0.42,
    )
    return fig


def durum_dagilimi(sayimlar: list[tuple[str, int]]):
    """Rapor durumlarının dağılımı — sıralı kategoriler, tek renk."""
    etiketler = [s[0] for s in sayimlar]
    degerler = [s[1] for s in sayimlar]
    maks = max(degerler) if degerler else 1
    return _yatay_cubuk(etiketler, degerler, [str(d) for d in degerler],
                        "Rapor sayısı", maks * 1.25 + 1, 230)


AYLAR = {
    "01": "Oca", "02": "Şub", "03": "Mar", "04": "Nis", "05": "May", "06": "Haz",
    "07": "Tem", "08": "Ağu", "09": "Eyl", "10": "Eki", "11": "Kas", "12": "Ara",
}


def _gun_etiketi(tarih: str) -> str:
    """'2026-08-18' -> '18 Ağu'. Eksen kategorik kalır; tarih ayrıştırması yapılmaz."""
    parcalar = tarih.split("-")
    if len(parcalar) != 3:
        return tarih
    _, ay, gun = parcalar
    return f"{int(gun)} {AYLAR.get(ay, ay)}"


def gunluk_hacim(gunluk: list[dict]):
    """Günlük analiz edilen rapor sayısı — tek seri, uç noktası etiketli."""
    x = [_gun_etiketi(g["tarih"]) for g in gunluk]
    y = [g["analiz_edilen"] for g in gunluk]

    fig = go.Figure(
        go.Scatter(
            x=x,
            y=y,
            mode="lines+markers",
            line=dict(color=theme.SERIES[0], width=2),
            marker=dict(size=8, color=theme.SERIES[0],
                        line=dict(color=theme.SURFACE, width=2)),
            hovertemplate="<b>%{x}</b><br>%{y} rapor<extra></extra>",
        )
    )
    fig.add_annotation(
        x=x[-1], y=y[-1], text=f"<b>{y[-1]}</b>", showarrow=False,
        xanchor="left", xshift=10, font=dict(color=theme.INK, size=13),
    )
    fig.update_layout(
        height=250,
        showlegend=False,
        hovermode="x unified",
        xaxis=dict(type="category", showgrid=False, linecolor=theme.AXIS),
        yaxis=dict(title=dict(text="Analiz edilen rapor", font=dict(color=theme.MUTED, size=12)),
                   showgrid=True, gridcolor=theme.GRID, rangemode="tozero"),
        margin=dict(l=8, r=48, t=16, b=32),
    )
    return fig


def kategori_uygunlugu_olcegi(skor: float):
    """Tek sayı için ölçek — sıralı mavi rampa, eşik çizgisiyle."""
    fig = go.Figure(
        go.Bar(
            x=[skor * 100],
            y=[""],
            orientation="h",
            marker=dict(color=theme.SERIES[0], line=dict(width=0)),
            text=[f"<b>%{skor * 100:.0f}</b>"],
            textposition="outside",
            textfont=dict(color=theme.INK, size=13),
            cliponaxis=False,
            hovertemplate="Kategori uyum skoru: %{x:.0f}<extra></extra>",
        )
    )
    fig.add_vline(x=60, line=dict(color=theme.STATUS["uyari"], width=2))
    fig.add_annotation(x=60, y=0.42, text="eşik 60", showarrow=False,
                       font=dict(color=theme.MUTED, size=11), xanchor="left", xshift=6)
    fig.update_layout(
        height=104,
        showlegend=False,
        xaxis=dict(range=[0, 100], showgrid=True, gridcolor=theme.GRID,
                   title=dict(text="Kategori uyum skoru (0–100)",
                              font=dict(color=theme.MUTED, size=12))),
        yaxis=dict(showticklabels=False, showgrid=False, linewidth=0),
        margin=dict(l=8, r=52, t=8, b=32),
        bargap=0.72,
    )
    return fig


def benzerlik_olcegi(oran: float):
    """İntihal / benzerlik oranı ölçeği (0-100%)."""
    yuzde = oran * 100 if oran <= 1.0 else oran
    c_iyi = theme.STATUS.get("iyi", "#16A34A")
    c_uyari = theme.STATUS.get("uyari", "#D97706")
    c_hata = theme.STATUS.get("kritik", "#DC2626")

    renk = c_hata if yuzde > 25 else (c_uyari if yuzde > 15 else c_iyi)
    fig = go.Figure(
        go.Bar(
            x=[yuzde],
            y=[""],
            orientation="h",
            marker=dict(color=renk, line=dict(width=0)),
            text=[f"<b>%{yuzde:.0f}</b>"],
            textposition="outside",
            textfont=dict(color=theme.INK, size=13),
            cliponaxis=False,
            hovertemplate="Benzerlik Oranı: %{x:.1f}%<extra></extra>",
        )
    )
    fig.add_vline(x=15, line=dict(color=c_uyari, width=2, dash="dash"))
    fig.add_annotation(x=15, y=0.42, text="Azami İntihal Eşiği (%15)", showarrow=False,
                       font=dict(color=theme.MUTED, size=11), xanchor="left", xshift=6)
    fig.update_layout(
        height=104,
        showlegend=False,
        xaxis=dict(range=[0, 100], showgrid=True, gridcolor=theme.GRID,
                   title=dict(text="İntihal ve Çapraz Benzerlik Oranı (Azami %15)",
                              font=dict(color=theme.MUTED, size=12))),
        yaxis=dict(showticklabels=False, showgrid=False, linewidth=0),
        margin=dict(l=8, r=52, t=8, b=32),
        bargap=0.72,
    )
    return fig
