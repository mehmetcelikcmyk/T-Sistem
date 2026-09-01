"""
Vektör Veritabanı ve Benzerlik / İntihal Arama Motoru — GERÇEK ÖLÇÜM (bağımlılıksız)

SÖZLEŞME (bkz. docs/ENTEGRASYON_SOZLESMESI.md):
  find_similar_reports() listesinin HER ELEMANI src/api/schemas.py ->
  SimilarProjectMatch şemasına birebir uymak zorundadır.

  Risk seviyesi ve "yüksek risk" kararı Birhan'ın işi DEĞİLDİR: eşikler tek
  yerde toplansın diye bu modüldeki summarize_similarity() fonksiyonu üretir.

YÖNTEM (embedding altyapısı gelene kadar):
  Harici model/FAISS olmadan, standart kütüphanedeki difflib ile metin
  benzerliği ölçülür. Her rapor cümlelere bölünür; sorgu raporunun cümleleriyle
  aday raporun cümleleri arasında en yüksek örtüşen çiftler bulunur. Bu hem
  bütünsel bir benzerlik oranı hem de hakeme gösterilecek "en çok benzeyen
  paragraflar" üretir. Embedding hazır olduğunda (Birhan) bu sınıfın içi
  değiştirilir; DÖNÜŞ YAPISI korunur.
"""
from typing import Dict, Any, List
import re
from difflib import SequenceMatcher

# Risk eşikleri — tek doğruluk kaynağı
HIGH_RISK_THRESHOLD = 0.70    # %70 ve üzeri: kırmızı bayrak
MEDIUM_RISK_THRESHOLD = 0.40  # %40 - %70: sarı uyarı

RISK_HIGH = "HIGH"
RISK_MEDIUM = "MEDIUM"
RISK_LOW = "LOW"


def _normalize(text: str) -> str:
    """Karşılaştırma için metni sadeleştirir (küçük harf, tek boşluk)."""
    t = (text or "").lower()
    t = re.sub(r"\s+", " ", t)
    return t.strip()


def _cumleler(text: str) -> List[str]:
    """Metni kaba cümlelere böler; çok kısa parçaları eler."""
    ham = re.split(r"(?<=[.!?])\s+|\n+", text or "")
    return [c.strip() for c in ham if len(c.strip().split()) >= 6]


class VectorStore:
    def __init__(self):
        self.reports: List[Dict[str, Any]] = []

    def add_reports(self, reports: List[Dict[str, Any]]) -> None:
        """
        Karşılaştırma korpusunu belleğe alır.

        Args:
            reports: [{"report_id": str, "project_title": str, "text": str}, ...]
        """
        for r in reports or []:
            if not isinstance(r, dict):
                continue
            metin = r.get("text") or ""
            if not metin.strip():
                continue
            self.reports.append({
                "report_id": str(r.get("report_id", "")),
                "project_title": str(r.get("project_title", "") or "İsimsiz Proje"),
                "text": metin,
                "_norm": _normalize(metin),
                "_cumleler": _cumleler(metin),
            })

    def find_similar_reports(
        self,
        query_text: str,
        top_k: int = 3,
        threshold: float = HIGH_RISK_THRESHOLD,
    ) -> List[Dict[str, Any]]:
        """
        Sorgu metnine en benzeyen raporları döndürür.

        Returns:
            [{matched_report_id, project_title, similarity_ratio,
              matched_paragraphs}, ...]  (eşleşme yoksa BOŞ LİSTE)
        """
        query_norm = _normalize(query_text)
        if not query_norm or not self.reports:
            return []

        query_cumleler = _cumleler(query_text)
        sonuclar: List[Dict[str, Any]] = []

        for rapor in self.reports:
            # 1) Bütünsel benzerlik (hızlı, tüm metin)
            butunsel = SequenceMatcher(None, query_norm, rapor["_norm"]).ratio()

            # 2) En çok benzeyen cümle çiftleri (alıntı + daha hassas oran)
            alintilar, cumle_skorlari = self._benzer_cumleler(query_cumleler, rapor["_cumleler"])

            # Nihai oran: bütünsel ile cümle-bazlı en yüksek örtüşmenin harmanı
            cumle_zirve = max(cumle_skorlari, default=0.0)
            similarity_ratio = round(max(butunsel, 0.5 * butunsel + 0.5 * cumle_zirve), 4)

            sonuclar.append({
                "matched_report_id": rapor["report_id"],
                "project_title": rapor["project_title"],
                "similarity_ratio": float(similarity_ratio),
                "matched_paragraphs": alintilar,
            })

        sonuclar.sort(key=lambda m: m["similarity_ratio"], reverse=True)
        # Anlamsız (çok düşük) örtüşmeleri gösterme
        anlamli = [m for m in sonuclar if m["similarity_ratio"] >= MEDIUM_RISK_THRESHOLD]
        secilen = (anlamli or sonuclar)[:top_k]
        return secilen

    @staticmethod
    def _benzer_cumleler(
        query_cumleler: List[str],
        aday_cumleler: List[str],
        en_fazla: int = 3,
    ):
        """Sorgu cümleleriyle aday cümleler arasında en benzeyen çiftleri bulur."""
        ciftler: List[Any] = []
        for qc in query_cumleler:
            qn = _normalize(qc)
            en_iyi = 0.0
            for ac in aday_cumleler:
                oran = SequenceMatcher(None, qn, _normalize(ac)).ratio()
                if oran > en_iyi:
                    en_iyi = oran
            if en_iyi >= 0.60:
                ciftler.append((en_iyi, qc))
        ciftler.sort(key=lambda x: x[0], reverse=True)
        alintilar = [c[1] for c in ciftler[:en_fazla]]
        skorlar = [c[0] for c in ciftler]
        return alintilar, skorlar


def summarize_similarity(matches: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Eşleşme listesini API'nin SimilarityCheckResult şemasına dönüştürür.
    Risk eşikleri burada, tek yerde uygulanır.

    Returns:
        {highest_similarity, is_high_risk, risk_level, matches}
    """
    safe_matches = [m for m in (matches or []) if isinstance(m, dict)]
    highest = max((float(m.get("similarity_ratio", 0.0)) for m in safe_matches), default=0.0)

    if highest >= HIGH_RISK_THRESHOLD:
        risk_level = RISK_HIGH
    elif highest >= MEDIUM_RISK_THRESHOLD:
        risk_level = RISK_MEDIUM
    else:
        risk_level = RISK_LOW

    return {
        "highest_similarity": round(highest, 4),
        "is_high_risk": risk_level == RISK_HIGH,
        "risk_level": risk_level,
        "matches": safe_matches,
    }
