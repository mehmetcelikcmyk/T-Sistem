"""MVP 5 — Başvurular arası semantik benzerlik analizi.

Hedef: "Bu rapor, aynı yarışmadaki başka bir raporla anlamsal olarak ne kadar
örtüşüyor?" sorusunu, hakemin doğrulayabileceği KANITLA yanıtlamak.

Algoritma:
  1. Raporun her chunk'ı için, aynı yarışmadaki DİĞER raporların chunk'ları
     içinde top-k komşu aranır (Qdrant batch search, tek tur).
  2. Eşiği geçen eşleşmeler hedef rapora göre gruplanır.
  3. Her hedef rapor için üç ayrı gösterge üretilir:
       - aggregate_score : eşleşen chunk skorlarının ortalaması (ne kadar yakın)
       - coverage        : kaynak raporun yüzde kaçı eşleşti (ne kadar yaygın)
       - matched_chunks  : mutlak eşleşme sayısı (ne kadar çok)
     Tek skor yanıltıcı: bir paragraf %95 benzerse skor yüksek ama coverage
     düşüktür (alıntı olabilir). Coverage yüksekse yapısal kopya işaretidir.
  4. Önem derecesi bu üç göstergenin birleşiminden çıkar.

Not: Ortak tanım cümleleri ("TEKNOFEST, Türkiye'nin en büyük...") her raporda
geçtiği için "boilerplate" filtresi uygulanır — çok fazla rapora birden
eşleşen chunk'lar kopya kanıtı sayılmaz.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Sequence

import numpy as np

from ..config import settings
from ..models import (
    Chunk,
    Severity,
    SimilarPassage,
    SimilarReport,
    SimilarityReport,
)
from ..vectorstore.qdrant_store import QdrantStore

#: Bir chunk bu kadar farklı rapora birden eşleşiyorsa ortak kalıp sayılır
BOILERPLATE_REPORT_LIMIT = 4
#: Kanıt olarak hakeme gösterilecek en fazla pasaj (rapor çifti başına)
MAX_PASSAGES_PER_MATCH = 5
EXCERPT_CHARS = 320


def decide_severity(
    aggregate: float,
    coverage: float,
    matched: int,
    *,
    flag: float | None = None,
    warn: float | None = None,
) -> Severity:
    """Üç göstergeyi tek bir karara indirger.

    Eşikler dışarıdan verilebilir — kalibrasyon scripti (scripts/calibrate.py)
    bu fonksiyonu farklı eşiklerle çağırarak en iyi ayarı arıyor. Üretimde
    parametre verilmezse .env'deki değerler kullanılır.
    """
    flag = settings.similarity_flag_threshold if flag is None else flag
    warn = settings.similarity_warn_threshold if warn is None else warn
    if matched == 0:
        return Severity.OK
    # Yaygın VE yakın -> kırmızı
    if aggregate >= flag and (coverage >= 0.25 or matched >= 5):
        return Severity.ERROR
    # Çok yakın ama dar kapsam, ya da orta yakınlıkta geniş kapsam -> sarı
    if aggregate >= flag or (aggregate >= warn and coverage >= 0.35):
        return Severity.WARN
    if aggregate >= warn:
        return Severity.INFO
    return Severity.OK


#: Geriye dönük uyumluluk için eski ad
_severity = decide_severity


def _excerpt(text: str) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= EXCERPT_CHARS else text[:EXCERPT_CHARS].rstrip() + "…"


def analyze_similarity(
    *,
    report_id: str,
    competition_id: str,
    chunks: Sequence[Chunk],
    vectors: np.ndarray,
    store: QdrantStore,
    top_k: int | None = None,
    warn_threshold: float | None = None,
    max_matches: int | None = None,
    same_category_only: bool = False,
    category_id: str | None = None,
) -> SimilarityReport:
    top_k = top_k or 10
    warn = warn_threshold if warn_threshold is not None else settings.similarity_warn_threshold
    max_matches = max_matches or settings.similarity_top_k

    if not chunks or vectors.size == 0:
        return SimilarityReport(
            report_id=report_id,
            competition_id=competition_id,
            severity=Severity.OK,
            summary="Karşılaştırılacak içerik bulunamadı.",
        )

    query_filter = store.build_filter(
        competition_id=competition_id,
        category_id=category_id if same_category_only else None,
        exclude_report_ids=[report_id],
    )

    results = store.search_batch(
        vectors, limit=top_k, query_filter=query_filter, score_threshold=warn
    )

    # 1) Ortak kalıp (boilerplate) tespiti
    hit_reports: list[set[str]] = []
    for hits in results:
        hit_reports.append({h.get("report_id", "") for h in hits if h.get("report_id")})

    # 2) Rapor bazında topla
    per_report: dict[str, list[tuple[float, int, dict[str, Any]]]] = defaultdict(list)
    compared: set[str] = set()

    for i, hits in enumerate(results):
        if len(hit_reports[i]) >= BOILERPLATE_REPORT_LIMIT:
            continue  # her rapordaki ortak ifade — kopya kanıtı değil
        best_per_report: dict[str, tuple[float, dict[str, Any]]] = {}
        for hit in hits:
            rid = hit.get("report_id")
            if not rid or rid == report_id:
                continue
            compared.add(rid)
            score = float(hit["score"])
            prev = best_per_report.get(rid)
            if prev is None or score > prev[0]:
                best_per_report[rid] = (score, hit)
        for rid, (score, hit) in best_per_report.items():
            per_report[rid].append((score, i, hit))

    total_chunks = len(chunks)
    matches: list[SimilarReport] = []

    for rid, entries in per_report.items():
        entries.sort(key=lambda e: -e[0])
        scores = np.array([e[0] for e in entries], dtype=np.float32)
        matched_chunks = len({e[1] for e in entries})
        aggregate = float(scores.mean())
        coverage = matched_chunks / max(total_chunks, 1)
        sev = decide_severity(aggregate, coverage, matched_chunks)
        if sev == Severity.OK:
            continue

        passages = [
            SimilarPassage(
                score=round(score, 4),
                source_chunk_id=chunks[idx].chunk_id,
                source_section=chunks[idx].section_title,
                source_page=chunks[idx].page_start,
                source_excerpt=_excerpt(chunks[idx].text),
                target_chunk_id=hit.get("chunk_id", ""),
                target_section=hit.get("section_title"),
                target_page=int(hit.get("page_start", 0) or 0),
                target_excerpt=_excerpt(hit.get("text", "")),
            )
            for score, idx, hit in entries[:MAX_PASSAGES_PER_MATCH]
        ]

        matches.append(
            SimilarReport(
                report_id=rid,
                team_id=entries[0][2].get("team_id"),
                aggregate_score=round(aggregate, 4),
                matched_chunk_count=matched_chunks,
                coverage=round(coverage, 4),
                severity=sev,
                passages=passages,
            )
        )

    # Önce en riskliler: önem derecesi, sonra kapsam, sonra skor
    order = {Severity.ERROR: 0, Severity.WARN: 1, Severity.INFO: 2, Severity.OK: 3}
    matches.sort(key=lambda m: (order[m.severity], -m.coverage, -m.aggregate_score))
    matches = matches[:max_matches]

    if not matches:
        overall = Severity.OK
        summary = (
            f"{len(compared)} rapor ile karşılaştırıldı; eşiği aşan benzerlik "
            f"bulunmadı."
        )
    else:
        overall = matches[0].severity
        top = matches[0]
        summary = (
            f"{len(compared)} rapor ile karşılaştırıldı. En yüksek benzerlik: "
            f"{top.report_id} (skor {top.aggregate_score:.2f}, "
            f"kapsam %{top.coverage * 100:.0f}, {top.matched_chunk_count} bölüm eşleşti)."
        )
        if overall == Severity.ERROR:
            summary += " Yüksek benzerlik — uzman hakem incelemesi için işaretlendi."

    return SimilarityReport(
        report_id=report_id,
        competition_id=competition_id,
        scope="same_category" if same_category_only else "competition",
        compared_against=len(compared),
        matches=matches,
        severity=overall,
        summary=summary,
    )


def retrieve_for_criterion(
    *,
    criterion_text: str,
    report_id: str,
    store: QdrantStore,
    encoder,
    limit: int = 6,
    section_keys: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Kriter bazlı AI değerlendirmesi için kanıt getirir (MVP 6'nın girdisi).

    Mehmet'in prompt katmanı bu fonksiyonu çağırıp dönen parçaları LLM'e
    bağlam olarak verir; böylece hakeme sunulan her puan önerisi rapordaki
    somut bir pasaja dayanır (kaynak gösterimi).
    """
    vec = encoder.encode_one(criterion_text)
    flt = store.build_filter(
        include_report_ids=[report_id],
        section_keys=section_keys,
    )
    return store.search(vec, limit=limit, query_filter=flt)
