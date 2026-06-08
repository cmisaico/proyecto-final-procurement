"""
LLM and embedding factory.
Returns OpenAI-SDK-compatible clients pointing at either:
  - Ollama /v1 endpoint (Docker Compose development)
  - vLLM serving endpoint (Kubernetes production)
Config selects the backend via VLLM_BASE_URL / EMBEDDINGS_BASE_URL.
"""
from functools import lru_cache

from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from app.core.config import settings


@lru_cache(maxsize=1)
def get_llm(temperature: float = 0.1, max_tokens: int = 2048) -> ChatOpenAI:
    from app.core.agent_metrics import prometheus_llm_callback
    return ChatOpenAI(
        base_url=settings.VLLM_BASE_URL,
        api_key=settings.VLLM_API_KEY,
        model=settings.VLLM_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        callbacks=[prometheus_llm_callback],
    )


@lru_cache(maxsize=1)
def get_embeddings() -> OpenAIEmbeddings:
    return OpenAIEmbeddings(
        base_url=settings.EMBEDDINGS_BASE_URL,
        api_key=settings.VLLM_API_KEY,
        model=settings.EMBEDDINGS_MODEL,
        check_embedding_ctx_length=False,
        chunk_size=32,
    )
