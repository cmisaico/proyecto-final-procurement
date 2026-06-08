class AppException(Exception):
    def __init__(self, message: str, status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DocumentNotFoundException(AppException):
    def __init__(self, document_id: str):
        super().__init__(f"Document {document_id} not found", 404)


class TenderNotFoundException(AppException):
    def __init__(self, tender_id: str):
        super().__init__(f"Tender {tender_id} not found", 404)


class StorageException(AppException):
    def __init__(self, message: str):
        super().__init__(f"Storage error: {message}", 503)


class ProcessingException(AppException):
    def __init__(self, message: str):
        super().__init__(f"Processing error: {message}", 422)


class VectorStoreException(AppException):
    def __init__(self, message: str):
        super().__init__(f"Vector store error: {message}", 503)
