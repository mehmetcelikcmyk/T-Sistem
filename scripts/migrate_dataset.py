#!/usr/bin/env python3
"""T-Sistem · Faz 2 veri migrasyonu: yerel klasor -> Cloudflare D1 + R2.

Girdi
-----
`data/competition_migration_plans.json` (60 yarismalik hazir envanter) ve
envanterdeki `path` alanlarinin isaret ettigi yerel `teknofest_yarismalar`
klasoru.

Cikti
-----
1. D1/SQLite: `competitions`, `competition_specs`, `competition_stages`
2. R2: `Keys.spec()` / `Keys.template()` ile uretilen anahtarlar
3. Markdown migrasyon raporu (yarisma x sartname x asama x sablon matrisi)

Tasarim kararlari
-----------------
* VARSAYILAN MOD `--dry-run`. Hicbir yazma islemi `--apply` verilmeden olmaz.
* `SABLON` ve `YARISMACI_RAPORLARI` gercek asama degil, klasor adidir.
  - `SABLON` altindaki dosyalar varsayilan asamaya TASINIR (veri kaybi olmasin).
  - `YARISMACI_RAPORLARI` altindakiler Faz 2 KAPSAMI DISIDIR (bunlar yarismaci
    teslimleridir, `reports` tablosuna app_id ile girer). Rapora ayrica yazilir.
* Hic gecerli asamasi kalmayan yarismaya `CompetitionRepo.ensure_default_stage()`
  ile `is_auto_generated=1` OTR eklenir (KARAR #2).
* Dosya adlari sunucu uyumlu (`slugify`), DB'deki `title`/`original_name`
  insan okunabilir kalir.
* IDEMPOTENT: ikinci calistirma duplicate uretmez. `competition_specs` ve
  `competition_stages` tablolarinda `branch_code` NULL olabildigi ve SQLite'ta
  NULL degerler UNIQUE kisitinda birbirinden farkli sayildigi icin, mevcut
  satirlar once ARANIR, kimlikleri korunarak guncellenir.
* Hata YUTULMAZ: her hata rapora yazilir ve cikis kodu != 0 olur.

Kullanim
--------
    python3 scripts/migrate_dataset.py --plan data/competition_migration_plans.json
    python3 scripts/migrate_dataset.py --apply --source ~/teknofest_yarismalar
    python3 scripts/migrate_dataset.py --apply --skip-r2 --only roket-yarismasi
    python3 scripts/migrate_dataset.py --limit 5 --report rapor.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, Sequence

# Proje kokunu import yoluna ekle (scripts/ -> proje koku).
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.data import Keys, Repos, repos, slugify  # noqa: E402
from src.data.client import DataError  # noqa: E402
from src.data.enums import PublishStatus, SpecStatus, TeamLevel  # noqa: E402
from src.data.models import Competition, CompetitionSpec, Stage, now_iso  # noqa: E402
from src.data.r2 import R2Client, StorageError  # noqa: E402
from src.data.repo.competitions import (  # noqa: E402
    DEFAULT_STAGE_CODE,
    DEFAULT_STAGE_NAME,
    CompetitionRepo,
)


class MigrationError(RuntimeError):
    """Migrasyonu durduran kurulum/girdi hatasi."""


# ═══════════════════════════════════════════════════════════════════════════
# SABITLER
# ═══════════════════════════════════════════════════════════════════════════

# Plan JSON'undaki Windows yollarinin ortak kokunu bulmak icin isaretci.
PLAN_ROOT_MARKER = "teknofest_yarismalar"

# Klasor adi olup asama olmayan sahte kodlar (KARAR: bunlar elenir).
PSEUDO_STAGE_TEMPLATE = "SABLON"              # icerigi varsayilan asamaya tasinir
PSEUDO_STAGE_REPORTS = "YARISMACI_RAPORLARI"  # Faz 2 kapsami disi

# DB'de sablon icin yalnizca docx ve pdf kolonu var; digerleri "ek dosya".
TEMPLATE_DOCX_EXT = ".docx"
TEMPLATE_PDF_EXT = ".pdf"

# Asama kodu -> insan okunabilir Turkce ad.
STAGE_NAMES: dict[str, str] = {
    "OTR": "Ön Tasarım Raporu",
    "OAR": "Ön Aşama Raporu",
    "ODR": "Ön Değerlendirme Raporu",
    "ATR": "Ara Tasarım Raporu",
    "DTR": "Detaylı Tasarım Raporu",
    "KTR": "Kritik Tasarım Raporu",
    "FTR": "Final Tasarım Raporu",
    "FDR": "Final Değerlendirme Raporu",
    "DDR": "Detaylı Değerlendirme Raporu",
    "PDR": "Proje Detay Raporu",
    "PSR": "Proje Sonuç Raporu",
    "TTR": "Teknik Tasarım Raporu",
    "TYR": "Teknik Yeterlilik Raporu",
    "TYF": "Teknik Yeterlilik Formu",
    "PVT": "Proje Videosu ve Tanıtımı",
    "AHR": "Atış Hazırlık Raporu",
}

# Rapor akisindaki mantiksal siralama (order_index uretimi icin).
STAGE_ORDER: tuple[str, ...] = (
    "OTR", "OAR", "ODR", "ATR", "DTR", "KTR", "FTR", "FDR",
    "DDR", "PDR", "TTR", "TYR", "TYF", "AHR", "PSR", "PVT",
)

# Seviye etiketleri — `TeamLevel` enum degerleriyle AYNI yazim kullanilir,
# aksi halde `applications`/`reports` eslesmesi bozulur (ASCII, Turkce yok).
LEVEL_ALIASES: dict[str, str] = {
    "genel": TeamLevel.GENEL.value,
    "ilkokul": "Ilkokul",
    "ortaokul": TeamLevel.ORTAOKUL.value,
    "lise": TeamLevel.LISE.value,
    "yildizlar": TeamLevel.LISE.value,
    "universite": TeamLevel.UNIVERSITE.value,
    "universite_ve_uzeri": TeamLevel.UNIVERSITE.value,
    "mezun": TeamLevel.MEZUN.value,
    "serbest_girisimci": "Serbest Girisimci",
}

# Alan (domain) tahmini — SIRA ONEMLIDIR, ilk eslesen kazanir.
DOMAIN_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("roket", "iha", "hava", "uydu", "drone", "uzay"), "Havacılık ve Uzay"),
    (("yapay_zeka", "veri"), "Yapay Zeka"),
    (("saglik", "onkoloji", "biyo"), "Sağlık"),
    (("enerji", "elektrikli"), "Enerji"),
    (("blokzincir", "finansal", "e_ticaret"), "Dijital Teknolojiler"),
    (("insansiz_deniz", "denizalti", "su_alti", "mavi_vatan", "deniz"), "Denizcilik"),
    (("robo", "mekatronik"), "Robotik"),
    (("cip", "kuantum", "elektronik"), "Elektronik ve Yarı İletken"),
    (("egitim", "mesleki"), "Eğitim Teknolojileri"),
)
DOMAIN_FALLBACK = "Teknoloji"

# Slug sozlugu: alt cizgi/tire ile ayrilmis kelimelerin Turkce karsiligi.
SLUG_WORDS: dict[str, str] = {
    "3t": "3T", "5g": "5G", "ajanlari": "Ajanları", "akilli": "Akıllı",
    "alti": "Altı", "anahat": "Anahat", "arac": "Araç", "araci": "Aracı",
    "araclari": "Araçları", "arasi": "Arası", "arastirma": "Araştırma",
    "atik": "Atık", "avci": "Avcı", "bagimliliklarla": "Bağımlılıklarla",
    "bilim": "Bilim", "binek": "Binek", "biyoteknoloji": "Biyoteknoloji",
    "blokzincir": "Blokzincir", "celikkubbe": "Çelikkubbe", "cip": "Çip",
    "cup": "Cup", "degisikligi": "Değişikliği", "deniz": "Deniz",
    "destekli": "Destekli", "dikey": "Dikey", "dil": "Dil",
    "doktora": "Doktora", "dongusel": "Döngüsel", "drone": "Drone",
    "e": "E", "ekonomi": "Ekonomi", "elektrikli": "Elektrikli",
    "elektronik": "Elektronik", "enerji": "Enerji", "film": "Film",
    "finansal": "Finansal", "fpv": "FPV", "gelistirme": "Geliştirme",
    "gorsel": "Görsel", "guneydogu": "Güneydoğu", "guvenligi": "Güvenliği",
    "hackmasters": "HackMasters", "hareketli": "Hareketli", "harp": "Harp",
    "hata": "Hata", "hava": "Hava", "havacilikta": "Havacılıkta",
    "havayolu": "Havayolu", "hyperloop": "Hyperloop", "iha": "İHA",
    "iklim": "İklim", "ile": "ile", "ileri": "İleri", "ilkokul": "İlkokul",
    "inisli": "İnişli", "inovasyon": "İnovasyon", "insanlik": "İnsanlık",
    "insansiz": "İnsansız", "izleme": "İzleme", "jet": "Jet", "kara": "Kara",
    "kuantum": "Kuantum", "kure": "KÜRE", "kutup": "Kutup", "lise": "Lise",
    "liseler": "Liseler", "lojistik": "Lojistik", "madde": "Madde",
    "maden": "Maden", "mavi": "Mavi", "mesleki": "Mesleki",
    "mimari": "Mimari", "model": "Model", "motor": "Motor",
    "mucadelede": "Mücadelede", "nsosyal": "NSosyal", "nukleer": "Nükleer",
    "odulleri": "Ödülleri", "ogrencileri": "Öğrencileri", "oneri": "Öneri",
    "onkolojide": "Onkolojide", "operasyon": "Operasyon",
    "optimizasyonu": "Optimizasyonu", "ortaokul": "Ortaokul",
    "otonom": "Otonom", "pardus": "Pardus", "proje": "Proje",
    "projeleri": "Projeleri", "resim": "Resim", "robolig": "Robolig",
    "robotaksi": "Robotaksi", "robotik": "Robotik", "roket": "Roket",
    "saglikta": "Sağlıkta", "sampiyonasi": "Şampiyonası",
    "sanayide": "Sanayide", "savasan": "Savaşan", "savunma": "Savunma",
    "seviyesi": "Seviyesi", "sifir": "Sıfır", "sistemler": "Sistemler",
    "sistemleri": "Sistemleri", "su": "Su", "suru": "Sürü", "tarim": "Tarım",
    "tasarim": "Tasarım", "teknofest": "TEKNOFEST", "teknolojik": "Teknolojik",
    "teknolojiler": "Teknolojiler", "teknolojileri": "Teknolojileri",
    "terminali": "Terminali", "ticaret": "Ticaret", "tracking": "Tracking",
    "tuba": "TÜBA", "uluslararasi": "Uluslararası", "universite": "Üniversite",
    "uydu": "Uydu", "uygulamalar": "Uygulamalar", "vatan": "Vatan",
    "ve": "ve", "world": "World", "yakalama": "Yakalama", "yapay": "Yapay",
    "yararina": "Yararına", "yarislari": "Yarışları",
    "yarismalari": "Yarışmaları", "yarismasi": "Yarışması", "yazim": "Yazım",
    "yetenek": "Yetenek", "yildizlar": "Yıldızlar", "yol": "Yol",
    "zeka": "Zeka",
}

# Sozlukten cevrilemeyen ozel durumlar (tam slug eslesmesi).
SLUG_TITLE_OVERRIDES: dict[str, str] = {
    "e-ticaret-yarismasi": "E-Ticaret Yarışması",
}

# Dal (branch) adi cikarirken atilacak dolgu kelimeler.
BRANCH_NOISE: frozenset[str] = frozenset({
    "teknofest", "myy", "tr", "en", "sartname", "sartnamesi", "yarismasi",
    "yarisma", "yarismalari", "kategori", "kategorisi", "kategorisi_sartnamesi",
    "kat", "duzeltilmis", "final", "guncel", "v", "ve", "ile", "mesleki",
    "yetenek", "bolum", "senaryo",
})

# "Birinci Senaryo" gibi sirali dal adlari icin.
ORDINALS: dict[str, int] = {
    "birinci": 1, "ikinci": 2, "ucuncu": 3, "dorduncu": 4, "besinci": 5,
    "altinci": 6, "yedinci": 7, "sekizinci": 8, "dokuzuncu": 9, "onuncu": 10,
}

_PERCENT_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_UNDERSCORE_HEX_RUN = re.compile(r"(?:_[0-9A-Fa-f]{2})+")
_RANDOM_SUFFIX_RE = re.compile(r"^[A-Za-z0-9]{5,6}$")
_BOLUM_RE = re.compile(r"bolum_?(\d+)")
_SENARYO_NUM_RE = re.compile(r"senaryo_?(\d+)")
_SENARYO_ORD_RE = re.compile(r"(" + "|".join(sorted(ORDINALS)) + r")_senaryo")
_VERSION_TOKEN_RE = re.compile(r"^v?\d+([._]\d+)*$", re.IGNORECASE)

_TR_LOWER_MAP = str.maketrans({"I": "ı", "İ": "i"})
_TR_UPPER_MAP = str.maketrans({"i": "İ", "ı": "I"})


# ═══════════════════════════════════════════════════════════════════════════
# METIN YARDIMCILARI
# ═══════════════════════════════════════════════════════════════════════════

def tr_lower(text: str) -> str:
    """Turkce kurallariyla kucuk harfe cevirir (I -> i degil, I -> ı)."""
    return text.translate(_TR_LOWER_MAP).lower()


def tr_upper(text: str) -> str:
    """Turkce kurallariyla buyuk harfe cevirir (i -> İ)."""
    return text.translate(_TR_UPPER_MAP).upper()


def tr_capitalize(word: str) -> str:
    """Turkce bas harf buyutme: 'istanbul' -> 'İstanbul'."""
    if not word:
        return word
    return tr_upper(word[0]) + tr_lower(word[1:])


def _decode_underscore_hex(text: str) -> str:
    """`_C4_B0` bicimindeki bozuk URL kodlamasini cozer (%'ler _ olmus).

    Yalnizca cozulen bayt dizisi GECERLI UTF-8 ve tamami ASCII disi yazdirilabilir
    karakter ise degistirir. Boylece `_A2_A3` (gecersiz UTF-8) veya `_17` (kontrol
    karakteri) gibi gercek dosya adi parcalari bozulmaz.
    """

    def _replace(match: re.Match[str]) -> str:
        raw = match.group(0)
        pairs = [p for p in raw.split("_") if p]
        try:
            decoded = bytes(int(p, 16) for p in pairs).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return raw
        if not decoded:
            return raw
        for char in decoded:
            if ord(char) < 128 or unicodedata.category(char).startswith("C"):
                return raw
        return decoded

    return _UNDERSCORE_HEX_RUN.sub(_replace, text)


def decode_name(raw: str) -> str:
    """URL-encoded dosya adini coz: `%C4%B1` -> `ı`, `_C4_B0` -> `İ`."""
    text = str(raw or "")
    if _PERCENT_RE.search(text):
        try:
            text = urllib.parse.unquote(text, encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            # Kismi/bozuk kodlama: ham hali korunur, rapora dusmesi icin degistirilmez.
            text = urllib.parse.unquote(text, encoding="utf-8", errors="replace")
    return _decode_underscore_hex(text)


def readable_title(slug: str) -> str:
    """Slug'dan insan okunabilir Turkce baslik uretir."""
    override = SLUG_TITLE_OVERRIDES.get(slug)
    if override:
        return override
    words: list[str] = []
    for index, token in enumerate(re.split(r"[-_]+", slug)):
        if not token:
            continue
        mapped = SLUG_WORDS.get(token)
        if mapped is None:
            mapped = tr_capitalize(token)
        elif index == 0 and mapped == mapped.lower():
            # Baslik ilk kelimesi kucuk kalmaz ("ve", "ile" gibi baglaclar).
            mapped = tr_capitalize(mapped)
        words.append(mapped)
    return " ".join(words) if words else slug


def guess_domain(slug: str) -> str:
    """Slug anahtar kelimelerinden alan tahmini."""
    key = slug.replace("-", "_").lower()
    # Ozel durum: su alti roketleri havacilik degil denizcilik kapsamindadir.
    if "su_alti" in key and "roket" in key:
        return "Denizcilik"
    for keywords, domain in DOMAIN_RULES:
        for keyword in keywords:
            if keyword in key:
                return domain
    return DOMAIN_FALLBACK


def normalize_level(raw: str | None) -> str:
    """Plan JSON'undaki `detected_level` degerini kanonik seviyeye cevirir."""
    if not raw:
        return TeamLevel.GENEL.value
    key = slugify(str(raw))
    return LEVEL_ALIASES.get(key, tr_capitalize(str(raw).replace("_", " ")))


def normalize_stage_code(raw: str) -> str:
    """Asama kodunu ASCII buyuk harfe indirger (`ÖDR` -> `ODR`).

    R2 anahtarlari ve UNIQUE kisiti icin ASCII zorunludur; kodun kendisi
    kisaltilmaz veya yeniden adlandirilmaz (KARAR #2).
    """
    return slugify(raw).upper()


def stage_name_for(stage_code: str) -> str:
    return STAGE_NAMES.get(stage_code, f"{stage_code} Aşaması")


def stage_order_for(stage_code: str) -> int:
    if stage_code in STAGE_ORDER:
        return STAGE_ORDER.index(stage_code)
    return len(STAGE_ORDER)


# ═══════════════════════════════════════════════════════════════════════════
# DAL (BRANCH) CIKARIMI
# ═══════════════════════════════════════════════════════════════════════════

def _is_random_suffix(token: str) -> bool:
    """`Du4UI`, `OQJqr` gibi rastgele indirme eklerini tanir.

    Olcut: 5-6 alfanumerik karakter, en az bir kucuk harf ve ILK karakterden
    SONRA en az bir buyuk harf. Boylece "Bolum"/"Senaryo" gibi normal
    baslik-bicimli kelimeler elenmez.
    """
    if not _RANDOM_SUFFIX_RE.match(token):
        return False
    if not any(char.islower() for char in token):
        return False
    return any(char.isupper() for char in token[1:])


def _clean_tokens(stem: str) -> list[str]:
    """Dosya adi govdesini anlamli kelimelere ayirir (yil, surum, rastgele ek atilir)."""
    tokens: list[str] = []
    for token in re.split(r"[\s_\-.]+", stem):
        if not token:
            continue
        if token.isdigit() and len(token) == 4:      # yil (2026)
            continue
        if _VERSION_TOKEN_RE.match(token):           # V1, V2.5, 17.07
            continue
        if _is_random_suffix(token):
            continue                                  # rastgele indirme eki (Du4UI)
        tokens.append(token)
    return tokens


def derive_branch(file_name: str, order: int) -> tuple[str, str]:
    """Sartname dosya adindan (branch_code, branch_name) uretir.

    Desteklenen kaliplar (sirayla):
      1. "... BÖLÜM 3 ..."      -> ("bolum_3", "Bölüm 3")
      2. "... Ikinci Senaryo"   -> ("senaryo_2", "Senaryo 2")
      3. "... KAYNAKÇILIK KATEGORİSİ" -> ("kaynakcilik", "Kaynakçılık")
      4. Kalan anlamli kelimeler (en fazla 3 tane).
    Hicbiri tutmazsa sirali yedek ad (`dal_1`) kullanilir.
    """
    stem = decode_name(file_name)
    stem = re.sub(r"\.[A-Za-z0-9]{2,5}$", "", stem)
    # Kalip aramasi ASCII'ye indirgenmis govde uzerinde yapilir: "BOLUM_1" ve
    # "Bolum 1" ayni sonucu verir.
    flat = slugify(stem, max_len=200)

    # 1. BOLUM <n>
    bolum = _BOLUM_RE.search(flat)
    if bolum:
        number = int(bolum.group(1))
        return f"bolum_{number}", f"Bölüm {number}"

    # 2. Senaryo <n> / <sirasayi> Senaryo
    senaryo = _SENARYO_NUM_RE.search(flat)
    if senaryo:
        number = int(senaryo.group(1))
        return f"senaryo_{number}", f"Senaryo {number}"
    ordinal_match = _SENARYO_ORD_RE.search(flat)
    if ordinal_match:
        number = ORDINALS[ordinal_match.group(1)]
        return f"senaryo_{number}", f"Senaryo {number}"

    tokens = _clean_tokens(stem)
    lowered = [tr_lower(t) for t in tokens]

    # 3. "<dal adi> KATEGORISI"
    marker = None
    for index, token in enumerate(lowered):
        if slugify(token).startswith("kategori") or slugify(token) == "kat":
            marker = index
            break
    candidates = tokens[:marker] if marker is not None else tokens

    # 4. Dolgu kelimeleri at, en fazla 3 kelime birak.
    meaningful = [t for t in candidates if slugify(t) not in BRANCH_NOISE and slugify(t)]
    meaningful = [t for t in meaningful if not slugify(t).endswith("yarismasi")]
    meaningful = [t for t in meaningful if not slugify(t).endswith("sartnamesi")]
    if not meaningful:
        return f"dal_{order}", f"Dal {order}"
    picked = meaningful[:3]
    code = slugify("_".join(picked), max_len=40)
    name = " ".join(tr_capitalize(word) for word in picked)
    return (code or f"dal_{order}"), name


# ═══════════════════════════════════════════════════════════════════════════
# PLANLAMA MODELLERI
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class PlannedFile:
    """R2'ye yuklenecek tek dosya."""

    source: Path
    original_name: str          # insan okunabilir (cozulmus) ad
    raw_name: str               # plan JSON'undaki ham ad
    r2_key: str
    size_kb: float
    exists: bool = False
    uploaded: bool = False


@dataclass
class PlannedSpec:
    title: str
    branch_code: str | None
    branch_name: str | None
    is_primary: bool
    file: PlannedFile


@dataclass
class PlannedStage:
    stage_code: str
    stage_name: str
    level: str
    order_index: int
    is_auto_generated: bool = False
    docx: PlannedFile | None = None
    pdf: PlannedFile | None = None
    extras: list[PlannedFile] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def all_files(self) -> list[PlannedFile]:
        files = [f for f in (self.docx, self.pdf) if f is not None]
        return files + self.extras


@dataclass
class PlannedCompetition:
    slug: str
    name: str
    domain: str
    levels: str
    specs: list[PlannedSpec] = field(default_factory=list)
    stages: list[PlannedStage] = field(default_factory=list)
    out_of_scope: list[PlannedFile] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class Config:
    source: Path
    plan: Path
    apply: bool
    only: list[str]
    skip_r2: bool
    limit: int | None
    report: Path | None
    overwrite_metadata: bool


# ═══════════════════════════════════════════════════════════════════════════
# MIGRASYON
# ═══════════════════════════════════════════════════════════════════════════

class Migrator:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.repos: Repos | None = None
        self.competitions: CompetitionRepo | None = None
        self.storage: R2Client | None = None
        self.r2_enabled = False

        self.used_keys: set[str] = set()
        self.plans: list[PlannedCompetition] = []
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.missing_files: list[tuple[str, str]] = []   # (slug, yol)
        self.counters: dict[str, int] = {
            "competitions": 0,
            "specs": 0,
            "branches": 0,
            "stages": 0,
            "stages_auto": 0,
            "templates_docx": 0,
            "templates_pdf": 0,
            "templates_extra": 0,
            "files_total": 0,
            "files_uploaded": 0,
            "files_out_of_scope": 0,
        }

    # ── kayit ─────────────────────────────────────────────────────────────
    def log(self, message: str) -> None:
        print(message, flush=True)

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        print(f"  [UYARI] {message}", flush=True)

    def fail(self, message: str) -> None:
        """Hatayi kaydeder — YUTMAZ. Cikis kodu bu listeye gore belirlenir."""
        self.errors.append(message)
        print(f"  [HATA] {message}", flush=True)

    # ── baglantilar ───────────────────────────────────────────────────────
    def connect(self) -> None:
        """Veri katmanini acar. `--dry-run` modunda baglanti ZORUNLU degildir."""
        try:
            self.repos = repos()
        except DataError as exc:
            if self.cfg.apply:
                raise MigrationError(f"Veri katmani acilamadi: {exc}") from exc
            self.warn(f"Veri katmani acilamadi, mevcut kayit kontrolu atlanacak: {exc}")
            return

        self.competitions = self.repos.competitions
        self.storage = self.repos.storage
        backend = self.repos.client.backend
        self.log(f"[baglanti] veritabani backend={backend}")

        if self.cfg.skip_r2:
            self.log("[baglanti] R2 devre disi (--skip-r2) — yalnizca D1 yazilacak")
            return
        if not self.storage.is_configured:
            self.warn(
                "R2 kimlik bilgileri eksik (CLOUDFLARE_R2_*). Dosyalar YUKLENMEYECEK, "
                "yalnizca D1 kayitlari ve r2_key degerleri yazilacak."
            )
            return
        self.r2_enabled = True
        health = self.storage.healthcheck()
        if not health.get("ok"):
            self.r2_enabled = False
            self.warn(f"R2 erisim testi basarisiz, yukleme atlanacak: {health.get('error')}")
        else:
            self.log(f"[baglanti] R2 hazir bucket={health['bucket']} url={health['public_url']}")

    # ── plan okuma ────────────────────────────────────────────────────────
    def load_plan(self) -> list[dict[str, Any]]:
        if not self.cfg.plan.is_file():
            raise MigrationError(f"Plan dosyasi bulunamadi: {self.cfg.plan}")
        try:
            raw = json.loads(self.cfg.plan.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MigrationError(f"Plan dosyasi okunamadi ({self.cfg.plan}): {exc}") from exc
        if not isinstance(raw, list):
            raise MigrationError("Plan dosyasi bir yarisma listesi olmali (JSON array).")

        entries = [e for e in raw if isinstance(e, dict) and e.get("slug")]
        if len(entries) != len(raw):
            self.warn(f"Plan icinde {len(raw) - len(entries)} gecersiz kayit atlandi.")
        if self.cfg.only:
            wanted = {s.strip() for s in self.cfg.only if s.strip()}
            entries = [e for e in entries if e["slug"] in wanted]
            missing = wanted - {e["slug"] for e in entries}
            for slug in sorted(missing):
                self.fail(f"--only ile istenen slug plan icinde yok: {slug}")
        if self.cfg.limit is not None:
            entries = entries[: self.cfg.limit]
        return entries

    def local_path(self, raw_path: str) -> Path:
        """Plan JSON'undaki Windows yolunu `--source` altina esler."""
        parts = list(PureWindowsPath(str(raw_path)).parts)
        index = None
        for position, part in enumerate(parts):
            if part.lower() == PLAN_ROOT_MARKER:
                index = position
                break
        relative = parts[index + 1:] if index is not None else parts[-1:]
        return self.cfg.source.joinpath(*relative)

    def unique_key(self, key: str) -> str:
        """Ayni R2 anahtari iki dosyaya verilmesin (or. ayni asamada iki docx)."""
        if key not in self.used_keys:
            self.used_keys.add(key)
            return key
        stem, dot, ext = key.rpartition(".")
        counter = 2
        while True:
            candidate = f"{stem}_{counter}.{ext}" if dot else f"{key}_{counter}"
            if candidate not in self.used_keys:
                self.used_keys.add(candidate)
                return candidate
            counter += 1

    def make_file(self, entry: dict[str, Any], key: str, slug: str) -> PlannedFile:
        raw_name = str(entry.get("orig_name") or "")
        clean = str(entry.get("clean_name") or "") or raw_name
        readable = decode_name(clean)
        path = self.local_path(str(entry.get("path") or ""))
        planned = PlannedFile(
            source=path,
            original_name=readable,
            raw_name=raw_name,
            r2_key=self.unique_key(key) if key else "",
            size_kb=float(entry.get("size_kb") or 0.0),
            exists=path.is_file(),
        )
        self.counters["files_total"] += 1
        if not planned.exists:
            self.missing_files.append((slug, str(path)))
        return planned

    # ── planlama ──────────────────────────────────────────────────────────
    def plan_competition(self, entry: dict[str, Any]) -> PlannedCompetition:
        slug = str(entry["slug"])
        name = readable_title(slug)
        domain = guess_domain(slug)

        planned = PlannedCompetition(slug=slug, name=name, domain=domain, levels="")

        # ── sartnameler ───────────────────────────────────────────────────
        specs = [s for s in entry.get("specs", []) if isinstance(s, dict)]
        specs.sort(key=lambda s: str(s.get("clean_name") or s.get("orig_name") or ""))
        multi = len(specs) > 1
        seen_codes: set[str] = set()
        for order, spec_entry in enumerate(specs, start=1):
            source_name = str(spec_entry.get("clean_name") or spec_entry.get("orig_name") or "")
            if multi:
                code, branch_name = derive_branch(source_name, order)
                while code in seen_codes:
                    code = f"{code}_{order}"
                seen_codes.add(code)
                title = f"{name} - {branch_name} Dalı"
            else:
                code, branch_name, title = None, None, f"{name} Şartnamesi"
            planned_file = self.make_file(spec_entry, Keys.spec(slug, code), slug)
            planned.specs.append(
                PlannedSpec(
                    title=title,
                    branch_code=code,
                    branch_name=branch_name,
                    is_primary=(order == 1),
                    file=planned_file,
                )
            )
        if not specs:
            planned.notes.append("Şartname bekleniyor (plan içinde şartname yok).")

        # ── asamalar ──────────────────────────────────────────────────────
        rehome: list[dict[str, Any]] = []     # SABLON sahte asamasindan tasinacak dosyalar
        raw_stages = [s for s in entry.get("stages", []) if isinstance(s, dict)]
        real_stages: list[dict[str, Any]] = []
        for stage_entry in raw_stages:
            code = normalize_stage_code(str(stage_entry.get("stage_code") or ""))
            files = [f for f in stage_entry.get("files", []) if isinstance(f, dict)]
            if code == PSEUDO_STAGE_TEMPLATE:
                rehome.extend(files)
                if files:
                    planned.notes.append(
                        f"Sahte aşama '{PSEUDO_STAGE_TEMPLATE}' elendi; "
                        f"{len(files)} şablon dosyası varsayılan aşamaya taşındı."
                    )
                continue
            if code == PSEUDO_STAGE_REPORTS:
                for file_entry in files:
                    out_file = self.make_file(file_entry, "", slug)
                    planned.out_of_scope.append(out_file)
                    self.counters["files_out_of_scope"] += 1
                if files:
                    planned.notes.append(
                        f"Sahte aşama '{PSEUDO_STAGE_REPORTS}' elendi; "
                        f"{len(files)} yarışmacı teslimi Faz 2 kapsamı dışında."
                    )
                continue
            if not code:
                self.fail(f"{slug}: boş aşama kodu atlandı.")
                continue
            real_stages.append({"code": code, "files": files})

        for stage_info in sorted(real_stages, key=lambda s: stage_order_for(s["code"])):
            planned.stages.extend(self._plan_stages(slug, stage_info["code"], stage_info["files"]))

        # ── varsayilan asama (KARAR #2) ───────────────────────────────────
        if not planned.stages:
            default_stage = PlannedStage(
                stage_code=DEFAULT_STAGE_CODE,
                stage_name=DEFAULT_STAGE_NAME,
                level=TeamLevel.GENEL.value,
                order_index=0,
                is_auto_generated=True,
            )
            # Varsayilan asama bir yer tutucudur; seviyeye BOLUNMEZ.
            self._attach_files(slug, default_stage, rehome)
            planned.stages.append(default_stage)
            planned.notes.append(
                f"Geçerli aşama bulunamadı; varsayılan {DEFAULT_STAGE_CODE} "
                "aşaması üretildi (is_auto_generated=1)."
            )
        elif rehome:
            # Gecerli asama varken SABLON dosyalari ilk asamaya baglanir.
            self._attach_files(slug, planned.stages[0], rehome)

        # ── seviyeler ─────────────────────────────────────────────────────
        levels: list[str] = []
        for stage in planned.stages:
            if stage.level not in levels:
                levels.append(stage.level)
        for token in re.split(r"[-_]+", slug):
            alias = LEVEL_ALIASES.get(token)
            if alias and alias not in levels:
                levels.append(alias)
        if len(levels) > 1 and TeamLevel.GENEL.value in levels:
            levels.remove(TeamLevel.GENEL.value)
        planned.levels = ", ".join(levels) if levels else TeamLevel.GENEL.value

        for index, stage in enumerate(planned.stages):
            stage.order_index = index
        return planned

    def _plan_stages(
        self, slug: str, code: str, files: Sequence[dict[str, Any]]
    ) -> list[PlannedStage]:
        """Bir asama kodunu `detected_level` degerine gore satirlara boler.

        `competition_stages` UNIQUE kisiti (competition_id, stage_code, level,
        branch_code) seviyeye ozel asama satirini zaten destekler; ayni asamada
        Lise ve Genel sablonu varsa IKI satir uretilir, dosyalar karismaz.
        """
        grouped: dict[str, list[dict[str, Any]]] = {}
        for file_entry in files:
            grouped.setdefault(normalize_level(file_entry.get("detected_level")), []).append(
                file_entry
            )
        if not grouped:
            grouped[TeamLevel.GENEL.value] = []

        stages: list[PlannedStage] = []
        for level, level_files in grouped.items():
            stage = PlannedStage(
                stage_code=code,
                stage_name=stage_name_for(code),
                level=level,
                order_index=0,
            )
            self._attach_files(slug, stage, level_files)
            stages.append(stage)
        # Genel her zaman once gelsin, ozel seviyeler sonra.
        stages.sort(key=lambda s: (s.level != TeamLevel.GENEL.value, s.level))
        return stages

    def _attach_files(
        self, slug: str, stage: PlannedStage, files: Sequence[dict[str, Any]]
    ) -> None:
        """Dosyalari asamaya baglar.

        `competition_stages` tablosunda sablon icin YALNIZCA iki kolon vardir
        (`sablon_docx_r2_key`, `sablon_pdf_r2_key`). Ilk docx ve ilk pdf bu
        kolonlara yazilir; kalan dosyalar (fazladan pdf, pptx, seviye ekleri)
        ayni R2 klasorune KENDI adiyla yuklenir ve rapora "ek dosya" olarak
        gecer — hicbiri atlanmaz.
        """
        for file_entry in files:
            raw_name = str(file_entry.get("clean_name") or file_entry.get("orig_name") or "")
            ext = str(file_entry.get("ext") or Path(raw_name).suffix).lower() or ".bin"
            level = normalize_level(file_entry.get("detected_level"))
            template_key = Keys.template(slug, stage.stage_code, level=level, ext=ext.lstrip("."))

            if ext == TEMPLATE_DOCX_EXT and stage.docx is None:
                stage.docx = self.make_file(file_entry, template_key, slug)
                self.counters["templates_docx"] += 1
                continue
            if ext == TEMPLATE_PDF_EXT and stage.pdf is None:
                stage.pdf = self.make_file(file_entry, template_key, slug)
                self.counters["templates_pdf"] += 1
                continue

            extra_key = self._extra_key(template_key, decode_name(raw_name), ext)
            planned_file = self.make_file(file_entry, extra_key, slug)
            stage.extras.append(planned_file)
            self.counters["templates_extra"] += 1
            stage.notes.append(
                f"Ek dosya R2'ye yüklenir, DB'de şablon alanı dolu: "
                f"{planned_file.original_name}"
            )

    @staticmethod
    def _extra_key(template_key: str, original_name: str, ext: str) -> str:
        """Ek dosyayi `Keys.template()` klasorunde kendi adiyla konumlandirir."""
        folder = template_key.rsplit("/", 1)[0]
        stem = slugify(Path(original_name).stem, max_len=60)
        return f"{folder}/{stem}{ext}"

    # ── yazma ─────────────────────────────────────────────────────────────
    def upload(self, planned_file: PlannedFile, slug: str) -> None:
        if not self.cfg.apply or not self.r2_enabled or not planned_file.r2_key:
            return
        if not planned_file.exists:
            self.fail(f"{slug}: kaynak dosya yok, R2'ye yuklenemedi -> {planned_file.source}")
            return
        try:
            payload = planned_file.source.read_bytes()
        except OSError as exc:
            self.fail(f"{slug}: dosya okunamadi ({planned_file.source}): {exc}")
            return
        try:
            stored = self.storage.upload(payload, planned_file.r2_key)
        except StorageError as exc:
            self.fail(f"{slug}: R2 yukleme hatasi ({planned_file.r2_key}): {exc}")
            return
        planned_file.uploaded = True
        self.counters["files_uploaded"] += 1
        self.log(f"    -> R2 {stored.key} ({stored.size / 1024:.1f} KB)")

    def write_competition(self, planned: PlannedCompetition) -> None:
        repo = self.competitions
        if repo is None:
            return
        existing = repo.get(planned.slug)
        keep = existing is not None and not self.cfg.overwrite_metadata

        comp = Competition(
            competition_id=planned.slug,
            name=(existing.name if keep and existing.name else planned.name),
            slug=planned.slug,
            domain=(existing.domain if keep and existing.domain else planned.domain),
            sub_category=(existing.sub_category if existing else None),
            levels=(existing.levels if keep and existing.levels else planned.levels),
            description=(existing.description if existing else None),
            logo_r2_key=(existing.logo_r2_key if existing else None),
            schedule_json=(existing.schedule_json if existing else None),
            awards_json=(existing.awards_json if existing else None),
            publish_status=(existing.publish_status if existing else PublishStatus.TASLAK),
            spec_status=(existing.spec_status if existing else SpecStatus.BEKLENIYOR),
            created_at=(existing.created_at if existing else now_iso()),
        )
        repo.upsert(comp, actor=None)

    def write_specs(self, planned: PlannedCompetition) -> None:
        repo = self.competitions
        if repo is None:
            return
        existing_specs = repo.list_specs(planned.slug)
        for planned_spec in planned.specs:
            match = next(
                (s for s in existing_specs if (s.branch_code or None) == planned_spec.branch_code),
                None,
            )
            if match is not None and planned_spec.branch_code is None:
                # SQLite'ta NULL degerler UNIQUE kisitinda esit sayilmaz; ON CONFLICT
                # tetiklenmeyecegi icin eski satir ayni kimlikle yeniden yazilir.
                repo.delete_spec(match.spec_id, actor=None)
            fields: dict[str, Any] = {
                "competition_id": planned.slug,
                "title": planned_spec.title,
                "branch_code": planned_spec.branch_code,
                "branch_name": planned_spec.branch_name,
                "r2_key": planned_spec.file.r2_key,
                "original_name": planned_spec.file.original_name,
                "is_primary": planned_spec.is_primary,
            }
            if match is not None:
                fields["spec_id"] = match.spec_id          # kimlik KORUNUR
                fields["created_at"] = match.created_at
                fields["page_count"] = match.page_count
                fields["analyzed_at"] = match.analyzed_at
            repo.add_spec(CompetitionSpec(**fields), actor=None)

    def write_stages(self, planned: PlannedCompetition) -> None:
        repo = self.competitions
        if repo is None:
            return
        for planned_stage in planned.stages:
            if planned_stage.is_auto_generated:
                # KARAR #2: varsayilan asama HER ZAMAN repo uzerinden uretilir.
                repo.ensure_default_stage(planned.slug, actor=None)
            existing_stages = repo.list_stages(planned.slug)
            match = next(
                (
                    s for s in existing_stages
                    if s.stage_code == planned_stage.stage_code
                    and s.level == planned_stage.level
                    and (s.branch_code or None) is None
                ),
                None,
            )
            changes: dict[str, Any] = {
                "stage_name": planned_stage.stage_name,
                "order_index": planned_stage.order_index,
                "is_auto_generated": 1 if planned_stage.is_auto_generated else 0,
            }
            if planned_stage.docx is not None:
                changes["sablon_docx_r2_key"] = planned_stage.docx.r2_key
            if planned_stage.pdf is not None:
                changes["sablon_pdf_r2_key"] = planned_stage.pdf.r2_key
            if match is not None:
                repo.update_stage(match.stage_id, changes, actor=None)
                continue
            repo.add_stage(
                Stage(
                    competition_id=planned.slug,
                    stage_code=planned_stage.stage_code,
                    stage_name=planned_stage.stage_name,
                    level=planned_stage.level,
                    branch_code=None,
                    sablon_docx_r2_key=changes.get("sablon_docx_r2_key"),
                    sablon_pdf_r2_key=changes.get("sablon_pdf_r2_key"),
                    is_auto_generated=planned_stage.is_auto_generated,
                    order_index=planned_stage.order_index,
                ),
                actor=None,
            )

    # ── ana akis ──────────────────────────────────────────────────────────
    def run(self) -> int:
        mode = "UYGULA (--apply)" if self.cfg.apply else "PROVA (--dry-run, hicbir sey yazilmaz)"
        self.log("=" * 78)
        self.log("T-SISTEM · FAZ 2 VERI MIGRASYONU")
        self.log("=" * 78)
        self.log(f"[mod]      {mode}")
        self.log(f"[plan]     {self.cfg.plan}")
        self.log(f"[kaynak]   {self.cfg.source}")
        if not self.cfg.source.is_dir():
            self.warn(f"Kaynak klasor bulunamadi: {self.cfg.source} — dosyalar eksik sayilacak.")

        entries = self.load_plan()
        self.log(f"[plan]     {len(entries)} yarisma islenecek")
        self.connect()
        self.log("-" * 78)

        for position, entry in enumerate(entries, start=1):
            slug = str(entry.get("slug"))
            try:
                planned = self.plan_competition(entry)
            except (KeyError, TypeError, ValueError) as exc:
                self.fail(f"{slug}: plan cozumlenemedi: {exc}")
                continue
            self.plans.append(planned)
            self._process(position, len(entries), planned)

        self.log("-" * 78)
        self.summary()
        if self.cfg.report is not None:
            self.write_report()
        return 1 if self.errors else 0

    def _process(self, position: int, total: int, planned: PlannedCompetition) -> None:
        self.counters["competitions"] += 1
        self.log(f"[{position:>2}/{total}] {planned.slug}")
        self.log(f"    ad     : {planned.name}")
        self.log(f"    alan   : {planned.domain} | seviye: {planned.levels}")

        if planned.specs:
            branch_count = sum(1 for s in planned.specs if s.branch_code)
            self.counters["specs"] += len(planned.specs)
            self.counters["branches"] += branch_count
            label = f"{len(planned.specs)} sartname"
            if branch_count:
                label += f" ({branch_count} dal)"
            self.log(f"    {label}")
            for planned_spec in planned.specs:
                marker = "*" if planned_spec.is_primary else "-"
                code = planned_spec.branch_code or "(tek)"
                self.log(f"      {marker} [{code}] {planned_spec.title}")
                self.log(f"        key: {planned_spec.file.r2_key}")
        else:
            self.log("    0 sartname (bekleniyor)")

        self.counters["stages"] += len(planned.stages)
        for planned_stage in planned.stages:
            if planned_stage.is_auto_generated:
                self.counters["stages_auto"] += 1
            suffix = " [otomatik]" if planned_stage.is_auto_generated else ""
            docx = planned_stage.docx.r2_key if planned_stage.docx else "-"
            pdf = planned_stage.pdf.r2_key if planned_stage.pdf else "-"
            self.log(
                f"    asama  : {planned_stage.stage_code} · {planned_stage.stage_name} "
                f"· seviye={planned_stage.level}{suffix}"
            )
            self.log(f"        docx: {docx}")
            self.log(f"        pdf : {pdf}")
            for extra in planned_stage.extras:
                self.log(f"        ek  : {extra.r2_key}")

        for note in planned.notes:
            self.log(f"    not    : {note}")
        for slug, path in [m for m in self.missing_files if m[0] == planned.slug]:
            self.log(f"    eksik  : {path}")

        if not self.cfg.apply:
            return

        try:
            self.write_competition(planned)
            self.write_specs(planned)
            self.write_stages(planned)
        except DataError as exc:
            self.fail(f"{planned.slug}: D1 yazma hatasi: {exc}")
            return
        self.log("    D1     : yazildi (competitions + specs + stages)")

        for planned_spec in planned.specs:
            self.upload(planned_spec.file, planned.slug)
        for planned_stage in planned.stages:
            for planned_file in planned_stage.all_files:
                self.upload(planned_file, planned.slug)

    # ── ozet ve rapor ─────────────────────────────────────────────────────
    @property
    def mapped_files(self) -> int:
        """Bir D1 kaydina ve/veya R2 anahtarina eslenen dosya sayisi.

        Kapsam disi birakilanlar (yarismaci teslimleri) haric her dosyanin
        hedefi vardir; kaynak dosya bu makinede yoksa bile anahtar uretilmistir.
        """
        return self.counters["files_total"] - self.counters["files_out_of_scope"]

    @property
    def coverage(self) -> float:
        """'0 atlandi' hedefi: plan dosyalarinin yuzde kaci hedefe eslendi."""
        total = self.counters["files_total"]
        if not total:
            return 100.0
        return self.mapped_files / total * 100.0

    def summary(self) -> None:
        counters = self.counters
        self.log("OZET")
        self.log(f"  yarisma            : {counters['competitions']}")
        self.log(f"  sartname           : {counters['specs']} ({counters['branches']} dalli)")
        self.log(f"  asama              : {counters['stages']} "
                 f"({counters['stages_auto']} otomatik OTR)")
        self.log(f"  sablon docx / pdf  : {counters['templates_docx']} / {counters['templates_pdf']}")
        self.log(f"  ek dosya           : {counters['templates_extra']}")
        self.log(f"  toplam dosya       : {counters['files_total']}")
        self.log(f"  R2'ye yuklenen     : {counters['files_uploaded']}")
        self.log(f"  kapsam disi        : {counters['files_out_of_scope']} (yarismaci raporlari)")
        self.log(f"  kaynagi eksik      : {len(self.missing_files)} (bu makinede bulunamadi)")
        self.log(
            f"  eslesme orani      : %{self.coverage:.1f} "
            f"({self.mapped_files}/{counters['files_total']}) — '0 atlandi' hedefi"
        )
        self.log(f"  uyari / hata       : {len(self.warnings)} / {len(self.errors)}")

    def write_report(self) -> None:
        target = self.cfg.report
        if target is None:
            return
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.render_report(), encoding="utf-8")
        except OSError as exc:
            self.fail(f"Rapor yazilamadi ({target}): {exc}")
            return
        self.log(f"[rapor]    {target}")

    def render_report(self) -> str:
        counters = self.counters
        mode = "UYGULANDI" if self.cfg.apply else "PROVA (dry-run)"
        lines: list[str] = [
            "# T-Sistem · Faz 2 Veri Migrasyon Raporu",
            "",
            f"- **Mod:** {mode}",
            f"- **Tarih:** {now_iso()}",
            f"- **Plan:** `{self.cfg.plan}`",
            f"- **Kaynak klasör:** `{self.cfg.source}`",
            f"- **R2 yükleme:** {'açık' if self.r2_enabled else 'kapalı'}",
            "",
            "## 1. Özet",
            "",
            "| Ölçüt | Değer |",
            "| --- | ---: |",
            f"| Yarışma | {counters['competitions']} |",
            f"| Şartname | {counters['specs']} |",
            f"| Dallı şartname | {counters['branches']} |",
            f"| Aşama | {counters['stages']} |",
            f"| Otomatik varsayılan aşama | {counters['stages_auto']} |",
            f"| Şablon (DOCX) | {counters['templates_docx']} |",
            f"| Şablon (PDF) | {counters['templates_pdf']} |",
            f"| Ek dosya | {counters['templates_extra']} |",
            f"| Toplam dosya | {counters['files_total']} |",
            f"| R2'ye yüklenen | {counters['files_uploaded']} |",
            f"| Kapsam dışı (yarışmacı raporu) | {counters['files_out_of_scope']} |",
            f"| Kaynağı bulunamayan | {len(self.missing_files)} |",
            f"| **Eşleşme oranı** | **%{self.coverage:.1f}** |",
            f"| Uyarı / Hata | {len(self.warnings)} / {len(self.errors)} |",
            "",
            "## 2. Yarışma × Şartname × Aşama × Şablon matrisi",
            "",
            "| # | Yarışma | Alan | Seviye | Şartname | Dal | Aşama | DOCX | PDF | Ek |",
            "| ---: | --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: |",
        ]
        for index, planned in enumerate(self.plans, start=1):
            branch_count = sum(1 for s in planned.specs if s.branch_code)
            stage_labels = ", ".join(
                f"{s.stage_code}{'*' if s.is_auto_generated else ''}" for s in planned.stages
            )
            docx = sum(1 for s in planned.stages if s.docx is not None)
            pdf = sum(1 for s in planned.stages if s.pdf is not None)
            extra = sum(len(s.extras) for s in planned.stages)
            lines.append(
                f"| {index} | {planned.name} | {planned.domain} | {planned.levels} | "
                f"{len(planned.specs)} | {branch_count} | {stage_labels or '-'} | "
                f"{docx} | {pdf} | {extra} |"
            )
        lines += ["", "`*` = `ensure_default_stage()` ile üretilen varsayılan OTR aşaması.", ""]

        lines += ["## 3. Çok dallı yarışmalar", "",
                  "| Yarışma | branch_code | branch_name | R2 anahtarı |",
                  "| --- | --- | --- | --- |"]
        multi_found = False
        for planned in self.plans:
            for planned_spec in planned.specs:
                if not planned_spec.branch_code:
                    continue
                multi_found = True
                lines.append(
                    f"| {planned.slug} | `{planned_spec.branch_code}` | "
                    f"{planned_spec.branch_name} | `{planned_spec.file.r2_key}` |"
                )
        if not multi_found:
            lines.append("| — | — | — | — |")
        lines.append("")

        lines += ["## 4. Aşama detayı", "",
                  "| Yarışma | Aşama | Ad | Seviye | Otomatik | DOCX anahtarı | PDF anahtarı |",
                  "| --- | --- | --- | --- | :---: | --- | --- |"]
        for planned in self.plans:
            for planned_stage in planned.stages:
                lines.append(
                    f"| {planned.slug} | {planned_stage.stage_code} | {planned_stage.stage_name} | "
                    f"{planned_stage.level} | {'evet' if planned_stage.is_auto_generated else 'hayır'} | "
                    f"`{planned_stage.docx.r2_key if planned_stage.docx else '-'}` | "
                    f"`{planned_stage.pdf.r2_key if planned_stage.pdf else '-'}` |"
                )
        lines.append("")

        lines += ["## 5. Atlanan ve kapsam dışı dosyalar", ""]
        out_of_scope = [(p.slug, f) for p in self.plans for f in p.out_of_scope]
        lines.append(
            f"**Kapsam dışı (yarışmacı teslimleri, `reports` tablosuna aittir): "
            f"{len(out_of_scope)} dosya**"
        )
        lines.append("")
        if out_of_scope:
            lines += ["| Yarışma | Dosya | Boyut (KB) |", "| --- | --- | ---: |"]
            for slug, planned_file in out_of_scope:
                lines.append(f"| {slug} | {planned_file.original_name} | {planned_file.size_kb:.1f} |")
            lines.append("")

        lines.append(f"**Kaynağı bulunamayan dosyalar: {len(self.missing_files)}**")
        lines.append("")
        if self.missing_files:
            lines += ["| Yarışma | Beklenen yol |", "| --- | --- |"]
            for slug, path in self.missing_files:
                lines.append(f"| {slug} | `{path}` |")
            lines.append("")

        extras = [(p.slug, s, f) for p in self.plans for s in p.stages for f in s.extras]
        lines.append(
            f"**Ek dosyalar (R2'ye yüklenir, DB'de şablon alanı zaten dolu): {len(extras)}**"
        )
        lines.append("")
        if extras:
            lines += ["| Yarışma | Aşama | Dosya | R2 anahtarı |", "| --- | --- | --- | --- |"]
            for slug, planned_stage, planned_file in extras:
                lines.append(
                    f"| {slug} | {planned_stage.stage_code} | {planned_file.original_name} | "
                    f"`{planned_file.r2_key}` |"
                )
            lines.append("")

        lines += ["## 6. Notlar", ""]
        note_found = False
        for planned in self.plans:
            for note in planned.notes:
                note_found = True
                lines.append(f"- `{planned.slug}`: {note}")
        if not note_found:
            lines.append("- Not yok.")
        lines.append("")

        lines += ["## 7. Uyarılar", ""]
        lines += [f"- {w}" for w in self.warnings] or ["- Uyarı yok."]
        lines += ["", "## 8. Hatalar", ""]
        lines += [f"- {e}" for e in self.errors] or ["- Hata yok."]
        lines += [
            "",
            "## 9. '0 atlandı' hedefi",
            "",
            f"Plan içindeki {counters['files_total']} dosyanın {self.mapped_files} tanesi "
            "bir D1 kaydına ve/veya R2 anahtarına eşlendi.",
            "",
            f"- **Eşleşme oranı: %{self.coverage:.1f}** "
            f"({self.mapped_files}/{counters['files_total']})",
            "- Sessizce atlanan dosya: **0** — her dosya ya bir şablon/şartname "
            "kaydına bağlandı, ya 'ek dosya' olarak R2'ye alındı, ya da bu raporda "
            "gerekçesiyle listelendi.",
            f"- Bilinçli kapsam dışı: {counters['files_out_of_scope']} yarışmacı teslimi — "
            "bunlar Faz 3'te `reports` tablosuna `app_id` ile girer.",
            f"- Bu çalıştırmada kaynağı bulunamayan (yüklenemeyen): {len(self.missing_files)}",
            f"- R2'ye yüklenen: {counters['files_uploaded']}",
        ]
        return "\n".join(lines) + "\n"


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def default_source(plan_path: Path) -> Path:
    """Plan JSON'undaki yollarin ortak kokunu yerel bir klasore esler.

    Plan Windows'ta uretildigi icin ortak kok (`...\\teknofest_yarismalar`) bu
    makinede genellikle yoktur; ayni adli klasor once proje kokunde, sonra
    plan dosyasinin yaninda, sonra ev dizininde aranir.
    """
    candidates = [
        _PROJECT_ROOT / PLAN_ROOT_MARKER,
        plan_path.parent / PLAN_ROOT_MARKER,
        plan_path.parent.parent / PLAN_ROOT_MARKER,
        Path.home() / PLAN_ROOT_MARKER,
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def parse_args(argv: Sequence[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(
        prog="migrate_dataset.py",
        description="T-Sistem Faz 2: yerel yarisma klasorunu Cloudflare D1 + R2'ye tasir.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--plan", type=Path, default=_PROJECT_ROOT / "data" / "competition_migration_plans.json",
        help="Yarisma envanteri JSON dosyasi.",
    )
    parser.add_argument(
        "--source", type=Path, default=None,
        help="Yerel `teknofest_yarismalar` klasoru (varsayilan: plan yollarinin ortak koku).",
    )
    parser.add_argument(
        "--dry-run", action="store_true", default=True,
        help="VARSAYILAN. Hicbir sey yazmaz, yalnizca ne yapilacagini gosterir.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Gercekten yazar (D1 + R2). Verilmezse dry-run calisir.",
    )
    parser.add_argument(
        "--only", action="append", default=[], metavar="SLUG",
        help="Yalnizca bu slug islenir. Birden fazla kez verilebilir.",
    )
    parser.add_argument("--skip-r2", action="store_true", help="R2 yuklemesini atla, yalnizca D1.")
    parser.add_argument("--limit", type=int, default=None, help="En fazla N yarisma isle.")
    parser.add_argument("--report", type=Path, default=None, help="Markdown rapor cikti dosyasi.")
    parser.add_argument(
        "--overwrite-metadata", action="store_true",
        help="Yeniden calistirmada plan degerleri mevcut kayitlari EZER "
             "(varsayilan: yonetici duzenlemeleri korunur).",
    )
    args = parser.parse_args(argv)

    if args.limit is not None and args.limit <= 0:
        parser.error("--limit pozitif bir tamsayi olmali.")

    only: list[str] = []
    for item in args.only:
        only.extend(part.strip() for part in str(item).split(",") if part.strip())

    plan = args.plan.expanduser().resolve()
    source = (args.source or default_source(plan)).expanduser()
    return Config(
        source=source,
        plan=plan,
        apply=bool(args.apply),
        only=only,
        skip_r2=bool(args.skip_r2),
        limit=args.limit,
        report=args.report.expanduser() if args.report else None,
        overwrite_metadata=bool(args.overwrite_metadata),
    )


def main(argv: Sequence[str] | None = None) -> int:
    cfg = parse_args(argv)
    migrator = Migrator(cfg)
    try:
        return migrator.run()
    except MigrationError as exc:
        print(f"[HATA] {exc}", file=sys.stderr, flush=True)
        return 2
    except DataError as exc:
        print(f"[HATA] Veri katmani: {exc}", file=sys.stderr, flush=True)
        return 2
    except StorageError as exc:
        print(f"[HATA] R2: {exc}", file=sys.stderr, flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
