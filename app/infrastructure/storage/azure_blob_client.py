from typing import BinaryIO

from azure.core.exceptions import AzureError
from azure.storage.blob import BlobServiceClient

from app.core.config import settings
from app.core.exceptions import StorageException
from app.core.logging import get_logger
from app.infrastructure.storage.base import StorageClient

logger = get_logger(__name__)


class AzureBlobStorageClient(StorageClient):
    def __init__(self):
        self._container = settings.AZURE_STORAGE_CONTAINER
        self._client = BlobServiceClient.from_connection_string(
            settings.AZURE_STORAGE_CONNECTION_STRING
        )
        self._container_client = self._client.get_container_client(self._container)

    def ensure_bucket(self) -> None:
        try:
            props = self._container_client.get_container_properties()
            logger.info("Azure Blob container ready", extra={"container": self._container})
        except AzureError as e:
            raise StorageException(f"Azure container '{self._container}' not accessible: {e}")

    def upload_file(self, object_name: str, data: BinaryIO, size: int, content_type: str = "application/pdf") -> str:
        try:
            self._container_client.upload_blob(
                name=object_name,
                data=data,
                overwrite=True,
                content_settings=self._content_settings(content_type),
            )
            logger.info("File uploaded to Azure Blob", extra={"object": object_name})
            return f"{self._container}/{object_name}"
        except AzureError as e:
            raise StorageException(str(e))

    def download_file(self, object_name: str) -> bytes:
        try:
            blob_client = self._container_client.get_blob_client(object_name)
            return blob_client.download_blob().readall()
        except AzureError as e:
            raise StorageException(str(e))

    def delete_file(self, object_name: str) -> None:
        try:
            self._container_client.delete_blob(object_name)
        except AzureError as e:
            raise StorageException(str(e))

    @staticmethod
    def _content_settings(content_type: str):
        from azure.storage.blob import ContentSettings
        return ContentSettings(content_type=content_type)
