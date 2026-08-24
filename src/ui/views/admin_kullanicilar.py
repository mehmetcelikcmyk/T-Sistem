"""T-Sistem · Kullanıcı ve Yetki Yönetim Paneli (Admin).

Yöneticinin yeni Hakem, Yarışmacı ve Yarışma Yöneticisi profilleri tanımlamasını,
durumlarını değiştirmesini ve yetkilendirmesini sağlar.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from auth_service import auth_service


def render() -> None:
    """Admin Kullanıcı Yönetimi arayüzünü render eder."""
    
    st.markdown(
        """
        <div style="margin-bottom: 20px;">
            <div style="font-size: 1.45rem; font-weight: 750; color: #0F172A;">Kullanıcı ve Rol Yönetim Paneli</div>
            <div style="font-size: 0.90rem; color: #64748B; margin-top: 2px;">
                Sistem kullanıcılarını görüntüleyin, yetkilendirin ve yeni değerlendirici profilleri tanımlayın.
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    kullanicilar = auth_service.get_all_users()
    toplam_sayi = len(kullanicilar)
    hakem_sayisi = len([u for u in kullanicilar if u.get("role") == "hakem"])
    yarismaci_sayisi = len([u for u in kullanicilar if u.get("role") == "yarismaci"])
    yonetici_sayisi = len([u for u in kullanicilar if u.get("role") in ("admin", "yonetici")])

    # Metrik Kartları
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Toplam Kullanıcı</div>
                <div class="ts-metric-val">{toplam_sayi}</div>
                <div class="ts-metric-sub">Kayıtlı Profil</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Hakem / Jüri</div>
                <div class="ts-metric-val">{hakem_sayisi}</div>
                <div class="ts-metric-sub">Değerlendirici</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Yarışmacı</div>
                <div class="ts-metric-val">{yarismaci_sayisi}</div>
                <div class="ts-metric-sub">Takım / Bireysel</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f"""
            <div class="ts-metric-box">
                <div class="ts-metric-label">Yönetici</div>
                <div class="ts-metric-val">{yonetici_sayisi}</div>
                <div class="ts-metric-sub">İcra & Süpervizör</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<br>", unsafe_allow_html=True)

    tab_liste, tab_yeni = st.tabs(["Kullanıcı Listesi ve Durum", "Yeni Kullanıcı Profili Ekle"])

    # --- KULLANICI LİSTESİ ---
    with tab_liste:
        if not kullanicilar:
            st.info("Sistemde henüz kayıtlı kullanıcı bulunmuyor.")
        else:
            tablo_verisi = []
            for u in kullanicilar:
                tablo_verisi.append({
                    "Kullanıcı ID": u["user_id"],
                    "Ad Soyad": u["name"],
                    "E-Posta": u["email"],
                    "Rol": u["role"].upper(),
                    "Kurum": u["institution"] or "Belirtilmedi",
                    "Durum": u["status"].upper(),
                    "Kayıt Tarihi": u["created_at"][:10] if u.get("created_at") else "-",
                })
            
            df = pd.DataFrame(tablo_verisi)
            st.dataframe(df, use_container_width=True, hide_index=True)

            st.markdown("---")
            st.markdown("#### Kullanıcı Bilgilerini Düzenleme ve Silme")
            
            kullanici_secenekleri = {f"{u['name']} ({u['email']}) · [{u['role'].upper()}]": u for u in kullanicilar}
            secilen_etiket = st.selectbox("Düzenlenecek / Silinecek Kullanıcıyı Seçiniz", list(kullanici_secenekleri.keys()))
            
            if secilen_etiket:
                secilen_u = kullanici_secenekleri[secilen_etiket]
                with st.container(border=True):
                    st.markdown(f"**Profil Düzenle:** `{secilen_u['user_id']}`")
                    
                    e_col1, e_col2 = st.columns(2)
                    with e_col1:
                        edit_ad = st.text_input("Ad Soyad", value=secilen_u.get("name", ""), key=f"edit_name_{secilen_u['user_id']}")
                        edit_email = st.text_input("E-Posta Adresi", value=secilen_u.get("email", ""), key=f"edit_email_{secilen_u['user_id']}")
                        edit_kurum = st.text_input("Kurum / Bölüm / Uzmanlık", value=secilen_u.get("institution", ""), key=f"edit_inst_{secilen_u['user_id']}")
                    with e_col2:
                        edit_rol = st.selectbox(
                            "Sistem Rolü",
                            ["hakem", "yarismaci", "yonetici", "admin"],
                            index=["hakem", "yarismaci", "yonetici", "admin"].index(secilen_u["role"]) if secilen_u["role"] in ["hakem", "yarismaci", "yonetici", "admin"] else 1,
                            format_func=lambda x: {
                                "hakem": "Hakem / Jüri Değerlendiricisi",
                                "yonetici": "Yarışma Yöneticisi",
                                "yarismaci": "Yarışmacı / Takım Temsilcisi",
                                "admin": "Sistem Yöneticisi (Admin)"
                            }.get(x, x),
                            key=f"edit_role_{secilen_u['user_id']}"
                        )
                        edit_durum = st.selectbox(
                            "Hesap Durumu",
                            ["aktif", "pasif"],
                            index=0 if secilen_u.get("status") == "aktif" else 1,
                            format_func=lambda x: "Aktif (Giriş Yapabilir)" if x == "aktif" else "Pasif (Giriş Engellendi)",
                            key=f"edit_status_{secilen_u['user_id']}"
                        )
                        edit_pass = st.text_input("Yeni Şifre Belirle (Değiştirmek istemiyorsanız boş bırakın)", type="password", placeholder="Yeni şifre", key=f"edit_pass_{secilen_u['user_id']}")

                    st.markdown("<hr style='margin:12px 0; border-color:#E2E8F0;'>", unsafe_allow_html=True)
                    
                    b_col1, b_col2 = st.columns([3, 1])
                    with b_col1:
                        if st.button("💾 Değişiklikleri Veritabanına Kaydet", type="primary", use_container_width=True, key=f"btn_save_{secilen_u['user_id']}"):
                            basari, msg = auth_service.update_user_by_admin(
                                user_id=secilen_u["user_id"],
                                name=edit_ad,
                                email=edit_email,
                                role=edit_rol,
                                status=edit_durum,
                                institution=edit_kurum,
                                new_password=edit_pass if edit_pass.strip() else None
                            )
                            if basari:
                                st.success(msg)
                                st.rerun()
                            else:
                                st.error(msg)

                    with b_col2:
                        if secilen_u["email"] != "admin@tsistem.org":
                            if st.button("🗑️ Kullanıcıyı Sil", use_container_width=True, key=f"btn_del_{secilen_u['user_id']}"):
                                silindi = auth_service.delete_user(secilen_u["user_id"])
                                if silindi:
                                    st.warning(f"'{secilen_u['name']}' kullanıcısı veritabanından tamamen silindi.")
                                    st.rerun()
                                else:
                                    st.error("Kullanıcı silinirken bir hata oluştu.")
                        else:
                            st.caption("🔒 Ana yönetici silinemez.")

    # --- YENİ KULLANICI EKLEME ---
    with tab_yeni:
        st.markdown("##### Yeni Değerlendirici veya Yarışmacı Tanımla")
        with st.form("form_yeni_kullanici", clear_on_submit=True):
            f_col1, f_col2 = st.columns(2)
            with f_col1:
                ad = st.text_input("Ad Soyad", placeholder="Prof. Dr. Ayşe Demir")
                email = st.text_input("Kurumsal E-Posta", placeholder="ayse.demir@universite.edu.tr")
                sifre = st.text_input("Geçici Şifre", type="password", placeholder="En az 6 karakter")

            with f_col2:
                rol = st.selectbox(
                    "Sistem Rolü",
                    options=["hakem", "yonetici", "yarismaci", "admin"],
                    format_func=lambda x: {
                        "hakem": "Hakem / Jüri Değerlendiricisi",
                        "yonetici": "Yarışma Yöneticisi",
                        "yarismaci": "Yarışmacı / Takım Temsilcisi",
                        "admin": "Sistem Yöneticisi (Admin)"
                    }.get(x, x)
                )
                kurum = st.text_input("Kurum / Bölüm / Uzmanlık Alanı", placeholder="TÜBİTAK BİLGEM / Yapay Zekâ")

            submit_yeni = st.form_submit_button("Kullanıcıyı Sisteme Kaydet", type="primary", use_container_width=True)

            if submit_yeni:
                if not ad or not email or not sifre:
                    st.error("Lütfen ad, e-posta ve şifre alanlarını doldurunuz.")
                else:
                    basari, msg = auth_service.register_user(
                        name=ad,
                        email=email,
                        password=sifre,
                        role=rol,
                        institution=kurum,
                    )
                    if basari:
                        st.success(f"{ad} kullanıcısı sisteme başarıyla eklendi.")
                        st.rerun()
                    else:
                        st.error(msg)
