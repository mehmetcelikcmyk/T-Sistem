"""TEKNOFEST .docx rapor şablonundan `data/templates/*.json` üretir.

NEDEN
-----
Şartname MVP maddesi: "Yarışma Yöneticisi güncel rapor şablonunu tanımlar."
Elle JSON yazmak hem yavaş hem hataya açık — her yarışmanın şablonu farklı
(Savaşan İHA'nın KTR'si, Roket'in AHR'si, Sağlıkta YZ'nin PDR'si tamamen ayrı
başlık setleri). Bu script Word şablonunu okuyup yapıyı otomatik çıkarıyor.

ÇIKARDIĞI ŞEYLER
----------------
  * Bölüm başlıkları (Word stilinden — tahmin değil)
  * **Puan ağırlıkları** — "OTONOM GÖREVLER (25 Puan)" → points: 25
    Bu, MVP 6'daki kriter değerlendirmesinin ağırlığını doğrudan veriyor.
  * Alt bölümler (retrieval'da bölüm filtresi için)
  * Şablondaki talimat cümleleri → criteria_hint

2026 ŞABLONLARINDAN ÖĞRENİLENLER
--------------------------------
  * Ana bölüm seviyesi şablona göre değişiyor (Jet Motor: Heading 2,
    Savaşan İHA: Heading 1) → seviye veriden tespit ediliyor.
  * Bazı şablonlarda talimat cümlesi başlık stiliyle yazılmış → eleniyor.
  * Bazı gerçek bölümler sadece kalın yazılmış → alınıyor ama
    "_belirsiz": true ile işaretleniyor, insan gözden geçirsin.

KULLANIM
--------
    python scripts/template_from_docx.py <sablon.docx> --template-id savasan_iha_ktr_2026
    python scripts/template_from_docx.py <sablon.docx> --dry-run
    python scripts/template_from_docx.py --batch docs/raporvesablon
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tsistem.models import Heading  # noqa: E402
from tsistem.pipeline.docx_extractor import (  # noqa: E402
    detect_section_level,
    extract_docx,
    extract_marker_sections,
    looks_like_placeholder,
)
from tsistem.pipeline.section_parser import normalize  # noqa: E402

TEMPLATE_DIR = ROOT / "data" / "templates"

#: Başlık stiliyle yazılmış ama BÖLÜM olmayan satırlar (önsöz/arka madde).
#: Not: "EKLER" burada YOK — Jet Motor DTR'de "EKLER (10 PUAN)" puanlı gerçek
#: bir bölüm. Puanı olan hiçbir başlık atlanmıyor (aşağıdaki kontrole bak).
SKIP_PATTERNS = (
    "icindekiler", "sekil listesi", "sekiller", "tablo listesi", "tablolar",
    "kisaltmalar", "simgeler", "terimler sozlugu", "onsoz",
    "ilave notlar", "puanlama", "puanlamasi",
    "table of contents", "list of figures", "list of tables",
    "revizyon gecmisi", "surum gecmisi",
)

#: Bölüm türüne göre asgari kelime tahmini. BAŞLANGIÇ değeri — gerçek
#: raporlarla kalibre edilecek (bkz. scripts/calibrate_wordcount.py çıktısı).
WORD_HINTS: list[tuple[tuple[str, ...], int]] = [
    (("ozet", "abstract", "summary", "proje tanimi", "rapor ozeti"), 120),
    (("problem", "sorun", "ihtiyac", "gerekce", "mevcut durum"), 150),
    (("cozum", "onerilen", "solution", "yaklasim"), 200),
    (("tasarim", "mimari", "algoritma", "yontem", "metodoloji",
      "method", "analiz", "hesap", "yazilim", "donanim", "entegrasyon"), 250),
    (("yenilik", "inovatif", "ozgun", "innovation"), 120),
    (("uygulanabilirlik", "ticari", "surdurulebilir", "feasibility"), 100),
    (("maliyet", "butce", "zaman", "takvim", "cizelge", "is plani"), 80),
    (("hedef kitle", "kullanici", "pazar", "target"), 60),
    (("risk", "b plani", "onlem"), 60),
    (("test", "dogrulama", "sonuc", "bulgu", "performans", "simulasyon"), 100),
    (("guvenlik", "emniyet", "safety"), 80),
    (("yerlilik", "tecrube", "organizasyon", "takim"), 60),
    (("kaynak", "referans", "bibliyografya", "reference", "ekler"), 20),
]
DEFAULT_MIN_WORDS = 100


def slugify(text: str) -> str:
    t = normalize(text)
    t = unicodedata.normalize("NFKD", t)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    t = re.sub(r"\s+", "_", t.strip())
    return t[:44] or "bolum"


def guess_min_words(title: str) -> int:
    n = normalize(title)
    for keys, words in WORD_HINTS:
        if any(k in n for k in keys):
            return words
    return DEFAULT_MIN_WORDS


def should_skip(h: Heading) -> bool:
    """Puanı olan başlık asla atlanmaz — puan, bölüm olduğunun kanıtı."""
    if h.points is not None:
        return False
    if looks_like_placeholder(h.text):
        return True
    n = normalize(h.text)
    if len(n) < 3:
        return True
    return any(p in n for p in SKIP_PATTERNS)


def _demote_point_subsections(
    sections: list[dict],
) -> tuple[list[dict], list[str]]:
    """Puanı üst bölümün puanına eşit olan ardışık bölümleri alt bölüme indirir.

    Gerçek şablon hatası: Havacılıkta YZ OTR'de bölümler şöyle yazılmış —

        ALGORİTMALAR VE SİSTEM MİMARİSİ (30 PUAN)   <- ana bölüm
          Veri Setleri (10 Puan)                    <- Heading 1 (yanlış)
          Algoritmalar (15 Puan)                    <- Heading 1 (yanlış)
          Akış Şeması (5 Puan)                      <- Heading 1 (yanlış)

    Üçünün toplamı (10+15+5) üst bölümün puanına (30) eşit; yani bunlar
    alt kırılım, ayrı bölüm değil. Hepsi ana bölüm sayılınca toplam puan
    100 yerine 130 çıkıyor ve şablon uyum yüzdesi bozuluyor.

    Bu kontrol tahmine değil aritmetiğe dayanıyor: toplam eşitse indir.

    YANLIŞ POZİTİF KORUMASI: puan toplamı tesadüfen de eşitlenebiliyor.
    Sanayide Robotik şablonunda "TEST" ve "ZAMAN, BÜTÇE VE RİSK PLANLAMASI"
    ayrı bölümler ama puanları önceki bölümün puanına eşit çıkıyordu; indirmek
    toplamı 100'den 85'e düşürüyordu. O yüzden indirme yalnızca **toplamı
    100'e yaklaştırıyorsa** kabul ediliyor — şablonlar 100 puan üzerinden
    kurgulanıyor, bu yüzden 100'e yakınlık nesnel bir doğruluk ölçütü.
    """
    def _dist(secs: list[dict]) -> float:
        total = sum(x.get("points", 0) for x in secs)
        return abs(total - 100.0) if total else float("inf")

    before = _dist(sections)
    out: list[dict] = []
    demoted: list[str] = []
    i = 0
    while i < len(sections):
        cur = sections[i]
        parent_pts = cur.get("points")
        if not parent_pts:
            out.append(cur)
            i += 1
            continue

        # Sonraki bölümlerin puanlarını biriktirip üst puana eşitlik ara
        run: list[dict] = []
        acc = 0.0
        j = i + 1
        while j < len(sections) and sections[j].get("points"):
            run.append(sections[j])
            acc += sections[j]["points"]
            j += 1
            if len(run) >= 2 and abs(acc - parent_pts) < 0.01:
                break
            if acc >= parent_pts:
                break

        if len(run) >= 2 and abs(acc - parent_pts) < 0.01:
            # İndirme toplamı 100'e yaklaştırmıyorsa vazgeç
            trial = [x for x in sections if x not in run]
            if _dist(trial) > before:
                out.append(cur)
                i += 1
                continue
            subs = cur.setdefault("subsections", [])
            for child in run:
                subs.append(child["expected_title"])
                demoted.append(child["expected_title"])
            cur["_alt_bolum_puanlari"] = {
                c["expected_title"]: c["points"] for c in run
            }
            out.append(cur)
            i = i + 1 + len(run)
        else:
            out.append(cur)
            i += 1
    return out, demoted


def _is_all_caps(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 3:
        return False
    return sum(1 for c in letters if c.isupper()) / len(letters) >= 0.85


def _demote_by_casing(
    sections: list[dict],
) -> tuple[list[dict], list[str]]:
    """Yazarın BÜYÜK HARF / Başlık Biçimi ayrımını hiyerarşi sinyali olarak kullanır.

    2026 şablonlarında tekrar eden bir düzen var: yazarlar ana bölümleri
    BÜYÜK HARF, alt kırılımları Başlık Biçimi yazıyor.

        ARAÇ TASARIMI                 <- ana bölüm  (BÜYÜK)
          Mekanik Tasarım Süreci      <- alt bölüm  (Başlık Biçimi)
          Malzemeler
          Üretim Yöntemleri

    Word başlık stili kullanılmadığı için (sadece kalınlaştırılmış) ikisi
    aynı seviyede görünüyordu; hepsini ana bölüm saymak "18 zorunlu bölüm"
    gibi yanlış bir şablon üretiyor ve uyum yüzdesini yapay olarak düşürüyor.

    Kural yalnızca şablonun ana bölümleri AĞIRLIKLI OLARAK BÜYÜK HARF ise
    uygulanıyor. Roket AHR gibi tamamı Başlık Biçimi olan şablonlarda
    ayrım sinyali yok, o yüzden hiçbir şey indirilmiyor.
    """
    caps = [s for s in sections if _is_all_caps(s["expected_title"])]
    if len(sections) < 4 or len(caps) / len(sections) < 0.5:
        return sections, []          # ayrım sinyali yok — dokunma

    out: list[dict] = []
    demoted: list[str] = []
    for sec in sections:
        if _is_all_caps(sec["expected_title"]):
            # Yazarın BÜYÜK HARF tercihi "bu ana bölüm" demek; Word stili
            # kullanılmamış olsa da belirsizlik kalmadı, işareti kaldır.
            sec.pop("_belirsiz", None)
            out.append(sec)
            continue
        if not sec.get("_belirsiz"):
            out.append(sec)
            continue
        # Başlık Biçimi + belirsiz -> önceki BÜYÜK HARF bölümün altına
        if out:
            parent = out[-1]
            parent.setdefault("subsections", []).append(sec["expected_title"])
            demoted.append(sec["expected_title"])
        else:
            out.append(sec)
    return out, demoted


def _demote_by_structure(
    sections: list[dict],
) -> tuple[list[dict], list[str]]:
    """Word stilli başlıkların ARASINA sıkışan kalın başlıkları alt bölüme indirir.

    Neden gerekli: BÜYÜK HARF kuralı yalnız yazarın büyük/küçük ayrımı yaptığı
    şablonlarda işliyor. Roket AHR şablonunun tamamı Başlık Biçimi olduğu için
    o sinyal yok. Orada yapısal sinyal var:

        [Heading 1] Uçuş Kontrol Bilgisayarı      <- Word stili = ana bölüm
        (kalın)     Özgün UKB Algoritma Testi     <- araya sıkışmış = alt bölüm
        (kalın)     Haberleşme Testi              <- alt bölüm
        (kalın)     Özgün UKB Testi               <- alt bölüm
        [Heading 1] Ekler                         <- Word stili = ana bölüm

    Word stiliyle işaretlenmiş başlıklar iskeleti tanımlıyor; aralarına giren
    kalın başlıklar önceki ana bölümün alt kırılımıdır.

    İSTİSNA: ilk Word stilli başlıktan ÖNCE gelen kalın başlıklar (Roket'te
    "Özet", "Terimler", "Giriş") altına girecek bir üst bölüm bulunmadığı için
    ana bölüm olarak kalır. Makale formatının açılış bölümleri bunlar.
    """
    first_styled = next(
        (i for i, s in enumerate(sections) if not s.get("_belirsiz")), None
    )
    if first_styled is None:
        return sections, []          # hiç Word stilli başlık yok — iskelet kurulamaz

    out: list[dict] = []
    demoted: list[str] = []
    for i, sec in enumerate(sections):
        if not sec.get("_belirsiz") or i < first_styled:
            out.append(sec)
            continue
        parent = next((p for p in reversed(out) if not p.get("_belirsiz")), None)
        if parent is None:
            out.append(sec)
            continue
        parent.setdefault("subsections", []).append(sec["expected_title"])
        demoted.append(sec["expected_title"])
    return out, demoted


def _build_from_markers(
    docx_path: Path,
    template_id: str,
    template_name: str,
    doc,
    headings: list[Heading],
    markers: list[dict],
    language: str,
) -> dict:
    """Şablonun kendi bölüm işaretlerinden şablon JSON'u kurar."""
    full = doc.full_text
    sections: list[dict] = []

    for mk in markers:
        title = mk["title"]
        if not title:
            continue
        body = full[mk["char_start"]:mk["char_end"]].strip()
        hint = next(
            (ln.strip()[:240] for ln in body.split("\n")
             if ln.strip() and looks_like_placeholder(ln)), ""
        )
        # İşaretli aralığın İÇİNDE kalan başlıklar alt bölümdür
        subs = [
            h.text for h in headings
            if mk["char_start"] < h.char_start < mk["char_end"]
            and normalize(h.text) != normalize(title)
            and not looks_like_placeholder(h.text)
        ]
        sections.append({
            "key": slugify(title),
            "expected_title": title,
            "aliases": sorted({normalize(title)} - {""}),
            "required": True,
            "min_words": guess_min_words(title),
            "criteria_hint": hint,
            **({"subsections": subs} if subs else {}),
        })

    # İşaretli aralıkların DIŞINDA kalan başlıklar (makale açılışı "Özet",
    # kapanışı "Ekler") — bunlar da zorunlu bölüm, işaretlenmemiş olabilir
    first, last = markers[0]["char_start"], markers[-1]["char_end"]
    known = {normalize(s["expected_title"]) for s in sections}
    for s_sub in sections:
        known |= {normalize(x) for x in s_sub.get("subsections", [])}

    outside = []
    for h in headings:
        if h.level == 0 or looks_like_placeholder(h.text):
            continue
        if first <= h.char_start <= last:
            continue
        if normalize(h.text) in known:
            continue
        outside.append({
            "key": slugify(h.text),
            "expected_title": h.text,
            "aliases": sorted({normalize(h.text)} - {""}),
            "required": True,
            "min_words": guess_min_words(h.text),
            "criteria_hint": "",
            "_isaret_disi": True,
        })
        known.add(normalize(h.text))

    before = [s for s in outside if True]
    all_sections = sorted(
        sections + before,
        key=lambda s: next(
            (h.char_start for h in headings
             if normalize(h.text) == normalize(s["expected_title"])),
            next((m["char_start"] for m in markers
                  if normalize(m["title"]) == normalize(s["expected_title"])), 0),
        ),
    )

    return {
        "template_id": template_id,
        "template_name": template_name,
        "expected_language": language,
        "sections": all_sections,
        "_kaynak": docx_path.name,
        "_bolum_kaynagi": "sablon_bolum_isaretleri",
        "_isaret_sayisi": len(markers),
        "_toplam_puan": None,
        "_belirsiz_basliklar": [],
        "_atlanan_basliklar": [],
        "_not": (
            "Bölümler şablonun kendi 'Bölüm Başlangıcı / Bölüm Sonu' "
            "işaretlerinden okundu — tipografi tahmini kullanılmadı. "
            "'_isaret_disi': true olan bölümler işaretli aralıkların dışında "
            "kalan (makale açılış/kapanış) başlıklardır."
        ),
    }


