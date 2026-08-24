"""Embedding servisi — BGE-M3 (yerel) + deterministik yedek encoder.

Tasarım kararı: encoder arkasında tek bir arayüz var (`Encoder`). Böylece
  * demo makinesinde model indirilemezse pipeline durmuyor (yedek encoder),
  * ileride modeli değiştirmek tek satırlık iş,
  * testler ağ erişimi olmadan çalışıyor.

BGE-M3 seçim gerekçesi: Türkçe dahil 100+ dil, 8192 token bağlam (rapor
bölümleri uzun), asimetrik sorgu/doküman ayrımı gerektirmiyor, MIT-uyumlu.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
from abc import ABC, abstractmethod

import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)
WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)


def l2_normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


class Encoder(ABC):
    dim: int
    name: str
    #: True ise anlamsal (parafraz yakalar), False ise yalnız sözel benzerlik.
    #: Kategori uyum analizi bu bayrağa göre yorumunu yumuşatır.
    is_semantic: bool = True

    @abstractmethod
    def encode(self, texts: list[str], *, batch_size: int | None = None) -> np.ndarray:
        """L2-normalize edilmiş (n, dim) float32 matris döner."""

    def encode_one(self, text: str) -> np.ndarray:
        return self.encode([text])[0]


class BGEM3Encoder(Encoder):
    """sentence-transformers üzerinden BAAI/bge-m3."""

    def __init__(self, model_name: str | None = None, device: str | None = None):
        from sentence_transformers import SentenceTransformer  # ağır import, tembel

        self.name = model_name or settings.embedding_model
        resolved = device or settings.embedding_device
        if resolved == "cpu":
            try:
                import torch

                if torch.cuda.is_available():
                    resolved = "cuda"
            except Exception:
                pass
        logger.info("BGE-M3 yükleniyor (%s, device=%s)", self.name, resolved)
        self.model = SentenceTransformer(self.name, device=resolved)
        self.dim = int(self.model.get_sentence_embedding_dimension())
        self.is_semantic = True

    def encode(self, texts: list[str], *, batch_size: int | None = None) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        vecs = self.model.encode(
            texts,
            batch_size=batch_size or settings.embedding_batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return vecs.astype(np.float32)


class HashingEncoder(Encoder):
    """Ağ gerektirmeyen deterministik yedek encoder.

    Kelime uniigram/bigram + karakter 4-gram özelliklerini hashing trick ile
    sabit boyuta indirger, sub-linear tf ve L2 normalizasyon uygular.
    Semantik değil sözel benzerlik ölçer; kopya/şablon tespiti için makul,
    kavramsal kategori eşleştirmesi için zayıftır. Üretimde BGE-M3 kullanılmalı.
    """

    is_semantic = False

    def __init__(self, dim: int | None = None):
        self.dim = dim or settings.embedding_dim
        self.name = f"hashing-fallback-{self.dim}"

    @staticmethod
    def _features(text: str) -> list[str]:
        words = [w.lower() for w in WORD_RE.findall(text)]
        feats: list[str] = list(words)
        feats += [f"{a}_{b}" for a, b in zip(words, words[1:])]
        compact = " ".join(words)
        feats += [f"#{compact[i:i + 4]}" for i in range(0, max(len(compact) - 3, 0), 2)]
        return feats

    def encode(self, texts: list[str], *, batch_size: int | None = None) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for feat in self._features(text):
                h = hashlib.blake2b(feat.encode("utf-8"), digest_size=8).digest()
                idx = int.from_bytes(h[:4], "little") % self.dim
                sign = 1.0 if h[4] & 1 else -1.0
                out[i, idx] += sign
        # sub-linear ölçekleme: uzun chunk'lar baskın olmasın
        out = np.sign(out) * np.log1p(np.abs(out))
        return l2_normalize(out).astype(np.float32)


_encoder: Encoder | None = None
_lock = threading.Lock()


def get_encoder(force_fallback: bool = False) -> Encoder:
    """Süreç genelinde tek encoder örneği (model yüklemesi pahalı)."""
    global _encoder
    if _encoder is not None and not force_fallback:
        return _encoder
    with _lock:
        if _encoder is not None and not force_fallback:
            return _encoder
        if force_fallback:
            _encoder = HashingEncoder()
            return _encoder
        try:
            _encoder = BGEM3Encoder()
        except Exception as exc:
            if not settings.allow_fallback_encoder:
                raise
            logger.warning(
                "BGE-M3 yüklenemedi (%s). Yedek encoder'a düşülüyor — "
                "sonuçlar sözel benzerlik düzeyinde olacak.", exc,
            )
            _encoder = HashingEncoder()
        return _encoder


def reset_encoder() -> None:
    """Testlerde encoder'ı sıfırlamak için."""
    global _encoder
    _encoder = None
