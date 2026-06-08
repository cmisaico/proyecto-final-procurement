# Stage 1: builder — tooling adicional sobre base slim
FROM python:3.12-slim AS builder

RUN pip install --no-cache-dir --prefix=/install \
    huggingface_hub==0.26.2

# Stage 2: GPU runtime — extiende el servidor oficial vLLM OpenAI-compatible.
# La imagen base incluye CUDA 12.x, cuDNN, PyTorch y los binarios de vLLM.
FROM vllm/vllm-openai:v0.8.5.post1 AS runtime

COPY --from=builder /install /usr/local

# Non-root user con directorio de caché dedicado
RUN useradd -r -u 1001 -m vllmuser && \
    mkdir -p /data/cache && \
    chown -R vllmuser /data/cache /home/vllmuser

USER vllmuser

ENV HOME=/home/vllmuser \
    HF_HOME=/data/cache \
    HF_HUB_DISABLE_PROGRESS_BARS=1 \
    VLLM_WORKER_MULTIPROC_METHOD=spawn

EXPOSE 8000

ENTRYPOINT ["python3", "-m", "vllm.entrypoints.openai.api_server"]
