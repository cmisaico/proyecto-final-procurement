"""
OpenAI-compatible embedding service backed by sentence-transformers.
Serves nomic-ai/nomic-embed-text-v1.5 (dim=768) via /v1/embeddings.
Drop-in replacement for Ollama embeddings in Kubernetes.
"""
import os
import time
import logging
from contextlib import asynccontextmanager
from typing import Union

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = os.getenv("MODEL_NAME", "nomic-ai/nomic-embed-text-v1.5")
EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "768"))

model: SentenceTransformer | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model
    logger.info(f"Loading embedding model: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME, trust_remote_code=True)
    model.max_seq_length = 512
    logger.info(f"Model loaded. Dimension={EMBEDDING_DIMENSION}, device={model.device}")
    yield
    model = None


app = FastAPI(
    title="Procurement Embedding Service",
    description="OpenAI-compatible /v1/embeddings endpoint",
    version="1.0.0",
    lifespan=lifespan,
)


class EmbeddingRequest(BaseModel):
    input: Union[list[str], str]
    model: str = "nomic-embed-text"
    encoding_format: str = "float"


class EmbeddingObject(BaseModel):
    object: str = "embedding"
    index: int
    embedding: list[float]


class UsageInfo(BaseModel):
    prompt_tokens: int
    total_tokens: int


class EmbeddingResponse(BaseModel):
    object: str = "list"
    data: list[EmbeddingObject]
    model: str
    usage: UsageInfo


@app.post("/v1/embeddings", response_model=EmbeddingResponse)
async def create_embeddings(request: EmbeddingRequest):
    if model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    texts = request.input if isinstance(request.input, list) else [request.input]
    if not texts:
        raise HTTPException(status_code=400, detail="Input cannot be empty")

    # nomic-embed-text requires search_document / search_query prefix
    prefixed = [f"search_document: {t}" for t in texts]

    embeddings = model.encode(
        prefixed,
        normalize_embeddings=True,
        show_progress_bar=False,
        convert_to_numpy=True,
    ).tolist()

    token_count = sum(len(t.split()) for t in texts)

    return EmbeddingResponse(
        data=[
            EmbeddingObject(index=i, embedding=emb)
            for i, emb in enumerate(embeddings)
        ],
        model=request.model,
        usage=UsageInfo(prompt_tokens=token_count, total_tokens=token_count),
    )


@app.get("/health")
async def health():
    return {
        "status": "ok" if model is not None else "loading",
        "model": MODEL_NAME,
        "dimension": EMBEDDING_DIMENSION,
        "device": str(model.device) if model else "unknown",
    }


@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "nomic-embed-text",
                "object": "model",
                "owned_by": "procurement",
            }
        ],
    }
