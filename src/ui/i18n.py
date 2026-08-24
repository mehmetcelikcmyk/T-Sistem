"""T-Sistem · Çoklu Dil Desteği Sözlüğü (Türkçe & İngilizce).
"""

from __future__ import annotations
from typing import Dict, Any

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    "tr": {
        # Genel & Marka
        "app_title": "Kurumsal Yönetim Sistemi",
        "app_subtitle": "TEKNOFEST & T3 Vakfı Değerlendirme Portalı",
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
        "google_complete_sub": "Lütfen T3 KYS sistemine giriş yapabilmek için eksik olan zorunlu bilgilerinizi tamamlayınız.",
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
        "register_btn": "Üye Ol",
        
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
        "logged_in_as": "olarak başarıyla giriş yapıldı.",
        
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
        "profile_sub": "Kayıt olurken beyan ettiğiniz tüm T3 KYS bilgileri aşağıda listelenmiştir. İhtiyaç halinde güncelleyebilirsiniz.",
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
        
        # Hata & Bildirimler
        "err_fill_fields": "Lütfen zorunlu (*) alanları doldurunuz.",
        "err_invalid_login": "Hatalı e-posta veya parola.",
        "err_pass_mismatch": "Parolalar eşleşmiyor.",
        "err_accept_kvkk": "Lütfen aydınlatma metnini onaylayınız.",
        "succ_reg": "Kaydınız başarıyla oluşturuldu! Şimdi giriş yapabilirsiniz.",
    },
    "en": {
        # General & Branding
        "app_title": "Corporate Management System",
        "app_subtitle": "TEKNOFEST & T3 Foundation Evaluation Portal",
        "system_name": "T-SYSTEM",
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
        "google_complete_sub": "Please complete your mandatory information to access T3 KYS portal.",
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
        "logged_in_as": "successfully logged in.",
        
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
        "profile_sub": "All T3 KYS registration details are listed below. You can update your profile when needed.",
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
        
        # Errors & Notifications
        "err_fill_fields": "Please fill in all mandatory (*) fields.",
        "err_invalid_login": "Invalid email or password.",
        "err_pass_mismatch": "Passwords do not match.",
        "err_accept_kvkk": "Please accept the clarification policy.",
        "succ_reg": "Registration successful! You can now log in.",
    }
}


def t(key: str, lang: str = "tr") -> str:
    """Belirtilen anahtar için seçili dildeki metni döner."""
    return TRANSLATIONS.get(lang, TRANSLATIONS["tr"]).get(key, key)

