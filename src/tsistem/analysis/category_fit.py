"""MVP 4 — Kategori uygunluğu analizi.

Yaklaşım: her kategori için bir "kategori profil vektörü" hesaplanır
(ad + açıklama + anahtar kelimeler). Rapor tarafında ise TÜM chunk'ların
ortalaması alınmaz — çünkü kaynakça, maliyet tablosu gibi bölümler konu
sinyalini seyreltiyor. Bunun yerine:

  * Konu taşıyan bölümler (özet, problem, çözüm, yöntem, yenilikçi yön)
    ağırlıklandırılır.
  * Kategori skoru = en iyi eşleşen chunk'ların ağırlıklı ortalaması
    (max değil: tek bir cümle yüzünden kategori değişmesin;
     mean değil: ilgisiz bölümler skoru bastırmasın).

Çıktı, beyan edilen kategori ile en iyi kategoriyi karşılaştırır ve
uyumsuzluk durumunda hakeme gerekçeli kanıt (evidence) sunar.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import PROJECT_ROOT, settings
from ..embedding.encoder import Encoder
from ..models import CategoryFitReport, CategoryScore, Chunk, Severity

CATEGORY_DIR = PROJECT_ROOT / "data" / "categories"

#: Konu sinyali taşıyan bölümler ve ağırlıkları
SECTION_WEIGHTS: dict[str, float] = {
    "ozet": 1.30,
    "problem": 1.20,
    "cozum": 1.25,
    "yontem": 1.15,
    "yenilikci_yon": 1.05,
    "hedef_kitle": 0.80,
    "uygulanabilirlik": 0.70,
    "riskler": 0.45,
    "maliyet_zaman": 0.25,
    "kaynakca": 0.10,
    "govde": 1.00,
}
DEFAULT_WEIGHT = 0.85


@dataclass(frozen=True)
class CategorySpec:
    category_id: str
    name: str
    description: str
    keywords: tuple[str, ...] = ()

    def profile_text(self) -> str:
        kw = ", ".join(self.keywords)
        return f"{self.name}. {self.description} Anahtar kavramlar: {kw}"


class CategoryRegistry:
    """Yarışma kategorilerini yükler ve profil vektörlerini önbelleğe alır."""

    def __init__(self, competition_id: str, category_dir: str | Path | None = None):
        directory = Path(category_dir) if category_dir else CATEGORY_DIR
        path = directory / f"{competition_id}.json"
        if not path.exists():
            raise FileNotFoundError(f"Kategori tanımı bulunamadı: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.competition_id = raw.get("competition_id", competition_id)
        self.categories: list[CategorySpec] = [
            CategorySpec(
                category_id=c["category_id"],
                name=c["name"],
                description=c.get("description", ""),
                keywords=tuple(c.get("keywords", ())),
            )
            for c in raw.get("categories", [])
        ]
        self._matrix: np.ndarray | None = None

    def get(self, category_id: str | None) -> CategorySpec | None:
        if not category_id:
            return None
        for c in self.categories:
            if c.category_id == category_id:
                return c
        return None

    def profile_matrix(self, encoder: Encoder) -> np.ndarray:
        """(kategori_sayısı, dim) normalize edilmiş profil matrisi."""
        if self._matrix is None:
            self._matrix = encoder.encode([c.profile_text() for c in self.categories])
        return self._matrix


def _weighted_topk_mean(scores: np.ndarray, weights: np.ndarray, k: int) -> float:
    """En yüksek k skorun ağırlıklı ortalaması."""
    if scores.size == 0:
        return 0.0
    k = max(1, min(k, scores.size))
    idx = np.argsort(-scores)[:k]
    w = weights[idx]
    if w.sum() <= 0:
        return float(scores[idx].mean())
    return float(np.average(scores[idx], weights=w))


def analyze_category_fit(
    *,
    report_id: str,
    chunks: list[Chunk],
    vectors: np.ndarray,
    registry: CategoryRegistry,
    encoder: Encoder,
    declared_category_id: str | None = None,
    threshold: float | None = None,
    top_chunks: int = 8,
) -> CategoryFitReport:
    threshold = threshold if threshold is not None else settings.category_fit_threshold

    if not chunks or vectors.size == 0 or not registry.categories:
        return CategoryFitReport(
            report_id=report_id,
            declared_category_id=declared_category_id,
            message="Kategori analizi için yeterli içerik bulunamadı.",
            severity=Severity.INFO,
        )

    weights = np.array(
        [SECTION_WEIGHTS.get(c.section_key or "govde", DEFAULT_WEIGHT) for c in chunks],
        dtype=np.float32,
    )
    profiles = registry.profile_matrix(encoder)      # (C, dim)
    sim = vectors @ profiles.T                        # (N, C), kosinüs (normalize)

    ranking: list[CategoryScore] = []
    for ci, cat in enumerate(registry.categories):
        col = sim[:, ci]
        score = _weighted_topk_mean(col, weights, top_chunks)
        top_idx = np.argsort(-col)[:3]
        evidence = [
            f"[s.{chunks[i].page_start} · {chunks[i].section_title or '-'}] "
            f"{chunks[i].text[:220].strip()}…"
            for i in top_idx
            if col[i] > 0
        ]
        ranking.append(
            CategoryScore(
                category_id=cat.category_id,
                category_name=cat.name,
                score=round(float(score), 4),
                evidence=evidence,
            )
        )

    ranking.sort(key=lambda c: -c.score)
    best = ranking[0]
    declared = next((c for c in ranking if c.category_id == declared_category_id), None)
    declared_spec = registry.get(declared_category_id)

    # Sözel (yedek) encoder'da mutlak skorlar çok düşük çıkar; bu durumda
    # mutlak eşik yerine "en iyi kategoriye göreli konum" ölçütü kullanılır.
    semantic = getattr(encoder, "is_semantic", True)
    if not semantic and best.score > 0:
        relative = (declared.score / best.score) if declared else 0.0
        note = (" (sözel encoder — skorlar göreli yorumlanmıştır)")
    else:
        relative = 1.0
        note = ""

    is_mismatch = False
    severity = Severity.OK
    if not semantic and declared is not None:
        # Beyan edilen kategori, en iyi kategorinin %60'ından düşükse şüpheli
        if relative < 0.60:
            is_mismatch = True
            severity = Severity.WARN
            message = (
                f"Kategori uyumsuzluğu şüphesi: beyan edilen "
                f"'{declared.category_name}' ({declared.score:.3f}), içerikle en çok "
                f"örtüşen '{best.category_name}' ({best.score:.3f}) kategorisinin "
                f"yalnızca %{relative * 100:.0f}'i kadar uyum gösteriyor.{note}"
            )
        else:
            message = (
                f"Rapor beyan edilen '{declared.category_name}' kategorisiyle uyumlu "
                f"görünüyor.{note}"
            )
        return CategoryFitReport(
            report_id=report_id,
            declared_category_id=declared_category_id,
            declared_category_name=declared_spec.name if declared_spec else None,
            declared_score=declared.score,
            best_category_id=best.category_id,
            best_category_name=best.category_name,
            best_score=best.score,
            ranking=ranking,
            is_mismatch=is_mismatch,
            severity=severity,
            message=message,
        )

    if declared is None:
        message = (
            f"Kategori beyanı yok. İçerik en çok '{best.category_name}' "
            f"kategorisiyle örtüşüyor (skor {best.score:.2f})."
        )
        severity = Severity.INFO
    elif declared.score < threshold and best.category_id != declared.category_id:
        is_mismatch = True
        severity = Severity.WARN
        message = (
            f"Kategori uyumsuzluğu şüphesi: beyan edilen '{declared.category_name}' "
            f"skoru {declared.score:.2f} (eşik {threshold:.2f}); içerik "
            f"'{best.category_name}' kategorisine daha yakın ({best.score:.2f})."
        )
    elif best.category_id != declared.category_id and best.score - declared.score > 0.08:
        severity = Severity.INFO
        message = (
            f"Beyan edilen kategori ('{declared.category_name}', {declared.score:.2f}) "
            f"kabul edilebilir; ancak '{best.category_name}' ({best.score:.2f}) "
            f"daha yüksek uyum gösteriyor."
        )
    else:
        message = (
            f"Rapor beyan edilen '{declared.category_name}' kategorisiyle uyumlu "
            f"(skor {declared.score:.2f})."
        )

    return CategoryFitReport(
        report_id=report_id,
        declared_category_id=declared_category_id,
        declared_category_name=declared_spec.name if declared_spec else None,
        declared_score=declared.score if declared else 0.0,
        best_category_id=best.category_id,
        best_category_name=best.category_name,
        best_score=best.score,
        ranking=ranking,
        is_mismatch=is_mismatch,
        severity=severity,
        message=message,
    )
