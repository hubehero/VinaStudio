FROM node:22-slim AS web

WORKDIR /src
RUN corepack enable

COPY web/package.json web/pnpm-lock.yaml ./web/
RUN pnpm -C web install --frozen-lockfile

COPY web ./web
RUN mkdir -p vinastudio/server/static && pnpm -C web build

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libgomp1 \
        libxrender1 \
        libxext6 \
        libsm6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml README.en.md ./
COPY vinastudio ./vinastudio
COPY schemas ./schemas
COPY --from=web /src/vinastudio/server/static ./vinastudio/server/static

RUN pip install .

WORKDIR /work

ENTRYPOINT ["vinastudio-cli"]
CMD ["version", "--json"]
