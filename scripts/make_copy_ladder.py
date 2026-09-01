"""Kopya merdiveni üreteci — kalibrasyonun POZİTİF örnekleri.

SORUN
-----
Elimizdeki 36 gerçek rapor hep bağımsız (finalist takımlar). Yani kalibrasyon
için mükemmel "zor negatif" ama tek bir pozitif örnek yok. Eşiği pozitif
örnek olmadan belirlemek imkânsız: "kaçtan yukarısı kopya" sorusunun cevabı
kopya örneği görmeden verilemez.

ÇÖZÜM
-----
Gerçek raporlardan bilerek kopya üretiyoruz — ama tek çeşit değil, ŞİDDET
MERDİVENİ olarak. Çünkü kopya tek biçimde gelmiyor:

  L1  birebir        Kopyala-yapıştır. Yakalanması kolay, alt sınır referansı.
  L2  hafif parafraz Eşanlamlı değişimi. Kelimeler değişti, yapı aynı.
  L3  ağır parafraz  Eşanlamlı + cümle sırası + bağlaç değişimi. EN KRİTİK
                     seviye — eşiği belirleyen budur. Bunu yakalayamayan
                     sistem gerçek hilebazı da yakalayamaz.
  L4  yapısal        Aynı bölüm iskeleti, içerik başka rapordan. Skor düşük
                     çıkmalı; L4'ü kopya sayan sistem yanlış alarm üretir.
  L5  çeviri         Türkçe -> İngilizce kopya. Bu script üretmiyor (çevirici
                     gerekiyor); şablonu bırakıldı, elle veya LLM ile eklenir.

L4 kasten "kopya DEĞİL" etiketiyle üretiliyor: sistemin sadece yapı
benzerliğine bakıp alarm vermediğini doğrulamak için.

ÇIKTI
-----
  data/raw_kopya/*.pdf              üretilen kopya raporları
  data/labels/similarity_labels.json  etiketler (otomatik doldurulur)

KULLANIM
--------
    python scripts/make_copy_ladder.py --dir docs/raporvesablon
    python scripts/make_copy_ladder.py --dir docs/raporvesablon --per-level 3
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tsistem.pipeline.extractor import extract_document  # noqa: E402
from tsistem.pipeline.section_parser import build_sections, detect_headings  # noqa: E402
from tsistem.pipeline.templates import load_template  # noqa: E402

OUT_DIR = ROOT / "data" / "raw_kopya"
LABEL_PATH = ROOT / "data" / "labels" / "similarity_labels.json"

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FALLBACK_REGULAR = "helv"
FALLBACK_BOLD = "hebo"

#: Kaynak yarışma -> şablon (raporu bölümlere ayırmak için)
FOLDER_TEMPLATES = {
    "havacilikta-yapay-zeka": "havacilik_yz_otr_2026",
    "insansiz-su-alti-sistemleri": "su_alti_ktr_2026",
    "jet-motor-tasarim": "jet_motor_dtr_2026",
    "robotaksi-binek-otonom-arac": "robotaksi_ozgun_ktr_2026",
    "roket": "roket_a1_ahr_2026",
    "saglikta-yapay-zeka": "saglik_yz_pdr_2026",
    "sanayide-robotik-uygulamalar": "sanayi_robotik_pdr_2026",
    "savasan-iha": "savasan_iha_ktr_2026",
}

# --------------------------------------------------------------------------- #
#  Türkçe eşanlamlı sözlüğü (teknik rapor dili)
#  Not: kural tabanlı parafraz, LLM parafrazının yaklaşığıdır. Amaç mükemmel
#  Türkçe değil, ANLAMI KORUYUP YÜZEY BİÇİMİNİ DEĞİŞTİRMEK — semantik
#  benzerliğin yüzeysel örtüşmeden bağımsız çalıştığını ölçmek için yeterli.
# --------------------------------------------------------------------------- #
SYNONYMS: dict[str, str] = {
    "geliştirilmesi": "hazırlanması", "geliştirilmiştir": "hazırlanmıştır",
    "geliştirilmesidir": "hazırlanmasıdır", "geliştirmek": "hazırlamak",
    "amaçlanmaktadır": "hedeflenmektedir", "amaçlamaktadır": "hedeflemektedir",
    "amacıyla": "hedefiyle", "amaç": "hedef",
    "kullanılmıştır": "tercih edilmiştir", "kullanılarak": "yararlanılarak",
    "kullanılan": "yararlanılan", "kullanılmaktadır": "tercih edilmektedir",
    "sağlanmıştır": "temin edilmiştir", "sağlamaktadır": "temin etmektedir",
    "gerçekleştirilmiştir": "yapılmıştır", "gerçekleştirilen": "yapılan",
    "belirlenmiştir": "saptanmıştır", "belirlenen": "saptanan",
    "tespit": "saptama", "tespiti": "saptaması", "tespit edilmiştir": "saptanmıştır",
    "artırmak": "yükseltmek", "artırılmıştır": "yükseltilmiştir",
    "azaltmak": "düşürmek", "azaltılmıştır": "düşürülmüştür",
    "önemli": "kritik", "önemlidir": "kritiktir",
    "gerekli": "zorunlu", "gereklidir": "zorunludur",
    "yöntem": "metot", "yöntemi": "metodu", "yöntemler": "metotlar",
    "sistem": "düzenek", "sistemi": "düzeneği",
    "yapı": "kurgu", "yapısı": "kurgusu",
    "sonuç": "netice", "sonuçlar": "neticeler", "sonuçları": "neticeleri",
    "veri": "bilgi", "verileri": "bilgileri", "veriler": "bilgiler",
    "analiz": "inceleme", "analizi": "incelemesi",
    "değerlendirme": "inceleme", "değerlendirilmiştir": "incelenmiştir",
    "performans": "başarım", "performansı": "başarımı",
    "hesaplanmıştır": "bulunmuştur", "hesaplama": "bulma",
    "seçilmiştir": "yeğlenmiştir", "seçilen": "yeğlenen",
    "uygulanmıştır": "hayata geçirilmiştir", "uygulama": "hayata geçirme",
    "farklı": "başka", "benzer": "yakın", "ayrıca": "bunun yanında",
    "böylece": "bu sayede", "ancak": "fakat", "çünkü": "zira",
    "ilk": "birinci", "son": "nihai", "yeni": "güncel",
    "büyük": "geniş", "küçük": "dar", "yüksek": "üst düzey", "düşük": "alt düzey",
    "hızlı": "seri", "kolay": "rahat", "zor": "güç",
    "test": "deneme", "testleri": "denemeleri", "tasarım": "kurgulama",
    "geliştirme": "hazırlama", "üretim": "imalat", "üretilen": "imal edilen",
}
SENTENCE_SPLIT = re.compile(r"(?<=[\.\!\?])\s+")
WORD_TOKEN = re.compile(r"(\w+|\W+)", re.UNICODE)


def substitute_synonyms(text: str, rate: float, rng: random.Random) -> str:
    """Eşanlamlı değişimi. rate=1.0 tüm eşleşmeleri değiştirir."""
    out: list[str] = []
    for tok in WORD_TOKEN.findall(text):
        low = tok.lower()
        if low in SYNONYMS and rng.random() < rate:
            repl = SYNONYMS[low]
            if tok[:1].isupper():
                repl = repl[:1].upper() + repl[1:]
            out.append(repl)
        else:
            out.append(tok)
    return "".join(out)


def reorder_sentences(text: str, rng: random.Random, window: int = 3) -> str:
    """Cümleleri küçük pencereler içinde karıştırır (anlam akışını korur)."""
    sents = [s for s in SENTENCE_SPLIT.split(text) if s.strip()]
    if len(sents) < 3:
        return text
    out: list[str] = []
    for i in range(0, len(sents), window):
        block = sents[i:i + window]
        rng.shuffle(block)
        out.extend(block)
    return " ".join(out)


def paraphrase(text: str, level: str, rng: random.Random) -> str:
    if level == "L1":
        return text
    if level == "L2":
        return substitute_synonyms(text, 0.55, rng)
    if level == "L3":
        t = substitute_synonyms(text, 1.0, rng)
        t = reorder_sentences(t, rng)
        # Bağlaç/geçiş sözcüklerini de çevir — yüzey örtüşmesini daha da düşür
        for a, b in (("ve", "ile"), ("için", "amacıyla"), ("gibi", "benzeri")):
            t = re.sub(rf"\b{a}\b", b, t, count=max(t.count(a) // 2, 1))
        return t
    return text


# --------------------------------------------------------------------------- #
#  PDF yazımı
# --------------------------------------------------------------------------- #
def _fonts() -> tuple[str, str, str | None, str | None]:
    if Path(FONT_REGULAR).exists() and Path(FONT_BOLD).exists():
        return "TRR", "TRB", FONT_REGULAR, FONT_BOLD
    return FALLBACK_REGULAR, FALLBACK_BOLD, None, None


def write_pdf(path: Path, title: str, sections: list[tuple[str, str]]) -> None:
    reg, bold, reg_file, bold_file = _fonts()
    doc = pymupdf.open()
    page = doc.new_page()
    margin, width = 56.0, 483.0
    y = 60.0

    page.insert_textbox(pymupdf.Rect(margin, y, margin + width, y + 70), title,
                        fontsize=17, fontname=bold, fontfile=bold_file, align=1)
    y += 80

    for head, body in sections:
        if y > 720:
            page = doc.new_page(); y = 60.0
        page.insert_textbox(pymupdf.Rect(margin, y, margin + width, y + 26), head,
                            fontsize=13, fontname=bold, fontfile=bold_file)
        y += 28
        for para in [p for p in body.split("\n") if p.strip()]:
            est = (len(para) / 95 + 1) * 14.2
            if y + est > 770:
                page = doc.new_page(); y = 60.0
            bottom = min(y + est + 40, 790.0)
            rect = pymupdf.Rect(margin, y, margin + width, bottom)
            h = page.insert_textbox(rect, para, fontsize=10.5, fontname=reg,
                                    fontfile=reg_file, align=3)
            if h < 0:
                page = doc.new_page(); y = 60.0
                rect = pymupdf.Rect(margin, y, margin + width, 790.0)
                h = page.insert_textbox(rect, para, fontsize=10.5, fontname=reg,
                                        fontfile=reg_file, align=3)
            y += (rect.y1 - y) - max(h, 0) + 10
        y += 8
    doc.set_metadata({"title": title, "author": "T-Sistem kopya merdiveni"})
    doc.save(path)
    doc.close()


# --------------------------------------------------------------------------- #
def load_sections(path: Path, template_id: str) -> list[tuple[str, str]]:
    template = load_template(template_id)
    result = extract_document(path, ocr_if_scanned=False)
    headings = detect_headings(result)
    sections, _ = build_sections(result, template, headings)
    return [(s.title, s.text) for s in sections if s.word_count >= 60]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(ROOT / "docs" / "raporvesablon"))
    ap.add_argument("--per-level", type=int, default=2,
                    help="Her seviye için kaç kopya üretilsin")
    ap.add_argument("--seed", type=int, default=20260821)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    base = Path(args.dir)

    # Kaynak seçimi: bölüm çıkarımı iyi çalışan, uzun raporlar
    sources: list[tuple[str, Path, str]] = []
    for folder, template_id in FOLDER_TEMPLATES.items():
        for f in sorted((base / folder / "raporlar").glob("*")):
            if f.suffix.lower() not in (".pdf", ".docx"):
                continue
            sources.append((folder, f, template_id))

    usable: list[tuple[str, Path, str, list[tuple[str, str]]]] = []
    for folder, f, tid in sources:
        try:
            secs = load_sections(f, tid)
        except Exception:
            continue
        if len(secs) >= 4:
            usable.append((folder, f, tid, secs))

    print(f"{len(usable)}/{len(sources)} rapor kopya kaynağı olarak uygun "
          f"(>=4 bölüm, >=60 kelime)")
    if len(usable) < 2:
        print("Yeterli kaynak yok.")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for old in OUT_DIR.glob("*.pdf"):
        old.unlink()

    pairs: list[dict] = []
    made = 0

    def report_id_of(folder: str, f: Path) -> str:
        return f"{folder[:10]}-{f.stem[:8]}"

    # ---- L1/L2/L3: aynı raporun kopyası (POZİTİF) ----
    for level, label in (("L1", "birebir"), ("L2", "hafif parafraz"),
                         ("L3", "ağır parafraz")):
        picks = rng.sample(usable, min(args.per_level, len(usable)))
        for folder, f, tid, secs in picks:
            src_id = report_id_of(folder, f)
            new_id = f"KOPYA-{level}-{f.stem[:6]}"
            body = [(h, paraphrase(t, level, rng)) for h, t in secs]
            write_pdf(OUT_DIR / f"{new_id}.pdf", f"{new_id} ({label})", body)
            pairs.append({
                "report_a": src_id, "report_b": new_id, "is_copy": True,
                "seviye": level, "not": f"{label} — {f.name} kaynağından üretildi",
            })
            made += 1
            print(f"  ✓ {new_id:<24} {level} {label:<16} kaynak: {src_id}")

    # ---- L4: yapısal benzerlik, içerik farklı (NEGATİF) ----
    for i in range(args.per_level):
        skeleton_folder, skeleton_f, _, skeleton = rng.choice(usable)
        donors = [u for u in usable if u[1] != skeleton_f]
        if not donors:
            break
        donor_folder, donor_f, _, donor = rng.choice(donors)
        new_id = f"YAPISAL-L4-{skeleton_f.stem[:6]}-{i}"
        body = [
            (h, donor[j % len(donor)][1])
            for j, (h, _) in enumerate(skeleton)
        ]
        write_pdf(OUT_DIR / f"{new_id}.pdf", f"{new_id} (yapısal benzerlik)", body)
        # İskeleti veren raporla KOPYA DEĞİL: başlıklar aynı, içerik başka
        pairs.append({
            "report_a": report_id_of(skeleton_folder, skeleton_f),
            "report_b": new_id, "is_copy": False, "seviye": "L4",
            "not": ("aynı bölüm iskeleti, içerik "
                    f"{donor_f.name} raporundan — kopya SAYILMAMALI"),
        })
        # İçeriği veren raporla ise KOPYA: metin aynen taşındı
        pairs.append({
            "report_a": report_id_of(donor_folder, donor_f),
            "report_b": new_id, "is_copy": True, "seviye": "L4-icerik",
            "not": "içerik bu rapordan birebir alındı",
        })
        made += 1
        print(f"  ✓ {new_id:<24} L4 yapısal          iskelet: {skeleton_f.stem[:8]}"
              f"  içerik: {donor_f.stem[:8]}")

    LABEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    LABEL_PATH.write_text(json.dumps({
        "_aciklama": [
            "scripts/make_copy_ladder.py tarafından otomatik üretildi.",
            "L1-L3 pozitif (gerçek kopya), L4 çift etiketli:",
            "  iskeleti veren raporla KOPYA DEĞİL (sadece yapı benzer),",
            "  içeriği veren raporla KOPYA (metin taşındı).",
            "L5 (çeviri kopya) üretilmedi — çevirici gerekiyor, elle eklenebilir.",
            "Bu dosyaya gerçek kopya çiftleri de elle eklenebilir.",
        ],
        "competition_id": "teknofest_2026",
        "pairs": pairs,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    pos = sum(1 for p in pairs if p["is_copy"])
    print(f"\n{made} kopya raporu üretildi → {OUT_DIR}")
    print(f"{len(pairs)} etiketli çift ({pos} kopya, {len(pairs)-pos} kopya değil)"
          f" → {LABEL_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
