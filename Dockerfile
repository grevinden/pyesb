# Stage 1: Build environment
FROM astral/uv:python3.12-trixie

WORKDIR /app

# Install build dependencies and sync Python packages
#RUN --mount=type=cache,target=/var/cache/apt \
#    apt-get update && \
#    apt-get install -y --no-install-recommends mc libpython3-dev ca-certificates \
# && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock app/*.py ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

EXPOSE 9090 6698

ENTRYPOINT ["uv", "run", "fastapi", "run", "--workers=1"]
CMD ["--host=0.0.0.0", "--port=80"]
