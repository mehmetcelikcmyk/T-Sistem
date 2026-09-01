"""T-Sistem - benzerlik / intihal katmani.

IKI MOTOR
---------
1. `hybrid.HybridSimilarityEngine`  -> GUNCEL motor. Iki katmani birlikte
   calistirir (literal difflib + n-gram, anlamsal embedding) ve hakeme
   AYRI AYRI raporlar. Yeni kod bunu kullanmalidir.

2. `vector_store.VectorStore`       -> ESKI motor (yalnizca difflib). Mevcut
   cagiranlar kirilmasin diye oldugu gibi korunur. Sozlesmesi
   `SimilarProjectMatch` semasidir. YENI KOD KULLANMASIN.

Kullanim:
    from src.similarity import HybridSimilarityEngine
    from src.data import repos

    rapor  = repos().reports.get_or_raise(rapor_id)
    korpus = repos().reports.corpus_for(rapor)
    sonuc  = HybridSimilarityEngine().analyze(rapor, korpus)

    print(sonuc.highest, sonuc.risk_level)
    for eslesme in sonuc.matches:
        print(eslesme.matched_label,
              "birebir:", eslesme.literal_score,
              "anlamsal:", eslesme.semantic_score)
"""

from __future__ import annotations

from .hybrid import (
    ENGINE_VERSION,
    Chunk,
    CloudflareEmbeddingProvider,
    D1VectorStore,
    Document,
    EmbeddingProvider,
    EmbeddingUnavailable,
    HybridSimilarityEngine,
    LiteralMatcher,
    LiteralOutcome,
    MatchSpan,
    OpenAIEmbeddingProvider,
    SemanticMatcher,
    SemanticOutcome,
    SimilarityError,
    SimilarityMatch,
    SimilarityReport,
    StoredChunk,
    Thresholds,
    VectorizeStore,
    analyze_report,
    as_document,
    chunk_text,
    cosine_similarity,
    normalize,
    resolve_provider,
    turkish_lower,
)

# ── Geriye donuk uyumluluk: eski difflib motoru ────────────────────────────
from .vector_store import (
    HIGH_RISK_THRESHOLD,
    MEDIUM_RISK_THRESHOLD,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    VectorStore,
    summarize_similarity,
)

__all__ = [
    # guncel hibrit motor
    "HybridSimilarityEngine", "analyze_report", "ENGINE_VERSION",
    "SimilarityReport", "SimilarityMatch", "MatchSpan",
    "LiteralMatcher", "LiteralOutcome",
    "SemanticMatcher", "SemanticOutcome",
    "EmbeddingProvider", "CloudflareEmbeddingProvider", "OpenAIEmbeddingProvider",
    "resolve_provider", "VectorizeStore", "D1VectorStore",
    "Document", "as_document", "Chunk", "StoredChunk", "Thresholds",
    "normalize", "turkish_lower", "chunk_text", "cosine_similarity",
    "SimilarityError", "EmbeddingUnavailable",
    # eski motor (deprecated)
    "VectorStore", "summarize_similarity",
    "HIGH_RISK_THRESHOLD", "MEDIUM_RISK_THRESHOLD",
    "RISK_HIGH", "RISK_MEDIUM", "RISK_LOW",
]
