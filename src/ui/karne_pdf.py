"""Yarışmacı karnesinin PDF çıktısı.

Şartnamedeki yarışmacı akışı "sonucunu görüntüler → güçlü ve gelişime açık
yönlerini inceler → önerileri görür" diyor. Karnenin indirilebilir olması,
yarışmacının bu geri bildirimi ekip içinde paylaşabilmesini sağlar.

Font notu: sistem fontları platforma göre değişir (Windows'ta Arial,
Linux'ta Liberation/DejaVu). Aşağıdaki çözücü mevcut olan ilk Unicode fontu
seçer; hiçbiri bulunamazsa Helvetica'ya düşer — o durumda Türkçe karakterler
bozulabileceği için uyarı verilir.
"""

from __future__ import annotations

import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import theme

FONT_ADAYLARI = [
    ("KarneSans", "KarneSans-Bold",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    ("KarneSans", "KarneSans-Bold",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("KarneSans", "KarneSans-Bold",
     r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
    ("KarneSans", "KarneSans-Bold",
     r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
    ("KarneSans", "KarneSans-Bold",
     "/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf"),
]

_font_durumu: tuple[str, str, bool] | None = None


def _fontlar() -> tuple[str, str, bool]:
    """(normal, kalın, unicode_destegi) — bir kez çözülür."""
    global _font_durumu
    if _font_durumu is not None:
        return _font_durumu

    for normal, kalin, yol_n, yol_k in FONT_ADAYLARI:
        if Path(yol_n).exists() and Path(yol_k).exists():
            try:
                pdfmetrics.registerFont(TTFont(normal, yol_n))
                pdfmetrics.registerFont(TTFont(kalin, yol_k))
                _font_durumu = (normal, kalin, True)
                return _font_durumu
            except Exception:
                continue

    _font_durumu = ("Helvetica", "Helvetica-Bold", False)
    return _font_durumu


def unicode_destegi() -> bool:
    return _fontlar()[2]


def _stiller(normal: str, kalin: str) -> dict:
    return {
        "baslik": ParagraphStyle("b", fontName=kalin, fontSize=16, leading=20,
                                 textColor=colors.HexColor(theme.INK), spaceAfter=4),
        "alt": ParagraphStyle("a", fontName=normal, fontSize=10, leading=14,
                              textColor=colors.HexColor(theme.INK_2), spaceAfter=12),
        "bolum": ParagraphStyle("bo", fontName=kalin, fontSize=12, leading=16,
                                textColor=colors.HexColor(theme.INK),
                                spaceBefore=14, spaceAfter=6),
        "govde": ParagraphStyle("g", fontName=normal, fontSize=10, leading=15,
                                alignment=TA_JUSTIFY,
                                textColor=colors.HexColor(theme.INK), spaceAfter=5),
        "madde": ParagraphStyle("m", fontName=normal, fontSize=10, leading=15,
                                leftIndent=12, spaceAfter=4,
                                textColor=colors.HexColor(theme.INK)),
        "kucuk": ParagraphStyle("k", fontName=normal, fontSize=8, leading=11,
                                textColor=colors.HexColor(theme.MUTED),
                                alignment=TA_CENTER, spaceBefore=16),
        "puan": ParagraphStyle("p", fontName=kalin, fontSize=26, leading=30,
                               textColor=colors.HexColor(theme.SERIES[0])),
    }


def uret(rapor: dict, yarisma: dict) -> bytes:
    """Karneyi PDF olarak üretip bayt olarak döndürür."""
    normal, kalin, _ = _fontlar()
    st_ = _stiller(normal, kalin)

    tampon = io.BytesIO()
    doc = SimpleDocTemplate(
        tampon, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2.0 * cm, bottomMargin=2.0 * cm,
        title=f"Değerlendirme Karnesi — {rapor.get('proje_adi', '')}",
        author="T-Sistem",
    )

    kriterler = rapor.get("kriterler", [])
    tavan = sum(k["maks"] for k in kriterler) or 100
    toplam = round(sum(k["ai_puan"] for k in kriterler), 1)

    ak = [
        Paragraph("Değerlendirme Karnesi", st_["baslik"]),
        Paragraph(f"{yarisma.get('ad', '')} · {yarisma.get('rapor_turu', '')}", st_["alt"]),
    ]

    # Künye + genel puan
    kunye = [
        ["Proje", rapor.get("proje_adi", "—")],
        ["Takım", rapor.get("takim_adi", "—")],
        ["Başvuru no", rapor.get("rapor_id", "—")],
        ["Kategori", rapor.get("kategori", "—")],
    ]
    t_kunye = Table(kunye, colWidths=[3.2 * cm, 8.2 * cm], hAlign="LEFT")
    t_kunye.setStyle(TableStyle([
        ("FONT", (0, 0), (0, -1), kalin, 9),
        ("FONT", (1, 0), (1, -1), normal, 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor(theme.MUTED)),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
    ]))

    t_puan = Table([[Paragraph(f"{toplam:g}", st_["puan"])],
                    [Paragraph(f"{tavan:g} üzerinden genel puan", st_["alt"])]],
                   colWidths=[5.0 * cm], hAlign="RIGHT")
    t_puan.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "RIGHT"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))

    ust = Table([[t_kunye, t_puan]], colWidths=[11.4 * cm, 5.0 * cm])
    ust.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    ak.append(ust)

    # Kriter tablosu
    ak.append(Paragraph("Kriter bazlı değerlendirme", st_["bolum"]))
    satirlar = [["Kriter", "Tavan", "Puan", "Oran"]]
    for k in kriterler:
        oran = k["ai_puan"] / k["maks"] * 100 if k["maks"] else 0
        satirlar.append([k["ad"], f"{k['maks']:g}", f"{k['ai_puan']:g}", f"%{oran:.0f}"])
    satirlar.append(["TOPLAM", f"{tavan:g}", f"{toplam:g}",
                     f"%{toplam / tavan * 100:.0f}" if tavan else "—"])

    t_kriter = Table(satirlar, colWidths=[8.8 * cm, 2.2 * cm, 2.2 * cm, 3.2 * cm],
                     hAlign="LEFT")
    t_kriter.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), kalin, 9),
        ("FONT", (0, 1), (-1, -2), normal, 9),
        ("FONT", (0, -1), (-1, -1), kalin, 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f0efec")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor(theme.AXIS)),
        ("LINEABOVE", (0, -1), (-1, -1), 0.6, colors.HexColor(theme.AXIS)),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2),
         [colors.white, colors.HexColor("#fbfbf9")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    ak.append(t_kriter)

    gb = rapor.get("geri_bildirim") or {}
    if gb.get("ozet"):
        ak.append(Paragraph("Değerlendirme özeti", st_["bolum"]))
        ak.append(Paragraph(gb["ozet"], st_["govde"]))

    if gb.get("guclu_yonler"):
        ak.append(Paragraph("Güçlü yönler", st_["bolum"]))
        for g in gb["guclu_yonler"]:
            ak.append(Paragraph(f"• {g}", st_["madde"]))

    if gb.get("gelisim_onerileri"):
        ak.append(Paragraph("Gelişim önerileri", st_["bolum"]))
        for o in gb["gelisim_onerileri"]:
            ak.append(Paragraph(f"• {o}", st_["madde"]))

    # Biçim kontrolleri
    kont = rapor.get("kontroller") or {}
    if kont:
        ak.append(Paragraph("Biçim ve şablon kontrolü", st_["bolum"]))
        dil = kont.get("dil", {})
        sab = kont.get("sablon", {})
        bas = kont.get("basliklar", {})
        kont_satir = [
            ["Rapor dili", "Uygun" if dil.get("uygun") else
             f"Beklenenden farklı ({str(dil.get('tespit', '')).upper()})"],
            ["Şablon uyumu", "Uygun" if sab.get("uygun") else "Uyumsuzluk var"],
            ["Zorunlu başlıklar",
             "Tam" if not bas.get("eksik") else
             f"{len(bas.get('eksik', []))} başlık eksik: " + ", ".join(bas.get("eksik", []))],
        ]
        t_k = Table(kont_satir, colWidths=[4.2 * cm, 12.2 * cm], hAlign="LEFT")
        t_k.setStyle(TableStyle([
            ("FONT", (0, 0), (0, -1), kalin, 9),
            ("FONT", (1, 0), (1, -1), normal, 9),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ]))
        ak.append(t_k)

    ak.append(Spacer(1, 6))
    ak.append(Paragraph(
        "Bu karne, yapay zekâ ön değerlendirmesi ve hakem onayı sonucunda "
        "oluşturulmuştur. Yapay zekâ nihai karar verici değildir; puanlara ilişkin "
        "nihai yetki hakem heyetine aittir.", st_["kucuk"]))

    doc.build(ak)
    return tampon.getvalue()


def dosya_adi(rapor: dict) -> str:
    ham = f"{rapor.get('rapor_id', 'karne')}_karne.pdf"
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in ham)
