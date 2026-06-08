from abc import ABC, abstractmethod
from typing import BinaryIO


class StorageClient(ABC):

    @abstractmethod
    def ensure_bucket(self) -> None: ...

    @abstractmethod
    def upload_file(
        self,
        object_name: str,
        data: BinaryIO,
        size: int,
        content_type: str = "application/octet-stream",
    ) -> str: ...

    @abstractmethod
    def download_file(self, object_name: str) -> bytes: ...

    @abstractmethod
    def delete_file(self, object_name: str) -> None: ...
