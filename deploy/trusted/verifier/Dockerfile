ARG PYTHON_BASE=docker.io/library/python@sha256:78387bc3881b8273120a12ebe6c1ab22b018ccc2c9adf565ae1ac9b536e184ea
FROM ${PYTHON_BASE}

ENV \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml /tmp/agent-platform-pyproject.toml

RUN python - <<'PY'
import subprocess
import sys
import tomllib
from pathlib import Path

data = tomllib.loads(
    Path("/tmp/agent-platform-pyproject.toml").read_text(encoding="utf-8")
)

dependencies = list(data["project"]["dependencies"])
dependencies.extend(data["project"]["optional-dependencies"]["dev"])

subprocess.run(
    [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--no-cache-dir",
        *dependencies,
    ],
    check=True,
)
PY

RUN mkdir -p /opt/wheelhouse \
    && python -m pip download \
        --no-deps \
        --dest /opt/wheelhouse \
        "setuptools>=75"

RUN python -m pip check \
    && test -n "$(find /opt/wheelhouse -maxdepth 1 -type f -name 'setuptools-*.whl' -print -quit)" \
    && git --version \
    && python --version \
    && python -m pytest --version \
    && python -m ruff --version \
    && python -m mypy --version \
    && python -m build --version

WORKDIR /workspace

ENTRYPOINT []
