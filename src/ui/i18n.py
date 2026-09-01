"""T-Sistem · Çoklu Dil Desteği Sözlüğü (Türkçe & İngilizce).
"""

from __future__ import annotations
from typing import Dict, Any

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "tr": {
        # Genel & Marka
        "app_title": "T-SİSTEM",
        "app_subtitle": "TEKNOFEST Değerlendirme Portalı",
        "system_name": "T-SİSTEM",
        "system_sub": "TEKNOFEST DEĞERLENDİRME",
        
        # Giriş / Kayıt Sekmeleri & Butonlar
        "tab_email_login": "Giriş Yap",
        "tab_register": "Kayıt Ol",
        "google_login": "Google ile Giriş Yap",
        "google_register": "Google ile Kayıt Ol",
        "or_with_email": "─── VEYA E-POSTA İLE ───",
        "or_with_info": "─── VEYA BİLGİLERİNİZLE ───",
        
        # Google Profil Tamamlama
        "google_complete_title": "Google Hesabı Doğrulandı",
        "google_complete_sub": "Lütfen T-Sistem platformuna giriş yapabilmek için eksik olan zorunlu bilgilerinizi tamamlayınız.",
        "google_verified_badge": "Google ile Doğrulandı",
        "save_and_continue": "Bilgileri Kaydet ve Giriş Yap",
        
        # Form Alanları
        "email_label": "E-Posta *",
        "email_placeholder": "E-posta adresi",
        "password_label": "Parola *",
        "password_placeholder": "Parola",
        "forgot_password": "Şifremi unuttum",
        "remember_me": "Beni Hatırla",
        "login_btn": "Giriş Yap",
        
        # Kayıt Form Alanları
        "fullname_label": "Ad Soyad *",
        "fullname_placeholder": "Adınız ve Soyadınız",
        "inst_label": "Üniversite / Kurum",
        "inst_placeholder": "Üniversite veya Okul Adı",
        "pass1_label": "Parola *",
        "pass1_placeholder": "En az 6 karakter",
        "pass2_label": "Parola Tekrarı *",
        "pass2_placeholder": "Parolayı tekrar girin",
        "kvkk_text": "Aydınlatma Metnini okudum, onaylıyorum.",
        "register_btn": "Kayıt Ol",
        
        # Üst Navbar & Menü
        "nav_home": "Ana Sayfa",
        "nav_apps": "Başvurularım & Karne",
        "nav_teams": "Takımlarım",
        "nav_specs": "Şartnameler",
        "nav_specs_criteria": "Şartname & Kriterler",
        "nav_eval": "Rapor Değerlendirme",
        "nav_admin_yonetim": "Yarışma Yönetimi",
        "nav_admin_intihal": "İntihal Analizi",
        "nav_admin_users": "Kullanıcılar",
        "nav_profile": "Profilim",
        "nav_logout": "Çıkış Yap",
        "nav_announcement_mgmt": "Duyuru Yönetimi",
        "nav_team_mgmt": "Takım Yönetimi",
        "logged_in_as": "olarak başarıyla giriş yapıldı.",
        
        # Durumlar
        "status_waiting": "Beklemede",
        "status_done": "Tamamlandı",
        "status_assigned": "Hakeme Atandı",
        "status_rejected": "Reddedildi",
        
        # Modül Kartları
        "card_account": "Başvurularım & Karne",
        "card_account_desc": "Rapor yükleme, yapay zekâ ön kontrolü ve gelişim karneniz.",
        "card_btn_account": "BAŞVURULARA GİT",
        "card_tf_title": "TEKNOFEST 2026",
        "card_tf_desc": "Yeni yarışma kategorilerine başvurun ve takvimi takip edin.",
        "card_btn_tf": "YENİ BAŞVURU YAP",
        "card_teams_title": "Takımlarım",
        "card_teams_desc": "Mevcut takımlarınızı yönetin veya takım koduyla katılın.",
        "card_btn_teams": "TAKIMLARI YÖNET",
        "card_specs_title": "Şartnameler",
        "card_specs_desc": "Yarışma kural ve teknik değerlendirme kılavuzlarını indirin.",
        "card_btn_specs": "ŞARTNAMELERİ GÖR",
        
        # Takımlarım Sekmesi
        "teams_title": "Takımlarım ve Üyeler",
        "teams_sub": "TEKNOFEST yarışmalarına katıldığınız takımlarınızı yönetin veya yeni takım kurun.",
        "btn_create_team": "+ Yeni Takım Oluştur",
        "btn_join_team": "Takım Kodu ile Katıl",
        "lbl_team_name": "Takım Adı *",
        "lbl_team_cat": "Yarışma Kategorisi *",
        "btn_submit_team": "Takımı Oluştur",
        "lbl_join_code": "Takım Kodu *",
        "btn_submit_join": "Katıl",
        "exp_team_members": "Takım Üyeleri ve Yönetim",
        "btn_leave_team": "Takımdan Ayrıl / Sil",
        
        # Şartnameler ve Şablonlar İstasyonu
        "specs_portal_title": "Resmî Şartnameler, Şablonlar & Rapor Önizleme İstasyonu",
        "specs_portal_sub": "60+ TEKNOFEST yarışma kategorisinin resmî teknik şartnamelerini ve aşama rapor şablonlarını sayfa sayfa inceleyin ve indirin.",
        "tab_specs": "1. Teknik Şartnameler (Kurallar & İsterler)",
        "tab_templates": "2. Rapor Şablonları (Aşama Formatları)",
        "sel_category": "Yarışma Kategorisi",
        "sel_stage": "Rapor Aşaması",
        "btn_download_spec": "Şartnameyi İndir (PDF)",
        "btn_download_doc": "Dokümanı İndir (PDF)",
        "spec_doc_title": "Resmî Teknik Şartname Dokümanı",
        "template_doc_title": "Resmî Şablon & Örnek Rapor Dokümanı",
        "continuous_scroll_active": "Kaydırma & Büyüteç Aktif",
        
        # Profilim Sekmesi
        "profile_title": "Kişisel ve Kurumsal Profil Bilgileri",
        "profile_sub": "Kayıt olurken beyan ettiğiniz tüm T-Sistem profil bilgileri aşağıda listelenmiştir. İhtiyaç halinde güncelleyebilirsiniz.",
        "sec_panel_info": "Panel Bilgileri",
        "lbl_username": "Kullanıcı Adı *",
        "lbl_email_locked": "E-Posta Adresi (Kilitli)",
        "lbl_auth_method": "Oturum / Giriş Yöntemi",
        "sec_personal_info": "Kişisel Bilgiler",
        "lbl_name": "Adı *",
        "lbl_surname": "Soyadı *",
        "lbl_tc": "T.C. Vatandaşı *",
        "lbl_gender": "Cinsiyet *",
        "sec_contact_info": "İletişim ve Adres Bilgileri",
        "lbl_country_code": "Ülke Kodu *",
        "lbl_phone": "Cep Telefonu *",
        "lbl_country": "Ülke *",
        "lbl_address": "İl / İlçe / Açık Adres *",
        "sec_education_info": "Eğitim ve Program Bilgileri",
        "lbl_grad_status": "Mezuniyet Durumu *",
        "lbl_edu_level": "Eğitim Seviyesi *",
        "lbl_school": "Okul / Üniversite Adı *",
        "lbl_dept": "Bölüm / Program Adı *",
        "btn_save_profile": "Profil Bilgilerimi Güncelle",
        "succ_profile_save": "Profil bilgileriniz başarıyla güncellendi!",

        # Admin Pano
        "tab_admin_ops": "Canlı Operasyon Panosu & KPI'lar",
        "tab_admin_cats": "4 Kademeli Kategori & Aşama Yönetimi",
        
        # Yarışmacı Vitrini
        "yar_vitrin_title": "TEKNOFEST 2026 Yarışmaları",
        "yar_vitrin_cap": "İlgi duyduğunuz yarışmayı seçin, resmî şartnameleri inceleyin ve hemen başvurunuzu tamamlayın.",
        "yar_search_ph": "Yarışma adı ile ara...",
        "yar_filter_domain": "Alan / Kategori",
        "yar_filter_all_domains": "Tüm Alanlar",
        "yar_domain_hava": "Havacılık & Uzay",
        "yar_domain_yapay": "Yapay Zekâ & Yazılım",
        "yar_domain_otonom": "Otonom & Robotik",
        "yar_domain_saglik": "Sağlık & Biyoteknoloji",
        "yar_domain_enerji": "Enerji & Çevre",
        "yar_domain_insanlik": "İnsanlık Yararına & Sosyal",
        "yar_filter_level": "Seviye",
        "yar_filter_all_levels": "Tüm Seviyeler",
        "yar_level_ilkokul": "İlkokul",
        "yar_level_ortaokul": "Ortaokul",
        "yar_level_lise": "Lise",
        "yar_level_lisans": "Lisans / Ön Lisans",
        "yar_level_yuksek": "Yüksek Lisans / Doktora",
        "yar_level_mezun": "Mezun",
        "yar_count_prefix": "Toplam",
        "yar_count_suffix": "Yarışma Listeleniyor",
        "yar_card_btn_apply": "Başvur",
        "yar_default_domain": "Genel",
        "yar_default_level": "Tüm Seviyeler",
        "yar_card_levels": "Hedef Seviye",
        "yar_card_deadline": "Son Başvuru",
        
        # Hata & Bildirimler
        "err_fill_fields": "Lütfen zorunlu (*) alanları doldurunuz.",
        "err_invalid_login": "Hatalı e-posta veya parola.",
        "err_pass_mismatch": "Parolalar eşleşmiyor.",
        "err_accept_kvkk": "Lütfen aydınlatma metnini onaylayınız.",
        "succ_reg": "Kaydınız başarıyla oluşturuldu! Şimdi giriş yapabilirsiniz.",
    },
    "en": {
        # General & Branding
        "app_title": "T-SİSTEM",
        "app_subtitle": "TEKNOFEST Evaluation Portal",
        "system_name": "T-SİSTEM",
        "system_sub": "TEKNOFEST AI EVALUATION",
        
        # Auth Tabs & Buttons
        "tab_email_login": "Sign In",
        "tab_register": "Register",
        "google_login": "Sign in with Google",
        "google_register": "Sign up with Google",
        "or_with_email": "─── OR WITH EMAIL ───",
        "or_with_info": "─── OR WITH YOUR DETAILS ───",
        
        # Google Complete Profile
        "google_complete_title": "Google Account Verified",
        "google_complete_sub": "Please complete your mandatory information to access T-System portal.",
        "google_verified_badge": "Verified with Google",
        "save_and_continue": "Save Information & Sign In",
        
        # Form Fields
        "email_label": "Email Address *",
        "email_placeholder": "Email address",
        "password_label": "Password *",
        "password_placeholder": "Password",
        "forgot_password": "Forgot password?",
        "remember_me": "Remember Me",
        "login_btn": "Sign In",
        
        # Registration Form Fields
        "fullname_label": "Full Name *",
        "fullname_placeholder": "Your Full Name",
        "inst_label": "University / Organization",
        "inst_placeholder": "University or Organization Name",
        "pass1_label": "Password *",
        "pass1_placeholder": "At least 6 characters",
        "pass2_label": "Confirm Password *",
        "pass2_placeholder": "Re-enter password",
        "kvkk_text": "I have read and agree to the Privacy & Clarification Policy.",
        "register_btn": "Sign Up",
        
        # Top Navbar & Menu
        "nav_home": "Home",
        "nav_apps": "My Applications & Scorecard",
        "nav_teams": "My Teams",
        "nav_specs": "Specifications",
        "nav_specs_criteria": "Specs & Rubrics",
        "nav_eval": "Report Evaluation",
        "nav_admin_yonetim": "Competition Management",
        "nav_admin_intihal": "Plagiarism Analysis",
        "nav_admin_users": "Users",
        "nav_profile": "My Profile",
        "nav_logout": "Logout",
        "nav_announcement_mgmt": "Announcement Management",
        "nav_team_mgmt": "Team Management",
        "logged_in_as": "successfully logged in.",
        
        # Durumlar
        "status_waiting": "Pending",
        "status_done": "Completed",
        "status_assigned": "Assigned",
        "status_rejected": "Rejected",
        
        # Module Cards
        "card_account": "My Applications & Scorecard",
        "card_account_desc": "Upload reports, track AI pre-checks, and review your development scorecard.",
        "card_btn_account": "GO TO APPLICATIONS",
        "card_tf_title": "TEKNOFEST 2026",
        "card_tf_desc": "Apply for new competition categories and follow the schedule.",
        "card_btn_tf": "START APPLICATION",
        "card_teams_title": "My Teams",
        "card_teams_desc": "Manage existing teams or join using an invite team code.",
        "card_btn_teams": "MANAGE TEAMS",
        "card_specs_title": "Specifications",
        "card_specs_desc": "Download official rules and technical evaluation guidelines.",
        "card_btn_specs": "VIEW SPECS",
        
        # Teams Tab
        "teams_title": "My Teams & Members",
        "teams_sub": "Manage your registered TEKNOFEST teams or form a new team.",
        "btn_create_team": "+ Create New Team",
        "btn_join_team": "Join with Team Code",
        "lbl_team_name": "Team Name *",
        "lbl_team_cat": "Competition Category *",
        "btn_submit_team": "Create Team",
        "lbl_join_code": "Team Code *",
        "btn_submit_join": "Join Team",
        "exp_team_members": "Team Members & Management",
        "btn_leave_team": "Leave / Delete Team",
        
        # Specs & Templates Station
        "specs_portal_title": "Official Specifications, Templates & Report Preview Station",
        "specs_portal_sub": "Explore and download official technical specifications and stage templates for 60+ TEKNOFEST competition categories page by page.",
        "tab_specs": "1. Technical Specifications (Rules & Guidelines)",
        "tab_templates": "2. Report Templates (Stage Formats)",
        "sel_category": "Competition Category",
        "sel_stage": "Report Stage",
        "btn_download_spec": "Download Spec (PDF)",
        "btn_download_doc": "Download Document (PDF)",
        "spec_doc_title": "Official Technical Specification Document",
        "template_doc_title": "Official Stage Report Template Document",
        "continuous_scroll_active": "Continuous Scroll & Zoom Active",
        
        # Profile Tab
        "profile_title": "Personal & Institutional Profile Information",
        "profile_sub": "All profile registration details are listed below. You can update your profile when needed.",
        "sec_panel_info": "Panel Information",
        "lbl_username": "Username *",
        "lbl_email_locked": "Email Address (Locked)",
        "lbl_auth_method": "Authentication Method",
        "sec_personal_info": "Personal Information",
        "lbl_name": "First Name *",
        "lbl_surname": "Last Name *",
        "lbl_tc": "Turkish Citizen *",
        "lbl_gender": "Gender *",
        "sec_contact_info": "Contact & Address Information",
        "lbl_country_code": "Country Code *",
        "lbl_phone": "Mobile Phone *",
        "lbl_country": "Country *",
        "lbl_address": "City / District / Full Address *",
        "sec_education_info": "Education & Program Information",
        "lbl_grad_status": "Graduation Status *",
        "lbl_edu_level": "Education Level *",
        "lbl_school": "School / University Name *",
        "lbl_dept": "Department / Major Name *",
        "btn_save_profile": "Update My Profile",
        "succ_profile_save": "Your profile information has been successfully updated!",

        # Admin Pano
        "tab_admin_ops": "Live Operations Dashboard & KPIs",
        "tab_admin_cats": "4-Tier Category & Stage Management",

        # Yarışmacı Vitrini
        "yar_vitrin_title": "TEKNOFEST 2026 Competitions",
        "yar_vitrin_cap": "Select a competition you are interested in, review official specifications, and complete your application.",
        "yar_search_ph": "Search by competition name...",
        "yar_filter_domain": "Domain / Category",
        "yar_filter_all_domains": "All Domains",
        "yar_domain_hava": "Aviation & Space",
        "yar_domain_yapay": "Artificial Intelligence & Software",
        "yar_domain_otonom": "Autonomous & Robotics",
        "yar_domain_saglik": "Health & Biotechnology",
        "yar_domain_enerji": "Energy & Environment",
        "yar_domain_insanlik": "Social & Humanitarian",
        "yar_filter_level": "Level",
        "yar_filter_all_levels": "All Levels",
        "yar_level_ilkokul": "Primary School",
        "yar_level_ortaokul": "Middle School",
        "yar_level_lise": "High School",
        "yar_level_lisans": "Undergraduate",
        "yar_level_yuksek": "Graduate / PhD",
        "yar_level_mezun": "Alumni",
        "yar_count_prefix": "Showing",
        "yar_count_suffix": "Competitions",
        "yar_card_btn_apply": "Apply",
        "yar_default_domain": "General",
        "yar_default_level": "All Levels",
        "yar_card_levels": "Target Level",
        "yar_card_deadline": "Application Deadline",

        # Errors & Notifications
        "err_fill_fields": "Please fill in all mandatory (*) fields.",
        "err_invalid_login": "Invalid email or password.",
        "err_pass_mismatch": "Passwords do not match.",
        "err_accept_kvkk": "Please accept the clarification policy.",
        "succ_reg": "Registration successful! You can now log in.",
    }
}

