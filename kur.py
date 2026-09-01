"""T-Sistem · TEK KOMUTLA KURULUM.

    python kur.py            # yalnizca kontrol eder, hicbir sey degistirmez
    python kur.py --uygula   # eksikleri tamamlar ve semayi kurar

Ne yapar
--------
1. Python surumu ve gerekli paketleri kontrol eder
2. `.env` dosyasini kontrol eder; EKSIK olan yeni degiskenleri ekler
   (mevcut anahtarlariniza DOKUNMAZ)
3. Word -> PDF motorunu kontrol eder
4. Cloudflare D1 ve R2 baglantisini test eder
5. Var olan ESKI tablolari yeni semaya tasir (veri kaybi olmadan)
6. 20 tabloluk semayi uygular ve dogrular
7. Sirada ne yapmaniz gerektigini soyler
"""

from __future__ import annotations

import argparse
import importlib
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV_PATH = ROOT / ".env"

OK = "  [OK]  "
UYARI = "  [!]   "
HATA = "  [HATA]"
BILGI = "        "

GEREKLI_PAKETLER = [
    ("streamlit", "streamlit"), ("pydantic", "pydantic"), ("boto3", "boto3"),
    ("requests", "requests"), ("pymupdf", "pymupdf"), ("docx", "python-docx"),
    ("plotly", "plotly"), ("pandas", "pandas"), ("reportlab", "reportlab"),
    ("dotenv", "python-dotenv"),
]
ISTEGE_BAGLI = [
    ("argon2", "argon2-cffi", "Parola guvenligi (yoksa PBKDF2 kullanilir)"),
    ("anthropic", "anthropic", "Claude saglayicisi"),
    ("openai", "openai", "OpenAI saglayicisi"),
    ("groq", "groq", "Groq saglayicisi"),
    ("mammoth", "mammoth", "DOCX onizleme"),
]

# Yeni kodun ihtiyac duydugu, eski .env'de OLMAYAN degiskenler
YENI_DEGISKENLER = [
    ("TSISTEM_DB_BACKEND", "d1",
     "Veri kaynagi: d1 (bulut) veya sqlite (yerel)"),
    ("CLOUDFLARE_R2_PUBLIC_URL", "",
     "R2 custom domain adresiniz (or. https://dosya.tsistem.org). "
     "Bos birakirsaniz sistem otomatik presigned URL uretir."),
    ("TSISTEM_JWT_SECRET", None,
     "FastAPI oturum imzasi (otomatik uretilir)"),
    ("TSISTEM_OAUTH_REDIRECT", "http://localhost:8501",
     "Google girisi donus adresi"),
    ("TSISTEM_ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929",
     "Gecerli Claude model kimligi (eskisi gecersizdi)"),
    ("TSISTEM_GROQ_MODEL", "llama-3.3-70b-versatile", "Groq modeli"),
    ("TSISTEM_OPENAI_MODEL", "gpt-4o-mini", "OpenAI modeli"),
    ("TSISTEM_LLM_ORDER", "anthropic,groq,openai", "Saglayici deneme sirasi"),
    ("TSISTEM_SIMILARITY_MODE", "hybrid", "literal | semantic | hybrid"),
    ("TSISTEM_EMBEDDING_MODEL", "@cf/baai/bge-m3", "Anlamsal benzerlik modeli"),
    ("CLOUDFLARE_VECTORIZE_INDEX", "t-sistem-raporlar", "Vectorize indeks adi"),
    ("CORS_ALLOWED_ORIGINS", "http://localhost:8501", "FastAPI icin izinli adresler"),
]

_sorunlar: list[str] = []
_yapilacaklar: list[str] = []


def baslik(no: int, metin: str) -> None:
    print(f"\n{no}. {metin}")
    print("   " + "-" * (len(metin) + 2))


