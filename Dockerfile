# ── Stage 1: Build ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /app

# Install only what pip needs for native module compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies to a known location for later copy
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ─────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# ONNX Runtime (used by fastembed) needs libgomp for parallel inference
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy only installed packages (no build tools in final image)
COPY --from=builder /install /usr/local

# Copy application code
COPY core/       core/
COPY tools/       tools/
COPY memory/      memory/
COPY models/      models/
COPY server.py    .
COPY main.py      .

# ── Runtime config ───────────────────────────────────────────────────────────
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

# Default: FastAPI server. Override CMD for CLI mode.
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