# ── Dashboard (dashboard.py) anahtarları ─────────────────────────────────────
_DASH_TR = {
    "dash_title": "Canlı Operasyon Panosu",
    "dash_sub": "Tüm yarışmalara ait rapor ve değerlendirme metriklerini anlık takip edin.",
    "dash_kategori": "Kategori Filtresi",
    "dash_durum": "Durum Filtresi",
    "dash_filtre_rapor_yok": "Seçili filtrelere uygun rapor bulunamadı.",
    "dash_filtre_genislet": "Filtreleri genişletmeyi deneyin.",
    "dash_toplam_rapor": "Toplam Rapor",
    "dash_kategori_label": "kategori",
    "dash_tamamlanma": "Tamamlanma",
    "dash_rapor_onaylandi": "rapor onaylandı",
    "dash_ort_ai_puan": "Ort. AI Puanı",
    "dash_100_uzerinden": "100 üzerinden",
    "dash_benzerlik_uyarisi": "Benzerlik Uyarısı",
    "dash_hakem_incelemesi": "hakem incelemesi gerekiyor",
    "dash_bekleyen": "Bekleyen",
    "dash_analiz_hakem": "analiz / hakem",
    "dash_sablon_uyumsuz": "Şablon Uyumsuz",
    "dash_otomatik_isaretlendi": "otomatik işaretlendi",
    "dash_dil_uyumsuz": "Dil Uyumsuz",
    "dash_beklenen_dilden": "beklenen dilden farklı",
    "dash_hatali": "Hatalı",
    "dash_islemeyen": "işlenemeyen rapor",
    "dash_kriter_ort": "Kriter Ortalamaları",
    "dash_kriter_sub": "Her değerlendirme kriterinin ortalama puanı ve oranı.",
    "dash_kriter": "Kriter",
    "dash_tavan": "Tavan",
    "dash_ort_puan": "Ort. Puan",
    "dash_oran": "Oran",
}
_DASH_EN = {
    "dash_title": "Live Operations Dashboard",
    "dash_sub": "Track real-time report and evaluation metrics for all competitions.",
    "dash_kategori": "Category Filter",
    "dash_durum": "Status Filter",
    "dash_filtre_rapor_yok": "No reports match the selected filters.",
    "dash_filtre_genislet": "Try broadening your filters.",
    "dash_toplam_rapor": "Total Reports",
    "dash_kategori_label": "categories",
    "dash_tamamlanma": "Completion",
    "dash_rapor_onaylandi": "reports approved",
    "dash_ort_ai_puan": "Avg AI Score",
    "dash_100_uzerinden": "out of 100",
    "dash_benzerlik_uyarisi": "Similarity Warning",
    "dash_hakem_incelemesi": "require referee review",
    "dash_bekleyen": "Pending",
    "dash_analiz_hakem": "analysis / referee",
    "dash_sablon_uyumsuz": "Template Mismatch",
    "dash_otomatik_isaretlendi": "auto-flagged",
    "dash_dil_uyumsuz": "Language Mismatch",
    "dash_beklenen_dilden": "differs from expected language",
    "dash_hatali": "Errored",
    "dash_islemeyen": "unprocessable reports",
    "dash_kriter_ort": "Criterion Averages",
    "dash_kriter_sub": "Average score and ratio for each evaluation criterion.",
    "dash_kriter": "Criterion",
    "dash_tavan": "Max",
    "dash_ort_puan": "Avg Score",
    "dash_oran": "Ratio",
}

