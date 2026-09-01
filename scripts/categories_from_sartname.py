"""Şartname PDF'lerinden yarışma kategori profillerini üretir.

NEDEN
-----
MVP 4 (kategori uygunluğu) her kategori için bir "konu profili" vektörüne
ihtiyaç duyuyor: rapor içeriği beyan ettiği kategoriye gerçekten uyuyor mu?

Bu profili elle yazmak iki yüzden kötü:
  * Uydurma olur — benim tahminimle yarışmanın gerçek kapsamı örtüşmeyebilir.
  * Yarışma kapsamı her yıl güncelleniyor; elle yazılan metin bayatlıyor.

Şartnamenin "AMAÇ / KAPSAM" bölümü tam olarak bu işi tarif ediyor ve resmî
kaynak. Bu script o bölümü çıkarıp kategori profil metni olarak kaydediyor.

KULLANIM
--------
    python scripts/categories_from_sartname.py \\
        --dir docs/raporvesablon/_sartnameler \\
        --competition teknofest_2026
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

CATEGORY_DIR = ROOT / "data" / "categories"
TEMPLATE_DIR = ROOT / "data" / "templates"

#: Yarışma -> o yarışmanın rapor şablonları.
#: Şablon başlıkları konu bakımından ÇOK ayırt edici ("Kurtarma Sistemi,
#: Görev Yükü, Aerodinamik, Uçuş Kontrol Bilgisayarı" = roket) ve şartnamenin
#: amaç bölümü zayıf çıktığında (Jet Motor, Roket) profili kurtarıyorlar.
COMPETITION_TEMPLATES: dict[str, list[str]] = {
    "havacilikta_yapay_zeka": ["havacilik_yz_otr_2026"],
    "insansiz_su_alti": ["su_alti_ktr_2026"],
    "jet_motor_tasarim": ["jet_motor_dtr_2026"],
    "robotaksi_otonom_arac": ["robotaksi_hazir_ktr_2026", "robotaksi_ozgun_ktr_2026"],
    "roket": ["roket_a1_ahr_2026", "roket_a2a3_ahr_2026"],
    "saglikta_yapay_zeka": ["saglik_yz_pdr_2026"],
    "sanayide_robotik": ["sanayi_robotik_pdr_2026"],
    "savasan_iha": ["savasan_iha_ktr_2026"],
}


def template_topic_text(category_id: str) -> str:
    """O yarışmanın şablon bölüm + alt bölüm başlıklarını tek metne çevirir."""
    titles: list[str] = []
    for tid in COMPETITION_TEMPLATES.get(category_id, []):
        path = TEMPLATE_DIR / f"{tid}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for sec in data.get("sections", []):
            titles.append(sec["expected_title"])
            titles.extend(sec.get("subsections", []))
    # Tekrarları koru sırasını bozmadan at
    seen, out = set(), []
    for t in titles:
        k = t.lower()
        if k not in seen:
            seen.add(k)
            out.append(t)
    return ", ".join(out)

#: Dosya adından yarışmayı tanı → (category_id, insan okunur ad)
COMPETITION_MAP: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"havacilikta[_\s]*yapay[_\s]*zeka|HAVACILIKTA_YAPAY", re.I),
     "havacilikta_yapay_zeka", "Havacılıkta Yapay Zekâ"),
    (re.compile(r"su[_\s]*alti|SU_ALTI", re.I),
     "insansiz_su_alti", "İnsansız Su Altı Sistemleri"),
    (re.compile(r"jet[_\s]*motor", re.I),
     "jet_motor_tasarim", "Jet Motor Tasarım"),
    (re.compile(r"robotaksi", re.I),
     "robotaksi_otonom_arac", "Robotaksi Binek Otonom Araç"),
    (re.compile(r"roket", re.I),
     "roket", "Roket"),
    (re.compile(r"saglikta[_\s]*yapay|Sağlıkta[_\s]*Yapay", re.I),
     "saglikta_yapay_zeka", "Sağlıkta Yapay Zekâ"),
    (re.compile(r"SRUY|sanayide[_\s]*robotik", re.I),
     "sanayide_robotik", "Sanayide Robotik Uygulamalar"),
    (re.compile(r"savasan[_\s]*iha|SAVASAN_İHA", re.I),
     "savasan_iha", "Savaşan İHA"),
]

#: Amaç/kapsam bölümünün başlangıcı
PURPOSE_START = re.compile(
    r"^\s*(?:\d+\s*[\.\)]?\s*)?"
    r"(amac|amaç|yarismanin amaci|yarışmanın amacı|yarismanin amaci ve kapsami"
    r"|yarışmanın amacı ve kapsamı|giris|giriş|kapsam)\s*$",
    re.IGNORECASE,
)
#: Bir sonraki ana bölüm (amaç bölümünün sonu)
PURPOSE_END = re.compile(
    r"^\s*(?:\d+\s*[\.\)]?\s*)?"
    r"(yarismaya|yarışmaya|katilim|katılım|genel bilgiler|takvim|basvuru"
    r"|başvuru|tanimlar|tanımlar|kisaltmalar|kısaltmalar|yarisma kategori"
    r"|yarışma kategori)",
    re.IGNORECASE,
)

STOP = {
    "ve", "ile", "bir", "bu", "için", "olarak", "daha", "veya", "gibi", "olan",
    "olduğu", "edilen", "yapılan", "üzerinde", "tarafından", "amacıyla", "her",
    "ise", "de", "da", "ki", "en", "çok", "tüm", "aynı", "kendi", "hem",
    "yarışma", "yarışması", "yarışmanın", "teknofest", "takım", "takımlar",
    "takımların", "puan", "madde", "bölüm", "rapor", "başvuru", "katılım",
}
WORD = re.compile(r"[^\W\d_]{4,}", re.UNICODE)


def identify(file_name: str) -> tuple[str, str] | None:
    for pat, cid, name in COMPETITION_MAP:
        if pat.search(file_name):
            return cid, name
    return None


def extract_purpose(path: Path, max_chars: int = 2600) -> str:
    """Şartnamenin amaç/kapsam bölümünü metin olarak çıkarır.

    Şartnameler farklı yapıda olduğu için üç aşamalı geri çekilme var:
      1) "AMAÇ" başlığı ile sonraki ana başlık arasındaki metin
      2) bulunamazsa ilk 6 sayfadaki "amaçlamaktadır/hedeflenmektedir"
         geçen paragraflar
      3) o da yoksa ilk 4 sayfanın düz metni
    """
    doc = pymupdf.open(path)
    try:
        pages = [doc.load_page(i).get_text() or "" for i in range(min(doc.page_count, 12))]
    finally:
        doc.close()

    lines: list[str] = []
    for t in pages:
        lines.extend(ln.strip() for ln in t.split("\n"))

    # 1) Başlık aralığı
    start = None
    for i, ln in enumerate(lines):
        if ln and PURPOSE_START.match(ln):
            start = i + 1
            break
    if start is not None:
        buf: list[str] = []
        for ln in lines[start:]:
            if ln and PURPOSE_END.match(ln) and len(" ".join(buf)) > 400:
                break
            if ln:
                buf.append(ln)
            if len(" ".join(buf)) > max_chars:
                break
        text = " ".join(buf).strip()
        if len(text) > 400:
            return text[:max_chars]

    # 2) Amaç cümlesi geçen paragraflar
    hits = [
        ln for ln in lines
        if len(ln) > 60 and re.search(
            r"(amaçla|hedefle|kapsamında|geliştirilmesi|teşvik|yetiştir)", ln, re.I
        )
    ]
    if hits:
        text = " ".join(hits)[:max_chars]
        if len(text) > 400:
            return text

    # 3) Son çare
    return " ".join(l for l in lines if l)[:max_chars]


def top_keywords(text: str, k: int = 14) -> list[str]:
    """Metinden ayırt edici anahtar kelimeleri çıkarır (basit frekans + eleme)."""
    from collections import Counter

    words = [w.lower() for w in WORD.findall(text)]
    words = [w for w in words if w not in STOP]
    return [w for w, _ in Counter(words).most_common(k)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True, help="Şartname PDF'lerinin klasörü")
    ap.add_argument("--competition", default="teknofest_2026",
                    help="Çıktı dosya adı (data/categories/<ad>.json)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.pdf"))
    if not files:
        print(f"'{args.dir}' altında PDF yok.")
        return 1

    categories: list[dict] = []
    seen: set[str] = set()
    for f in files:
        ident = identify(f.name)
        if not ident:
            print(f"  ? tanınmadı, atlandı: {f.name[:60]}")
            continue
        cid, name = ident
        if cid in seen:
            print(f"  · zaten var, atlandı: {cid}")
            continue
        seen.add(cid)

        purpose = extract_purpose(f)
        topics = template_topic_text(cid)
        # Şablon başlıkları profili konu bazında sabitliyor; şartname metni
        # zayıf çıktığında (kısa/gürültülü) tek dayanak bunlar oluyor.
        description = (
            f"{name} yarışması. {purpose}"
            + (f" Rapor bölümleri: {topics}." if topics else "")
        )
        kws = top_keywords(purpose + " " + topics)
        categories.append({
            "category_id": cid,
            "name": name,
            "description": description,
            "keywords": kws,
            "_kaynak_sartname": f.name,
            "_sartname_karakter": len(purpose),
            "_sablon_basliklari": bool(topics),
        })
        flag = "" if len(purpose) > 800 else "  (şartname zayıf, şablon başlıkları taşıyor)"
        print(f"  ✓ {cid:<24} {len(description):>5} kar.  {', '.join(kws[:5])}{flag}")

    if args.dry_run:
        print("\n(--dry-run: yazılmadı)")
        return 0

    CATEGORY_DIR.mkdir(parents=True, exist_ok=True)
    out = CATEGORY_DIR / f"{args.competition}.json"
    out.write_text(json.dumps({
        "competition_id": args.competition,
        "_not": (
            "Kategori açıklamaları şartnamelerin AMAÇ/KAPSAM bölümlerinden "
            "otomatik çıkarıldı (scripts/categories_from_sartname.py). "
            "Elle yazılmış tahmin DEĞİL, resmî kaynak metni."
        ),
        "categories": categories,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ {out}  ({len(categories)} kategori)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
