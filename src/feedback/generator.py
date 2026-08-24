"""
Yarışmacı Gelişim Karnesi ve Geri Bildirim Üretici Modülü
T3 Vakfı Problem 4 PRD: "Yarışmacıya gelişim odaklı yapıcı geri bildirim sunulması" şartını karşılar.
"""
import os
from typing import Dict, Any, List, Optional, Tuple
from pydantic import BaseModel, Field


# --- Türkçe uyumlu PDF fontu (bir kez kaydedilir) ---------------------------
# NOT: reportlab'ın yerleşik "Helvetica" fontu ş, ğ, ı, İ gibi Türkçe
# karakterleri BASAMAZ (kutu/boşluk çıkar). Bu yüzden Türkçe'yi tam kapsayan
# bir TTF (DejaVu/Vera) gömüyoruz ve font ailesini kaydediyoruz ki <b> etiketi
# de doğru çalışsın.
_PDF_FONT = "KarneSans"
_PDF_FONT_BOLD = "KarneSans-Bold"
_pdf_fonts_registered = False


def _ensure_pdf_fonts() -> Tuple[str, str]:
    """Türkçe karakterleri tam kapsayan bir TTF fontu kaydeder; (normal, bold) döner."""
    global _pdf_fonts_registered
    if _pdf_fonts_registered:
        return _PDF_FONT, _PDF_FONT_BOLD

    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab

    rl_fonts = os.path.join(os.path.dirname(reportlab.__file__), "fonts")

    def _bul(adaylar: List[str]) -> Optional[str]:
        for p in adaylar:
            if os.path.exists(p):
                return p
        return None

    normal = _bul([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        os.path.join(rl_fonts, "DejaVuSans.ttf"),
        os.path.join(rl_fonts, "Vera.ttf"),
    ])
    bold = _bul([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        os.path.join(rl_fonts, "DejaVuSans-Bold.ttf"),
        os.path.join(rl_fonts, "VeraBd.ttf"),
    ])

    if not normal:
        # TTF bulunamazsa yerleşik Helvetica'ya düş (Türkçe eksik olabilir ama çökmez).
        _pdf_fonts_registered = True
        return "Helvetica", "Helvetica-Bold"

    pdfmetrics.registerFont(TTFont(_PDF_FONT, normal))
    pdfmetrics.registerFont(TTFont(_PDF_FONT_BOLD, bold or normal))
    # <b> etiketinin bold varyanta eşlenmesi için font ailesi kaydı:
    pdfmetrics.registerFontFamily(
        _PDF_FONT, normal=_PDF_FONT, bold=_PDF_FONT_BOLD,
        italic=_PDF_FONT, boldItalic=_PDF_FONT_BOLD,
    )
    _pdf_fonts_registered = True
    return _PDF_FONT, _PDF_FONT_BOLD

class ContestantFeedbackCard(BaseModel):
    project_id: str
    overall_status: str
    congratulations_message: str
    strengths: List[str]
    areas_to_improve: List[str]
    actionable_roadmap: List[str]
    pedagogical_advice: str

