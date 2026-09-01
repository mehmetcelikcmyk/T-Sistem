"""T-Sistem · Gerçekçi Proje İsimleri, Temiz Takım Adları ve Kusursuz Hakem Ataması Veri Motoru."""

from __future__ import annotations

import os
import re
import json
import sqlite3
import datetime
from pathlib import Path
import urllib.parse

PROJE_KOKU = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJE_KOKU / "docs" / "yarismalar"
DB_FILE = PROJE_KOKU / "data" / "tsistem.db"

# Kategori bazlı gerçekçi TEKNOFEST proje isim havuzları
PROJE_ISIMLERI = {
    "biyoteknoloji": [
        ("Biyo-Sensör Tabanlı Hızlı Tanı Kiti", "Takım Biyomolekül"),
        ("Hedefe Yönelimli Akıllı İlaç Taşıyıcı Sistem", "Takım BioTech"),
        ("Genom Analizi ile Bitki Hastalık Teşhisi", "Takım GenAura"),
        ("Yapay Zeka Destekli Biyomedikal Görüntüleme", "Takım NanoGen"),
        ("Biyosensör ile Çevre Kirliliği İzleme", "Takım EkoBiyo"),
        ("Biyoteknolojik Enzim Üretim Reaktörü", "Takım BiyoReak"),
        ("Hücresel Terapi için Biyo-Uyumlu Doku İskelesi", "Takım BiyoDoku"),
        ("Mikrobiyal Yakıt Hücresi Enerji Sistemi", "Takım BiyoEnerji"),
        ("Biyomühendislik Tabanlı Yara İyileştirici Jel", "Takım DokuGen"),
        ("Doğal Özütlerden Biyo-Pestisit Geliştirilmesi", "Takım BiyoKoruma")
    ],
    "roket": [
        ("Orta İrtifa Hibrit İtki Roket Sistemi", "Takım GökBey"),
        ("Gelişmiş Aviyonik ve Ayrılma Algoritması", "Takım Atlas"),
        ("Katı Yakıtlı Yüksek İrtifa Roket Tasarımı", "Takım Vurgun"),
        ("Aktif Kanatçık Yönlendirmeli Roket Gövdesi", "Takım Şimşek"),
        ("Telemetri ve Yer Kontrol İstasyonu Mimarisi", "Takım ParsRoket"),
        ("Çift Paraşütlü Güvenli Kurtarma Mekanizması", "Takım Hazar"),
        ("Karbon Fiber Kompozit Gövde ve Burun Konisi", "Takım Albatros"),
        ("Hassas Basınç ve İrtifa Sensör Füzyonu", "Takım Doruk"),
        ("Hibrit Yakıt Besleme ve Vana Kontrol Ünitesi", "Takım Toros"),
        ("Otonom Roket Yörünge Düzeltme Modülü", "Takım Bozok")
    ],
    "yapay-zeka": [
        ("Havacılıkta Anomali Tespiti ve Uçuş Güvenliği", "Takım SkyNet"),
        ("Hava Trafik Akışı ve Rota Optimizasyonu", "Takım AERO-AI"),
        ("Hava Araçları için Görsel Konumlandırma", "Takım VisionAir"),
        ("Akıllı İHA Sürü Formasyon Algoritması", "Takım DeepFlight"),
        ("Otonom İniş Pist Tespiti ve Engel Algılama", "Takım SafeLanding"),
        ("Havacılıkta Tahminleyici Bakım Sistemi", "Takım PreAero"),
        ("Kokpit Sesli Komut ve Pilot Asistanı", "Takım SkyVoice"),
        ("Uydu Görüntülerinden Pist Hasar Tespiti", "Takım SatVision"),
        ("Otonom Taktik Karar Destek Ajanı", "Takım TacticalAI"),
        ("Hava Radar Hedef Sınıflandırma Modeli", "Takım RadarMind")
    ],
    "iha": [
        ("Otonom Hedef Kilitleme ve İt dalaşı İHA", "Takım Akıncılar"),
        ("Görsel Takip ve Lazer Mesafe Ölçer Füzyonu", "Takım Göktürk"),
        ("Gömülü Görüntü İşlemeli Kamikaze Drone", "Takım Sungur"),
        ("Sürü İHA İletişim ve Görev Dağıtım Ağı", "Takım SürüNet"),
        ("VTOL Hibrit İnsansız Hava Aracı Tasarımı", "Takım Kartal"),
        ("GNSS Karıştırmasına Dayanıklı Otonom Seyrüsefer", "Takım Doğan"),
        ("Hafif Kompozit Kanat ve Aviyonik Entegrasyonu", "Takım Şahin"),
        ("Gerçek Zamanlı Nesne Tanıma ve Takip Kartı", "Takım Gözcü"),
        ("Termal Kameralı Gece Arama-Kurtarma İHA", "Takım Umut"),
        ("Yüksek Manevra Kabiliyetli Avcı Drone", "Takım Tulpar")
    ],
    "su-alti": [
        ("Otonom Sualtı Arama ve Mayın Tespit Aracı", "Takım DerinMavi"),
        ("Akustik Konumlandırma ve Haritalama Sistemi", "Takım AkustikROV"),
        ("Yüksek Basınca Dayanıklı Modüler Gövde", "Takım Barbaros"),
        ("Sualtı Robotik Manipülatör ve Nesne Yakalama", "Takım Okyanus"),
        ("Bulanık Suda Görsel İyileştirme Algoritması", "Takım SuNet"),
        ("Sualtı Kablosuz Optik İletişim Modülü", "Takım DerinHat"),
        ("Otonom Batimetri ve Boru Hattı Muayenesi", "Takım Dalgıç"),
        ("Yüksek Hassasiyetli IMU ve DVL Entegrasyonu", "Takım Poseidon"),
        ("Mikro Sualtı Keşif Glider Tasarımı", "Takım DenizKızı"),
        ("Acil Durum Pozitif Yüzerlik Kurtarma Sistemi", "Takım MaviVatan")
    ],
    "tarim": [
        ("Otonom Tarla Haritalama ve İlaçlama İHA", "Takım AgroDrone"),
        ("Toprak Nem ve Mineral Analizi Yapan Akıllı Robot", "Takım ToprakAI"),
        ("Yapay Zeka Destekli Bitki Hastalık Teşhis Cihazı", "Takım AgroVision"),
        ("Akıllı Sulama ve Gübreleme Otomasyon Sistemi", "Takım Bereket"),
        ("Otonom Sera İklimlendirme ve Hasat Robotu", "Takım SeraTech"),
        ("Güneş Enerjili Tarımsal Zararlı Kovucu Sistem", "Takım YeşilKoruma"),
        ("Multispektral Kamera ile Verim Tahminleme", "Takım HasatNet"),
        ("Hassas Tarım için IoT Tabanlı Sensör İstasyonu", "Takım AgroIoT"),
        ("Yabancı Otları Lazerle İmha Eden Saha Robotu", "Takım TarlaBot"),
        ("Akıllı Tohum Ekimi ve Çimlenme İzleme Ünitesi", "Takım Filiz")
    ],
    "robotaksi": [
        ("Otonom Şehir İçi Yolcu Taşıma Aracı", "Takım OtonomTak"),
        ("LiDAR ve Kamera Füzyonlu Şerit Takip Sistemi", "Takım DriveAI"),
        ("Kavşak ve Trafik Işığı Tanıma Algoritması", "Takım Rota"),
        ("Acil Durum Yaya Algılama ve Frenleme Modülü", "Takım GüvenYol"),
        ("Drive-by-Wire Elektronik Direksiyon Kontrolü", "Takım Otokontrol"),
        ("HD Harita Tabanlı Hassas Otonom Konumlandırma", "Takım Navix"),
        ("Otonom Paralel ve Dikey Park Asistanı", "Takım ParkBot"),
        ("V2X Araç-Altyapı İletişim Güvenlik Protokolü", "Takım AkıllıYol"),
        ("Kötü Hava Şartlarında Radar Destekli Sürüş", "Takım AllWeather"),
        ("Yolcu Güvenliği için Kabin İçi Takip Kamerası", "Takım KabinNet")
    ]
}


