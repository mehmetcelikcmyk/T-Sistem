"""
TEKNOFEST Değerlendirme Kriterleri ve Rubric Tanımları (Problem 4 PRD Uyumlu)

ÇOK AŞAMALI (ÖTR/KTR/FTR):
  TEKNOFEST yarışmalarında tek aşama yoktur. Aynı yarışmanın Ön Tasarım Raporu
  (ÖTR), Kritik Tasarım Raporu (KTR) ve Final Tasarım Raporu (FTR) aşamaları
  farklı şablona (bölümler + sayfa sınırı) ve farklı puanlama ağırlıklarına
  sahiptir. Rubric bu yüzden (kategori, aşama) ikilisiyle çözümlenir.
"""
import re
import unicodedata
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field


# ==========================================
# AŞAMA (STAGE) YARDIMCILARI
# ==========================================

# Bilinen TEKNOFEST rapor aşamaları ve açık adları.
# ÖNEMLİ: Bu liste KAPALI (fixed) DEĞİLDİR — yalnızca sık kullanılan aşamalara
# okunabilir Türkçe ad vermek içindir. TEKNOFEST'te her yarışmanın aşama seti
# FARKLIDIR (Roket: ÖTR/KTR/AHR; Model Uydu: POR/PDR/CDR/QR/FRR/PFR; İHA: PDR/KTR;
# bazıları: ÖDR/KTR). Bu yüzden normalize_stage BİLİNMEYEN bir aşamayı GENEL'e
# ÇEVİRMEZ; kodu sadeleştirerek KORUR. Böylece yönetici herhangi bir yarışma için
# istediği aşamayı tanımlayabilir ve sistem onu ayrı bir şartname olarak tutar.
KNOWN_STAGES: Dict[str, str] = {
    "ODR": "Ön Değerlendirme Raporu",
    "OTR": "Ön Tasarım Raporu",
    "PDR": "Proje Detay / Ön Tasarım İnceleme Raporu",
    "KTR": "Kritik Tasarım Raporu",
    "CDR": "Kritik Tasarım İnceleme Raporu",
    "DTR": "Detaylı Tasarım Raporu",
    "AHR": "Atışa Hazırlık Raporu",
    "POR": "Proje Planı ve Organizasyon Raporu",
    "QR": "Yeterlilik İnceleme Raporu",
    "FRR": "Uçuşa Yeterlilik Raporu",
    "PFR": "Uçuş Sonrası İnceleme Raporu",
    "FTR": "Final Tasarım Raporu",
    "FYR": "Final Yarışma Raporu",
    "PTR": "Proje Teknik Raporu",
    "GENEL": "Genel",
}

# Serbest yazımları standart koda eşleyen takma adlar (ASCII, boşluksuz, büyük harf).
_STAGE_ALIASES: Dict[str, str] = {
    "ODR": "ODR", "ONDEGERLENDIRME": "ODR", "ONDEGERLENDIRMERAPORU": "ODR",
    "OTR": "OTR", "ONTASARIM": "OTR", "ONTASARIMRAPORU": "OTR",
    "PDR": "PDR", "PROJEDETAY": "PDR", "PROJEDETAYRAPORU": "PDR", "ONTASARIMINCELEME": "PDR",
    "KTR": "KTR", "KRITIKTASARIM": "KTR", "KRITIKTASARIMRAPORU": "KTR",
    "CDR": "CDR", "KRITIKTASARIMINCELEME": "CDR",
    "DTR": "DTR", "DETAYLITASARIM": "DTR", "DETAYLITASARIMRAPORU": "DTR",
    "AHR": "AHR", "ATISAHAZIRLIK": "AHR", "ATISAHAZIRLIKRAPORU": "AHR",
    "POR": "POR", "QR": "QR", "FRR": "FRR", "PFR": "PFR",
    "FTR": "FTR", "FINALTASARIM": "FTR", "FINALTASARIMRAPORU": "FTR",
    "FYR": "FYR", "FINALYARISMA": "FYR", "FINALYARISMARAPORU": "FYR",
    "PTR": "PTR", "PROJETEKNIK": "PTR", "PROJETEKNIKRAPORU": "PTR",
    "GENEL": "GENEL", "": "GENEL",
}


