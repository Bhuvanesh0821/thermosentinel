# ThermoSentinel API (FastAPI) - production image. Build context: repository root.
#   docker build -f docker/backend.Dockerfile -t thermosentinel-api .
# Used by Render (render.yaml). Secrets (DATABASE_URL, ADMIN_API_TOKEN, NASA_FIRMS_MAP_KEY,
# SMTP_*) come from the runtime environment only - nothing secret is baked into the image.
FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # Small-instance tuning (Render free: 512 MB): one BLAS/OpenMP thread, fewer malloc arenas.
    OMP_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    MALLOC_ARENA_MAX=2 \
    APP_ENV=production \
    LOG_FORMAT=json \
    PORT=8000

WORKDIR /srv/thermosentinel

COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt

COPY backend/app backend/app
COPY database database
COPY data_pipeline data_pipeline

RUN useradd --create-home --uid 10001 thermo && chown -R thermo /srv/thermosentinel
USER thermo

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\", \"8000\")}/api/health', timeout=4)"

# One worker: the ingestion scheduler runs in-process (a database lease also guards against
# overlap). --proxy-headers trusts X-Forwarded-* from the platform's TLS proxy; streaming
# connections (SSE/WebSocket) get 10 s to close on deploy/shutdown.
CMD ["sh", "-c", "exec python -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port ${PORT} --workers 1 --proxy-headers --forwarded-allow-ips='*' --timeout-graceful-shutdown 10 --timeout-keep-alive 30 --no-server-header"]
