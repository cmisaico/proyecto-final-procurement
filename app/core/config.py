from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Procurement Intelligence Platform"
    APP_VERSION: str = "3.0.0"
    DEBUG: bool = False

    # PostgreSQL
    POSTGRES_HOST: str = "postgres"
    POSTGRES_PORT: int = 5432
    POSTGRES_DB: str = "procurement_db"
    POSTGRES_USER: str = "procurement"
    POSTGRES_PASSWORD: str = "procurement_pass"

    @property
    def DATABASE_URL(self) -> str:
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    @property
    def DATABASE_URL_SYNC(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # Storage backend: "minio" (local/k3s) | "azure" (AKS)
    STORAGE_BACKEND: str = "minio"

    # MinIO (used when STORAGE_BACKEND=minio)
    MINIO_ENDPOINT: str = "minio:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "procurement-docs"
    MINIO_SECURE: bool = False

    # Azure Blob Storage (used when STORAGE_BACKEND=azure)
    AZURE_STORAGE_CONNECTION_STRING: str = ""
    AZURE_STORAGE_ACCOUNT: str = "stprocurementazdev"
    AZURE_STORAGE_CONTAINER: str = "licitaciones"

    # Qdrant
    QDRANT_HOST: str = "qdrant"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "procurement_chunks"

    # LLM — OpenAI-compatible (Ollama for Docker Compose, vLLM for K8s)
    # Docker Compose default: Ollama's /v1 endpoint
    # Kubernetes: http://vllm.ai-platform.svc.cluster.local:8000/v1
    VLLM_BASE_URL: str = "http://ollama:11434/v1"
    VLLM_MODEL: str = "qwen2.5:7b"
    VLLM_API_KEY: str = "not-needed"

    # Embeddings service — OpenAI-compatible
    # Docker Compose: Ollama's /v1 endpoint  |  K8s: embedding microservice
    EMBEDDINGS_BASE_URL: str = "http://ollama:11434/v1"
    EMBEDDINGS_MODEL: str = "nomic-embed-text"
    EMBEDDING_DIMENSION: int = 768

    # Legacy Ollama settings (kept for backward compatibility)
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_LLM_MODEL: str = "qwen2.5:7b"
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"

    # Chunking
    CHUNK_SIZE: int = 1000
    CHUNK_OVERLAP: int = 200

    # Context Handling (Fase 2)
    CONTEXT_TOP_K: int = 10
    MAX_CONTEXT_TOKENS: int = 4000
    GUARDRAIL_THRESHOLD: float = 0.35

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