def _ascii_upper(metin: str) -> str:
    """Türkçe karakterleri sadeleştirip büyük harfe çevirir (ı->I, ş->S ...)."""
    if not metin:
        return ""
    eslem = str.maketrans("ıİşŞğĞçÇöÖüÜ", "iIsSgGcCoOuU")
    metin = metin.translate(eslem)
    metin = unicodedata.normalize("NFKD", metin)
    metin = "".join(c for c in metin if not unicodedata.combining(c))
    return metin.upper()


def normalize_stage(stage: Optional[str]) -> str:
    """
    Serbest metinli aşama girdisini kararlı bir koda çevirir.

    * Boş/None -> "GENEL"
    * Bilinen takma ad -> standart kod (ör. "ön tasarım raporu" -> "OTR")
    * BİLİNMEYEN ama dolu girdi -> sadeleştirilmiş kod olarak KORUNUR
      (ör. "AHR-2" -> "AHR2"). Bilinmeyen aşamalar GENEL'e ÇEVRİLMEZ; çünkü
      her yarışmanın aşama seti farklıdır ve tanım kaybı olmamalıdır.
    """
    if not stage:
        return "GENEL"
    anahtar = re.sub(r"[^A-Z0-9]", "", _ascii_upper(stage))
    if not anahtar:
        return "GENEL"
    if anahtar in _STAGE_ALIASES:
        return _STAGE_ALIASES[anahtar]
    # Bilinen bir kodla başlıyorsa o koda indir (ör. "KTR2026" -> "KTR").
    for kod in KNOWN_STAGES:
        if kod != "GENEL" and anahtar.startswith(kod):
            return kod
    # Aksi hâlde girdinin kendisini (sadeleştirilmiş biçimde) KORU.
    return anahtar


def stage_display_name(stage: Optional[str]) -> str:
    """Aşama kodunun okunabilir adı; bilinmiyorsa kodun kendisini döndürür."""
    kod = normalize_stage(stage)
    return KNOWN_STAGES.get(kod, kod)

class CriterionDefinition(BaseModel):
    id: str
    name: str
    max_score: float = 20.0
    weight: float = 0.20
    description: str
    guiding_questions: List[str]

# TEKNOFEST Problem 4 ve Şartname Rubric Kriterleri (Toplam 100 Puan)
TEKNOFEST_RUBRIC: List[CriterionDefinition] = [
    CriterionDefinition(
        id="novelty",
        name="Özgünlük ve Yenilik",
        max_score=20.0,
        weight=0.20,
        description="Projenin ortaya koyduğu fikrin, yöntemin veya yaklaşımın özgünlüğü, piyasadaki/literatürdeki mevcut çözümlerden farkı.",
        guiding_questions=[
            "Proje mevcut çözümlere kıyasla yenilikçi bir değer önerisi sunuyor mu?",
            "Özgün bir algoritma, mimari veya iş modeli geliştirilmiş mi?"
        ]
    ),
    CriterionDefinition(
        id="technical_depth",
        name="Teknik Derinlik ve Yöntem",
        max_score=20.0,
        weight=0.20,
        description="Kullanılan teknolojilerin, algoritmaların, matematiksel modellemenin ve sistem mimarisinin doğruluğu, tutarlılığı ve derinliği.",
        guiding_questions=[
            "Yöntem bölümünde sistem mimarisi, veri akışı ve algoritmalar yeterince detaylandırılmış mı?",
            "Kullanılan yapay zekâ, yazılım veya donanım katmanı problemin ihtiyacını karşılıyor mu?"
        ]
    ),
    CriterionDefinition(
        id="feasibility",
        name="Uygulanabilirlik ve Gerçekçilik",
        max_score=20.0,
        weight=0.20,
        description="Projenin mevcut teknolojik ve bütçesel imkânlarla hayata geçirilebilirliği, risk yönetimi ve prototip hazırlık seviyesi.",
        guiding_questions=[
            "Zaman, bütçe ve donanım planlaması gerçekçi mi?",
            "Proje tasarım aşamasından çalışan bir prototipe dönüştürülebilir mi?"
        ]
    ),
    CriterionDefinition(
        id="impact",
        name="Sosyal, Ekonomik ve Milli Etki",
        max_score=20.0,
        weight=0.20,
        description="Projenin Türkiye'nin teknoloji ekosistemine, topluma, sektöre veya savunma/sivil sanayiye sağlayacağı somut fayda.",
        guiding_questions=[
            "Hedef kitle net belirlenmiş ve yaratılacak etki ölçülebilir şekilde sunulmuş mu?",
            "Milli Teknoloji Hamlesi vizyonuna katkı sağlıyor mu?"
        ]
    ),
    CriterionDefinition(
        id="report_quality",
        name="Raporlama Kalitesi ve Sunum Düzeni",
        max_score=20.0,
        weight=0.20,
        description="Raporun akademik ve teknik yazım standartlarına, şemalandırma kalitesine, terminoloji doğruluğuna ve tutarlılığına uygunluğu.",
        guiding_questions=[
            "Diyagramlar, tablolar ve akış şemaları profesyonel ve anlaşılır mı?",
            "Dil bilgisi, anlatım akıcılığı ve kaynakça atıfları yeterli mi?"
        ]
    )
]

