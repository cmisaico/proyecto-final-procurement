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