# ── Admin Kullanıcılar (admin_kullanicilar.py) anahtarları ───────────────────
_USR_TR = {
    "usr_panel_title": "Kullanıcı & Yetki Yönetimi",
    "usr_panel_sub": "Tüm kullanıcıları listeleyin, rollerini ve durumlarını güncelleyin.",
    "usr_toplam": "Toplam Kullanıcı",
    "usr_toplam_sub": "kayıtlı hesap",
    "usr_hakem": "Hakem",
    "usr_hakem_sub": "değerlendirici",
    "usr_yarismaci": "Yarışmacı",
    "usr_yarismaci_sub": "katılımcı",
    "usr_yonetici": "Yönetici",
    "usr_yonetici_sub": "admin / yönetici",
    "usr_tab_liste": "Kullanıcı Listesi",
    "usr_tab_yeni": "Yeni Kullanıcı Ekle",
    "usr_bos": "Sistemde kullanıcı bulunmamaktadır.",
    "usr_id": "ID",
    "usr_ad_soyad": "Ad Soyad",
    "usr_eposta": "E-posta",
    "usr_rol": "Rol",
    "usr_kurum": "Kurum",
    "usr_belirtilmedi": "Belirtilmedi",
    "usr_durum": "Durum",
    "usr_kayit": "Kayıt Tarihi",
    "usr_duzenle_title": "Kullanıcı Düzenle",
    "usr_duzenle_sec": "Düzenlenecek kullanıcıyı seçin",
    "usr_profil_duzenle": "Kullanıcı ID",
    "usr_ad_soyad_lbl": "Ad Soyad",
    "usr_eposta_lbl": "E-posta",
    "usr_kurum_lbl": "Kurum",
    "usr_rol_lbl": "Rol",
    "usr_rol_hakem": "Hakem",
    "usr_rol_yonetici": "Yönetici",
    "usr_rol_yarismaci": "Yarışmacı",
    "usr_rol_admin": "Admin",
    "usr_durum_lbl": "Durum",
    "usr_aktif": "Aktif",
    "usr_pasif": "Pasif",
    "usr_sifre_lbl": "Yeni Şifre",
    "usr_sifre_ph": "Boş bırakılırsa değişmez",
    "usr_kaydet_btn": "Değişiklikleri Kaydet",
    "usr_sil_btn": "Sil",
    "usr_sil_succ": "kullanıcısı silindi.",
    "usr_sil_err": "Silme işlemi başarısız oldu.",
    "usr_sil_koruma": "Sistem admini silinemez.",
    "usr_yeni_title": "Yeni Kullanıcı Oluştur",
    "usr_yeni_ad": "Ad Soyad *",
    "usr_yeni_ad_ph": "Adı ve soyadı giriniz",
    "usr_yeni_email": "E-posta *",
    "usr_yeni_email_ph": "kullanici@email.com",
    "usr_yeni_sifre": "Şifre *",
    "usr_yeni_sifre_ph": "En az 6 karakter",
    "usr_yeni_kurum": "Kurum",
    "usr_yeni_kurum_ph": "Üniversite veya kurum adı",
    "usr_yeni_kaydet": "Kullanıcıyı Oluştur",
    "usr_yeni_err": "Ad, e-posta ve şifre zorunludur.",
    "usr_yeni_succ": "başarıyla oluşturuldu.",
}
_USR_EN = {
    "usr_panel_title": "User & Permission Management",
    "usr_panel_sub": "List all users and update their roles and statuses.",
    "usr_toplam": "Total Users",
    "usr_toplam_sub": "registered accounts",
    "usr_hakem": "Referee",
    "usr_hakem_sub": "evaluators",
    "usr_yarismaci": "Contestant",
    "usr_yarismaci_sub": "participants",
    "usr_yonetici": "Manager",
    "usr_yonetici_sub": "admin / manager",
    "usr_tab_liste": "User List",
    "usr_tab_yeni": "Add New User",
    "usr_bos": "No users in the system.",
    "usr_id": "ID",
    "usr_ad_soyad": "Full Name",
    "usr_eposta": "Email",
    "usr_rol": "Role",
    "usr_kurum": "Institution",
    "usr_belirtilmedi": "Not specified",
    "usr_durum": "Status",
    "usr_kayit": "Registered",
    "usr_duzenle_title": "Edit User",
    "usr_duzenle_sec": "Select user to edit",
    "usr_profil_duzenle": "User ID",
    "usr_ad_soyad_lbl": "Full Name",
    "usr_eposta_lbl": "Email",
    "usr_kurum_lbl": "Institution",
    "usr_rol_lbl": "Role",
    "usr_rol_hakem": "Referee",
    "usr_rol_yonetici": "Manager",
    "usr_rol_yarismaci": "Contestant",
    "usr_rol_admin": "Admin",
    "usr_durum_lbl": "Status",
    "usr_aktif": "Active",
    "usr_pasif": "Passive",
    "usr_sifre_lbl": "New Password",
    "usr_sifre_ph": "Leave blank to keep unchanged",
    "usr_kaydet_btn": "Save Changes",
    "usr_sil_btn": "Delete",
    "usr_sil_succ": "user deleted.",
    "usr_sil_err": "Deletion failed.",
    "usr_sil_koruma": "System admin cannot be deleted.",
    "usr_yeni_title": "Create New User",
    "usr_yeni_ad": "Full Name *",
    "usr_yeni_ad_ph": "Enter first and last name",
    "usr_yeni_email": "Email *",
    "usr_yeni_email_ph": "user@email.com",
    "usr_yeni_sifre": "Password *",
    "usr_yeni_sifre_ph": "At least 6 characters",
    "usr_yeni_kurum": "Institution",
    "usr_yeni_kurum_ph": "University or organization name",
    "usr_yeni_kaydet": "Create User",
    "usr_yeni_err": "Name, email, and password are required.",
    "usr_yeni_succ": "created successfully.",
}