def get_rubric_prompt_context(
    category_name: Optional[str] = None,
    stage: Optional[str] = None,
) -> str:
    """
    LLM prompt'una beslenecek rubric açıklamasını metin olarak döndürür.
    Yarışma ve aşamaya özel resmî rubrik tablosundan (0-100 Puan) kriterleri çeker.
    """
    if category_name:
        try:
            from src.ui import rubrik
            r_data = rubrik.getir(category_name, stage)
            if r_data and r_data.get("kriterler"):
                lines = [
                    f"YARIŞMA VE AŞAMA RESMÎ RUBRİK PUANLAMA TABLOSU ({category_name.upper()} - {stage or 'PDR'} - TOPLAM 100 PUAN):",
                    "Aşağıdaki kriterler, yarışma yöneticisi tarafından sisteme yüklenen resmî rapor şablonundan çıkarılmıştır.",
                    "HER BİR KRİTERİN TAVAN PUANINI (max_score) ASLA DEĞİŞTİRME VE HER BİR KRİTERİ AYRI AYRI PUANLA:\n"
                ]
                for idx, c in enumerate(r_data["kriterler"], 1):
                    cid = c.get("id") or f"k_{idx}"
                    cad = c.get("ad", f"Kriter {idx}")
                    cmax = float(c.get("maks", 10.0))
                    caciklama = c.get("aciklama", "")
                    bolum = c.get("bolum", "")

                    lines.append(f"{idx}. ID: \"{cid}\" | Adı: **{cad}** (Tavan Puan: {cmax:.1f} Puan)")
                    if caciklama:
                        lines.append(f"   - Değerlendirme Esası & Beklentiler: {caciklama}")
                    if bolum:
                        lines.append(f"   - İlgili Rapor Bölümü: Bölüm {bolum}")
                    lines.append("")

                return "\n".join(lines)
        except Exception as e:
            print(f"[UYARI] Rubrik tablosu okunamadı: {e}")

    lines = ["TEKNOFEST GENEL DEĞERLENDİRME RUBRİC KRİTERLERİ (0-100 Puan):"]
    for c in TEKNOFEST_RUBRIC:
        lines.append(f"\n- ID: \"{c.id}\" | **{c.name}** (Maksimum {c.max_score:.0f} Puan, Ağırlık: %{int(c.weight*100)})")
        lines.append(f"  * Açıklama: {c.description}")
        lines.append(f"  * Kılavuz Sorular: {' | '.join(c.guiding_questions)}")
    return "\n".join(lines)

