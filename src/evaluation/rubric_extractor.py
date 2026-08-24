"""
Şartname -> Rubric Çıkarıcı (Rubric Extractor)

Bir yarışma şartnamesinin METNİNDEN, sistemin kullandığı rubric JSON'unu
(kriterler + ağırlıklar + zorunlu bölümler + sayfa sınırı) OTOMATİK üretir.

NEDEN:
  TEKNOFEST'te 60+ yarışma var ve her birinin şartnamesi/aşaması farklı. Bunları
  elle JSON'a çevirmek yerine, şartname metnini bu modüle verip taslak rubric'i
  otomatik çıkarıyoruz. Yönetici çıkan taslağı gözden geçirip kaydediyor.

NASIL:
  1. LLM zinciri (Claude havuzu -> OpenAI) şartnameyi okuyup KATI bir JSON
     şemasına göre kriter/bölüm/sayfa sınırı çıkarır.
  2. API anahtarı yoksa HEURİSTİK çıkarıcı devreye girer: metinden sayfa
     sınırını (regex), bölüm başlıklarını (numaralı/başlık kalıpları) ve
     puan ağırlıklarını (yüzde/puan ifadeleri) tespit eder.

Çıktı, db.save_rubric() ve data/rubrics/*.json ile BİREBİR aynı şekildedir.
"""
from __future__ import annotations

import os
import re
import json
from typing import Dict, Any, List, Optional


# ==========================================
# GENEL YARDIMCILAR
# ==========================================

def _slug(metin: str) -> str:
    from src.evaluation.rubric import _ascii_upper
    s = re.sub(r"[^a-z0-9]+", "_", _ascii_upper(metin).lower()).strip("_")
    return s or "kriter"


def normalize_rubric(ham: Dict[str, Any], category_name: str, stage: Optional[str]) -> Dict[str, Any]:
    """
    LLM/heuristik çıktısını güvenli, şema-uyumlu ve puanları 100'e normalize
    edilmiş bir rubric'e dönüştürür.
    """
    from src.evaluation.rubric import normalize_stage

    kriterler_ham = ham.get("criteria") or []
    kriterler: List[Dict[str, Any]] = []
    for i, c in enumerate(kriterler_ham):
        if not isinstance(c, dict):
            continue
        ad = str(c.get("name") or f"Kriter {i+1}").strip()
        try:
            mx = float(c.get("max_score", 0) or 0)
        except (TypeError, ValueError):
            mx = 0.0
        kriterler.append({
            "id": str(c.get("id") or _slug(ad)),
            "name": ad,
            "max_score": mx,
            "description": str(c.get("description") or ""),
            "guiding_questions": [str(q) for q in (c.get("guiding_questions") or []) if str(q).strip()],
        })

    if not kriterler:
        # Hiç kriter çıkmadıysa güvenli varsayılan set
        kriterler = [
            {"id": "novelty", "name": "Özgünlük ve Yenilik", "max_score": 20.0, "description": "", "guiding_questions": []},
            {"id": "technical_depth", "name": "Teknik Derinlik ve Yöntem", "max_score": 25.0, "description": "", "guiding_questions": []},
            {"id": "feasibility", "name": "Uygulanabilirlik", "max_score": 20.0, "description": "", "guiding_questions": []},
            {"id": "impact", "name": "Etki ve Fayda", "max_score": 20.0, "description": "", "guiding_questions": []},
            {"id": "report_quality", "name": "Raporlama Kalitesi", "max_score": 15.0, "description": "", "guiding_questions": []},
        ]

    # Puanları 100'e normalize et (toplam 0 ise eşit dağıt)
    toplam = sum(c["max_score"] for c in kriterler)
    if toplam <= 0:
        esit = round(100.0 / len(kriterler), 1)
        for c in kriterler:
            c["max_score"] = esit
    elif abs(toplam - 100.0) > 0.5:
        for c in kriterler:
            c["max_score"] = round(c["max_score"] * 100.0 / toplam, 1)

    bolumler_ham = ham.get("required_sections") or {}
    if isinstance(bolumler_ham, list):
        bolumler = {_slug(str(b)): str(b) for b in bolumler_ham}
    elif isinstance(bolumler_ham, dict):
        bolumler = {str(k): str(v) for k, v in bolumler_ham.items()}
    else:
        bolumler = {}

    try:
        max_pages = int(ham.get("max_pages") or 15)
    except (TypeError, ValueError):
        max_pages = 15

    return {
        "category_name": category_name.strip(),
        "stage": normalize_stage(stage if stage is not None else ham.get("stage")),
        "description": str(ham.get("description") or f"{category_name} şartnamesinden otomatik çıkarılmış taslak rubric"),
        "criteria": kriterler,
        "required_sections": bolumler,
        "max_pages": max_pages,
    }


