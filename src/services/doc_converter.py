"""T-Sistem · Word (.docx) -> PDF donusturucu.

ONCEKI DURUM
------------
Dosyanin docstring'i "LibreOffice destekli" diyordu ama KODDA `soffice` cagrisi
YOKTU. Yalnizca iki yol vardi:
  1. `win32com` (Windows + kurulu Microsoft Word),
  2. `docx2pdf` (yine Windows COM / macOS AppleScript; ustelik paket
     requirements.txt'te bile yoktu).
Linux/Docker'da ikisi de `ImportError` verir, `except Exception: pass` yutar ve
fonksiyon `None` doner. Cagiran taraf (`yonetici.py`) bunu kontrol etmedigi icin
kullaniciya HER ZAMAN "basariyla PDF'e donusturuldu" mesaji gosteriliyordu.

YENI DURUM
----------
* LibreOffice headless yolu EKLENDI (birincil, Linux/Docker'da calisir).
* Sirayla: LibreOffice -> docx2pdf -> Word COM. Ilki basarili olan kazanir.
* Basarisizlikta `ConversionError` FIRLATILIR; sahte basari yok.
* Turkce karakterlerin kutu cikmamasi icin gerekli font paketleri
  `ensure_fonts()` ile kontrol edilir ve eksikse uyari uretilir.

KURULUM (Docker/Debian):
    apt-get install -y libreoffice-writer fonts-dejavu fonts-liberation
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

log = logging.getLogger("tsistem.doc")

_SOFFICE_CANDIDATES = (
    "soffice", "libreoffice",
    "/usr/bin/soffice", "/usr/bin/libreoffice",
    "/usr/lib/libreoffice/program/soffice",
    "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    r"C:\Program Files\LibreOffice\program\soffice.exe",
)
_TIMEOUT = 180


class ConversionError(RuntimeError):
    """Donusum basarisiz. Cagiran taraf bunu KULLANICIYA gosterir."""


def find_soffice() -> str | None:
    """LibreOffice calistirilabilirini bulur."""
    env_path = os.getenv("TSISTEM_SOFFICE_PATH", "").strip()
    if env_path and Path(env_path).exists():
        return env_path
    for candidate in _SOFFICE_CANDIDATES:
        resolved = shutil.which(candidate) if os.sep not in candidate else (
            candidate if Path(candidate).exists() else None
        )
        if resolved:
            return resolved
    return None


def available_engines() -> list[str]:
    """Bu makinede kullanilabilir donusum motorlari."""
    engines: list[str] = []
    if find_soffice():
        engines.append("libreoffice")
    for module_name, engine_name in (("docx2pdf", "docx2pdf"), ("win32com.client", "word-com")):
        try:
            __import__(module_name)
        except ImportError as exc:
            log.debug("[doc] %s motoru yok: %s", engine_name, exc)
            continue
        engines.append(engine_name)
    return engines


def ensure_fonts() -> list[str]:
    """Turkce karakterler icin gerekli fontlarin varligini kontrol eder."""
    warnings: list[str] = []
    fc_list = shutil.which("fc-list")
    if not fc_list:
        return warnings
    try:
        output = subprocess.run(
            [fc_list], capture_output=True, text=True, timeout=20, check=False
        ).stdout.lower()
    except (subprocess.SubprocessError, OSError) as exc:
        log.debug("[doc] fc-list calistirilamadi: %s", exc)
        return warnings
    if "dejavu" not in output and "liberation" not in output:
        warnings.append(
            "Sistemde DejaVu/Liberation fontlari bulunamadi. Turkce karakterler "
            "PDF'te kutu olarak cikabilir. Kurulum: "
            "apt-get install -y fonts-dejavu fonts-liberation"
        )
    return warnings


# ── ana giris ──────────────────────────────────────────────────────────────
def docx_to_pdf_bytes(data: bytes, *, engine: str | None = None) -> bytes:
    """DOCX baytlarini PDF baytlarina cevirir.

    Basarisizlikta `ConversionError` firlatir — ASLA sessizce None donmez.
    """
    if not data or data[:2] != b"PK":
        raise ConversionError("Gecerli bir .docx dosyasi degil (ZIP imzasi yok).")

    engines = [engine] if engine else available_engines()
    if not engines:
        raise ConversionError(
            "Bu makinede Word -> PDF donusumu yapabilecek bir motor yok. "
            "LibreOffice kurunuz: apt-get install -y libreoffice-writer "
            "(veya TSISTEM_SOFFICE_PATH ortam degiskenini tanimlayiniz)."
        )

    errors: list[str] = []
    for name in engines:
        try:
            if name == "libreoffice":
                return _convert_libreoffice(data)
            if name == "docx2pdf":
                return _convert_docx2pdf(data)
            if name == "word-com":
                return _convert_word_com(data)
        except ConversionError as exc:
            errors.append(f"{name}: {exc}")
            log.warning("[doc] %s basarisiz: %s", name, exc)

    raise ConversionError("Tum donusum motorlari basarisiz oldu:\n  - " + "\n  - ".join(errors))


def docx_to_pdf(source: str | Path, target: str | Path | None = None) -> Path:
    """Dosya yolu tabanli surum (geriye donuk uyumluluk)."""
    src = Path(source)
    if not src.exists():
        raise ConversionError(f"Kaynak dosya bulunamadi: {src}")
    pdf_bytes = docx_to_pdf_bytes(src.read_bytes())
    out = Path(target) if target else src.with_suffix(".pdf")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(pdf_bytes)
    return out


# ── motorlar ───────────────────────────────────────────────────────────────
def _convert_libreoffice(data: bytes) -> bytes:
    """LibreOffice headless — Linux/Docker'da calisan birincil yol."""
    soffice = find_soffice()
    if not soffice:
        raise ConversionError("LibreOffice bulunamadi.")

    with tempfile.TemporaryDirectory(prefix="tsistem_doc_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "kaynak.docx"
        src.write_bytes(data)
        profile = tmp_path / "profile"

        cmd = [
            soffice, "--headless", "--norestore", "--nolockcheck", "--nodefault",
            f"-env:UserInstallation=file://{profile}",
            "--convert-to", "pdf:writer_pdf_Export",
            "--outdir", str(tmp_path), str(src),
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True,
                                    timeout=_TIMEOUT, check=False)
        except subprocess.TimeoutExpired as exc:
            raise ConversionError(f"Donusum {_TIMEOUT} saniyede tamamlanamadi.") from exc
        except OSError as exc:
            raise ConversionError(f"LibreOffice calistirilamadi: {exc}") from exc

        produced = tmp_path / "kaynak.pdf"
        if not produced.exists():
            detail = (result.stderr or result.stdout or "").strip()[:400]
            raise ConversionError(f"PDF uretilmedi. LibreOffice ciktisi: {detail or 'bos'}")
        pdf = produced.read_bytes()
        if not pdf.startswith(b"%PDF"):
            raise ConversionError("Uretilen dosya gecerli bir PDF degil.")
        return pdf


def _convert_docx2pdf(data: bytes) -> bytes:
    try:
        from docx2pdf import convert  # type: ignore
    except ImportError as exc:
        raise ConversionError("docx2pdf kurulu degil.") from exc

    with tempfile.TemporaryDirectory(prefix="tsistem_doc_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "kaynak.docx"
        src.write_bytes(data)
        out = tmp_path / "kaynak.pdf"
        try:
            convert(str(src), str(out))
        except Exception as exc:  # docx2pdf kendi hatalarini firlatir
            raise ConversionError(str(exc)) from exc
        if not out.exists():
            raise ConversionError("docx2pdf PDF uretmedi.")
        return out.read_bytes()


def _convert_word_com(data: bytes) -> bytes:
    try:
        import pythoncom  # type: ignore
        import win32com.client  # type: ignore
    except ImportError as exc:
        raise ConversionError("Microsoft Word COM arayuzu yok (yalnizca Windows).") from exc

    with tempfile.TemporaryDirectory(prefix="tsistem_doc_") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "kaynak.docx"
        src.write_bytes(data)
        out = tmp_path / "kaynak.pdf"

        pythoncom.CoInitialize()
        word = None
        try:
            word = win32com.client.DispatchEx("Word.Application")
            word.Visible = False
            word.DisplayAlerts = 0
            document = word.Documents.Open(str(src), ReadOnly=True)
            document.SaveAs(str(out), FileFormat=17)  # wdFormatPDF
            document.Close(False)
        except Exception as exc:
            raise ConversionError(str(exc)) from exc
        finally:
            if word is not None:
                try:
                    word.Quit()
                except Exception as exc:  # noqa: BLE001 - kapatma hatasi kritik degil
                    log.debug("[doc] Word kapatilamadi: %s", exc)
            pythoncom.CoUninitialize()

        if not out.exists():
            raise ConversionError("Word COM PDF uretmedi.")
        return out.read_bytes()


def diagnostics() -> dict[str, object]:
    """Kurulum durumunu ozetler — admin panelinde gosterilebilir."""
    engines = available_engines()
    return {
        "engines": engines,
        "soffice_path": find_soffice(),
        "ready": bool(engines),
        "font_warnings": ensure_fonts(),
    }


__all__ = [
    "docx_to_pdf_bytes", "docx_to_pdf", "ConversionError",
    "available_engines", "find_soffice", "ensure_fonts", "diagnostics",
]
