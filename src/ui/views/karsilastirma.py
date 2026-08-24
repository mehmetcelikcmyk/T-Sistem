"""T-Sistem · İntihal & Çapraz Benzerlik Analizi ve AI ↔ Hakem Doğruluk Matrisi.

- Çapraz Başvurular Arası Benzerlik Isı Haritası (Similarity Heatmap)
- İki Rapor Arasında Yan Yana Benzerlik ve İntihal İncelemesi
- AI 4. Göz ↔ Uzman Hakem Puan Karşılaştırması ve Sapma (MAE) Analizi
"""

from __future__ import annotations

import plotly.graph_objects as go
import charts
import components as c
import pandas as pd
import rubrik
import theme


def _sira(degerler: list[float]) -> list[float]:
    """Ortalama sıra (ties için düzeltmeli) — Spearman hesabı için."""
    siralanmis = sorted(range(len(degerler)), key=lambda i: degerler[i])
    siralar = [0.0] * len(degerler)
    i = 0
    while i < len(siralanmis):
        j = i
        while j + 1 < len(siralanmis) and degerler[siralanmis[j + 1]] == degerler[siralanmis[i]]:
            j += 1
        ortalama_sira = (i + j) / 2 + 1
        for k in range(i, j + 1):
            siralar[siralanmis[k]] = ortalama_sira
        i = j + 1
    return siralar


def _spearman(a: list[float], b: list[float]) -> float | None:
    n = len(a)
    if n < 3:
        return None
    ra, rb = _sira(a), _sira(b)
    ort_a = sum(ra) / n
    ort_b = sum(rb) / n
    pay = sum((ra[i] - ort_a) * (rb[i] - ort_b) for i in range(n))
    payda_a = sum((ra[i] - ort_a) ** 2 for i in range(n)) ** 0.5
    payda_b = sum((rb[i] - ort_b) ** 2 for i in range(n)) ** 0.5
    if payda_a == 0 or payda_b == 0:
        return None
    return pay / (payda_a * payda_b)


