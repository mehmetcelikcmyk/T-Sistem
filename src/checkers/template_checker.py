"""
TEKNOFEST Rapor Şablon ve Format Uygunluk Kontrolörü

SÖZLEŞME (bkz. docs/ENTEGRASYON_SOZLESMESI.md):
  check_template() çıktısı src/api/schemas.py -> TemplateCheckResult şemasına
  BİREBİR uymak zorundadır.

İMZA NOTU: Bu fonksiyon eskiden `pdf_path: str` alıyordu. Ancak API katmanı
yüklenen dosyayı diske yazmadan bellekte tutuyor (UploadFile.read()), yani
çağrı anında bir dosya yolu YOK. Bu yüzden imza `file_bytes: bytes` oldu.
PyMuPDF ve pdfplumber ikisi de bellekten okumayı destekler:
    fitz.open(stream=file_bytes, filetype="pdf")
    pdfplumber.open(io.BytesIO(file_bytes))
"""
from typing import Dict, Any

DEFAULT_MAX_PAGES = 15


def check_template(
    file_bytes: bytes,
    max_pages: int = DEFAULT_MAX_PAGES,
    filename: str = "rapor.pdf",
) -> Dict[str, Any]:
    """
    Raporun sayfa sayısı, sayfa düzeni ve font kurallarına uygunluğunu denetler.

    TODO(Birhan - Issue #2): sayfa sayısı, kenar boşlukları ve font boyutu
      analizini kodla. DÖNÜŞ YAPISINI değiştirme.

    Args:
        file_bytes: PDF dosyasının ham baytları (diske yazmaya gerek yok).
        max_pages:  Şartnamenin izin verdiği en fazla sayfa sayısı.
        filename:   Yalnızca loglama / uyarı metinleri için.

    Returns:
        {
          "page_count": int,                    # tespit edilen sayfa sayısı
          "max_allowed": int,                   # şartname sınırı
          "is_valid": bool,                     # sınır aşılmadı ve uyarı yok
          "font_family_detected": str | None,   # ör. "Arial (11pt)"
          "warnings": list[str],                # hakeme gösterilecek Türkçe uyarılar
        }
    """
    # --- Geçici iskelet davranışı: gerçek PDF analizi yapılmıyor ---
    page_count = 0
    font_family_detected = None
    warnings: list = []
    # ---------------------------------------------------------------

    if page_count > max_pages:
        warnings.append(
            f"Rapor {page_count} sayfa; şartname en fazla {max_pages} sayfaya izin veriyor."
        )

    return {
        "page_count": page_count,
        "max_allowed": max_pages,
        "is_valid": len(warnings) == 0,
        "font_family_detected": font_family_detected,
        "warnings": warnings,
    }