def build_template(
    docx_path: Path,
    template_id: str,
    template_name: str,
    *,
    section_level: int | None = None,
    language: str = "tr",
) -> dict:
    doc, headings = extract_docx(docx_path)
    full = doc.full_text
    offsets = sorted({h.char_start for h in headings})

    # EN GÜVENİLİR YOL: şablon bölümlerini kendisi işaretlemişse onu kullan.
    # "Bölüm Başlangıcı – IX.Uçuş Kontrol Bilgisayarı" gibi işaretler
    # hangi başlığın ana bölüm olduğunu tartışmaya yer bırakmadan söylüyor.
    markers = extract_marker_sections(docx_path)
    if markers:
        return _build_from_markers(
            docx_path, template_id, template_name, doc, headings, markers, language
        )

    level = section_level or detect_section_level(headings)

    sections: list[dict] = []
    skipped: list[str] = []
    uncertain: list[str] = []
    seen: set[str] = set()

    # Ana bölümler bu seviyede; daha derinler alt bölüm olarak eklenir
    main = [h for h in headings if h.level == level]
    deeper = [h for h in headings if h.level > level]

    for h in main:
        if h.level == 0:
            continue
        if should_skip(h):
            skipped.append(h.text)
            continue

        key = slugify(h.text)
        if key in seen:
            key = f"{key}_{len(seen)}"
        seen.add(key)

        # Bölüm gövdesi: bu başlıktan sonraki ilk başlığa kadar
        start = h.char_start + len(h.raw_text or h.text)
        end = len(full)
        for off in offsets:
            if off > h.char_start:
                end = off
                break
        body = full[start:end].strip()

        hint = ""
        for line in body.split("\n"):
            line = line.strip()
            if line and looks_like_placeholder(line):
                hint = line[:240]
                break

        # Bu ana bölümün altındaki alt başlıklar (sonraki ana bölüme kadar)
        next_main_offset = next(
            (m.char_start for m in main if m.char_start > h.char_start), len(full)
        )
        subs = [
            d.text for d in deeper
            if h.char_start < d.char_start < next_main_offset
            and not looks_like_placeholder(d.text)
        ]

        aliases = sorted({
            normalize(h.text),
            normalize(re.sub(r"\(.*?\)", "", h.text)),
        } - {""})

        entry = {
            "key": key,
            "expected_title": h.text,
            "aliases": aliases,
            "required": True,
            "min_words": guess_min_words(h.text),
            "criteria_hint": hint,
        }
        if h.points is not None:
            entry["points"] = h.points
        if subs:
            entry["subsections"] = subs
        if h.detected_by == "bold":
            entry["_belirsiz"] = True

        sections.append(entry)

    sections, demoted = _demote_point_subsections(sections)
    sections, demoted_case = _demote_by_casing(sections)
    demoted = demoted + demoted_case
    if not demoted_case:
        # BÜYÜK HARF sinyali yoktu; yapısal sinyale düş
        sections, demoted_struct = _demote_by_structure(sections)
        demoted = demoted + demoted_struct
    # Belirsiz listesi indirme/onaylama kararlarından SONRA hesaplanır
    uncertain = [s["expected_title"] for s in sections if s.get("_belirsiz")]
    total_points = sum(s.get("points", 0) for s in sections)
    doc_title = next((h.text for h in headings if h.level == 0), None)

    return {
        "template_id": template_id,
        "template_name": template_name,
        "expected_language": language,
        "sections": sections,
        "_kaynak": docx_path.name,
        "_dokuman_basligi": doc_title,
        "_bolum_seviyesi": level,
        "_toplam_puan": round(total_points, 1) if total_points else None,
        "_belirsiz_basliklar": uncertain,
        "_alt_bolume_indirilenler": demoted,
        "_atlanan_basliklar": skipped,
        "_not": (
            "scripts/template_from_docx.py ile otomatik üretildi. "
            "min_words tahmindir. '_belirsiz': true olan bölümler Word başlık "
            "stiliyle değil kalın metinden tespit edildi — kontrol et. "
            "_toplam_puan 100 değilse bir bölüm kaçmış ya da fazla alınmış olabilir."
        ),
    }