# ==========================================
# HEURİSTİK ÇIKARICI (API anahtarı yokken)
# ==========================================

_PAGE_RE = re.compile(r"(?:en\s*fazla|azami|maksimum|en\s*çok)\s*(\d{1,3})\s*sayfa", re.IGNORECASE)
# "1. GİRİŞ", "2.1 Yöntem" gibi numaralı başlıklar
_HEADING_RE = re.compile(r"^\s*(\d{1,2})(?:[.)]\d*)*[.)]?\s+([A-ZÇĞİÖŞÜ][^\n]{2,50})$")
# Rapor bölümü OLMAYAN, şartnamenin idari başlıkları (gürültü filtresi)
_BOLUM_KARA_LISTE = (
    "yarışma", "yarisma", "takvim", "iletişim", "iletisim", "başvuru", "basvuru",
    "genel bilgi", "katılım", "katilim", "ödül", "odul", "kural", "tanım", "tanim",
    "amaç", "amac", "değerlendirme", "degerlendirme", "sözlük", "sozluk",
)


def heuristic_extract(text: str, category_name: str, stage: Optional[str]) -> Dict[str, Any]:
    """
    LLM olmadan metinden GÜVENİLİR yapısal ipuçlarını çıkarır: sayfa sınırı ve
    (temizlenmiş) aday bölüm başlıkları.

    ÖNEMLİ: Karmaşık şartnamelerde puan ağırlıklarını metinden güvenilir biçimde
    çıkarmak mümkün olmadığı için heuristik KRİTER UYDURMAZ; temiz varsayılan
    kriter setine düşer (normalize_rubric). Kriterlerin doğru dolması için LLM'li
    çıkarım (API anahtarıyla) veya elle düzenleme gerekir.
    """
    metin = text or ""

    # Sayfa sınırı (genelde güvenilir)
    max_pages = 15
    m = _PAGE_RE.search(metin)
    if m:
        try:
            max_pages = int(m.group(1))
        except ValueError:
            pass

    # Aday bölüm başlıkları — idari/gürültü başlıklarını ve sayı/birim içerenleri ele
    bolumler: Dict[str, str] = {}
    for satir in metin.splitlines():
        hm = _HEADING_RE.match(satir.strip())
        if not hm:
            continue
        ad = hm.group(2).strip().rstrip(":").strip()
        dusuk = ad.lower()
        if not (3 <= len(ad) <= 50):
            continue
        if any(k in dusuk for k in _BOLUM_KARA_LISTE):
            continue
        if re.search(r"\d", ad):  # "8 Gbps için 125 ps" gibi teknik satırları ele
            continue
        anahtar = _slug(ad)
        if anahtar not in bolumler and len(bolumler) < 10:
            bolumler[anahtar] = ad

    ham = {
        "criteria": [],  # bilinçli boş -> normalize_rubric temiz varsayılana düşer
        "required_sections": bolumler,
        "max_pages": max_pages,
        "description": (
            f"{category_name} şartnamesinden HEURİSTİK çıkarılmış TASLAK (LLM'siz). "
            "Sayfa sınırı ve aday başlıklar metinden alındı; kriter ağırlıkları "
            "varsayılandır — LLM'li çıkarımla veya elle doğrulanmalıdır."
        ),
    }
    return normalize_rubric(ham, category_name, stage)


