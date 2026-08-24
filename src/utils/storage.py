"""
Cloudflare R2 Bulut Depolama Yöneticisi
TEKNOFEST Raporlarının Cloudflare R2'ye yüklenmesi ve getirilmesi.
"""
import os
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv
from typing import Optional, Dict, Any

load_dotenv()

class CloudflareR2Storage:
    def __init__(self):
        self.endpoint_url = os.getenv("CLOUDFLARE_R2_ENDPOINT_URL")
        self.access_key = os.getenv("CLOUDFLARE_R2_ACCESS_KEY")
        self.secret_key = os.getenv("CLOUDFLARE_R2_SECRET_KEY")
        self.bucket_name = os.getenv("CLOUDFLARE_R2_BUCKET_NAME", "t-sistem-raporlar")
        
        self.client = None
        if self.endpoint_url and self.access_key and self.secret_key:
            self.client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name="auto"
            )

    def upload_file_bytes(self, file_bytes: bytes, filename: str, content_type: str = "application/pdf") -> Dict[str, Any]:
        """
        PDF dosyasını doğrudan Cloudflare R2 bucket'ına yükler.
        """
        if not self.client:
            return {"status": "LOCAL_FALLBACK", "url": f"/local_storage/{filename}", "message": "R2 yapılandırılmamış"}

        try:
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=filename,
                Body=file_bytes,
                ContentType=content_type
            )
            return {
                "status": "SUCCESS",
                "bucket": self.bucket_name,
                "key": filename,
                "r2_url": f"{self.endpoint_url}/{self.bucket_name}/{filename}"
            }
        except ClientError as e:
            print(f"[R2 Hatası]: {e}")
            return {"status": "ERROR", "error": str(e)}

    def get_file_bytes(self, filename: str) -> Optional[bytes]:
        """Bucket içerisinden dosyanın baytlarını indirir."""
        if not self.client:
            return None
        try:
            resp = self.client.get_object(Bucket=self.bucket_name, Key=filename)
            return resp["Body"].read()
        except Exception as e:
            print(f"[R2 İndirme Hatası]: {e}")
            return None

    def list_uploaded_reports(self):
        """Bucket içerisindeki kayıtlı raporları listeler."""
        if not self.client:
            return []
        try:
            resp = self.client.list_objects_v2(Bucket=self.bucket_name)
            return [obj["Key"] for obj in resp.get("Contents", [])]
        except Exception as e:
            print(f"[R2 Listeleme Hatası]: {e}")
            return []



# Uygulama genelinde tek örnek.
# routes.py "from src.utils.storage import storage" ile bu örneği kullanır;
# bu satır olmadan uygulama import aşamasında çöker.
storage = CloudflareR2Storage()