def generate_contestant_feedback(
    report_id: str = "",
    ai_evaluation_data: Optional[Dict[str, Any]] = None,
    checkers_data: Optional[Dict[str, Any]] = None,
    evaluation_result: Optional[Dict[str, Any]] = None,
    checks_result: Optional[Dict[str, Any]] = None,
    team_name: str = "",
    project_name: str = "",
    **kwargs: Any
) -> Dict[str, Any]:
    """
    Kriter puanlarını, güçlü/zayıf noktaları ve kural kontrollerini harmanlayarak
    yarışmacıya ilham verici, somut ve teknik rehber niteliğinde bir karne üretir.
    """
    eval_data = ai_evaluation_data or evaluation_result or {}
    chk_data = checkers_data or checks_result or {}
    
    total_score = float(eval_data.get("weighted_total_score") or eval_data.get("total_score") or 0.0)
    criteria = eval_data.get("criteria", [])
    
    # Güçlü yönleri ve gelişime açık alanları topla
    all_strengths = []
    all_weaknesses = []
    
    for crit in criteria:
        all_strengths.extend(crit.get("strengths", []))
        all_weaknesses.extend(crit.get("weaknesses", []))
    
    # Benzersiz yap ve en önemlileri seç
    unique_strengths = list(dict.fromkeys(all_strengths))[:4]
    unique_weaknesses = list(dict.fromkeys(all_weaknesses))[:4]
    
    if not unique_strengths:
        unique_strengths = ["Projenin problem tanımı anlaşılır şekilde ortaya konmuş.", "Rapor şablon formatına özen gösterilmiş."]
    if not unique_weaknesses:
        unique_weaknesses = ["Teknik doğrulama testleri ve sayısal metrikler artırılabilir."]

    # KALİBRASYON: "olumlu/başarılı" karne bandının alt eşiği yönetici panosundan
    # okunur (feedback_min_score_for_positive); yoksa 75.
    from src.utils.calibration import get_threshold
    olumlu_esik = get_threshold("feedback_min_score_for_positive", 75.0)

    # Duruma göre motive edici mesaj ve sonraki adım yol haritası
    if total_score >= olumlu_esik:
        status_label = "BAŞARILI / FİNALE UYGUN ADAY"
        welcome_msg = "Tebrikler! Projeniz teknik derinliği ve uygulanabilirliği ile öne çıkmaktadır. Bir sonraki aşamaya hazırlanırken aşağıdaki detayları güçlendirmeniz önerilir."
        roadmap = [
            "1. Adım: Çalışan prototip test sonuçlarınızı ve başarı metriklerinizi (hız, doğruluk, verim) grafiklerle rapora ekleyin.",
            "2. Adım: Jüri sunumunda göstereceğiniz 2 dakikalık video/canlı demo senaryonuzu hazırlayın.",
            "3. Adım: Seri üretim veya saha uygulama maliyet analizini tablolandırın."
        ]
    elif total_score >= 50:
        status_label = "GELİŞTİRİLEBİLİR / REVİZYON ADAYI"
        welcome_msg = "Projeniz çok değerli bir fikir üzerine kurulmuş. Raporunuzu yarışma şartnamesindeki teknik gereksinimlerle tam uyumlu hale getirmek için aşağıdaki adımları tamamlayınız."
        roadmap = [
            "1. Adım: 'Yöntem' bölümündeki sistem mimarisi şemasını daha ayrıntılı blok diyagramlara dönüştürün.",
            "2. Adım: Benzer piyasa/literatür çözümleriyle karşılaştırmalı bir avantaj tablosu oluşturun.",
            "3. Adım: Bütçe ve zaman planınızda karşılaşılabilecek risk senaryolarına ve alternatif planlara yer verin."
        ]
    else:
        status_label = "TEMEL GELİŞİM AŞAMASINDA"
        welcome_msg = "Çalışmanız teknoloji üretme yolunda kıymetli bir adımdır. Bir sonraki dönemde çok daha güçlü bir başvuru yapmak için şu kritik eksiklikleri tamamlamanızı tavsiye ederiz."
        roadmap = [
            "1. Adım: Zorunlu başlıkların (`Özet`, `Yöntem`, `Bütçe`) tamamını şablon formatına uygun doldurun.",
            "2. Adım: Kullanılacak donanım ve yazılım bileşenlerini somutlaştırın.",
            "3. Adım: Projenizin çözdüğü problemi sayısallaştırılmış istatistiki verilerle destekleyin."
        ]

    return {
        "report_id": report_id,
        "total_score": total_score,
        "status": status_label,
        "message": welcome_msg,
        "strengths": unique_strengths,
        "areas_to_improve": unique_weaknesses,
        "actionable_roadmap": roadmap,
        "pedagogical_advice": "Milli Teknoloji Hamlesi yolculuğunda her geri bildirim projenizi bir adım öteye taşımak için bir fırsattır. Başarılar dileriz!"
    }


