# Stage 1: Build environment
FROM astral/uv:debian AS builder

WORKDIR /app

# Install build dependencies and sync Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        mc \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Use uv to install dependencies with caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

# Stage 2: Runtime environment
FROM debian:bookworm-slim AS runtime

WORKDIR /app

# Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        libssl3 \
        libsasl2-2 \
        libsasl2-modules \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# Copy application code and dependencies from builder
COPY --from=builder /root/.cache/uv /root/.cache/uv
COPY --chown=appuser:appuser app /app/app
COPY --chown=appuser:appuser pyproject.toml uv.lock ./

# Ensure keys directory exists and has proper permissions
RUN mkdir -p /app/keys && chmod 755 /app/keys

# Environment variables with sensible defaults
ENV PORT=9090 \
    HOST=0.0.0.0 \
    LOG_LEVEL=info \
    PYTHONUNBUFFERED=true

# Health check endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

EXPOSE ${PORT}
EXPOSE 6698

# Use uv to run the application with proper signal handling
ENTRYPOINT ["uv", "run", "fastapi"]
CMD ["app.main:app", "--host", "${HOST}", "--port", "${PORT}", "--log-level", "${LOG_LEVEL}"]