_KAR_TR: dict = {
    "kar_title": "İntihal & Benzerlik Analizi",
    "kar_sub": "Çapraz başvuru benzerlik matrisi, ikili karşılaştırma ve AI ↔ Hakem kalibrasyon analizi.",
    "kar_tab_intihal": "Benzerlik Matrisi",
    "kar_tab_karsilastir": "İkili Karşılaştırma",
    "kar_tab_ai_hakem": "AI ↔ Hakem Uyumu",
    "kar_matris_title": "Çapraz Benzerlik Isı Haritası",
    "kar_matris_sub": "Başvurular arası benzerlik skorları — yüksek değerler olası intihal riski taşıyabilir.",
    "kar_min_rapor": "Benzerlik matrisi oluşturmak için en az 2 rapor gereklidir.",
    "kar_yuksek_risk": "Yüksek Benzerlik Uyarısı",
    "kar_ikili_title": "İkili Rapor Karşılaştırması",
    "kar_ikili_min": "Karşılaştırma için en az 2 rapor gereklidir.",
    "kar_rapor_1": "Rapor A",
    "kar_rapor_2": "Rapor B",
}

_KAR_EN: dict = {
    "kar_title": "Plagiarism & Similarity Analysis",
    "kar_sub": "Cross-application similarity matrix, side-by-side comparison and AI ↔ Referee calibration analysis.",
    "kar_tab_intihal": "Similarity Matrix",
    "kar_tab_karsilastir": "Side-by-Side Compare",
    "kar_tab_ai_hakem": "AI ↔ Referee Agreement",
    "kar_matris_title": "Cross-Similarity Heat Map",
    "kar_matris_sub": "Pairwise similarity scores — high values may indicate potential plagiarism risk.",
    "kar_min_rapor": "At least 2 reports are required to generate the similarity matrix.",
    "kar_yuksek_risk": "High Similarity Warning",
    "kar_ikili_title": "Side-by-Side Report Comparison",
    "kar_ikili_min": "At least 2 reports are required for comparison.",
    "kar_rapor_1": "Report A",
    "kar_rapor_2": "Report B",
}

