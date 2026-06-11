# Dockerfiles — Autonomous Procurement Intelligence Platform

**Fecha:** Junio 2026

---

## Resumen de imágenes

| Servicio | Archivo | Base image | Tamaño aprox. | Puerto |
|----------|---------|-----------|---------------|--------|
| API Gateway (backend) | `docker/backend/Dockerfile` | python:3.12-slim | ~350 MB | 8000 |
| Frontend | `docker/frontend/Dockerfile` | node:20-alpine | ~180 MB | 3000 |
| Embeddings Service | `docker/embeddings/Dockerfile` | python:3.12-slim | ~800 MB | 8080 |
| vLLM Inference | `docker/vllm/Dockerfile` | vllm/vllm-openai:v0.8.5.post1 | ~15 GB | 8000 |

---

## Backend — `docker/backend/Dockerfile`

```dockerfile
# Stage 1: build
ARG REGISTRY=""
FROM ${REGISTRY}python:3.12-slim AS builder

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: runtime
FROM ${REGISTRY}python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpoppler-cpp-dev \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Usuario no-root
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=appuser:appgroup guia_usuario .

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

USER appuser
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
```

### Decisiones de diseño

| Decisión | Razón |
|----------|-------|
| Multi-stage build | Stage `builder` compila dependencias con gcc; stage `runtime` no instala gcc → imagen más pequeña y menor superficie de ataque |
| `python:3.12-slim` | Imagen base mínima, sin extras innecesarios |
| `libpoppler-cpp-dev` + `poppler-utils` | Necesarios para `pdfplumber` (extracción de texto de PDFs en runtime) |
| Usuario no-root (`appuser`) | Seguridad: el proceso no corre como root dentro del contenedor |
| `--prefix=/install` | Instala paquetes en directorio separado para copiar limpiamente al stage de runtime vía `COPY --from=builder /install /usr/local` |
| `PYTHONUNBUFFERED=1` | Logs inmediatos a stdout (sin buffering), visible en `kubectl logs` |
| `--workers 2` | Uvicorn con 2 workers aprovecha múltiples vCPUs del pod |
| `ARG REGISTRY=""` | Permite cambiar el registry base (`docker.io/` en local, `ACR_NAME.azurecr.io/` en AKS) sin modificar el Dockerfile |

### Build en CI/CD

```bash
docker build \
  --build-arg REGISTRY=<ACR_NAME>.azurecr.io/ \
  -f docker/backend/Dockerfile \
  -t <ACR_NAME>.azurecr.io/procurement-api:<SHA> \
  .
```

---

## Frontend — `docker/frontend/Dockerfile`

```dockerfile
# Stage 1: build
ARG REGISTRY=""
FROM ${REGISTRY}node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
ENV BACKEND_URL=http://api-gateway.ai-platform.svc.cluster.local

RUN mkdir -p /app/public && npm run build

# Stage 2: runner
FROM ${REGISTRY}node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV BACKEND_URL=http://api-gateway.ai-platform.svc.cluster.local

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
```

### Decisiones de diseño

| Decisión | Razón |
|----------|-------|
| `node:20-alpine` | Alpine es ~50% más pequeño que la imagen base Debian de Node |
| `npm ci` | Instalación reproducible (usa `package-lock.json`), más rápido que `npm install` en CI |
| `next build` output mode `standalone` | Next.js 13+ genera una carpeta `standalone` con solo lo necesario para runtime, elimina `node_modules` del runner |
| `BACKEND_URL` DNS interno | El proxy server-side de Next.js resuelve el hostname interno del cluster (`api-gateway.ai-platform.svc.cluster.local`). El cliente nunca llama directamente al backend |
| Usuario `nextjs:nodejs` (UID 1001) | No-root, compatible con los UIDs estándar de Node en contenedores |

---

## Embeddings Service — `docker/embeddings/Dockerfile`

```dockerfile
FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --upgrade pip --no-cache-dir
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.12-slim AS runtime
RUN useradd -r -u 1001 appuser && \
    mkdir -p /home/appuser/.cache/huggingface && \
    chown -R appuser /home/appuser

WORKDIR /app
COPY --from=builder /install /usr/local
COPY main.py .
RUN chown appuser /app
USER appuser

ENV HOME=/home/appuser \
    HF_HOME=/home/appuser/.cache/huggingface

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### Decisiones de diseño

| Decisión | Razón |
|----------|-------|
| `HF_HOME` como variable de entorno | Hugging Face Hub descarga el modelo al directorio configurado. En producción se monta un PVC aquí para persistir el modelo entre reinicios |
| `/home/appuser/.cache/huggingface` | El modelo `all-MiniLM-L6-v2` (~90 MB) se descarga en el primer arranque si no está cacheado |
| Multi-stage build | Los paquetes de sentence-transformers (~700 MB) se instalan en el stage builder con las herramientas necesarias |

---

## vLLM Inference — `docker/vllm/Dockerfile`

```dockerfile
# Stage 1: builder — tooling adicional sobre imagen slim
FROM python:3.12-slim AS builder
RUN pip install --no-cache-dir --prefix=/install \
    huggingface_hub==0.26.2

# Stage 2: GPU runtime — extiende el servidor oficial vLLM
FROM vllm/vllm-openai:v0.8.5.post1 AS runtime
COPY --from=builder /install /usr/local

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
```

### Decisiones de diseño

| Decisión | Razón |
|----------|-------|
| Imagen base `vllm/vllm-openai:v0.8.5.post1` | Incluye CUDA 12.x, cuDNN, PyTorch y los binarios de vLLM. No se puede partir de `python:3.12` porque CUDA requiere imagen nvidia/cuda |
| `huggingface_hub==0.26.2` | Solo se necesita esta herramienta para descargar el modelo AWQ desde HuggingFace Hub al arrancar |
| `HF_HOME=/data/cache` | En el Helm chart se monta un PVC en `/data/cache` para persistir el modelo (~4.2 GB) entre reinicios del pod |
| `VLLM_WORKER_MULTIPROC_METHOD=spawn` | Evita conflictos de CUDA con el método `fork` por defecto en Python multiprocessing |
| `HF_HUB_DISABLE_PROGRESS_BARS=1` | Limpia los logs de inicio (las barras de progreso generan ruido en `kubectl logs`) |
| Usuario no-root `vllmuser` (UID 1001) | Seguridad, aunque el GPU Operator necesita acceso privilegiado al nivel del nodo (no del pod) |
| `ENTRYPOINT` (no `CMD`) | El chart de Helm pasa los args (`--model`, `--quantization`, etc.) directamente al entrypoint |

### Tamaño de imagen

La imagen de vLLM es ~15 GB por incluir CUDA + PyTorch + todos los kernels GPU. Se recomienda:
1. Hacer el pull una vez al crear el nodo GPU (node pool warmup)
2. Usar ACR Basic en dev (sin geo-replication)
3. Configurar `imagePullPolicy: IfNotPresent` en el Helm chart

---

## Seguridad — resumen de todas las imágenes

| Práctica | Backend | Frontend | Embeddings | vLLM |
|----------|---------|----------|------------|------|
| Multi-stage build | ✅ | ✅ | ✅ | ✅ |
| Usuario no-root | ✅ appuser | ✅ nextjs | ✅ appuser | ✅ vllmuser |
| Imagen base slim/alpine | ✅ | ✅ alpine | ✅ | ✅ (base vllm) |
| Sin secrets en imagen | ✅ | ✅ | ✅ | ✅ |
| Trivy scan en CI/CD | ✅ | — | — | — |
| `ARG REGISTRY` para ACR | ✅ | ✅ | — | — |