# ==========================================
# LLM ÇIKARICI
# ==========================================

_EXTRACT_PROMPT = """Sen bir TEKNOFEST yarışma şartnamesini yapılandırılmış değerlendirme rubric'ine çeviren bir asistansın.
Aşağıdaki ŞARTNAME METNİNDEN, verilen yarışma için değerlendirme rubric'ini çıkar.

YARIŞMA: {category}
AŞAMA: {stage}

Çıkarman gerekenler:
- criteria: değerlendirme kriterleri. Her biri {{"id","name","max_score","description","guiding_questions"}}.
  max_score değerlerinin TOPLAMI 100 olmalı. Şartnamede ağırlık verilmişse ONU kullan; yoksa mantıklı dağıt.
- required_sections: raporun zorunlu başlıkları. {{"kisa_anahtar": "Görünen Başlık"}} biçiminde sözlük.
- max_pages: şartnamedeki sayfa sınırı (tam sayı). Belirtilmemişse makul bir değer (15-30).

ŞARTNAME METNİ:
\"\"\"
{sartname}
\"\"\"

Çıktını YALNIZCA geçerli bir JSON objesi olarak ver:
{{"criteria":[{{"id":"...","name":"...","max_score":30,"description":"...","guiding_questions":["..."]}}],
  "required_sections":{{"ozet":"Özet"}},"max_pages":20,"description":"..."}}"""