# ── Auth view (auth_view.py) anahtarları ─────────────────────────────────────
_AUTH_TR: dict = {
    # Giriş formu başlığı
    "login_title": "E-Posta ile Giriş Yap",
    "login_sub": "T-Sistem hesabınıza güvenli giriş yapın.",
    "forgot_password_link": "Şifremi Unuttum",
    # OAuth hataları
    "auth_oauth_state_error": "OAuth state hatası. Lütfen tekrar deneyin.",
    "auth_google_failed": "Google girişi başarısız. Lütfen tekrar deneyin.",
    # Şifre sıfırlama
    "fp_title": "Şifre Sıfırlama",
    "fp_sub": "Kayıtlı e-posta adresinize doğrulama kodu gönderilecektir.",
    "fp_email_label": "E-Posta Adresiniz",
    "fp_send_btn": "Doğrulama Kodu Gönder",
    "fp_err_email": "Geçerli bir e-posta adresi giriniz.",
    "fp_code_label": "6 Haneli Doğrulama Kodu",
    "fp_new_pass": "Yeni Parola *",
    "fp_new_pass_ph": "En az 6 karakter",
    "fp_new_pass_repeat": "Yeni Parola Tekrarı *",
    "fp_new_pass_repeat_ph": "Parolayı tekrar girin",
    "fp_save_btn": "Parolayı Güncelle",
    "fp_err_all_fields": "Lütfen tüm alanları doldurunuz.",
    "fp_err_pass_mismatch": "Parolalar eşleşmiyor.",
    "fp_err_pass_short": "Parola en az 6 karakter olmalıdır.",
    "fp_back_btn": "← Giriş Sayfasına Dön",
    # Kayıt formu
    "reg_title": "T-Sistem'e Kayıt Ol",
    "reg_sub": "TEKNOFEST T-Sistem Değerlendirme Portalı hesabınızı oluşturun.",
    "reg_sec_panel": "Panel Bilgileri",
    "reg_username": "Kullanıcı Adı *",
    "reg_username_ph": "kullanici_adi",
    "reg_email_lbl": "E-Posta *",
    "reg_pass_lbl": "Parola *",
    "reg_pass_ph": "En az 6 karakter",
    "reg_pass_repeat": "Parola Tekrarı *",
    "reg_pass_repeat_ph": "Parolayı tekrar girin",
    "reg_sec_personal": "Kişisel Bilgiler",
    "reg_first_name": "Adı *",
    "reg_first_name_ph": "Adınız",
    "reg_last_name": "Soyadı *",
    "reg_last_name_ph": "Soyadınız",
    "reg_tc_citizen": "T.C. Vatandaşı mısınız? *",
    "reg_tc_select": "Seçiniz",
    "reg_tc_yes": "Evet",
    "reg_tc_no": "Hayır",
    "reg_gender": "Cinsiyet *",
    "reg_gender_male": "Erkek",
    "reg_gender_female": "Kadın",
    "reg_birth_date": "Doğum Tarihi *",
    "reg_country_code": "Ülke Kodu *",
    "reg_phone": "Cep Telefonu *",
    "reg_how_heard": "Bizi Nasıl Duydunuz?",
    "reg_how_social": "Sosyal Medya",
    "reg_how_school": "Okul / Üniversite",
    "reg_how_friend": "Arkadaş / Tanıdık",
    "reg_sec_address": "Adres Bilgileri",
    "reg_country": "Ülke *",
    "reg_country_turkey": "Türkiye",
    "reg_country_other": "Diğer",
    "reg_address": "İl / İlçe / Açık Adres *",
    "reg_address_ph": "Adresinizi giriniz",
    "reg_sec_education": "Eğitim Bilgileri",
    "reg_graduate_chk": "Mezun / Girişimci",
    "reg_edu_level": "Eğitim Seviyesi *",
    "reg_school_other": "Okul / Üniversite Adı",
    "reg_school_other_ph": "Okul veya üniversite adı",
    # Google profil tamamlama
    "pending_google_user": "Google hesabınız doğrulandı, profil tamamlanıyor.",
    "gc_back_btn": "← Giriş'e Dön",
    "gc_sec_personal": "Kişisel Bilgiler",
    "gc_username_lbl": "Kullanıcı Adı *",
    "username": "Kullanıcı Adı",
    "gc_sec_contact": "İletişim Bilgileri",
    "gc_country_code": "Ülke Kodu *",
    "gc_phone": "Cep Telefonu *",
    "gc_phone_ph": "Telefon numaranız",
    "gc_address": "Adres *",
    "gc_address_ph": "İl / İlçe / Açık Adres",
    "gc_sec_education": "Eğitim Bilgileri",
    "gc_edu_level": "Eğitim Seviyesi *",
    "gc_institution": "Okul / Üniversite",
    "gc_institution_ph": "Okul veya üniversite adı",
    "gc_kvkk": "Aydınlatma Metnini okudum, onaylıyorum.",
    "gc_err_fill_fields": "Lütfen zorunlu (*) alanları doldurunuz.",
    "gc_err_kvkk": "Lütfen aydınlatma metnini onaylayınız.",
}

