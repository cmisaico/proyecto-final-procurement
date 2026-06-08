import io
from typing import BinaryIO

from minio import Minio
from minio.error import S3Error

from app.core.config import settings
from app.core.exceptions import StorageException
from app.core.logging import get_logger
from app.infrastructure.storage.base import StorageClient

logger = get_logger(__name__)


class MinIOStorageClient(StorageClient):
    def __init__(self):
        self._client = Minio(
            endpoint=settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        self._bucket = settings.MINIO_BUCKET

    def ensure_bucket(self) -> None:
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
                logger.info("MinIO bucket created", extra={"bucket": self._bucket})
        except S3Error as e:
            raise StorageException(str(e))

    def upload_file(self, object_name: str, data: BinaryIO, size: int, content_type: str = "application/pdf") -> str:
        try:
            self.ensure_bucket()
            self._client.put_object(
                bucket_name=self._bucket,
                object_name=object_name,
                data=data,
                length=size,
                content_type=content_type,
            )
            logger.info("File uploaded to MinIO", extra={"object": object_name})
            return f"{self._bucket}/{object_name}"
        except S3Error as e:
            raise StorageException(str(e))

    def download_file(self, object_name: str) -> bytes:
        try:
            response = self._client.get_object(self._bucket, object_name)
            return response.read()
        except S3Error as e:
            raise StorageException(str(e))
        finally:
            if "response" in locals():
                response.close()
                response.release_conn()

    def delete_file(self, object_name: str) -> None:
        try:
            self._client.remove_object(self._bucket, object_name)
        except S3Error as e:
            raise StorageException(str(e))
