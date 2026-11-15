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

RUN pip install .

WORKDIR /work

ENTRYPOINT ["vinastudio-cli"]
CMD ["version", "--json"]