_AUTH_EN: dict = {
    # Login form header
    "login_title": "Sign In with Email",
    "login_sub": "Securely sign in to your T-System account.",
    "forgot_password_link": "Forgot Password",
    # OAuth errors
    "auth_oauth_state_error": "OAuth state error. Please try again.",
    "auth_google_failed": "Google sign-in failed. Please try again.",
    # Forgot password
    "fp_title": "Password Reset",
    "fp_sub": "A verification code will be sent to your registered email address.",
    "fp_email_label": "Your Email Address",
    "fp_send_btn": "Send Verification Code",
    "fp_err_email": "Please enter a valid email address.",
    "fp_code_label": "6-Digit Verification Code",
    "fp_new_pass": "New Password *",
    "fp_new_pass_ph": "At least 6 characters",
    "fp_new_pass_repeat": "Confirm New Password *",
    "fp_new_pass_repeat_ph": "Re-enter new password",
    "fp_save_btn": "Update Password",
    "fp_err_all_fields": "Please fill in all fields.",
    "fp_err_pass_mismatch": "Passwords do not match.",
    "fp_err_pass_short": "Password must be at least 6 characters.",
    "fp_back_btn": "← Back to Sign In",
    # Register form
    "reg_title": "Register for T-System",
    "reg_sub": "Create your TEKNOFEST T-System Evaluation Portal account.",
    "reg_sec_panel": "Panel Information",
    "reg_username": "Username *",
    "reg_username_ph": "username",
    "reg_email_lbl": "Email *",
    "reg_pass_lbl": "Password *",
    "reg_pass_ph": "At least 6 characters",
    "reg_pass_repeat": "Confirm Password *",
    "reg_pass_repeat_ph": "Re-enter password",
    "reg_sec_personal": "Personal Information",
    "reg_first_name": "First Name *",
    "reg_first_name_ph": "Your first name",
    "reg_last_name": "Last Name *",
    "reg_last_name_ph": "Your last name",
    "reg_tc_citizen": "Turkish Citizen? *",
    "reg_tc_select": "Select",
    "reg_tc_yes": "Yes",
    "reg_tc_no": "No",
    "reg_gender": "Gender *",
    "reg_gender_male": "Male",
    "reg_gender_female": "Female",
    "reg_birth_date": "Date of Birth *",
    "reg_country_code": "Country Code *",
    "reg_phone": "Mobile Phone *",
    "reg_how_heard": "How Did You Hear About Us?",
    "reg_how_social": "Social Media",
    "reg_how_school": "School / University",
    "reg_how_friend": "Friend / Acquaintance",
    "reg_sec_address": "Address Information",
    "reg_country": "Country *",
    "reg_country_turkey": "Turkey",
    "reg_country_other": "Other",
    "reg_address": "City / District / Full Address *",
    "reg_address_ph": "Enter your address",
    "reg_sec_education": "Education Information",
    "reg_graduate_chk": "Graduate / Entrepreneur",
    "reg_edu_level": "Education Level *",
    "reg_school_other": "School / University Name",
    "reg_school_other_ph": "School or university name",
    # Google complete profile
    "pending_google_user": "Your Google account is verified, completing profile.",
    "gc_back_btn": "← Back to Sign In",
    "gc_sec_personal": "Personal Information",
    "gc_username_lbl": "Username *",
    "username": "Username",
    "gc_sec_contact": "Contact Information",
    "gc_country_code": "Country Code *",
    "gc_phone": "Mobile Phone *",
    "gc_phone_ph": "Your phone number",
    "gc_address": "Address *",
    "gc_address_ph": "City / District / Full Address",
    "gc_sec_education": "Education Information",
    "gc_edu_level": "Education Level *",
    "gc_institution": "School / University",
    "gc_institution_ph": "School or university name",
    "gc_kvkk": "I have read and agree to the Privacy & Clarification Policy.",
    "gc_err_fill_fields": "Please fill in all mandatory (*) fields.",
    "gc_err_kvkk": "Please accept the clarification policy.",
}

