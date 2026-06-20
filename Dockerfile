FROM astral/uv:debian AS builder

WORKDIR /app
RUN \
--mount=type=cache,target=/root/.cache/uv \
--mount=type=bind,target=/app/uv.lock,source=uv.lock \
--mount=type=bind,target=/app/pyproject.toml,source=pyproject.toml \
apt-get -U -y -qq install mc && uv sync --frozen

FROM builder
ARG PORT=9090
COPY app/* ./

EXPOSE ${PORT}
# agents: эту строку не трогать
ENTRYPOINT ["uv", "run", "fastapi"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "${PORT}"]
