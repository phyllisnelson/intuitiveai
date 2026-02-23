# ── Stage 1: dependency builder ───────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install uv via the official binary image (faster than pip install uv).
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Use /app as WORKDIR so the venv paths match the runtime stage exactly.
# If the builder used a different directory (e.g. /build), scripts inside the
# venv would embed that path in their shebangs and break at runtime.
WORKDIR /app

# Layer-cache: only re-install when the lock file changes.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 2: production runtime ───────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Non-root user — principle of least privilege.
RUN groupadd --system appuser && useradd --system --gid appuser --no-create-home appuser

WORKDIR /app

# Copy only the pre-built venv and application source — no build tools needed.
COPY --from=builder /app/.venv /app/.venv
COPY app/ ./app/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c \
        "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