_HAK_HOME_TR = {
    "hk_home_title": "Hakem Değerlendirme İstasyonu",
    "hk_home_sub": "Atanan yarışmacı raporlarını inceleyin, yapay zekâ ön kontrollerini onaylayın ve puanlama yapın.",
    "hk_metric_rapor": "Rapor",
    "hk_metric_atanan": "Atanan Raporlar",
    "hk_metric_tamamlanan": "Değerlendirilen",
    "hk_metric_bekleyen": "İnceleme Bekleyen",
    "hk_btn_eval": "Rapor Değerlendirmeye Git",
    "hk_btn_specs": "Şartname & Kriterleri İncele",
}

_HAK_HOME_EN = {
    "hk_home_title": "Referee Evaluation Station",
    "hk_home_sub": "Review assigned participant reports, verify AI pre-checks and submit scores.",
    "hk_metric_rapor": "Report",
    "hk_metric_atanan": "Assigned Reports",
    "hk_metric_tamamlanan": "Evaluated",
    "hk_metric_bekleyen": "Pending Review",
    "hk_btn_eval": "Go to Report Evaluation",
    "hk_btn_specs": "View Specs & Criteria",
}

# Eksik anahtarları ana sözlüğe ekle
TRANSLATIONS["tr"].update(_DASH_TR)
TRANSLATIONS["tr"].update(_USR_TR)
TRANSLATIONS["tr"].update(_KAR_TR)
TRANSLATIONS["tr"].update(_AUTH_TR)
TRANSLATIONS["tr"].update(_HAK_HOME_TR)

