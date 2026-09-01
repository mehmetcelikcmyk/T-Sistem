"""
PDF Ingestion ve Metin Ayrıştırma Modülü — HİBRİT (Metin + Görsel)

İMZA NOTU: API katmanı yüklenen dosyayı diske yazmadan bellekte tutar
(UploadFile.read()), o yüzden imza `file_bytes: bytes`.

DAYANIKLILIK: Metin çıkarımı için birden çok arka uç SIRAYLA denenir —
pdfplumber → pypdf → pymupdf. Biri kurulu değilse veya (pymupdf'te olduğu gibi)
DLL politikası yüzünden yüklenemezse bir sonrakine geçilir. Hiçbiri çalışmazsa
success=False + Türkçe hata döner; ASLA exception fırlatmaz, uygulamayı çökertmez.

HİBRİT GÖRSEL ÇIKARIMI: extract_images_from_pdf() ile PDF içindeki gömülü
görseller (şema, grafik, devre, mimari diyagram vb.) ayrı ayrı çıkarılır.
Küçük ikonlar ve logolar MIN_IMAGE_PX eşiğiyle filtrelenir.
Görseller base64 olarak AI vision API'sine gönderilebilir.
"""
from typing import Dict, Any, List, Optional, Tuple
import io

# Görsel filtreleme eşiği — bu piksel boyutunun altındaki görseller atlanır
# (bullet, ikon, imza vb. küçük elemanlar)
MIN_IMAGE_PX = 120

# Bir değerlendirme çağrısında AI'ya gönderilecek maksimum görsel sayısı
# (token maliyeti ve hız dengesi için)
MAX_IMAGES_PER_EVAL = 20


def _bos_sonuc(filename: str, error: Optional[str]) -> Dict[str, Any]:
    return {
        "filename": filename,
        "total_pages": 0,
        "raw_text": "",
        "pages": [],
        "tables": [],
        "images": [],
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


def extract_images_from_pdf(
    file_bytes: bytes,
    min_px: int = MIN_IMAGE_PX,
    max_images: int = MAX_IMAGES_PER_EVAL,
) -> List[Dict[str, Any]]:
    """PDF içindeki gömülü görselleri çıkarır.

    Her görsel için dönen sözlük:
        page        : sayfa numarası (1-tabanlı)
        index       : sayfa içindeki görsel sırası
        ext         : dosya uzantısı ('png', 'jpeg', vb.)
        data        : ham bayt (bytes) — base64'e çevrilmeden önce
        mime_type   : 'image/png' veya 'image/jpeg' vb.
        width       : piksel genişliği
        height      : piksel yüksekliği
        label       : "Sayfa {page} — Şekil {index+1}" gibi okunabilir etiket

    Filtreler:
        - width < min_px VEYA height < min_px olan küçük ikonlar atlanır
        - Yinelenen xref'ler (aynı görsel birden fazla sayfada) yalnızca bir kez alınır
        - max_images'tan fazla görsel kesilir (en büyükler önce alınır)

    pymupdf yüklü değilse boş liste döner; ASLA exception fırlatmaz.
    """
    try:
        import pymupdf  # type: ignore
    except Exception:
        return []

    images: List[Dict[str, Any]] = []
    seen_xrefs: set = set()

    try:
        with pymupdf.open(stream=file_bytes, filetype="pdf") as doc:
            for page_no, page in enumerate(doc, 1):
                for img_idx, img_info in enumerate(page.get_images(full=True)):
                    xref = img_info[0]
                    if xref in seen_xrefs:
                        continue  # aynı görsel başka sayfada tekrar geçiyor
                    seen_xrefs.add(xref)

                    try:
                        base_img = doc.extract_image(xref)
                    except Exception:
                        continue

                    if not base_img or not base_img.get("image"):
                        continue

                    w = base_img.get("width", 0)
                    h = base_img.get("height", 0)
                    if w < min_px or h < min_px:
                        continue  # çok küçük — ikon/bullet/imza

                    ext = base_img.get("ext", "png").lower()
                    mime_map = {
                        "png": "image/png",
                        "jpeg": "image/jpeg",
                        "jpg": "image/jpeg",
                        "webp": "image/webp",
                        "gif": "image/gif",
                    }
                    mime_type = mime_map.get(ext, "image/png")

                    images.append({
                        "page": page_no,
                        "index": img_idx,
                        "ext": ext,
                        "data": base_img["image"],  # bytes
                        "mime_type": mime_type,
                        "width": w,
                        "height": h,
                        "label": f"Sayfa {page_no} — Şekil {len(images) + 1} ({w}×{h}px)",
                    })

    except Exception as e:
        print(f"[PDF görsel] çıkarım hatası: {type(e).__name__}: {e}")
        return []

    # Büyükten küçüğe sırala (en bilgi taşıyan görseller önce)
    images.sort(key=lambda x: x["width"] * x["height"], reverse=True)
    return images[:max_images]


def images_to_base64(images: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """extract_images_from_pdf() çıktısındaki 'data' baytlarını base64 dizisine çevirir.

    LLM API çağrısı için hazır format:
        [{"mime_type": "image/png", "data": "<base64>", "label": "..."}]

    'data' anahtarı bytes'tan str'e dönüştürülür; orijinal bytes korunmaz.
    """
    import base64
    result = []
    for img in images:
        raw = img.get("data")
        if not raw:
            continue
        result.append({
            "mime_type": img.get("mime_type", "image/png"),
            "data": base64.b64encode(raw).decode("utf-8"),
            "label": img.get("label", ""),
            "page": img.get("page", 0),
            "width": img.get("width", 0),
            "height": img.get("height", 0),
        })
    return result


def load_pdf(file_bytes: bytes, filename: str = "rapor.pdf") -> Dict[str, Any]:
    """Verilen PDF baytlarını okur; metin + gömülü görselleri ayıklar.

    Returns (sözleşme):
        {filename, total_pages, raw_text, pages[{page_number,text}],
         tables, images[{page,index,ext,data,mime_type,width,height,label}],
         success, error}

    'images' listesi yalnızca MIN_IMAGE_PX'ten büyük gömülü görselleri içerir.
    Görsel yoksa (veya pymupdf kurulu değilse) boş liste döner — bu bir hata DEĞİLDİR.
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

    # Görselleri her durumda çıkarmayı dene (metin boş olsa bile)
    images = extract_images_from_pdf(file_bytes)

    if not raw_text:
        # Sayfalar okundu ama metin yok -> muhtemelen taranmış (görüntü) PDF.
        # Yine de görseller varsa bunları döndür — kısmi değerlendirme mümkün.
        return {
            "filename": filename,
            "total_pages": len(pages),
            "raw_text": "",
            "pages": pages,
            "tables": [],
            "images": images,
            "success": False,
            "error": (
                "PDF'te metin katmanı bulunamadı (taranmış/görüntü PDF olabilir; OCR gerekir)."
                + (f" {len(images)} gömülü görsel bulundu." if images else "")
            ),
        }

    return {
        "filename": filename,
        "total_pages": len(pages),
        "raw_text": raw_text,
        "pages": pages,
        "tables": [],
        "images": images,
        "success": True,
        "error": None,
    }
