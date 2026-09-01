"""Analiz servisi HTTP arayüzü — Mehmet'in backend'i ile kontrat.

Bu servis, ana backend'in ÖNÜNDE değil YANINDA çalışır: ana backend
kimlik doğrulama, rol yönetimi ve hakem ekranlarını yönetir; bu servis
yalnızca ağır işi (PDF -> vektör -> analiz) yapar ve saf JSON döner.

Çalıştırma:
    uvicorn tsistem.api:app --host 0.0.0.0 --port 8100
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .analysis.similarity import retrieve_for_criterion
from .config import settings
from .models import ReportAnalysis, RetrievedContext
from .pipeline.templates import list_templates
from .service import ReportPipeline

logger = logging.getLogger(__name__)

app = FastAPI(
    title="T-Sistem · Rapor Analiz Servisi",
    description=(
        "TEKNOFEST Yapay Zekâ Destekli Değerlendirme Sistemi — "
        "PDF pipeline, vektör veritabanı ve semantik benzerlik analizi katmanı."
    ),
    version="0.1.0",
)

_pipeline: ReportPipeline | None = None


def get_pipeline() -> ReportPipeline:
    global _pipeline
    if _pipeline is None:
        _pipeline = ReportPipeline()
    return _pipeline


# --------------------------------------------------------------------------- #
#  Sağlık / meta
# --------------------------------------------------------------------------- #
@app.get("/health", tags=["meta"])
def health() -> dict:
    p = get_pipeline()
    return {
        "status": "ok",
        "encoder": p.encoder.name,
        "embedding_dim": p.encoder.dim,
        "collection": p.store.collection,
        "indexed_chunks": p.store.count(),
        "qdrant_embedded_mode": p.store.embedded,
    }


@app.get("/templates", tags=["meta"])
def templates() -> list[dict]:
    """Yarışma Yöneticisi'nin tanımladığı güncel rapor şablonları."""
    return list_templates()


# --------------------------------------------------------------------------- #
#  Ana akış — rapor analizi
# --------------------------------------------------------------------------- #
@app.post("/reports/analyze", response_model=ReportAnalysis, tags=["analiz"])
async def analyze_report(
    file: UploadFile = File(..., description="Rapor PDF dosyası"),
    report_id: str = Form(...),
    competition_id: str = Form(...),
    template_id: str = Form("teknofest_pdr_2026"),
    category_id: str | None = Form(None),
    team_id: str | None = Form(None),
    run_similarity: bool = Form(True),
    run_category_fit: bool = Form(True),
) -> ReportAnalysis:
    """PDF'i işler; dil/şablon kontrolü, kategori uyumu ve benzerlik analizini döner.

    Backend bu yanıtı doğrudan hakem ekranına taşıyabilir:
      * `template`      -> MVP 1-3 (dil, şablon, başlık/içerik kontrolü)
      * `category_fit`  -> MVP 4 (kategori uygunluğu)
      * `similarity`    -> MVP 5 (başvurular arası benzerlik + kanıt pasajları)
      * `overall_severity` -> liste ekranındaki renk kodu
    """
    if not file.filename or not file.filename.lower().endswith((".pdf", ".docx")):
        raise HTTPException(
            status_code=400,
            detail="Yalnızca PDF veya DOCX dosyası kabul edilir.",
        )

    tmp_dir = Path(tempfile.mkdtemp(prefix="tsistem_"))
    tmp_path = tmp_dir / file.filename
    try:
        with tmp_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
        return get_pipeline().ingest(
            tmp_path,
            report_id=report_id,
            competition_id=competition_id,
            template_id=template_id,
            category_id=category_id,
            team_id=team_id,
            run_similarity=run_similarity,
            run_category_fit=run_category_fit,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Analiz hatası: %s", report_id)
        raise HTTPException(status_code=500, detail=f"Analiz başarısız: {exc}") from exc
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# --------------------------------------------------------------------------- #
#  Kriter bazlı kanıt getirme — MVP 6'nın girdisi
# --------------------------------------------------------------------------- #
class CriterionRequest(BaseModel):
    report_id: str
    criteria: list[dict] = Field(
        ...,
        description=(
            "Değerlendirme kriterleri. Her öğe: "
            "{'key': 'ozgunluk', 'text': 'Projenin özgün yönü net mi?', "
            "'section_keys': ['yenilikci_yon']}"
        ),
    )
    limit: int = 6


@app.post("/reports/context", response_model=list[RetrievedContext], tags=["analiz"])
def criterion_context(payload: CriterionRequest = Body(...)) -> list[RetrievedContext]:
    """Her kriter için rapordan ilgili kanıt parçalarını getirir.

    Mehmet'in prompt katmanı bu çıktıyı LLM'e bağlam olarak verir; böylece
    üretilen puan ve gerekçe, rapordaki somut pasajlara dayanır ve hakem
    kaynağı doğrulayabilir.
    """
    p = get_pipeline()
    out: list[RetrievedContext] = []
    for c in payload.criteria:
        text = c.get("text") or c.get("key", "")
        if not text:
            continue
        hits = retrieve_for_criterion(
            criterion_text=text,
            report_id=payload.report_id,
            store=p.store,
            encoder=p.encoder,
            limit=payload.limit,
            section_keys=c.get("section_keys"),
        )
        out.append(
            RetrievedContext(
                criterion_key=c.get("key", text[:40]),
                criterion_text=text,
                chunks=hits,
            )
        )
    return out


@app.get("/reports/{report_id}/chunks", tags=["analiz"])
def report_chunks(report_id: str, limit: int = 500) -> list[dict]:
    """Raporun indekslenmiş parçaları (hata ayıklama / şeffaflık için)."""
    return get_pipeline().store.get_report_chunks(report_id, limit=limit)


@app.delete("/reports/{report_id}", tags=["analiz"])
def delete_report(report_id: str) -> dict:
    get_pipeline().store.delete_report(report_id)
    return {"deleted": report_id}


@app.get("/competitions/{competition_id}/stats", tags=["meta"])
def competition_stats(competition_id: str) -> dict:
    p = get_pipeline()
    return {
        "competition_id": competition_id,
        "indexed_chunks": p.store.count(competition_id=competition_id),
        "similarity_flag_threshold": settings.similarity_flag_threshold,
        "similarity_warn_threshold": settings.similarity_warn_threshold,
        "category_fit_threshold": settings.category_fit_threshold,
    }
