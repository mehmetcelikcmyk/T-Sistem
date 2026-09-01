"""Merkezi konfigürasyon.

Tüm ayarlar ortam değişkeni ile ezilebilir (bkz. .env.example).
Birhan / T-Sistem — Problem 4: Yapay Zekâ Destekli Değerlendirme Sistemi
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="TSISTEM_", extra="ignore"
    )

    # ---------------- Qdrant ----------------
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    #: Rapor parçalarının tutulduğu ana koleksiyon
    collection_chunks: str = "rapor_chunks"
    #: Kategori tanımlarının (referans metinler) tutulduğu koleksiyon
    collection_categories: str = "kategori_profilleri"

    # ---------------- Embedding ----------------
    #: BAAI/bge-m3 -> 1024 boyut, 8192 token, Türkçe destekli
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024
    embedding_device: str = "cpu"  # "cuda" varsa otomatik denenir
    embedding_batch_size: int = 8
    #: Model indirilemediğinde deterministik yedek encoder'a düş
    allow_fallback_encoder: bool = True

    # ---------------- Chunking ----------------
    chunk_target_tokens: int = 512
    chunk_overlap_tokens: int = 64
    #: Bir chunk'ın anlamlı sayılması için gereken minimum karakter
    chunk_min_chars: int = 120

    # ---------------- Benzerlik eşikleri ----------------
    #: Bu değerin üstü "yüksek benzerlik" -> hakeme işaretlenir
    similarity_flag_threshold: float = 0.86
    #: Bu değerin üstü "incelenmeli" -> uyarı
    similarity_warn_threshold: float = 0.78
    #: Benzerlik raporunda bir rapor için tutulacak en fazla eşleşme
    similarity_top_k: int = 5
    #: Kategori uyumu bu değerin altındaysa "kategori uyumsuz" uyarısı
    category_fit_threshold: float = 0.55

    # ---------------- Yollar ----------------
    data_dir: Path = Field(default=PROJECT_ROOT / "data")
    cache_dir: Path = Field(default=PROJECT_ROOT / ".cache")

    @property
    def raw_dir(self) -> Path:
        return self.data_dir / "raw"

    @property
    def out_dir(self) -> Path:
        return self.data_dir / "out"


settings = Settings()
settings.cache_dir.mkdir(parents=True, exist_ok=True)
settings.out_dir.mkdir(parents=True, exist_ok=True)
