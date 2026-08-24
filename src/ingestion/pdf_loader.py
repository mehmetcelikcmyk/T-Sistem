"""
PDF Ingestion ve Metin Ayrıştırma Modülü — GERÇEK ÇIKARIM

İMZA NOTU: API katmanı yüklenen dosyayı diske yazmadan bellekte tutar
(UploadFile.read()), o yüzden imza `file_bytes: bytes`.

DAYANIKLILIK: Metin çıkarımı için birden çok arka uç SIRAYLA denenir —
pdfplumber → pypdf → pymupdf. Biri kurulu değilse veya (pymupdf'te olduğu gibi)
DLL politikası yüzünden yüklenemezse bir sonrakine geçilir. Hiçbiri çalışmazsa
success=False + Türkçe hata döner; ASLA exception fırlatmaz, uygulamayı çökertmez.
"""
from typing import Dict, Any, List, Optional
import io


def _bos_sonuc(filename: str, error: Optional[str]) -> Dict[str, Any]:
    return {
        "filename": filename,
        "total_pages": 0,
        "raw_text": "",
        "pages": [],
        "tables": [],
        "success": error is None,
        "error": error,
    }


def _try_pdfplumber(file_bytes: bytes) -> Optional[List[Dict[str, Any]]]:
    try:
        import pdfplumber
    except Exception:
        return None
    try:
        pages: List[Dict[str, Any]] = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, sayfa in enumerate(pdf.pages):
                pages.append({"page_number": i + 1, "text": sayfa.extract_text() or ""})
        return pages
    except Exception as e:
        print(f"[PDF pdfplumber] ayrıştırma hatası: {type(e).__name__}: {e}")
        return None


def _try_pypdf(file_bytes: bytes) -> Optional[List[Dict[str, Any]]]:
    try:
        try:
            from pypdf import PdfReader
        except Exception:
            from PyPDF2 import PdfReader  # eski ad
    except Exception:
        return None
    try:
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = [{"page_number": i + 1, "text": (s.extract_text() or "")}
                 for i, s in enumerate(reader.pages)]
        return pages
    except Exception as e:
        print(f"[PDF pypdf] ayrıştırma hatası: {type(e).__name__}: {e}")
        return None


def _try_pymupdf(file_bytes: bytes) -> Optional[List[Dict[str, Any]]]:
    try:
        import pymupdf  # DLL engelliyse burada patlar -> None
    except Exception:
        return None
    try:
        pages: List[Dict[str, Any]] = []
        with pymupdf.open(stream=file_bytes, filetype="pdf") as belge:
            for i, sayfa in enumerate(belge):
                pages.append({"page_number": i + 1, "text": sayfa.get_text() or ""})
        return pages
    except Exception as e:
        print(f"[PDF pymupdf] ayrıştırma hatası: {type(e).__name__}: {e}")
        return None


def load_pdf(file_bytes: bytes, filename: str = "rapor.pdf") -> Dict[str, Any]:
    """
    Verilen PDF baytlarını okur ve sayfaları metin olarak ayıklar.

    Returns (sözleşme korunur):
        {filename, total_pages, raw_text, pages[{page_number,text}], tables,
         success, error}
    """
    if not file_bytes:
        return _bos_sonuc(filename, "Boş dosya: PDF içeriği okunamadı.")

    pages: Optional[List[Dict[str, Any]]] = None
    for arka_uc in (_try_pdfplumber, _try_pypdf, _try_pymupdf):
        pages = arka_uc(file_bytes)
        if pages is not None:
            break

    if pages is None:
        return _bos_sonuc(
            filename,
            "PDF metni çıkarılamadı: kurulu ve çalışan bir PDF kütüphanesi yok "
            "(pdfplumber / pypdf / pymupdf). 'pip install pdfplumber' önerilir.",
        )

    raw_text = "\n".join(p["text"] for p in pages).strip()
    if not raw_text:
        # Sayfalar okundu ama metin yok -> muhtemelen taranmış (görüntü) PDF.
        return {
            "filename": filename,
            "total_pages": len(pages),
            "raw_text": "",
            "pages": pages,
            "tables": [],
            "success": False,
            "error": "PDF'te metin katmanı bulunamadı (taranmış/görüntü PDF olabilir; OCR gerekir).",
        }

    return {
        "filename": filename,
        "total_pages": len(pages),
        "raw_text": raw_text,
        "pages": pages,
        "tables": [],
        "success": True,
        "error": None,
    }
