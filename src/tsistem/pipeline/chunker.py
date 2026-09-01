"""Bölüm-farkında (section-aware) chunking.

Neden düz sabit-boy chunking değil:
  * Benzerlik analizinde "hangi bölüm kopyalanmış" bilgisi hakem için kritik.
    Chunk bölüm sınırını aşarsa bu bilgi kaybolur.
  * Kriter bazlı AI değerlendirmesinde (Mehmet'in prompt katmanı) ilgili
    bölümün chunk'larını filtreleyebilmek gerekiyor.

Strateji: önce bölümlere böl -> her bölümü paragraf sınırlarında topla ->
hedef token bütçesini aşınca kes -> cümle düzeyinde overlap bırak.
Şablon eşleşmesi yoksa tüm metin "govde" adıyla tek akış olarak işlenir.
"""

from __future__ import annotations

import hashlib
import re

from ..config import settings
from ..models import Chunk, Section
from .extractor import ExtractionResult, page_of_offset

PARAGRAPH_RE = re.compile(r"\n\s*\n")
SENTENCE_RE = re.compile(r"(?<=[\.\!\?])\s+(?=[A-ZÇĞİÖŞÜ0-9])")


def estimate_tokens(text: str) -> int:
    """Kaba token tahmini.

    Türkçe sondan eklemeli olduğu için kelime başına ~1.6 token düşer
    (İngilizcede ~1.3). Model tokenizer'ı yüklemeden hızlı bütçe kontrolü için
    yeterli; kesin sayım encoder katmanında yapılır.
    """
    words = len(text.split())
    return int(words * 1.6) + 1


def _split_long(text: str, max_tokens: int) -> list[str]:
    """Tek başına bütçeyi aşan paragrafı cümlelere böler."""
    sentences = SENTENCE_RE.split(text)
    out: list[str] = []
    buf: list[str] = []
    budget = 0
    for sent in sentences:
        t = estimate_tokens(sent)
        if budget + t > max_tokens and buf:
            out.append(" ".join(buf).strip())
            buf, budget = [], 0
        if t > max_tokens:  # tek cümle bile uzunsa kelimeyle kes
            words = sent.split()
            step = max(int(max_tokens / 1.6), 40)
            for i in range(0, len(words), step):
                out.append(" ".join(words[i:i + step]))
            continue
        buf.append(sent)
        budget += t
    if buf:
        out.append(" ".join(buf).strip())
    return [o for o in out if o.strip()]


def _tail_overlap(text: str, overlap_tokens: int) -> str:
    """Chunk sonundan, sonraki chunk'a taşınacak bağlam kuyruğu."""
    if overlap_tokens <= 0:
        return ""
    words = text.split()
    take = max(int(overlap_tokens / 1.6), 0)
    return " ".join(words[-take:]) if take else ""


def _chunk_id(report_id: str, ordinal: int, text: str) -> str:
    digest = hashlib.sha1(f"{report_id}:{ordinal}:{text[:200]}".encode()).hexdigest()
    return f"{report_id}-{ordinal:04d}-{digest[:8]}"


def chunk_document(
    result: ExtractionResult,
    sections: list[Section],
    *,
    report_id: str,
    competition_id: str,
    category_id: str | None = None,
    team_id: str | None = None,
    target_tokens: int | None = None,
    overlap_tokens: int | None = None,
    min_chars: int | None = None,
) -> list[Chunk]:
    target = target_tokens or settings.chunk_target_tokens
    overlap = overlap_tokens or settings.chunk_overlap_tokens
    min_c = min_chars or settings.chunk_min_chars

    # Bölüm yoksa tüm metni tek sanal bölüm say
    if sections:
        units = [(s.key, s.title, s.text, s.char_start) for s in sections]
    else:
        units = [("govde", "Gövde", result.document.full_text, 0)]

    chunks: list[Chunk] = []
    ordinal = 0

    for key, title, body, base_offset in units:
        if not body.strip():
            continue
        paragraphs = [p.strip() for p in PARAGRAPH_RE.split(body) if p.strip()]
        if not paragraphs:
            paragraphs = [body.strip()]

        buf: list[str] = []
        budget = 0
        cursor = base_offset
        carry = ""

        def flush(local_cursor: int) -> str:
            """Biriken metni chunk'a çevirir, sonraki chunk için kuyruk döner."""
            nonlocal ordinal, buf, budget
            text = " ".join(buf).strip()
            buf, budget = [], 0
            if len(text) < min_c:
                return ""
            start_page = page_of_offset(result.page_offsets, local_cursor - len(text))
            end_page = page_of_offset(result.page_offsets, local_cursor)
            cid = _chunk_id(report_id, ordinal, text)
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    report_id=report_id,
                    competition_id=competition_id,
                    category_id=category_id,
                    team_id=team_id,
                    section_key=key,
                    section_title=title,
                    page_start=min(start_page, end_page),
                    page_end=max(start_page, end_page),
                    ordinal=ordinal,
                    text=text,
                    char_count=len(text),
                    # Bölüm başlığını gömme metnine ekle: aynı cümle farklı
                    # bölümdeyse vektörü de farklı olsun.
                    embed_text=f"[{title}] {text}",
                )
            )
            ordinal += 1
            return _tail_overlap(text, overlap)

        for para in paragraphs:
            pieces = [para] if estimate_tokens(para) <= target else _split_long(para, target)
            for piece in pieces:
                t = estimate_tokens(piece)
                if budget + t > target and buf:
                    carry = flush(cursor)
                    if carry:
                        buf.append(carry)
                        budget = estimate_tokens(carry)
                buf.append(piece)
                budget += t
                cursor += len(piece) + 1
        if buf:
            flush(cursor)

    return chunks
