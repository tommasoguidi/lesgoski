# ---------- Stage 0: CSS build ----------
FROM node:20-slim AS css-builder

WORKDIR /css
COPY package.json tailwind.config.js ./
COPY src/lesgoski/webapp/static/input.css src/lesgoski/webapp/static/input.css
COPY src/lesgoski/webapp/templates/ src/lesgoski/webapp/templates/
COPY src/lesgoski/webapp/static/scripts.js src/lesgoski/webapp/static/
COPY src/lesgoski/webapp/static/style.css src/lesgoski/webapp/static/

RUN npm install \
    && npx tailwindcss \
       -i src/lesgoski/webapp/static/input.css \
       -o /out/tailwind.css \
       --minify

# ---------- Stage 1: Python build ----------
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

# Copy built Tailwind CSS into the installed package's static directory
COPY --from=css-builder /out/tailwind.css /usr/local/lib/python3.12/site-packages/lesgoski/webapp/static/tailwind.css

RUN useradd --create-home appuser \
    && mkdir -p /app/data \
    && chown appuser:appuser /app/data

USER appuser
WORKDIR /app

CMD ["lesgoski-web"]