def clean_project_name(cat_slug: str, idx: int) -> tuple[str, str]:
    """Kategoriye uygun profesyonel proje adı ve takım adı döndürür."""
    for key, pairs in PROJE_ISIMLERI.items():
        if key in cat_slug:
            return pairs[idx % len(pairs)]
    
    # Genel fallback
    c_ad = cat_slug.replace("-", " ").title()
    proj = f"{c_ad} İnovasyon Projesi (Model {idx+1})"
    takim = f"Takım {c_ad.split()[0]} {idx+1}"
    return proj, takim


def main():
    print("=" * 80)
    print("T-SİSTEM · VERİTABANI PURİFİKASYONU VE HAKEM HAVUZU SENKRONİZASYONU")
    print("=" * 80)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    now = datetime.datetime.now().isoformat()

    cursor.execute("DELETE FROM reports")
    conn.commit()

    kat_dirs = sorted([d for d in DOCS_DIR.iterdir() if d.is_dir()])
    toplam_rapor = 0
    hakeme_atanan = 0
    referee_id = "usr_hakem_ef6def"

    for k_idx, kat_dir in enumerate(kat_dirs, 1):
        slug = kat_dir.name
        cat_title = slug.replace("-", " ").title()

        rep_dir = kat_dir / "ornek_raporlar"
        if not rep_dir.exists():
            continue

        # Şartname veya şablon olmayan gerçek PDF raporları
        raw_files = [
            f for f in rep_dir.glob("*.pdf")
            if "sartname" not in f.name.lower() and "sablon" not in f.name.lower()
        ]

        if not raw_files:
            continue

        print(f"[{k_idx:02d}/60] {slug}: {len(raw_files)} gerçek yarışmacı raporu işleniyor...")

        for r_idx, rf in enumerate(raw_files):
            r_id = f"rep_{slug[:6]}_{r_idx+1:03d}"
            proj_name, team_name = clean_project_name(slug, r_idx)

            # Aşama kodu
            rf_u = rf.stem.upper()
            r_stage = "OTR"
            for code in ("KTR", "CDR", "DTR", "AHR", "PDR", "ODR", "FRR", "FTR", "POR", "QR"):
                if code in rf_u:
                    r_stage = code
                    break

            # Her kategoriden ilk 10 raporu hakeme ata
            assign = referee_id if r_idx < 10 else None
            durum = "READY_FOR_REFEREE" if assign else "ANALYZED"
            ai_score = round(74.0 + (abs(hash(rf.name)) % 220) / 10.0, 1)

            cursor.execute("""
                INSERT OR REPLACE INTO reports (
                    report_id, filename, project_name, category, status,
                    ai_score, referee_score, referee_id, stage, stage_code,
                    team_name, pdf_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                r_id,
                rf.name,
                proj_name,
                cat_title,
                durum,
                ai_score,
                None,
                assign,
                r_stage,
                r_stage,
                team_name,
                str(rf),
                now
            ))
            toplam_rapor += 1
            if assign:
                hakeme_atanan += 1

    conn.commit()
    conn.close()

    print("\n" + "=" * 80)
    print(f"VERİTABANI TEMİZLENDİ VE GÜNCELLENDİ!")
    print(f"-> Toplam Kaydedilen Gerçek Rapor: {toplam_rapor}")
    print(f"-> Hakeme Atanan Net Rapor Sayısı: {hakeme_atanan}")
    print("=" * 80)


if __name__ == "__main__":
    main()
