"""Qdrant vektör deposu.

Koleksiyon tasarımı — tek koleksiyon, zengin payload:
    rapor_chunks
      vector : COSINE, dim = encoder.dim
      payload: report_id, competition_id, category_id, team_id,
               section_key, section_title, page_start/end, ordinal, text

Neden tek koleksiyon: benzerlik analizi "aynı yarışmadaki DİĞER raporlar"
üzerinde çalışıyor. Rapor başına koleksiyon açmak N sorgu demek; tek koleksiyon
+ payload filtresi ile tek sorguda hallediliyor. Filtrelenen alanlara payload
index açıldığı için filtre maliyeti sabit kalıyor.

`url=":memory:"` verilirse sunucusuz gömülü modda çalışır (test/CI için).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Iterable, Sequence

import numpy as np
from qdrant_client import QdrantClient, models as qm

from ..config import settings
from ..models import Chunk

logger = logging.getLogger(__name__)

#: Filtrelemede kullanılan ve index açılan payload alanları
INDEXED_FIELDS = (
    "report_id",
    "competition_id",
    "category_id",
    "team_id",
    "section_key",
)


def _point_id(chunk_id: str) -> str:
    """Qdrant UUID/int ister; chunk_id'yi deterministik UUID'ye çevirir."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, chunk_id))


class QdrantStore:
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection: str | None = None,
        dim: int | None = None,
    ):
        self.collection = collection or settings.collection_chunks
        self.dim = dim or settings.embedding_dim
        target = url or settings.qdrant_url
        if target in (":memory:", "memory"):
            self.client = QdrantClient(":memory:")
            self.embedded = True
        else:
            self.client = QdrantClient(url=target, api_key=api_key or settings.qdrant_api_key)
            self.embedded = False

    # ------------------------------------------------------------------ #
    #  Şema
    # ------------------------------------------------------------------ #
    def ensure_collection(self, recreate: bool = False) -> None:
        exists = self.client.collection_exists(self.collection)
        if exists and recreate:
            self.client.delete_collection(self.collection)
            exists = False
        if not exists:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=qm.VectorParams(size=self.dim, distance=qm.Distance.COSINE),
                # Kopya tespitinde recall kritik: HNSW bağlantısı biraz yüksek
                hnsw_config=qm.HnswConfigDiff(m=32, ef_construct=200),
                optimizers_config=qm.OptimizersConfigDiff(default_segment_number=2),
            )
            logger.info("Koleksiyon oluşturuldu: %s (dim=%s)", self.collection, self.dim)

        if self.embedded:
            # Gömülü modda payload index desteklenmiyor; koleksiyon küçük olduğu
            # için filtreler yine doğru çalışır, yalnız hızlandırma olmaz.
            return
        for field in INDEXED_FIELDS:
            try:
                self.client.create_payload_index(
                    collection_name=self.collection,
                    field_name=field,
                    field_schema=qm.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass  # zaten varsa sorun değil

    # ------------------------------------------------------------------ #
    #  Yazma
    # ------------------------------------------------------------------ #
    def upsert_chunks(
        self, chunks: Sequence[Chunk], vectors: np.ndarray, batch_size: int = 128
    ) -> int:
        if len(chunks) != len(vectors):
            raise ValueError(
                f"chunk ({len(chunks)}) ve vektör ({len(vectors)}) sayısı eşleşmiyor"
            )
        if not chunks:
            return 0
        points = [
            qm.PointStruct(
                id=_point_id(c.chunk_id),
                vector=vectors[i].tolist(),
                payload=c.payload(),
            )
            for i, c in enumerate(chunks)
        ]
        for i in range(0, len(points), batch_size):
            self.client.upsert(
                collection_name=self.collection,
                points=points[i:i + batch_size],
                wait=True,
            )
        return len(points)

    def delete_report(self, report_id: str) -> None:
        """Rapor yeniden yüklendiğinde eski chunk'ları temizler (idempotanlık)."""
        self.client.delete(
            collection_name=self.collection,
            points_selector=qm.FilterSelector(
                filter=qm.Filter(
                    must=[qm.FieldCondition(key="report_id",
                                            match=qm.MatchValue(value=report_id))]
                )
            ),
            wait=True,
        )

    # ------------------------------------------------------------------ #
    #  Okuma
    # ------------------------------------------------------------------ #
    @staticmethod
    def build_filter(
        *,
        competition_id: str | None = None,
        category_id: str | None = None,
        section_keys: Iterable[str] | None = None,
        include_report_ids: Iterable[str] | None = None,
        exclude_report_ids: Iterable[str] | None = None,
    ) -> qm.Filter | None:
        must: list[qm.Condition] = []
        must_not: list[qm.Condition] = []

        if competition_id:
            must.append(qm.FieldCondition(key="competition_id",
                                          match=qm.MatchValue(value=competition_id)))
        if category_id:
            must.append(qm.FieldCondition(key="category_id",
                                          match=qm.MatchValue(value=category_id)))
        if section_keys:
            keys = list(section_keys)
            if keys:
                must.append(qm.FieldCondition(key="section_key",
                                              match=qm.MatchAny(any=keys)))
        if include_report_ids:
            ids = list(include_report_ids)
            if ids:
                must.append(qm.FieldCondition(key="report_id", match=qm.MatchAny(any=ids)))
        if exclude_report_ids:
            ids = list(exclude_report_ids)
            if ids:
                must_not.append(qm.FieldCondition(key="report_id", match=qm.MatchAny(any=ids)))

        if not must and not must_not:
            return None
        return qm.Filter(must=must or None, must_not=must_not or None)

    def search(
        self,
        vector: np.ndarray,
        *,
        limit: int = 10,
        query_filter: qm.Filter | None = None,
        score_threshold: float | None = None,
    ) -> list[dict[str, Any]]:
        res = self.client.query_points(
            collection_name=self.collection,
            query=vector.tolist(),
            limit=limit,
            query_filter=query_filter,
            score_threshold=score_threshold,
            with_payload=True,
        )
        return [{"score": float(p.score), **(p.payload or {})} for p in res.points]

    def search_batch(
        self,
        vectors: np.ndarray,
        *,
        limit: int = 10,
        query_filter: qm.Filter | None = None,
        score_threshold: float | None = None,
    ) -> list[list[dict[str, Any]]]:
        """Çok sayıda chunk'ı tek turda arar (benzerlik analizinin sıcak yolu)."""
        requests = [
            qm.QueryRequest(
                query=vec.tolist(),
                limit=limit,
                filter=query_filter,
                score_threshold=score_threshold,
                with_payload=True,
            )
            for vec in vectors
        ]
        if not requests:
            return []
        responses = self.client.query_batch_points(
            collection_name=self.collection, requests=requests
        )
        return [
            [{"score": float(p.score), **(p.payload or {})} for p in r.points]
            for r in responses
        ]

    def get_report_chunks(self, report_id: str, limit: int = 10_000) -> list[dict[str, Any]]:
        points, _ = self.client.scroll(
            collection_name=self.collection,
            scroll_filter=qm.Filter(
                must=[qm.FieldCondition(key="report_id",
                                        match=qm.MatchValue(value=report_id))]
            ),
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        return [p.payload or {} for p in points]

    def count(self, competition_id: str | None = None) -> int:
        flt = self.build_filter(competition_id=competition_id)
        return int(self.client.count(self.collection, count_filter=flt, exact=True).count)