TRANSLATIONS["en"].update(_DASH_EN)
TRANSLATIONS["en"].update(_USR_EN)
TRANSLATIONS["en"].update(_KAR_EN)
TRANSLATIONS["en"].update(_AUTH_EN)
TRANSLATIONS["en"].update(_HAK_HOME_EN)

try:
    from src.ui.i18n_hakem import TRANSLATIONS as _HAK_TRANS
    if "tr" in _HAK_TRANS:
        TRANSLATIONS["tr"].update(_HAK_TRANS["tr"])
    if "en" in _HAK_TRANS:
        TRANSLATIONS["en"].update(_HAK_TRANS["en"])
except Exception:
    pass

try:
    from src.ui.i18n_yarismaci import EXTRA_TR as _YSC_TR, EXTRA_EN as _YSC_EN
    TRANSLATIONS["tr"].update(_YSC_TR)
    TRANSLATIONS["en"].update(_YSC_EN)
except Exception:
    pass

try:
    from src.ui.i18n_yonetici import TRANSLATIONS as _YNT_TRANS
    if "tr" in _YNT_TRANS:
        TRANSLATIONS["tr"].update(_YNT_TRANS["tr"])
    if "en" in _YNT_TRANS:
        TRANSLATIONS["en"].update(_YNT_TRANS["en"])
except Exception:
    pass


def t(key: str, lang: str | None = None) -> str:
    """Belirtilen anahtar için seçili dildeki metni döner.

    lang belirtilmezse ``st.session_state.lang`` otomatik okunur;
    Streamlit bağlamı dışında (örn. script/test) "tr" varsayılır.
    """
    if lang is None:
        try:
            import streamlit as st
            lang = getattr(st.session_state, "lang", None) or "tr"
        except Exception:
            lang = "tr"
    return TRANSLATIONS.get(lang, TRANSLATIONS["tr"]).get(key, key)

