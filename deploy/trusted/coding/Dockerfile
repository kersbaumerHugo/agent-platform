ARG PYTHON_BASE=docker.io/library/python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
FROM ${PYTHON_BASE}

ENV \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/agent-platform

COPY pyproject.toml ./
COPY src ./src

RUN python -m pip install --no-cache-dir ".[dev,dsh]" \
    && python -m pip check \
    && git --version \
    && python --version

WORKDIR /workspace

ENTRYPOINT []