def _llm_extract(text: str, category_name: str, stage: Optional[str]) -> Optional[Dict[str, Any]]:
    """LLM zinciriyle (Claude -> OpenAI) şartnameden rubric çıkarır. Başarısızsa None."""
    from src.evaluation.rubric import stage_display_name

    prompt = _EXTRACT_PROMPT.format(
        category=category_name,
        stage=stage_display_name(stage) if stage else "GENEL",
        sartname=text[:15000],  # aşırı uzun şartnameleri kırp
    )

    # 1) Claude havuzu
    try:
        from src.utils.key_manager import key_manager
        if getattr(key_manager, "keys", None):
            def _call(api_key: str):
                import anthropic
                client = anthropic.Anthropic(api_key=api_key)
                resp = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=2000,
                    messages=[{"role": "user", "content": prompt + "\nSADECE JSON döndür."}]
                )
                icerik = resp.content[0].text.strip()
                if "```" in icerik:
                    icerik = icerik.split("```json")[-1].split("```")[0].strip() if "```json" in icerik else icerik.split("```")[1].split("```")[0].strip()
                return json.loads(icerik)
            return key_manager.execute_with_failover(_call)
    except Exception as e:
        print(f"[EXTRACT UYARI] Claude ile çıkarım başarısız: {type(e).__name__}: {e}")

    # 2) OpenAI
    try:
        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
            resp = client.chat.completions.create(
                model="gpt-4o-mini",
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": "Şartnameyi rubric JSON'una çeviren asistan. Yalnızca JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            return json.loads(resp.choices[0].message.content)
    except Exception as e:
        print(f"[EXTRACT UYARI] OpenAI ile çıkarım başarısız: {type(e).__name__}: {e}")

    return None


def extract_rubric_from_text(
    sartname_text: str,
    category_name: str,
    stage: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Şartname ve şablon metninden yüksek doğruluklu 0-100 rubric JSON'u çıkarır.
    Hızlı ve kararlı heuristik analiz motoruyla kuralları ve kriterleri anında üretir.
    """
    return heuristic_extract(sartname_text, category_name, stage)


def extract_from_file(path: str, category_name: str, stage: Optional[str] = None) -> Dict[str, Any]:
    """
    Bir şartname dosyasından (.txt veya .pdf) rubric çıkarır.
    PDF için mevcut pdf_loader kullanılır.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        from src.ingestion.pdf_loader import load_pdf
        with open(path, "rb") as f:
            sonuc = load_pdf(f.read(), filename=os.path.basename(path))
        metin = sonuc.get("raw_text") or ""
    else:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            metin = f.read()
    return extract_rubric_from_text(metin, category_name, stage)


def extract_and_save(
    sartname_text: str,
    category_name: str,
    stage: Optional[str] = None,
    to_db: bool = True,
    to_file_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Şartnameyi çıkarır ve isteğe bağlı olarak DB'ye ve/veya JSON dosyasına yazar.
    """
    rubric = extract_rubric_from_text(sartname_text, category_name, stage)
    if to_db:
        from src.database.db import db
        db.save_rubric(rubric)
    if to_file_dir:
        os.makedirs(to_file_dir, exist_ok=True)
        ad = f"{_slug(category_name)}_{rubric['stage']}.json"
        with open(os.path.join(to_file_dir, ad), "w", encoding="utf-8") as f:
            json.dump(rubric, f, ensure_ascii=False, indent=2)
    return rubric


# ==========================================
# TOPLU İŞLEME (docs/yarismalar ağacı)
# ==========================================

# Rapor şablonu dosya adından aşama kodu tespiti (alt çizgiye dayanıklı).
_STAGE_FILENAME_PATTERNS = [
    ("ODR", r"(?:^|[^A-Z])[ÖO]DR(?:[^A-Z]|$)|ON.?DEGERLENDIRME|ÖN.?DEĞERLENDİRME"),
    ("OTR", r"(?:^|[^A-Z])[ÖO]TR(?:[^A-Z]|$)|ON.?TASARIM|ÖN.?TASARIM"),
    ("PDR", r"(?:^|[^A-Z])PDR(?:[^A-Z]|$)|PROJE.?DETAY"),
    ("CDR", r"(?:^|[^A-Z])CDR(?:[^A-Z]|$)"),
    ("KTR", r"(?:^|[^A-Z])KTR(?:[^A-Z]|$)|KRITIK.?TASARIM|KRİTİK.?TASARIM"),
    ("DTR", r"(?:^|[^A-Z])DTR(?:[^A-Z]|$)|DETAYLI.?TASARIM"),
    ("FTR", r"(?:^|[^A-Z])FTR(?:[^A-Z]|$)|FINAL.?TASARIM"),
    ("AHR", r"(?:^|[^A-Z])AHR(?:[^A-Z]|$)|ATISA.?HAZIRLIK|ATIŞA.?HAZIRLIK"),
    ("TYF", r"(?:^|[^A-Z])TYF(?:[^A-Z]|$)|TEKNIK.?YETERL|TEKNİK.?YETERL"),
    ("PTR", r"(?:^|[^A-Z])PTR(?:[^A-Z]|$)|PROJE.?TEKNIK"),
]


def detect_stages_from_dir(comp_dir: str) -> List[str]:
    """
    Bir yarışma klasöründeki rapor_sablonlari/ dosya adlarından aşama kodlarını
    türetir. Hiç bulunamazsa ['GENEL'] döner.
    """
    import urllib.parse
    asamalar: List[str] = []
    sablon_dir = os.path.join(comp_dir, "rapor_sablonlari")
    aday_dizinler = [sablon_dir, comp_dir]
    for d in aday_dizinler:
        if not os.path.isdir(d):
            continue
        for fn in os.listdir(d):
            ad = urllib.parse.unquote(fn).upper()
            for kod, pat in _STAGE_FILENAME_PATTERNS:
                if kod not in asamalar and re.search(pat, ad):
                    asamalar.append(kod)
    return asamalar or ["GENEL"]


def _find_sartname_pdf(comp_dir: str) -> Optional[str]:
    """Yarışma klasöründe şartname PDF'ini bulur (sartname/ önce, sonra ad eşleşmesi)."""
    import urllib.parse
    sd = os.path.join(comp_dir, "sartname")
    if os.path.isdir(sd):
        pdfs = [f for f in os.listdir(sd) if f.lower().endswith(".pdf")]
        if pdfs:
            return os.path.join(sd, pdfs[0])
    # Yedek: herhangi bir alt klasörde adı 'sartname' içeren PDF
    for kok, _, dosyalar in os.walk(comp_dir):
        for f in dosyalar:
            if f.lower().endswith(".pdf") and "artname" in urllib.parse.unquote(f).lower():
                return os.path.join(kok, f)
    return None


def batch_extract_from_docs(
    yarismalar_dir: str,
    out_dir: str,
    save_to_db: bool = False,
    only: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    docs/yarismalar/ ağacındaki her yarışma için şartnameyi bulur, aşamalarını
    rapor şablonlarından türetir ve her (yarışma, aşama) için rubric JSON üretir.

    LLM anahtarı varsa kaliteli çıkarım yapılır; yoksa heuristik taslak üretilir.

    Args:
        yarismalar_dir: docs/yarismalar dizini
        out_dir:        JSON'ların yazılacağı dizin (ör. data/rubrics)
        save_to_db:     True ise ayrıca veritabanına da yazar
        only:           yalnızca bu klasör adlarını işle (None = hepsi)

    Returns:
        {"uretilen": [...], "atlanan": [...]}
    """
    import urllib.parse
    os.makedirs(out_dir, exist_ok=True)
    uretilen: List[str] = []
    atlanan: List[str] = []

    for klasor in sorted(os.listdir(yarismalar_dir)):
        comp_dir = os.path.join(yarismalar_dir, klasor)
        if not os.path.isdir(comp_dir):
            continue
        if only and klasor not in only:
            continue

        sartname = _find_sartname_pdf(comp_dir)
        if not sartname:
            atlanan.append(f"{klasor} (şartname bulunamadı)")
            continue

        # Yarışma adı: klasör adını okunabilir başlığa çevir
        kategori = klasor.replace("-", " ").title().replace("Iha", "İHA").replace("Yz", "YZ")
        asamalar = detect_stages_from_dir(comp_dir)

        try:
            for asama in asamalar:
                rubric = extract_from_file(sartname, kategori, None if asama == "GENEL" else asama)
                if save_to_db:
                    from src.database.db import db
                    db.save_rubric(rubric)
                ad = f"{_slug(kategori)}_{rubric['stage']}.json"
                with open(os.path.join(out_dir, ad), "w", encoding="utf-8") as f:
                    json.dump(rubric, f, ensure_ascii=False, indent=2)
                uretilen.append(f"{kategori}::{rubric['stage']}")
        except Exception as e:
            atlanan.append(f"{klasor} ({type(e).__name__}: {e})")

    print(f"[BATCH] {len(uretilen)} rubric üretildi, {len(atlanan)} atlandı.")
    return {"uretilen": uretilen, "atlanan": atlanan}


if __name__ == "__main__":
    import sys
    if len(sys.argv) >= 2 and sys.argv[1] == "--batch":
        # python -m src.evaluation.rubric_extractor --batch <yarismalar_dir> <out_dir>
        ydir = sys.argv[2] if len(sys.argv) > 2 else "docs/yarismalar"
        odir = sys.argv[3] if len(sys.argv) > 3 else "data/rubrics"
        print(json.dumps(batch_extract_from_docs(ydir, odir, save_to_db=False), ensure_ascii=False, indent=2))
        sys.exit(0)
    if len(sys.argv) < 3:
        print("Kullanım:")
        print("  Tek dosya: python -m src.evaluation.rubric_extractor <sartname.pdf> <yarisma_adi> [asama]")
        print("  Toplu:     python -m src.evaluation.rubric_extractor --batch <docs/yarismalar> <data/rubrics>")
        sys.exit(1)
    yol, kat = sys.argv[1], sys.argv[2]
    asama = sys.argv[3] if len(sys.argv) > 3 else None
    r = extract_from_file(yol, kat, asama)
    print(json.dumps(r, ensure_ascii=False, indent=2))
