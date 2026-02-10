# ---------- Stage 1: build ----------
FROM python:3.12-slim AS builder

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY pyproject.toml README.md ./
COPY src/ src/

RUN pip install --no-cache-dir .

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim

# Copy installed packages and entry-point scripts from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/lesgoski-* /usr/local/bin/

RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

USER appuser
WORKDIR /app

CMD ["lesgoski-web"]
