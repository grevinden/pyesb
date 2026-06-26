# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# Install dependencies (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application code
COPY app/ ./app/

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

# Default config via env vars
ENV FWQ_BIND_HOST=0.0.0.0
ENV FWQ_BIND_PORT=8000

CMD ["uv", "run", "fastapi", "run", "--host=0.0.0.0", "--port=8000"]