# ═══════════════════════════════════════════════════════════════════════════
def adim_python() -> None:
    baslik(1, "PYTHON VE PAKETLER")
    surum = sys.version_info
    if surum < (3, 10):
        print(f"{HATA} Python {surum.major}.{surum.minor} — en az 3.10 gerekli")
        _sorunlar.append("Python 3.10+ kurun")
    else:
        print(f"{OK} Python {surum.major}.{surum.minor}.{surum.micro}")

    eksik: list[str] = []
    for modul, paket in GEREKLI_PAKETLER:
        try:
            importlib.import_module(modul)
        except ImportError:
            eksik.append(paket)
    if eksik:
        print(f"{HATA} Eksik paket: {', '.join(eksik)}")
        _yapilacaklar.append("pip install -r requirements.txt")
    else:
        print(f"{OK} {len(GEREKLI_PAKETLER)} zorunlu paket kurulu")

    for modul, paket, aciklama in ISTEGE_BAGLI:
        try:
            importlib.import_module(modul)
        except ImportError:
            print(f"{UYARI} {paket} yok — {aciklama}")


def adim_env(uygula: bool) -> None:
    baslik(2, "ORTAM DEGISKENLERI (.env)")
    if not ENV_PATH.exists():
        print(f"{HATA} .env bulunamadi. `.env.example` dosyasini `.env` olarak kopyalayin.")
        _sorunlar.append(".env dosyasi yok")
        return

    satirlar = ENV_PATH.read_text(encoding="utf-8").splitlines()
    mevcut = {
        s.split("=", 1)[0].strip()
        for s in satirlar
        if "=" in s and not s.strip().startswith("#")
    }

    zorunlu = [
        "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_D1_DATABASE_ID", "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_R2_ACCESS_KEY", "CLOUDFLARE_R2_SECRET_KEY",
        "CLOUDFLARE_R2_ENDPOINT_URL", "CLOUDFLARE_R2_BUCKET_NAME",
    ]
    eksik_zorunlu = [d for d in zorunlu if d not in mevcut]
    if eksik_zorunlu:
        print(f"{HATA} Eksik zorunlu degisken: {', '.join(eksik_zorunlu)}")
        _sorunlar.append("Cloudflare kimlik bilgileri eksik")
    else:
        print(f"{OK} Cloudflare kimlik bilgileri mevcut (degistirilmedi)")

    llm = [d for d in ("ANTHROPIC_API_KEYS", "GROQ_API_KEYS", "OPENAI_API_KEYS",
                       "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY")
           if d in mevcut]
    if llm:
        print(f"{OK} LLM anahtarlari mevcut: {', '.join(sorted(set(d.split('_API')[0] for d in llm)))}")
    else:
        print(f"{UYARI} Hicbir LLM anahtari yok — AI analizleri calismaz")

    eklenecek = [(ad, deger, acik) for ad, deger, acik in YENI_DEGISKENLER if ad not in mevcut]
    if not eklenecek:
        print(f"{OK} Yeni degiskenlerin hepsi tanimli")
        return

    print(f"{UYARI} {len(eklenecek)} yeni degisken eksik:")
    for ad, _, acik in eklenecek:
        print(f"{BILGI}   {ad} — {acik}")

    if not uygula:
        _yapilacaklar.append("python kur.py --uygula   (yeni degiskenleri .env'e ekler)")
        return

    yedek = ENV_PATH.with_suffix(".env.yedek")
    shutil.copy2(ENV_PATH, yedek)
    ek = ["", "# ─── Yeni veri katmani icin eklenen degiskenler ───"]
    for ad, deger, acik in eklenecek:
        if deger is None:
            deger = secrets.token_urlsafe(48)
        ek.append(f"# {acik}")
        ek.append(f"{ad}={deger}")
    ENV_PATH.write_text(
        ENV_PATH.read_text(encoding="utf-8").rstrip() + "\n" + "\n".join(ek) + "\n",
        encoding="utf-8",
    )
    print(f"{OK} {len(eklenecek)} degisken .env'e eklendi (yedek: {yedek.name})")
    if any(ad == "CLOUDFLARE_R2_PUBLIC_URL" for ad, _, _ in eklenecek):
        _yapilacaklar.append(
            "CLOUDFLARE_R2_PUBLIC_URL degerini .env icinde custom domain adresinizle doldurun"
        )