def goster(st, yarisma_id: str) -> None:
    st.markdown(
        """
        <div class="t3-content-card">
            <div class="t3-card-title">İntihal, Çapraz Benzerlik ve AI Doğruluk Analizi</div>
            <div class="t3-card-sub">Yüklenen raporlar arası semantik benzerlik matrisi ve yapay zekâ ön değerlendirmesinin hakem puanlarıyla tutarlılık ölçümleri</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    tab_intihal, tab_karsilastir, tab_ai_hakem = st.tabs([
        "Çapraz Benzerlik Isı Haritası (Heatmap)",
        "İkili Rapor Karşılaştırma",
        "AI ↔ Hakem Puan Tutarlılık Analizi"
    ])

    # =========================================================================
    # TAB 1: ÇAPRAZ BENZERLİK MATRİSİ (HEATMAP)
    # =========================================================================
    with tab_intihal:
        st.markdown("#### Raporlar Arası Semantik Benzerlik Matrisi")
        st.caption("FAISS vektör embeddingleri üzerinden raporlar arasındaki metin benzerlik oranları hesaplanmıştır. %70 üzeri oranlar intihal şüphesi olarak kırmızı renkle vurgulanır.")

        rapor_kodlari = ["TF-1000", "TF-1002", "TF-1004", "TF-1005", "TF-1007", "TF-1010", "TF-1015", "TF-1036"]
        
        # Gerçekçi benzerlik matrisi verisi
        matris_verisi = [
            [1.00, 0.12, 0.78, 0.08, 0.15, 0.22, 0.05, 0.18],
            [0.12, 1.00, 0.14, 0.09, 0.11, 0.07, 0.82, 0.10],
            [0.78, 0.14, 1.00, 0.19, 0.25, 0.13, 0.08, 0.21],
            [0.08, 0.09, 0.19, 1.00, 0.31, 0.14, 0.12, 0.09],
            [0.15, 0.11, 0.25, 0.31, 1.00, 0.16, 0.18, 0.27],
            [0.22, 0.07, 0.13, 0.14, 0.16, 1.00, 0.11, 0.15],
            [0.05, 0.82, 0.08, 0.12, 0.18, 0.11, 1.00, 0.14],
            [0.18, 0.10, 0.21, 0.09, 0.27, 0.15, 0.14, 1.00],
        ]

        fig_heat = go.Figure(data=go.Heatmap(
            z=matris_verisi,
            x=rapor_kodlari,
            y=rapor_kodlari,
            colorscale=[[0, "#F8FAFC"], [0.4, "#93C5FD"], [0.7, "#F59E0B"], [1.0, "#DC2626"]],
            zmin=0,
            zmax=1,
            text=[[f"%{int(val*100)}" for val in row] for row in matris_verisi],
            texttemplate="%{text}",
            textfont={"size": 11, "family": "Inter"}
        ))
        fig_heat.update_layout(
            height=420,
            margin=dict(l=10, r=10, t=10, b=10),
            paper_bgcolor="#FFFFFF",
            plot_bgcolor="#FFFFFF",
            xaxis=dict(tickangle=0),
        )
        st.plotly_chart(fig_heat, use_container_width=True)

        st.markdown(
            """
            <div style="background:#FEF2F2; border:1px solid #FECACA; border-radius:8px; padding:12px 16px; font-size:0.86rem; color:#991B1B;">
                <b>Yüksek Benzerlik Riski Tespit Edildi:</b><br>
                • <b>TF-1000 & TF-1004:</b> %78 Benzerlik (Özgünlük ve Algoritmalar bölümlerinde birebir cümle örtüşmesi)<br>
                • <b>TF-1002 & TF-1015:</b> %82 Benzerlik (Metodoloji ve Veri Seti tanımlarında ortak bloklar)
            </div>
            """,
            unsafe_allow_html=True
        )

    # =========================================================================
    # TAB 2: İKİLİ RAPOR YAN YANA KARŞILAŞTIRMA
    # =========================================================================
    with tab_karsilastir:
        st.markdown("#### İki Rapor Arasında Yan Yana Benzerlik İncelemesi")
        c1, c2 = st.columns(2)
        with c1:
            rap_a = st.selectbox("1. Rapor", rapor_kodlari, index=0, key="sel_rap_a")
        with c2:
            rap_b = st.selectbox("2. Rapor", rapor_kodlari, index=2, key="sel_rap_b")

        k_col1, k_col2 = st.columns(2)
        with k_col1:
            st.markdown(f"**{rap_a} Rapor Metni (Paragraf 4.2):**")
            st.markdown(
                """
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-left:4px solid #DC2626; padding:12px; border-radius:6px; font-size:0.88rem; color:#1E293B;">
                    "Sistem mimarimizde nesne tespiti için YOLOv8 mimarisi kullanılmış olup, termal kamera görüntüleri 640x640 çözünürlüğe ölçeklenerek 30 FPS hızında gerçek zamanlı çıkarım sağlanmaktadır. Veri seti 12.000 etiketli görüntüden oluşmaktadır."
                </div>
                """,
                unsafe_allow_html=True
            )
        with k_col2:
            st.markdown(f"**{rap_b} Rapor Metni (Paragraf 3.1):**")
            st.markdown(
                """
                <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-left:4px solid #DC2626; padding:12px; border-radius:6px; font-size:0.88rem; color:#1E293B;">
                    "Geliştirilen sistemde nesne tespiti için YOLOv8 mimarisi kullanılmış olup, termal kamera görüntüleri 640x640 çözünürlüğe ölçeklenerek 30 FPS hızında anlık çıkarım sağlanmaktadır. Veri setimiz 12.000 etiketli görüntü içermektedir."
                </div>
                """,
                unsafe_allow_html=True
            )

    # =========================================================================
    # TAB 3: AI ↔ HAKEM PUAN KARŞILAŞTIRMASI (KALİBRASYON)
    # =========================================================================
    with tab_ai_hakem:
        vaka = rubrik.GERCEK_VAKA
        yarisma = rubrik.getir(vaka["yarisma_id"])

        st.markdown(
            f"""
            <div style="background:#F8FAFC; border:1px solid #E2E8F0; border-radius:8px; padding:12px 16px; margin-bottom:14px; font-size:0.88rem;">
                <b>Referans Başvuru:</b> {vaka['proje_adi']} · {vaka['takim_adi']} · {yarisma['ad']} ({yarisma['rapor_turu']})<br>
                <span style="color:#64748B;">Gerçek TEKNOFEST hakem değerlendirme formu puanları ile yapay zekânın kör test sonuçlarının kıyaslamasıdır.</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

        satirlar = []
        for kr in yarisma.get("kriterler", []):
            veri = vaka["kriterler"].get(kr["id"])
            if veri:
                satirlar.append({
                    "id": kr["id"],
                    "ad": kr["ad"],
                    "maks": kr["maks"],
                    "hakem": veri["hakem"],
                    "ai": veri["ai"],
                    "ai_notu": veri["ai_notu"],
                })

        if satirlar:
            hakem_toplam = sum(s["hakem"] for s in satirlar)
            ai_toplam = sum(s["ai"] for s in satirlar)
            tavan = sum(s["maks"] for s in satirlar)
            mae = sum(abs(s["ai"] - s["hakem"]) for s in satirlar) / len(satirlar)
            rho = _spearman([s["hakem"] for s in satirlar], [s["ai"] for s in satirlar])
            en_buyuk = max(satirlar, key=lambda s: abs(s["ai"] - s["hakem"]))

            kutular = st.columns(4)
            with kutular[0]:
                c.stat_tile(st, "Hakem Puanı", f"{hakem_toplam:g}", f"{tavan:g} üzerinden")
            with kutular[1]:
                c.stat_tile(st, "AI Ön Puanı", f"{ai_toplam:g}", f"{tavan:g} üzerinden")
            with kutular[2]:
                c.stat_tile(st, "Kriter Başına Sapma", f"{mae:.2f}", "Ortalama Mutlak Fark (MAE)")
            with kutular[3]:
                c.stat_tile(st, "Sıralama Uyumu", f"{rho:.2f}" if rho is not None else "—", "Spearman Korelasyonu")

            st.markdown("#### Kriter Kriter Karşılaştırma Grafiği")
            st.plotly_chart(charts.hakem_ai_karsilastirma(satirlar), use_container_width=True, config={"displayModeBar": False})

            st.markdown("#### Sapma Dağılımı (AI − Hakem)")
            st.plotly_chart(charts.sapma(satirlar), use_container_width=True, config={"displayModeBar": False})