def process_one(path: Path, template_id: str | None, name: str | None,
                section_level: int | None, language: str, dry_run: bool) -> int:
    tid = template_id or slugify(path.stem)
    tname = name or path.stem.replace("_", " ")
    data = build_template(path, tid, tname, section_level=section_level,
                          language=language)
    sections = data["sections"]

    print(f"\n{'=' * 78}")
    print(f"KAYNAK : {path.name}")
    if data.get("_bolum_kaynagi") == "sablon_bolum_isaretleri":
        kaynak = f"şablonun kendi bölüm işaretleri ({data['_isaret_sayisi']} işaret)"
    else:
        kaynak = f"tipografi · Heading {data.get('_bolum_seviyesi', '?')}"
    print(f"ID     : {tid}   ·   bölüm kaynağı: {kaynak}")
    print(f"{'=' * 78}")

    if not sections:
        print("✗ Bölüm bulunamadı. --section-level ile seviyeyi elle ver.")
        return 1

    print(f"{'#':<3} {'PUAN':>5}  {'ANAHTAR':<38} {'ASG':>4}  ALT  BAŞLIK")
    print("-" * 78)
    for i, s in enumerate(sections, 1):
        pts = f"{s['points']:g}" if "points" in s else "–"
        flag = " ⚠" if s.get("_belirsiz") else ""
        nsub = len(s.get("subsections", []))
        print(f"{i:<3} {pts:>5}  {s['key']:<38} {s['min_words']:>4}  "
              f"{nsub:>3}  {s['expected_title'][:26]}{flag}")

    tp = data["_toplam_puan"]
    if tp:
        mark = "✓" if 95 <= tp <= 105 else "⚠ 100 değil — bölüm kaçmış olabilir"
        print(f"\nToplam puan: {tp:g}  {mark}")
    if data.get("_alt_bolume_indirilenler"):
        print(f"↓ Alt bölüme indirildi (puan toplamı üst bölüme eşit): "
              f"{', '.join(data['_alt_bolume_indirilenler'][:6])}")
    if data["_belirsiz_basliklar"]:
        print(f"⚠ Belirsiz (kalın metinden): {', '.join(data['_belirsiz_basliklar'][:6])}")
    if data["_atlanan_basliklar"]:
        print(f"Atlanan (bölüm değil): {', '.join(data['_atlanan_basliklar'][:6])}")

    if dry_run:
        print("\n(--dry-run: dosya yazılmadı)")
        return 0

    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    out = TEMPLATE_DIR / f"{tid}.json"
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ {out}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("docx", nargs="?")
    ap.add_argument("--template-id")
    ap.add_argument("--name")
    ap.add_argument("--section-level", type=int,
                    help="Ana bölüm seviyesini elle ver (otomatik tespiti ez)")
    ap.add_argument("--language", default="tr")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", help="Klasördeki tüm .docx dosyalarını işle")
    args = ap.parse_args()

    if args.batch:
        files = [f for f in sorted(Path(args.batch).rglob("*.docx"))
                 if not f.name.startswith("~$")]
        if not files:
            print(f"'{args.batch}' altında .docx yok.")
            return 1
        rc = 0
        for f in files:
            rc |= process_one(f, None, None, args.section_level,
                              args.language, args.dry_run)
        return rc

    if not args.docx:
        ap.print_help()
        return 1
    return process_one(Path(args.docx), args.template_id, args.name,
                       args.section_level, args.language, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