def adim_word() -> None:
    baslik(3, "WORD -> PDF MOTORU")
    try:
        sys.path.insert(0, str(ROOT))
        from src.services.doc_converter import diagnostics
    except ImportError as exc:
        print(f"{HATA} doc_converter okunamadi: {exc}")
        return
    tani = diagnostics()
    if tani["ready"]:
        print(f"{OK} Motor hazir: {', '.join(tani['engines'])}")
        if tani["soffice_path"]:
            print(f"{BILGI}   LibreOffice: {tani['soffice_path']}")
    else:
        print(f"{UYARI} Word -> PDF motoru yok. Sablon yuklerken PDF uretilmez.")
        if os.name == "nt":
            print(f"{BILGI}   Windows: LibreOffice kurun (libreoffice.org) veya MS Word yeterli")
        else:
            print(f"{BILGI}   sudo apt-get install -y libreoffice-writer fonts-dejavu fonts-liberation")
        _yapilacaklar.append("LibreOffice kurun (Word sablonlarindan PDF uretimi icin)")
    for uyari in tani.get("font_warnings", []):
        print(f"{UYARI} {uyari}")


def adim_baglanti() -> bool:
    baslik(4, "CLOUDFLARE BAGLANTISI")
    try:
        from src.data.client import D1Client, DataError, NotConfigured
        from src.data.r2 import get_r2
    except ImportError as exc:
        print(f"{HATA} Veri katmani okunamadi: {exc}")
        return False

    try:
        istemci = D1Client()
    except NotConfigured as exc:
        print(f"{HATA} {exc}")
        _sorunlar.append("Cloudflare kimlik bilgileri eksik")
        return False

    print(f"{BILGI}   Backend: {istemci.backend}")
    saglik = istemci.healthcheck()
    if saglik.get("ok"):
        print(f"{OK} D1 baglantisi calisiyor ({saglik['latency_ms']} ms · "
              f"{saglik['tables']} tablo)")
    else:
        print(f"{HATA} D1: {saglik.get('error')}")
        _sorunlar.append("D1'e baglanilamadi — CLOUDFLARE_API_TOKEN yetkilerini kontrol edin")
        return False

    r2 = get_r2().healthcheck()
    if r2.get("ok"):
        print(f"{OK} R2 baglantisi calisiyor (bucket: {r2['bucket']} · "
              f"public: {r2['public_url']})")
    else:
        print(f"{UYARI} R2: {r2.get('error')}")
        _yapilacaklar.append("R2 erisimini kontrol edin (dosya yukleme calismaz)")
    return True


def adim_sema(uygula: bool) -> None:
    baslik(5, "VERITABANI SEMASI")
    from src.data.migrate import apply_schema, seed_calibration, upgrade_legacy, verify_schema

    hedef = "d1" if os.getenv("TSISTEM_DB_BACKEND", "d1") == "d1" else "sqlite"

    print("   Eski tablolar taraniyor...")
    islemler = upgrade_legacy(hedef, dry_run=not uygula)
    if not uygula and any(islemler.values()):
        _yapilacaklar.append("python kur.py --uygula   (semayi kurar)")
        return
    if not uygula:
        return

    apply_schema(hedef)
    seed_calibration(hedef)
    if verify_schema(hedef):
        print(f"\n{OK} Sema tutarli")
    else:
        print(f"\n{UYARI} Sema uyusmazligi var — yukaridaki listeyi inceleyin")


