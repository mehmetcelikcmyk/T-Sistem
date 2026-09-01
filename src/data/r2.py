"""T-Sistem · TEK Cloudflare R2 istemcisi.

Onceki kod tabaninda iki ayri R2 istemcisi vardi (`services/r2_service.py` ve
`utils/storage.py`), UC farkli bucket adi dolasiyordu ve public URL uretimi
hicbir yolda calismiyordu:

  * `r2_service.upload_file` URL degil ham object key donduruyordu,
  * `storage.upload_file_bytes` imzasiz erisilemeyen S3 API adresini donduruyordu,
  * `sartname_rehber` var olmayan `download_file` metodunu cagiriyordu.

Bu modul hepsini tek noktada toplar.

PUBLIC URL: Kullanicinin Cloudflare hesabinda custom domain tanimli oldugu icin
public erisim `CLOUDFLARE_R2_PUBLIC_URL` uzerinden yapilir. Tanimli degilse
otomatik olarak presigned URL'e duser (guvenli varsayilan).
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, BinaryIO
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("tsistem.r2")

_TR_MAP = str.maketrans({
    "ı": "i", "İ": "i", "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
})

_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".txt": "text/plain; charset=utf-8",
}


class StorageError(RuntimeError):
    """R2 hatalarinin tabani. Sessizce yutulmaz, UI'a tasinir."""


class StorageNotConfigured(StorageError):
    pass


@dataclass(frozen=True)
class StoredObject:
    key: str
    size: int
    content_type: str
    url: str


def slugify(text: str, *, max_len: int = 80) -> str:
    """Sunucu uyumlu ad: kucuk harf, Turkce karakter yok, bosluk yok.

    Kullanicinin isteri (#251): "sunucu yapisina uygun sekilde adlandir,
    kucuk harflerle, turkce karakterler olmadan, bosluk olmadan".
    """
    if not text:
        return "adsiz"
    value = str(text).translate(_TR_MAP)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return (value or "adsiz")[:max_len]


def guess_content_type(key: str) -> str:
    for ext, ctype in _CONTENT_TYPES.items():
        if key.lower().endswith(ext):
            return ctype
    return "application/octet-stream"


# ── R2 anahtar uretecleri (tek yerden, kod icinde string birlestirme yok) ──
class Keys:
    """R2 klasor hiyerarsisi. Tum anahtarlar BURADAN uretilir."""

    @staticmethod
    def logo(competition_slug: str) -> str:
        return f"logos/{slugify(competition_slug)}.png"

    @staticmethod
    def spec(competition_slug: str, branch_code: str | None = None) -> str:
        base = slugify(competition_slug)
        if branch_code:
            return f"yarismalar/{base}/sartname/{base}_{slugify(branch_code)}_sartnamesi.pdf"
        return f"yarismalar/{base}/sartname/{base}_sartnamesi.pdf"

    @staticmethod
    def template(competition_slug: str, stage_code: str, level: str = "genel",
                 ext: str = "docx", branch_code: str | None = None) -> str:
        base = slugify(competition_slug)
        stage = slugify(stage_code)
        parts = [base, stage]
        if branch_code:
            parts.append(slugify(branch_code))
        parts.append(slugify(level))
        name = "_".join(parts)
        return f"yarismalar/{base}/asamalar/{stage_code.upper()}/sablon/{name}_rapor_sablonu.{ext}"

    @staticmethod
    def report(competition_slug: str, stage_code: str, app_id: str,
               team_name: str, version: int = 1) -> str:
        base = slugify(competition_slug)
        stage = stage_code.upper()
        name = f"{slugify(team_name)}_{base}_{slugify(stage)}_raporu_v{version}.pdf"
        return f"yarismalar/{base}/asamalar/{stage}/raporlar/{app_id}/{name}"

    @staticmethod
    def report_card(competition_slug: str, stage_code: str, app_id: str, team_name: str) -> str:
        base = slugify(competition_slug)
        name = f"{slugify(team_name)}_{base}_{slugify(stage_code)}_karnesi.pdf"
        return f"karneler/{app_id}/{name}"


