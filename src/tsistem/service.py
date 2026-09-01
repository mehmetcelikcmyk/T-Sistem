"""Uçtan uca ingest servisi — PDF girer, ReportAnalysis çıkar.

Bu sınıf Birhan'ın modülünün dış dünyaya açılan tek kapısıdır.
Mehmet'in backend'i yalnızca `ReportPipeline.ingest(...)` ve
`retrieve_for_criterion(...)` fonksiyonlarını bilir; içerideki
extractor/chunker/encoder/qdrant zincirini bilmek zorunda değildir.
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from .analysis.category_fit import CategoryRegistry, analyze_category_fit
from .analysis.similarity import analyze_similarity
from .config import settings
from .embedding.encoder import Encoder, get_encoder
from .models import Chunk, ReportAnalysis, Severity
from .pipeline.chunker import chunk_document
from .pipeline.extractor import extract_document
from .pipeline.section_parser import build_sections, check_template, detect_headings
from .pipeline.templates import load_template
from .vectorstore.qdrant_store import QdrantStore

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {Severity.OK: 0, Severity.INFO: 1, Severity.WARN: 2, Severity.ERROR: 3}


def _worst(*severities: Severity | None) -> Severity:
    best = Severity.OK
    for s in severities:
        if s and _SEVERITY_ORDER[s] > _SEVERITY_ORDER[best]:
            best = s
    return best


class ReportPipeline:
    def __init__(
        self,
        store: QdrantStore | None = None,
        encoder: Encoder | None = None,
        *,
        auto_create_collection: bool = True,
    ):
        self.encoder = encoder or get_encoder()
        self.store = store or QdrantStore(dim=self.encoder.dim)
        if self.store.dim != self.encoder.dim:
            logger.warning(
                "Koleksiyon boyutu (%s) encoder boyutuyla (%s) uyuşmuyor; "
                "koleksiyon encoder'a göre ayarlanıyor.",
                self.store.dim, self.encoder.dim,
            )
            self.store.dim = self.encoder.dim
        if auto_create_collection:
            self.store.ensure_collection()
        self._registries: dict[str, CategoryRegistry] = {}

    # ------------------------------------------------------------------ #
    def _registry(self, competition_id: str) -> CategoryRegistry | None:
        if competition_id in self._registries:
            return self._registries[competition_id]
        try:
            reg = CategoryRegistry(competition_id)
        except FileNotFoundError:
            logger.info("Kategori tanımı yok (%s); kategori analizi atlanıyor.",
                        competition_id)
            return None
        self._registries[competition_id] = reg
        return reg

    @staticmethod
    @contextmanager
    def _timed(bucket: dict[str, float], key: str):
        t0 = time.perf_counter()
        yield
        bucket[key] = round((time.perf_counter() - t0) * 1000, 2)

    # ------------------------------------------------------------------ #
    def ingest(
        self,
        pdf_path: str | Path,   # PDF veya DOCX
        *,
        report_id: str,
        competition_id: str,
        template_id: str,
        category_id: str | None = None,
        team_id: str | None = None,
        run_similarity: bool = True,
        run_category_fit: bool = True,
        index: bool = True,
        ocr_if_scanned: bool = True,
    ) -> ReportAnalysis:
        """Tek raporu baştan sona işler.

        Sıra önemli: benzerlik analizi, raporun kendisi indekslendikten SONRA
        değil ÖNCE yapılır — aksi halde rapor kendi kendisiyle eşleşir.
        (Kendi report_id'si filtrede hariç tutulsa da, indeksleme maliyetini
        gereksiz yere sorgu yoluna sokmamak için bu sıra tercih edildi.)
        """
        timings: dict[str, float] = {}
        warnings: list[str] = []

        with self._timed(timings, "extract"):
            result = extract_document(pdf_path, ocr_if_scanned=ocr_if_scanned)

        doc = result.document
        meta = doc.meta
        if meta.is_scanned:
            warnings.append(
                "Rapor taranmış görüntü içeriyor; metin çıkarımı OCR'a dayanıyor "
                "ve doğruluk düşebilir."
            )
        if meta.total_chars < 1500:
            warnings.append(
                f"Rapordan yalnızca {meta.total_chars} karakter metin çıkarıldı; "
                "dosya bozuk veya içerik yetersiz olabilir."
            )

        template = load_template(template_id)

        with self._timed(timings, "sections"):
            headings = detect_headings(result)
            sections, match_scores = build_sections(result, template, headings)
            template_report = check_template(result, template, sections, match_scores)

        if not sections:
            warnings.append(
                "Şablon başlıklarının hiçbiri eşleştirilemedi; rapor tek gövde "
                "olarak işlendi (bölüm bazlı analiz sınırlı olacak)."
            )

        with self._timed(timings, "chunk"):
            chunks: list[Chunk] = chunk_document(
                result,
                sections,
                report_id=report_id,
                competition_id=competition_id,
                category_id=category_id,
                team_id=team_id,
            )

        with self._timed(timings, "embed"):
            texts = [c.embed_text or c.text for c in chunks]
            vectors = (
                self.encoder.encode(texts)
                if texts
                else np.zeros((0, self.encoder.dim), dtype=np.float32)
            )

        analysis = ReportAnalysis(
            report_id=report_id,
            competition_id=competition_id,
            category_id=category_id,
            team_id=team_id,
            document=meta,
            language=doc.language,
            template=template_report,
            chunk_count=len(chunks),
        )

        if run_similarity and chunks:
            with self._timed(timings, "similarity"):
                analysis.similarity = analyze_similarity(
                    report_id=report_id,
                    competition_id=competition_id,
                    chunks=chunks,
                    vectors=vectors,
                    store=self.store,
                    category_id=category_id,
                )

        if run_category_fit and chunks:
            registry = self._registry(competition_id)
            if registry is not None:
                with self._timed(timings, "category_fit"):
                    analysis.category_fit = analyze_category_fit(
                        report_id=report_id,
                        chunks=chunks,
                        vectors=vectors,
                        registry=registry,
                        encoder=self.encoder,
                        declared_category_id=category_id,
                    )

        if index and chunks:
            with self._timed(timings, "index"):
                self.store.delete_report(report_id)   # yeniden yükleme idempotan
                self.store.upsert_chunks(chunks, vectors)
            analysis.indexed = True

        analysis.warnings = warnings
        analysis.timings_ms = timings
        analysis.overall_severity = _worst(
            template_report.severity,
            analysis.similarity.severity if analysis.similarity else None,
            analysis.category_fit.severity if analysis.category_fit else None,
            Severity.WARN if warnings else Severity.OK,
        )
        return analysis

    # ------------------------------------------------------------------ #
    def reindex_competition(
        self,
        pdf_dir: str | Path,
        *,
        competition_id: str,
        template_id: str,
        manifest: dict[str, dict] | None = None,
    ) -> list[ReportAnalysis]:
        """Bir klasördeki tüm raporları sırayla işler.

        İki turlu çalışır: önce hepsi indekslenir, sonra benzerlik hesaplanır.
        Böylece ilk yüklenen rapor da kendisinden sonrakileri görebilir
        (tek turda çalışsaydı yalnız kendisinden öncekilerle kıyaslanırdı).
        """
        pdf_dir = Path(pdf_dir)
        pdfs = sorted(
            p for p in pdf_dir.iterdir()
            if p.suffix.lower() in (".pdf", ".docx", ".docm")
        )
        manifest = manifest or {}

        # 1. tur: indeksle, benzerliği atla
        for pdf in pdfs:
            info = manifest.get(pdf.name, {})
            self.ingest(
                pdf,
                report_id=info.get("report_id", pdf.stem),
                competition_id=competition_id,
                template_id=template_id,
                category_id=info.get("category_id"),
                team_id=info.get("team_id"),
                run_similarity=False,
                run_category_fit=False,
                index=True,
            )

        # 2. tur: tam analiz
        out: list[ReportAnalysis] = []
        for pdf in pdfs:
            info = manifest.get(pdf.name, {})
            out.append(
                self.ingest(
                    pdf,
                    report_id=info.get("report_id", pdf.stem),
                    competition_id=competition_id,
                    template_id=template_id,
                    category_id=info.get("category_id"),
                    team_id=info.get("team_id"),
                    run_similarity=True,
                    run_category_fit=True,
                    index=True,
                )
            )
        return out