def adim_hesaplar() -> None:
    baslik(6, "HESAPLAR")
    try:
        from src.data import repos
    except ImportError:
        return
    try:
        kullanicilar = repos().users.list(limit=200)
    except Exception as exc:  # noqa: BLE001 - kurulum araci, sebebi gosterilir
        print(f"{UYARI} Kullanici listesi okunamadi: {exc}")
        return

    if not kullanicilar:
        print(f"{UYARI} Hic kullanici yok.")
        print(f"{BILGI}   .env icinde TSISTEM_BOOTSTRAP=1, TSISTEM_ADMIN_EMAIL ve")
        print(f"{BILGI}   TSISTEM_ADMIN_PASSWORD tanimlayip su komutu calistirin:")
        print(f"{BILGI}   python -c \"from src.data import repos; print(repos().users.bootstrap_admin())\"")
        _yapilacaklar.append("Ilk yonetici hesabini olusturun")
        return

    sayim: dict[str, int] = {}
    for kullanici in kullanicilar:
        sayim[kullanici.role.value] = sayim.get(kullanici.role.value, 0) + 1
    print(f"{OK} {len(kullanicilar)} kullanici mevcut: "
          + " · ".join(f"{rol}={adet}" for rol, adet in sorted(sayim.items())))
    print(f"{BILGI}   Mevcut parolalariniz AYNEN calisir; ilk giriste hash otomatik")
    print(f"{BILGI}   guclendirilir (SHA-256 -> Argon2). Yeniden kayit gerekmez.")


def adim_veri() -> None:
    baslik(7, "YARISMA VERISI")
    try:
        from src.data import repos
        from src.data.enums import PublishStatus
        toplam = repos().competitions.count()
        yayinda = repos().competitions.count(PublishStatus.YAYINDA)
    except Exception as exc:  # noqa: BLE001
        print(f"{UYARI} Yarisma sayisi okunamadi: {exc}")
        return

    if toplam == 0:
        print(f"{UYARI} Veritabaninda hic yarisma yok.")
        print(f"{BILGI}   60 yarismayi tasimak icin:")
        print(f"{BILGI}   python scripts/migrate_dataset.py --source <klasor> \\")
        print(f"{BILGI}       --plan data/competition_migration_plans.json --report rapor.md")
        print(f"{BILGI}   (once kuru calistirma; sonra --apply ekleyin)")
        _yapilacaklar.append("60 yarismayi Cloudflare'e tasiyin (scripts/migrate_dataset.py)")
    else:
        print(f"{OK} {toplam} yarisma kayitli ({yayinda} tanesi yayinda)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="T-Sistem kurulum araci")
    parser.add_argument("--uygula", action="store_true",
                        help="Eksikleri tamamla ve semayi kur (varsayilan: yalnizca kontrol)")
    args = parser.parse_args(argv)

    print("=" * 70)
    print("T-SISTEM KURULUM" + ("  ·  UYGULAMA MODU" if args.uygula else "  ·  KONTROL MODU"))
    print("=" * 70)

    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_PATH)
    except ImportError:
        pass

    sys.path.insert(0, str(ROOT))

    adim_python()
    adim_env(args.uygula)
    adim_word()
    if adim_baglanti():
        adim_sema(args.uygula)
        adim_hesaplar()
        adim_veri()

    print("\n" + "=" * 70)
    if _sorunlar:
        print("COZULMESI GEREKEN SORUNLAR")
        for sorun in _sorunlar:
            print(f"  - {sorun}")
    if _yapilacaklar:
        print("\nSIRADAKI ADIMLAR")
        for adim in dict.fromkeys(_yapilacaklar):
            print(f"  - {adim}")
    if not _sorunlar and not _yapilacaklar:
        print("HER SEY HAZIR")
        print("\nUygulamayi baslatin:")
        print("  streamlit run src/ui/app.py")
    elif not args.uygula:
        print("\nBunlari otomatik yapmak icin:  python kur.py --uygula")
    print("=" * 70)
    return 1 if _sorunlar else 0


if __name__ == "__main__":
    sys.exit(main())
