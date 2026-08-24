"""Değerlendirme Yöneticisi ekranı — canlı operasyon panosu."""

from __future__ import annotations

import api_client
import charts
import components as c
import pandas as pd

DURUM_ADI = {
    "tamamlandi": "Tamamlandı",
    "hakem_bekliyor": "Hakem bekliyor",
    "ai_analiz_tamam": "AI analizi tamam",
    "kuyrukta": "Kuyrukta",
    "hatali": "Hatalı",
}
DURUM_SIRA = ["tamamlandi", "hakem_bekliyor", "ai_analiz_tamam", "kuyrukta", "hatali"]


def goster(st, yarisma_id: str) -> None:
    st.markdown("# Değerlendirme Operasyon Panosu")
    st.markdown('<div class="ts-sub">Analiz durumları, hakem tamamlama oranları ve '
                'yarışma geneli metrikler.</div>', unsafe_allow_html=True)

    tum_raporlar = api_client.raporlar(yarisma_id)

    # --- Filtre satırı: tüm grafikleri aynı dilim üzerinden çalıştırır ----
    st.markdown("---")
    f1, f2 = st.columns([2, 2])
    kategoriler = sorted({r["kategori"] for r in tum_raporlar})
    with f1:
        secili_kategoriler = st.multiselect("Kategori", kategoriler, default=kategoriler)
    with f2:
        secili_durumlar = st.multiselect(
            "Durum", [DURUM_ADI[d] for d in DURUM_SIRA],
            default=[DURUM_ADI[d] for d in DURUM_SIRA],
        )

    ters_ad = {v: k for k, v in DURUM_ADI.items()}
    raporlar = [
        r for r in tum_raporlar
        if r["kategori"] in secili_kategoriler
        and r["durum"] in {ters_ad[d] for d in secili_durumlar}
    ]

    if not raporlar:
        c.bos_durum(st, "Seçilen filtrede rapor yok", "Filtreleri genişletmeyi dene.")
        return

    import mock_data

    m = mock_data.metrikler(raporlar) if not api_client.CANLI else api_client.metrikler(yarisma_id)

    # --- Üst KPI satırı ---------------------------------------------------
    tamamlanma = int(round(m["tamamlanan"] / m["toplam"] * 100)) if m["toplam"] else 0
    kutular = st.columns(4)
    with kutular[0]:
        c.stat_tile(st, "Toplam rapor", m["toplam"], f"{len(secili_kategoriler)} kategori")
    with kutular[1]:
        c.stat_tile(st, "Tamamlanma", f"%{tamamlanma}",
                    f"{m['tamamlanan']} / {m['toplam']} rapor onaylandı")
    with kutular[2]:
        c.stat_tile(st, "Ortalama AI puanı", m["ortalama_puan"], "100 üzerinden ağırlıklı")
    with kutular[3]:
        c.stat_tile(st, "Benzerlik uyarısı", m["benzerlik_uyarilari"], "hakem incelemesi bekliyor")

    kutular_2 = st.columns(4)
    with kutular_2[0]:
        c.stat_tile(st, "Bekleyen", m["bekleyen"], "analiz veya hakem aşamasında")
    with kutular_2[1]:
        c.stat_tile(st, "Şablon uyumsuz", m["sablon_uyumsuz"], "otomatik kontrolde işaretlendi")
    with kutular_2[2]:
        c.stat_tile(st, "Dil uyumsuz", m["dil_uyumsuz"], "beklenen dilden farklı")
    with kutular_2[3]:
        c.stat_tile(st, "Hatalı", m["hatali"], "işlenemeyen dosya")

    # --- Grafikler --------------------------------------------------------
    st.markdown("## Kriter bazlı ortalama puanlar")
    st.markdown('<div class="ts-sub">Kriterlerin tavanı farklı olduğu için oran olarak '
                'gösterilir; parantez içinde ortalama puan / tavan.</div>',
                unsafe_allow_html=True)
    st.plotly_chart(charts.kriter_ortalamalari(m["kriter_ortalamalari"]),
                    width='stretch', config={"displayModeBar": False})
    c.tablo_ikizi(
        st,
        pd.DataFrame([{"Kriter": k["ad"], "Tavan": k["maks"],
                       "Ortalama puan": k["ortalama"],
                       "Oran": f"%{int(k['oran'] * 100)}"}
                      for k in m["kriter_ortalamalari"]]),
    )

    sol, sag = st.columns(2)
    with sol:
        st.markdown("## Rapor durumları")
        sayimlar = [(DURUM_ADI[d], sum(1 for r in raporlar if r["durum"] == d)) for d in DURUM_SIRA]
        st.plotly_chart(charts.durum_dagilimi(sayimlar),
                        width='stretch', config={"displayModeBar": False})
        c.tablo_ikizi(st, pd.DataFrame(sayimlar, columns=["Durum", "Rapor sayısı"]))
    with sag:
        st.markdown("## Günlük analiz hacmi")
        st.plotly_chart(charts.gunluk_hacim(m["gunluk_hacim"]),
                        width='stretch', config={"displayModeBar": False})
        c.tablo_ikizi(
            st,
            pd.DataFrame([{"Tarih": g["tarih"], "Analiz edilen": g["analiz_edilen"]}
                          for g in m["gunluk_hacim"]]),
        )

    # --- AI ↔ hakem uyumu -------------------------------------------------
    st.markdown("## AI – hakem uyumu")
    if not m.get("uyum_trendi"):
        c.bos_durum(st, "Henüz karşılaştırılabilir veri yok",
                    "Hakem puanı girilmiş rapor bulunmuyor. Uyum ölçümü, hakem "
                    "onayı verilmiş raporlar üzerinden hesaplanır.")
    else:
        st.markdown(f'<div class="ts-sub">{m["uyum_rapor_sayisi"]} onaylanmış rapor '
                    f'üzerinden hesaplanıyor. Sapma, kriter başına ortalama mutlak '
                    f'fark (MAE) — düşmesi iyidir.</div>', unsafe_allow_html=True)

        uyum_kutu = st.columns(3)
        with uyum_kutu[0]:
            c.stat_tile(st, "Ortalama sapma", m["ortalama_mae"], "kriter başına puan")
        with uyum_kutu[1]:
            c.stat_tile(st, "Karşılaştırılan rapor", m["uyum_rapor_sayisi"],
                        "hakem onayı verilmiş")
        with uyum_kutu[2]:
            sapmalar = m.get("kriter_sapmalari") or []
            if sapmalar:
                en = max(sapmalar, key=lambda x: abs(x["ortalama_fark"]))
                c.stat_tile(st, "En çok ayrışan kriter", en["ad"],
                            f"{en['ortalama_fark']:+.2f} puan (AI − hakem)")
            else:
                c.stat_tile(st, "En çok ayrışan kriter", "—", "")

        u_sol, u_sag = st.columns([1, 1])
        with u_sol:
            st.markdown("### Günlük sapma trendi")
            st.plotly_chart(charts.uyum_trendi(m["uyum_trendi"]),
                            width='stretch', config={"displayModeBar": False})
            c.tablo_ikizi(st, pd.DataFrame([
                {"Tarih": t["tarih"], "Ortalama sapma": t["mae"], "Rapor": t["rapor"]}
                for t in m["uyum_trendi"]]))
        with u_sag:
            st.markdown("### Kriter bazlı sapma")
            if m.get("kriter_sapmalari"):
                st.plotly_chart(charts.kriter_sapmalari(m["kriter_sapmalari"]),
                                width='stretch', config={"displayModeBar": False})
                c.tablo_ikizi(st, pd.DataFrame([
                    {"Kriter": x["ad"], "Tavan": x["maks"],
                     "Ortalama fark (AI−hakem)": x["ortalama_fark"],
                     "Ortalama mutlak fark": x["mutlak_fark"],
                     "Rapor": x["adet"]} for x in m["kriter_sapmalari"]]))
        st.markdown('<div class="ts-muted">Eksi değer: AI hakemden daha sert '
                    'puanlıyor. Sistematik ayrışma, o kriterin rubrik tanımının ya da '
                    'prompt\'unun kalibre edilmesi gerektiğini gösterir.</div>',
                    unsafe_allow_html=True)

    # --- Hakem yükü -------------------------------------------------------
    st.markdown("## Hakem yükü")
    if not m.get("hakem_yuku"):
        c.bos_durum(st, "Atama yok", "Raporlar henüz hakemlere atanmamış.")
    else:
        yuku = m["hakem_yuku"]
        en_yuklu = max(yuku, key=lambda h: h["bekleyen"])
        y_kutu = st.columns(3)
        with y_kutu[0]:
            c.stat_tile(st, "Hakem sayısı", len(yuku), "atama yapılmış")
        with y_kutu[1]:
            c.stat_tile(st, "En yüklü hakem", en_yuklu["hakem"],
                        f"{en_yuklu['bekleyen']} rapor bekliyor")
        with y_kutu[2]:
            ortalama = sum(h["atanan"] for h in yuku) / len(yuku)
            c.stat_tile(st, "Hakem başına ortalama", f"{ortalama:.1f}", "atanan rapor")

        st.plotly_chart(charts.hakem_yuku(yuku),
                        width='stretch', config={"displayModeBar": False})
        c.tablo_ikizi(st, pd.DataFrame([
            {"Hakem": h["hakem"], "Atanan": h["atanan"], "Tamamlanan": h["tamamlanan"],
             "Bekleyen": h["bekleyen"],
             "Tamamlanma": f"%{h['tamamlanan'] / h['atanan'] * 100:.0f}" if h["atanan"] else "—"}
            for h in yuku]))

    # --- Benzerlik uyarı listesi -----------------------------------------
    st.markdown("## Benzerlik uyarıları")
    satirlar = []
    for r in raporlar:
        for b in r["benzerlik"]:
            satirlar.append({
                "Rapor": r["rapor_id"],
                "Proje": r["proje_adi"],
                "Benzeyen rapor": b["rapor_id"],
                "Benzerlik": f"%{int(b['skor'] * 100)}",
                "Eşleşen bölümler": ", ".join(b["eslesen_bolumler"]),
            })
    if satirlar:
        st.dataframe(pd.DataFrame(satirlar), width='stretch', hide_index=True)
        st.markdown('<div class="ts-muted">Bu liste bir intihal tespiti değildir; '
                    'eşiği geçen benzerlikler hakem incelemesi için işaretlenir.</div>',
                    unsafe_allow_html=True)
    else:
        c.bos_durum(st, "Uyarı yok", "Seçilen dilimde eşiği geçen benzerlik bulunmadı.")

    # --- Rapor tablosu ----------------------------------------------------
    st.markdown("## Tüm raporlar")
    st.dataframe(
        pd.DataFrame([{
            "Rapor": r["rapor_id"],
            "Proje": r["proje_adi"],
            "Takım": r["takim_adi"],
            "Kategori": r["kategori"],
            "Durum": DURUM_ADI[r["durum"]],
            "Hakem": r.get("atanan_hakem") or "—",
            "Şablon": "Uygun" if r["kontroller"]["sablon"]["uygun"] else "Uyumsuz",
            "Eksik başlık": len(r["kontroller"]["basliklar"]["eksik"]),
            "Kategori uyumu": f"%{int(r['kategori_uygunlugu']['skor'] * 100)}",
        } for r in raporlar]),
        width='stretch',
        hide_index=True,
    )