def generate_feedback_pdf(report_meta: Dict[str, Any], feedback_data: Dict[str, Any]) -> bytes:
    """
    Yarışmacı gelişim karnesini profesyonel ve şık bir PDF belgesine dönüştürür.
    Bellekte (BytesIO) oluşturup bayt dizisi olarak döndürür.
    """
    import io
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=40,
        leftMargin=40,
        topMargin=40,
        bottomMargin=40
    )

    styles = getSampleStyleSheet()

    # Türkçe karakter (ş, ğ, ı, İ ...) için gömülü fontu kaydet ve kullan.
    # Helvetica bu karakterleri basamadığı için tüm stiller bu fonta çevrilir.
    font_normal, font_bold = _ensure_pdf_fonts()

    # Özel Stiller
    title_style = ParagraphStyle(
        'MainTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#1A365D"),
        alignment=TA_CENTER,
        fontName=font_bold
    )

    subtitle_style = ParagraphStyle(
        'SubTitle',
        parent=styles['Normal'],
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#4A5568"),
        alignment=TA_CENTER,
        fontName=font_normal
    )

    h2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=13,
        leading=17,
        textColor=colors.HexColor("#2B6CB0"),
        fontName=font_bold,
        spaceBefore=10,
        spaceAfter=6
    )

    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#2D3748"),
        fontName=font_normal
    )

    elements = []

    # 1. Başlık & Header
    elements.append(Paragraph("T3 VAKFI & TEKNOFEST", subtitle_style))
    elements.append(Paragraph("YARIŞMACI GELİŞİM KARNESİ", title_style))
    elements.append(Paragraph("Yapay Zekâ Destekli 4. Göz Değerlendirme ve Geri Bildirim Raporu", subtitle_style))
    elements.append(Spacer(1, 12))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2B6CB0"), spaceAfter=15))

    # 2. Proje Bilgileri Tablosu
    project_name = report_meta.get("project_name", "Proje")
    category = report_meta.get("category", "Genel Kategori")
    report_id = report_meta.get("report_id", "N/A")
    total_score = feedback_data.get("total_score", 0.0)
    status_label = feedback_data.get("status", "DEĞERLENDİRİLDİ")

    score_color = "#2F855A" if total_score >= 75 else ("#DD6B20" if total_score >= 50 else "#E53E3E")

    info_data = [
        [
            Paragraph("<b>Proje Adı:</b>", body_style), Paragraph(str(project_name), body_style),
            Paragraph("<b>Toplam Puan:</b>", body_style), Paragraph(f"<b><font size=13 color='{score_color}'>{total_score:.1f} / 100</font></b>", body_style)
        ],
        [
            Paragraph("<b>Kategori:</b>", body_style), Paragraph(str(category), body_style),
            Paragraph("<b>Genel Durum:</b>", body_style), Paragraph(f"<b>{status_label}</b>", body_style)
        ],
        [
            Paragraph("<b>Rapor ID:</b>", body_style), Paragraph(str(report_id), body_style),
            Paragraph("<b>Tarih:</b>", body_style), Paragraph(report_meta.get("created_at", "")[:10] or "2026", body_style)
        ]
    ]

    info_table = Table(info_data, colWidths=[80, 180, 90, 180])
    info_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F7FAFC")),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#E2E8F0")),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#EDF2F7")),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(info_table)
    elements.append(Spacer(1, 15))

    # 3. Jüri / Değerlendirme Mesajı
    elements.append(Paragraph("Değerlendirme Özeti ve Karar Notu", h2_style))
    welcome_msg = feedback_data.get("message", "")
    elements.append(Paragraph(welcome_msg, body_style))
    elements.append(Spacer(1, 12))

    # 4. Güçlü Yönler & Gelişime Açık Alanlar
    strengths = feedback_data.get("strengths", [])
    weaknesses = feedback_data.get("areas_to_improve", [])

    str_items = "<br/>".join([f"• {s}" for s in strengths]) if strengths else "• Temel kriterler karşılanmıştır."
    weak_items = "<br/>".join([f"• {w}" for w in weaknesses]) if weaknesses else "• Belirgin bir eksiklik saptanmamıştır."

    strengths_weaknesses_data = [
        [
            Paragraph("<b><font color='#276749'>[+] Güçlü ve Başarılı Yönler</font></b>", body_style),
            Paragraph("<b><font color='#C53030'>[-] Gelişime Açık Kritik Alanlar</font></b>", body_style)
        ],
        [
            Paragraph(str_items, body_style),
            Paragraph(weak_items, body_style)
        ]
    ]

    sw_table = Table(strengths_weaknesses_data, colWidths=[265, 265])
    sw_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#F0FFF4")),
        ('BACKGROUND', (1, 0), (1, -1), colors.HexColor("#FFF5F5")),
        ('BOX', (0, 0), (0, -1), 1, colors.HexColor("#C6F6D5")),
        ('BOX', (1, 0), (1, -1), 1, colors.HexColor("#FED7D7")),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(sw_table)
    elements.append(Spacer(1, 15))

    # 5. Somut Gelişim Yol Haritası (Actionable Roadmap)
    elements.append(Paragraph("Takımınız İçin Sonraki Aşama Yol Haritası", h2_style))
    roadmap = feedback_data.get("actionable_roadmap", [])
    roadmap_items = [[Paragraph(f"<b>{step}</b>", body_style)] for step in roadmap]
    if roadmap_items:
        roadmap_table = Table(roadmap_items, colWidths=[530])
        roadmap_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#EBF8FF")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#BEE3F8")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#BEE3F8")),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(roadmap_table)
    elements.append(Spacer(1, 15))

    # 6. Pedagojik Tavsiye & Kapanış
    pedagogical = feedback_data.get("pedagogical_advice", "")
    if pedagogical:
        elements.append(Paragraph(f"<i>💡 <b>Tavsiye:</b> {pedagogical}</i>", body_style))
    
    elements.append(Spacer(1, 15))
    elements.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#CBD5E0"), spaceAfter=10))
    elements.append(Paragraph("<font size=8 color='#718096'>Bu karne T3 Vakfı T-Sistem AI 4. Göz Karar Destek Asistanı tarafından üretilmiştir. Resmi jüri değerlendirme sürecini desteklemek amacıyla hazırlanmıştır.</font>", subtitle_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer.getvalue()

