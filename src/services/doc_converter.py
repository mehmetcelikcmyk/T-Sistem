"""
Word (.docx) ➔ Orijinal Yüksek Çözünürlüklü PDF Dönüştürme Motoru.
Microsoft Word COM ve docx2pdf / Libreoffice destekli çalışır.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Union

def docx_to_pdf(input_docx_path: Union[str, Path], output_pdf_path: Optional[Union[str, Path]] = None) -> Optional[Path]:
    """
    .docx dosyasını kapak, logo ve tabloları bozulmadan %100 orijinal PDF'e dönüştürür.
    """
    in_path = Path(input_docx_path).resolve()
    if not in_path.exists():
        return None

    if output_pdf_path is None:
        out_path = in_path.with_suffix(".pdf")
    else:
        out_path = Path(output_pdf_path).resolve()

    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Yöntem: Windows Word COM (win32com)
    try:
        import win32com.client
        import pythoncom
        pythoncom.CoInitialize()
        
        # URL-encoded veya özel karakter sorunlarını aşmak için geçici ASCII dosya kullan
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_docx = Path(tmp_dir) / "source_doc.docx"
            tmp_pdf = Path(tmp_dir) / "output_doc.pdf"
            shutil.copy2(str(in_path), str(tmp_docx))

            word = win32com.client.Dispatch("Word.Application")
            word.Visible = False
            word.DisplayAlerts = False
            try:
                doc = word.Documents.Open(str(tmp_docx), ReadOnly=True)
                # wdFormatPDF = 17
                doc.SaveAs2(str(tmp_pdf), FileFormat=17)
                doc.Close(False)
            finally:
                word.Quit()
            
            if tmp_pdf.exists() and tmp_pdf.stat().st_size > 0:
                shutil.copy2(str(tmp_pdf), str(out_path))
                return out_path
    except Exception:
        pass

    # 2. Yöntem: docx2pdf kütüphanesi
    try:
        from docx2pdf import convert
        convert(str(in_path), str(out_path))
        if out_path.exists() and out_path.stat().st_size > 0:
            return out_path
    except Exception:
        pass

    return None
