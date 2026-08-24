"""
Cloudflare R2 Object Storage Hizmet Modülü.
Dosya yükleme, indirme, silme ve URL üretme işlemlerini gerçekleştirir.
"""

from __future__ import annotations

import os
import io
import re
from pathlib import Path
from typing import Optional, Union, Tuple
import boto3
from botocore.config import Config
from dotenv import load_dotenv

load_dotenv()

class R2Service:
    def __init__(self):
        self.account_id = os.getenv("CLOUDFLARE_ACCOUNT_ID")
        self.access_key = os.getenv("CLOUDFLARE_R2_ACCESS_KEY")
        self.secret_key = os.getenv("CLOUDFLARE_R2_SECRET_KEY")
        self.endpoint_url = os.getenv("CLOUDFLARE_R2_ENDPOINT_URL")
        self.bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET_NAME", "t-sistem")
        self._s3_client = None

    @property
    def client(self):
        if self._s3_client is None:
            if not (self.access_key and self.secret_key and self.endpoint_url):
                return None
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                config=Config(signature_version="s3v4", s3={"addressing_style": "path"})
            )
        return self._s3_client

    def slugify(self, text: str) -> str:
        """Türkçe karakterleri dönüştürür, sunucu ve URL uyumlu hale getirir."""
        tr_map = {
            'ç': 'c', 'Ç': 'c', 'ğ': 'g', 'Ğ': 'g', 'ı': 'i', 'İ': 'i', 'I': 'i',
            'ö': 'o', 'Ö': 'o', 'ş': 's', 'Ş': 's', 'ü': 'u', 'Ü': 'u',
            'â': 'a', 'Â': 'a', 'î': 'i', 'Î': 'i', 'û': 'u', 'Û': 'u'
        }
        for tr_char, eng_char in tr_map.items():
            text = text.replace(tr_char, eng_char)
        text = text.lower().strip()
        text = re.sub(r'[^a-z0-9_.]+', '_', text)
        return re.sub(r'_+', '_', text).strip('_')

    def upload_file(
        self,
        file_path_or_bytes: Union[str, Path, bytes, io.BytesIO],
        destination_key: str,
        content_type: str = "application/pdf"
    ) -> Tuple[bool, str]:
        """
        R2 Bucket'ına dosya veya bayt yükler.
        Dönüş: (success: bool, url_or_key: str)
        """
        if not self.client:
            return False, "R2 istemcisi yapılandırılmamış."

        clean_key = destination_key.lstrip("/")
        try:
            if isinstance(file_path_or_bytes, (str, Path)):
                p = Path(file_path_or_bytes)
                if not p.exists():
                    return False, f"Yerel dosya bulunamadı: {p}"
                with open(p, "rb") as f:
                    data = f.read()
            elif isinstance(file_path_or_bytes, io.BytesIO):
                data = file_path_or_bytes.getvalue()
            elif isinstance(file_path_or_bytes, bytes):
                data = file_path_or_bytes
            else:
                return False, "Geçersiz dosya tipi."

            self.client.put_object(
                Bucket=self.bucket_name,
                Key=clean_key,
                Body=data,
                ContentType=content_type
            )
            # R2 depolama anahtarı döner
            return True, clean_key
        except Exception as e:
            return False, str(e)

    def download_bytes(self, object_key: str) -> Optional[bytes]:
        """R2'den dosya baytlarını indirir."""
        if not self.client:
            return None
        clean_key = object_key.lstrip("/")
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=clean_key)
            return response["Body"].read()
        except Exception:
            return None

    def delete_file(self, object_key: str) -> bool:
        """R2'den belirtilen anahtardaki dosyayı siler."""
        if not self.client:
            return False
        clean_key = object_key.lstrip("/")
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=clean_key)
            return True
        except Exception:
            return False

    def generate_presigned_url(self, object_key: str, expires_in: int = 3600) -> str:
        """Geçici indirme URL'i üretir."""
        if not self.client:
            return ""
        clean_key = object_key.lstrip("/")
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket_name, "Key": clean_key},
                ExpiresIn=expires_in
            )
        except Exception:
            return ""


# Singleton Nesne
r2_service = R2Service()
