# syntax=docker/dockerfile:1
FROM python:3.13-slim-bookworm AS builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# Install dependencies (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

# ---------------------------------------------------------------------------
# Runtime image
# ---------------------------------------------------------------------------
FROM python:3.13-slim-bookworm

# OCI labels
LABEL org.opencontainers.image.title="pyesb-webhooker"
LABEL org.opencontainers.image.description="Webhook Delivery Service — доставщик уведомлений (OIDC + AMQP + HTTP)"
LABEL org.opencontainers.image.source="https://github.com/grevinden/pyesb-webhooker"
LABEL org.opencontainers.image.licenses="MIT"

# Signal handling — aiorun ожидает SIGTERM для graceful shutdown
STOPSIGNAL SIGTERM

WORKDIR /app

# Copy uv + venv from builder
COPY --from=builder /uv /bin/uv
COPY --from=builder /app/.venv /app/.venv

# Copy application code
COPY app/ ./app/

# Non-root user (security best practice)
RUN addgroup --system --gid 1001 app && \
    adduser --system --uid 1001 --ingroup app --no-create-home app && \
    chown -R app:app /app
USER app

# Default config
ENV FWQ_BIND_HOST=0.0.0.0
ENV FWQ_BIND_PORT=8000
ENV PATH="/app/.venv/bin:$PATH"

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000

ENTRYPOINT ["uv", "run", "--module", "app"]
