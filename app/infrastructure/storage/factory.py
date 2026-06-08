from app.core.config import settings
from app.infrastructure.storage.base import StorageClient


def _build_storage_client() -> StorageClient:
    if settings.STORAGE_BACKEND == "azure":
        from app.infrastructure.storage.azure_blob_client import AzureBlobStorageClient
        return AzureBlobStorageClient()
    from app.infrastructure.storage.minio_client import MinIOStorageClient
    return MinIOStorageClient()


storage_client: StorageClient = _build_storage_client()
