"""Değerlendirme Yöneticisi ekranı — canlı operasyon panosu."""

from __future__ import annotations

import api_client
import charts
import components as c
import pandas as pd
from i18n import t

DURUM_ADI_TR = {
    "tamamlandi": "Tamamlandı",
    "hakem_bekliyor": "Hakem bekliyor",
    "ai_analiz_tamam": "AI analizi tamam",
    "kuyrukta": "Kuyrukta",
    "hatali": "Hatalı",
}
DURUM_ADI_EN = {
    "tamamlandi": "Completed",
    "hakem_bekliyor": "Awaiting referee",
    "ai_analiz_tamam": "AI analysis done",
    "kuyrukta": "In queue",
    "hatali": "Errored",
}
DURUM_SIRA = ["tamamlandi", "hakem_bekliyor", "ai_analiz_tamam", "kuyrukta", "hatali"]


def goster(st, yarisma_id: str) -> None:
    lang = st.session_state.get("lang", "tr")
    DURUM_ADI = DURUM_ADI_TR if lang == "tr" else DURUM_ADI_EN

    st.markdown(f"# {t('dash_title', lang)}")
    st.markdown(
        f'<div class="ts-sub">{t("dash_sub", lang)}</div>',
        unsafe_allow_html=True
    )

    tum_raporlar = api_client.raporlar(yarisma_id)
    if not tum_raporlar:
        c.bos_durum(st, "Sistemde Henüz Kayıtlı Rapor Bulunmamaktadır", "Yarışmacılar rapor yükledikçe veya hakem atamaları yapıldıkça burada anlık olarak listelenecektir.")
        return

    # --- Filtre satırı ----------------------------------------------------
    st.markdown("---")
    f1, f2 = st.columns([2, 2])
    kategoriler = sorted(list({r.get("kategori", "Genel") for r in tum_raporlar}))
    with f1:
        secili_kategoriler = st.multiselect(t("dash_kategori", lang), kategoriler, default=kategoriler, key=f"dash_kat_sel_{yarisma_id}")
    with f2:
        secili_durumlar = st.multiselect(
            t("dash_durum", lang), [DURUM_ADI[d] for d in DURUM_SIRA],
            default=[DURUM_ADI[d] for d in DURUM_SIRA],
            key=f"dash_durum_sel_{yarisma_id}"
        )

    ters_ad = {v: k for k, v in DURUM_ADI.items()}
    aktif_kat = set(secili_kategoriler) if secili_kategoriler else set(kategoriler)
    aktif_durum = {ters_ad[d] for d in secili_durumlar} if secili_durumlar else set(DURUM_SIRA)

    raporlar = [
        r for r in tum_raporlar
        if r.get("kategori") in aktif_kat
        and r.get("durum") in aktif_durum
    ]

    if not raporlar:
        c.bos_durum(st, t("dash_filtre_rapor_yok", lang), t("dash_filtre_genislet", lang))
        return

    # Gerçek Veritabanı Metrik Hesaplaması
    toplam = len(raporlar)
    tamamlanan = sum(1 for r in raporlar if r.get("durum") == "tamamlandi")
    bekleyen = toplam - tamamlanan
    puanlar = [float(r["puan"]) for r in raporlar if r.get("puan") is not None and float(r.get("puan", 0)) > 0]
    ort_puan = round(sum(puanlar) / len(puanlar), 1) if puanlar else 0.0

    # Kriter Ortalamaları
    kr_toplam = {}
    kr_adet = {}
    kr_maks = {}
    for r in raporlar:
        for kr in r.get("kriterler", []):
            k_ad = kr["ad"]
            p = float(kr.get("hakem_puan") or kr.get("ai_puan") or 0.0)
            kr_toplam[k_ad] = kr_toplam.get(k_ad, 0.0) + p
            kr_adet[k_ad] = kr_adet.get(k_ad, 0) + 1
            kr_maks[k_ad] = float(kr.get("maks", 10.0))

    kriter_ortalamalari = []
    for k_ad, t_puan in kr_toplam.items():
        c_cnt = max(kr_adet.get(k_ad, 1), 1)
        maks_p = kr_maks.get(k_ad, 10.0)
        ort = round(t_puan / c_cnt, 1)
        oran = round(ort / maks_p, 2) if maks_p else 0.0
        kriter_ortalamalari.append({
            "ad": k_ad,
            "maks": maks_p,
            "ortalama": ort,
            "oran": min(max(oran, 0.0), 1.0)
        })

    # Günlük Hacim
    gun_map = {}
    for r in raporlar:
        t_str = str(r.get("yuklenme_tarihi", "2026-08-26"))[:10]
        gun_map[t_str] = gun_map.get(t_str, 0) + 1
    gunluk_hacim = [{"tarih": k, "analiz_edilen": v} for k, v in sorted(gun_map.items())]
    if not gunluk_hacim:
        gunluk_hacim = [{"tarih": "2026-08-26", "analiz_edilen": toplam}]

    # Hakem Yükü
    hakem_map = {}
    for r in raporlar:
        h_id = r.get("atanan_hakem") or "usr_hakem_ef6def"
        if h_id not in hakem_map:
            hakem_map[h_id] = {"hakem": h_id, "atanan": 0, "tamamlanan": 0, "bekleyen": 0}
        hakem_map[h_id]["atanan"] += 1
        if r.get("durum") == "tamamlandi":
            hakem_map[h_id]["tamamlanan"] += 1
        else:
            hakem_map[h_id]["bekleyen"] += 1
    hakem_yuku = list(hakem_map.values())

    m = {
        "toplam": toplam,
        "tamamlanan": tamamlanan,
        "bekleyen": bekleyen,
        "ortalama_puan": ort_puan,
        "benzerlik_uyarilari": sum(len(r.get("benzerlik", [])) for r in raporlar),
        "sablon_uyumsuz": 0,
        "dil_uyumsuz": 0,
        "hatali": sum(1 for r in raporlar if r.get("durum") == "hatali"),
        "kriter_ortalamalari": kriter_ortalamalari,
        "gunluk_hacim": gunluk_hacim,
        "hakem_yuku": hakem_yuku,
        "uyum_trendi": [],
        "kriter_sapmalari": []
    }

    # --- Üst KPI satırı ---------------------------------------------------
    tamamlanma = int(round(m["tamamlanan"] / m["toplam"] * 100)) if m["toplam"] else 0
    kutular = st.columns(4)
    with kutular[0]:
        c.stat_tile(st, t("dash_toplam_rapor", lang), m["toplam"], f"{len(aktif_kat)} {t('dash_kategori_label', lang)}")
    with kutular[1]:
        c.stat_tile(st, t("dash_tamamlanma", lang), f"%{tamamlanma}",
                    f"{m['tamamlanan']} / {m['toplam']} {t('dash_rapor_onaylandi', lang)}")
    with kutular[2]:
        c.stat_tile(st, t("dash_ort_ai_puan", lang), m["ortalama_puan"], t("dash_100_uzerinden", lang))
    with kutular[3]:
        c.stat_tile(st, t("dash_benzerlik_uyarisi", lang), m["benzerlik_uyarilari"], t("dash_hakem_incelemesi", lang))

    kutular_2 = st.columns(4)
    with kutular_2[0]:
        c.stat_tile(st, t("dash_bekleyen", lang), m["bekleyen"], t("dash_analiz_hakem", lang))
    with kutular_2[1]:
        c.stat_tile(st, t("dash_sablon_uyumsuz", lang), m["sablon_uyumsuz"], t("dash_otomatik_isaretlendi", lang))
    with kutular_2[2]:
        c.stat_tile(st, t("dash_dil_uyumsuz", lang), m["dil_uyumsuz"], t("dash_beklenen_dilden", lang))
    with kutular_2[3]:
        c.stat_tile(st, t("dash_hatali", lang), m["hatali"], t("dash_islemeyen", lang))

    # --- Grafikler --------------------------------------------------------
    st.markdown(f"## {t('dash_kriter_ort', lang)}")
    st.markdown(
        f'<div class="ts-sub">{t("dash_kriter_sub", lang)}</div>',
        unsafe_allow_html=True
    )
    st.plotly_chart(charts.kriter_ortalamalari(m["kriter_ortalamalari"]),
                    width='stretch', config={"displayModeBar": False})
    c.tablo_ikizi(
        st,
        pd.DataFrame([{
            t("dash_kriter", lang): k["ad"],
            t("dash_tavan", lang): k["maks"],
            t("dash_ort_puan", lang): k["ortalama"],
            t("dash_oran", lang): f"%{int(k['oran'] * 100)}"
        } for k in m["kriter_ortalamalari"]]),
    )

    sol, sag = st.columns(2)
    with sol:
        st.markdown(f"## {t('dash_rapor_durumlar', lang)}")
        sayimlar = [(DURUM_ADI[d], sum(1 for r in raporlar if r["durum"] == d)) for d in DURUM_SIRA]
        st.plotly_chart(charts.durum_dagilimi(sayimlar),
                        width='stretch', config={"displayModeBar": False})
        c.tablo_ikizi(st, pd.DataFrame(sayimlar, columns=[t("dash_durum_col", lang), t("dash_rapor_sayisi", lang)]))
    with sag:
        st.markdown(f"## {t('dash_gunluk_hacim', lang)}")
        st.plotly_chart(charts.gunluk_hacim(m["gunluk_hacim"]),
                        width='stretch', config={"displayModeBar": False})
        c.tablo_ikizi(
            st,
            pd.DataFrame([{
                t("dash_tarih", lang): g["tarih"],
                t("dash_analiz_edilen", lang): g["analiz_edilen"]
            } for g in m["gunluk_hacim"]]),
        )

    # --- AI ↔ hakem uyumu -------------------------------------------------
    st.markdown(f"## {t('dash_ai_hakem_uyumu', lang)}")
    if not m.get("uyum_trendi"):
        c.bos_durum(st, t("dash_veri_yok", lang), t("dash_veri_yok_sub", lang))
    else:
        st.markdown(
            f'<div class="ts-sub">{m["uyum_rapor_sayisi"]} {t("dash_hakem_onayi", lang)}.</div>',
            unsafe_allow_html=True
        )

        uyum_kutu = st.columns(3)
        with uyum_kutu[0]:
            c.stat_tile(st, t("dash_ort_sapma", lang), m["ortalama_mae"], t("dash_kriter_basi", lang))
        with uyum_kutu[1]:
            c.stat_tile(st, t("dash_karsilastirilan_rapor", lang), m["uyum_rapor_sayisi"],
                        t("dash_hakem_onayi", lang))
        with uyum_kutu[2]:
            sapmalar = m.get("kriter_sapmalari") or []
            if sapmalar:
                en = max(sapmalar, key=lambda x: abs(x["ortalama_fark"]))
                c.stat_tile(st, t("dash_en_cok_ayrisan", lang), en["ad"],
                            f"{en['ortalama_fark']:+.2f} {t('dash_ai_hakem_fark', lang)}")
            else:
                c.stat_tile(st, t("dash_en_cok_ayrisan", lang), "—", "")

        u_sol, u_sag = st.columns([1, 1])
        with u_sol:
            st.markdown(f"### {t('dash_gunluk_sapma', lang)}")
            st.plotly_chart(charts.uyum_trendi(m["uyum_trendi"]),
                            width='stretch', config={"displayModeBar": False})
            c.tablo_ikizi(st, pd.DataFrame([
                {
                    t("dash_tarih", lang): t_["tarih"],
                    t("dash_ort_sapma", lang): t_["mae"],
                    t("dash_rapor", lang): t_["rapor"]
                }
                for t_ in m["uyum_trendi"]]))
        with u_sag:
            st.markdown(f"### {t('dash_kriter_sapma', lang)}")
            if m.get("kriter_sapmalari"):
                st.plotly_chart(charts.kriter_sapmalari(m["kriter_sapmalari"]),
                                width='stretch', config={"displayModeBar": False})
                c.tablo_ikizi(st, pd.DataFrame([
                    {
                        t("dash_kriter", lang): x["ad"],
                        t("dash_tavan", lang): x["maks"],
                        "AI−Hakem": x["ortalama_fark"],
                        "MAE": x["mutlak_fark"],
                        t("dash_rapor", lang): x["adet"]
                    } for x in m["kriter_sapmalari"]]))

    # --- Hakem yükü -------------------------------------------------------
    st.markdown(f"## {t('dash_hakem_yuku', lang)}")
    if not m.get("hakem_yuku"):
        c.bos_durum(st, t("dash_atama_yok", lang), t("dash_atama_yok_sub", lang))
    else:
        yuku = m["hakem_yuku"]
        en_yuklu = max(yuku, key=lambda h: h["bekleyen"])
        y_kutu = st.columns(3)
        with y_kutu[0]:
            c.stat_tile(st, t("dash_hakem_sayisi", lang), len(yuku), t("dash_atama_yapilmis", lang))
        with y_kutu[1]:
            c.stat_tile(st, t("dash_en_yuklu", lang), en_yuklu["hakem"],
                        f"{en_yuklu['bekleyen']} {t('dash_rapor_bekliyor', lang)}")
        with y_kutu[2]:
            ortalama = sum(h["atanan"] for h in yuku) / len(yuku)
            c.stat_tile(st, t("dash_hbas_ort", lang), f"{ortalama:.1f}", t("dash_atanan_rapor", lang))

        st.plotly_chart(charts.hakem_yuku(yuku),
                        width='stretch', config={"displayModeBar": False})
        c.tablo_ikizi(st, pd.DataFrame([
            {
                t("dash_hakem", lang): h["hakem"],
                t("dash_atanan", lang): h["atanan"],
                t("dash_tamamlanan", lang): h["tamamlanan"],
                t("dash_bekleyen", lang): h["bekleyen"],
                t("dash_tamamlanma_yuz", lang): f"%{h['tamamlanan'] / h['atanan'] * 100:.0f}" if h["atanan"] else "—"
            }
            for h in yuku]))

    # --- Benzerlik uyarı listesi -----------------------------------------
    st.markdown(f"## {t('dash_benzerlik_uyarilari', lang)}")
    satirlar = []
    for r in raporlar:
        for b in r["benzerlik"]:
            satirlar.append({
                t("dash_rapor", lang): r["rapor_id"],
                t("dash_proje", lang): r["proje_adi"],
                t("dash_benzeyen", lang): b["rapor_id"],
                t("dash_benzerlik", lang): f"%{int(b['skor'] * 100)}",
                t("dash_eslesen", lang): ", ".join(b["eslesen_bolumler"]),
            })
    if satirlar:
        st.dataframe(pd.DataFrame(satirlar), width='stretch', hide_index=True)
        st.markdown(
            f'<div class="ts-muted">{t("dash_intihal_not", lang)}</div>',
            unsafe_allow_html=True
        )
    else:
        c.bos_durum(st, t("dash_uyari_yok", lang), t("dash_uyari_yok_sub", lang))

    # --- Rapor tablosu ----------------------------------------------------
    st.markdown(f"## {t('dash_tum_raporlar', lang)}")
    st.dataframe(
        pd.DataFrame([{
            t("dash_rapor", lang): r["rapor_id"],
            t("dash_proje", lang): r["proje_adi"],
            t("dash_takim", lang): r["takim_adi"],
            t("dash_kategori", lang): r["kategori"],
            t("dash_durum_col", lang): DURUM_ADI[r["durum"]],
            t("dash_hakem_col", lang): r.get("atanan_hakem") or "—",
            t("dash_sablon", lang): t("dash_uygun", lang) if r["kontroller"]["sablon"]["uygun"] else t("dash_uyumsuz", lang),
            t("dash_eksik_baslik", lang): len(r["kontroller"]["basliklar"]["eksik"]),
            t("dash_kat_uyumu", lang): f"%{int(r['kategori_uygunlugu']['skor'] * 100)}",
        } for r in raporlar]),
        width='stretch',
        hide_index=True,
    )