class R2Client:
    def __init__(
        self,
        access_key: str | None = None,
        secret_key: str | None = None,
        endpoint_url: str | None = None,
        bucket: str | None = None,
        public_base_url: str | None = None,
    ) -> None:
        self.access_key = access_key or os.getenv("CLOUDFLARE_R2_ACCESS_KEY", "")
        self.secret_key = secret_key or os.getenv("CLOUDFLARE_R2_SECRET_KEY", "")
        self.endpoint_url = endpoint_url or os.getenv("CLOUDFLARE_R2_ENDPOINT_URL", "")
        self.bucket = bucket or os.getenv("CLOUDFLARE_R2_BUCKET_NAME", "t-sistem")
        self.public_base_url = (
            public_base_url or os.getenv("CLOUDFLARE_R2_PUBLIC_URL", "")
        ).rstrip("/")
        self._client: Any = None

    # ── baglanti ──────────────────────────────────────────────────────────
    @property
    def is_configured(self) -> bool:
        return bool(self.access_key and self.secret_key and self.endpoint_url and self.bucket)

    @property
    def client(self) -> Any:
        if self._client is not None:
            return self._client
        if not self.is_configured:
            raise StorageNotConfigured(
                "R2 yapilandirilmamis. .env icinde CLOUDFLARE_R2_ACCESS_KEY, "
                "CLOUDFLARE_R2_SECRET_KEY, CLOUDFLARE_R2_ENDPOINT_URL, "
                "CLOUDFLARE_R2_BUCKET_NAME tanimli olmali."
            )
        try:
            import boto3  # type: ignore
            from botocore.config import Config  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise StorageNotConfigured("boto3 kurulu degil: pip install boto3") from exc

        self._client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path"},
                retries={"max_attempts": 3, "mode": "standard"},
            ),
        )
        return self._client

    def healthcheck(self) -> dict[str, Any]:
        try:
            self.client.head_bucket(Bucket=self.bucket)
            return {
                "ok": True,
                "bucket": self.bucket,
                "public_url": self.public_base_url or "(presigned)",
            }
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "bucket": self.bucket, "error": str(exc)}

    # ── temel islemler ────────────────────────────────────────────────────
    def upload(
        self,
        data: bytes | BinaryIO,
        key: str,
        content_type: str | None = None,
        *,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        """Dosya yukler. BASARISIZLIKTA HATA FIRLATIR — sessiz `(False, msg)` yok."""
        payload = data if isinstance(data, bytes) else data.read()
        ctype = content_type or guess_content_type(key)
        extra: dict[str, Any] = {"ContentType": ctype}
        if metadata:
            extra["Metadata"] = {k: str(v) for k, v in metadata.items()}
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=payload, **extra)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"R2 yukleme basarisiz ({key}): {exc}") from exc
        log.info("[r2] yuklendi key=%s boyut=%d", key, len(payload))
        return StoredObject(key=key, size=len(payload), content_type=ctype, url=self.url_for(key))

    def download_bytes(self, key: str) -> bytes:
        try:
            resp = self.client.get_object(Bucket=self.bucket, Key=key)
            return resp["Body"].read()
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"R2 indirme basarisiz ({key}): {exc}") from exc

    def try_download(self, key: str) -> bytes | None:
        """Yoksa None doner — ama sebebi LOGLANIR (sessiz `pass` degil)."""
        try:
            return self.download_bytes(key)
        except StorageError as exc:
            log.warning("[r2] indirilemedi key=%s sebep=%s", key, exc)
            return None

    def exists(self, key: str) -> bool:
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"R2 silme basarisiz ({key}): {exc}") from exc
        log.info("[r2] silindi key=%s", key)

    def delete_prefix(self, prefix: str) -> int:
        """Bir yarisma silindiginde dosyalarin yetim kalmamasi icin."""
        keys = [o["key"] for o in self.list(prefix)]
        for key in keys:
            self.delete(key)
        return len(keys)

    def list(self, prefix: str = "", limit: int = 1000) -> list[dict[str, Any]]:
        try:
            resp = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix, MaxKeys=limit)
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"R2 listeleme basarisiz ({prefix}): {exc}") from exc
        return [
            {"key": o["Key"], "size": o["Size"], "modified": o["LastModified"].isoformat()}
            for o in resp.get("Contents", [])
        ]

    # ── URL uretimi ───────────────────────────────────────────────────────
    def public_url(self, key: str) -> str | None:
        """Custom domain tanimliysa dogrudan erisilebilir URL."""
        if not self.public_base_url:
            return None
        return f"{self.public_base_url}/{key.lstrip('/')}"

    def presigned_url(self, key: str, expires_in: int = 3600, *, download_name: str | None = None) -> str:
        params: dict[str, Any] = {"Bucket": self.bucket, "Key": key}
        if download_name:
            params["ResponseContentDisposition"] = f'attachment; filename="{download_name}"'
        try:
            return self.client.generate_presigned_url(
                "get_object", Params=params, ExpiresIn=expires_in
            )
        except Exception as exc:  # noqa: BLE001
            raise StorageError(f"Presigned URL uretilemedi ({key}): {exc}") from exc

    def url_for(self, key: str, *, expires_in: int = 3600) -> str:
        """Public domain varsa onu, yoksa presigned URL'i dondurur."""
        return self.public_url(key) or self.presigned_url(key, expires_in)


_r2: R2Client | None = None


def get_r2() -> R2Client:
    global _r2
    if _r2 is None:
        _r2 = R2Client()
    return _r2


def reset_r2() -> None:
    global _r2
    _r2 = None


__all__ = [
    "R2Client", "get_r2", "reset_r2", "Keys", "StoredObject",
    "StorageError", "StorageNotConfigured", "slugify", "guess_content_type",
]
