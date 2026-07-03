# Зеркала по умолчанию — см. mirrors.env
ARG DOCKER_MIRROR=dockerhub.timeweb.cloud
ARG PYPI_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple

FROM ${DOCKER_MIRROR}/library/python:3.11-slim

WORKDIR /app

ENV PIP_INDEX_URL=${PYPI_MIRROR} \
    PIP_TRUSTED_HOST="pypi.tuna.tsinghua.edu.cn mirrors.aliyun.com"

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pip.conf /etc/pip.conf

COPY pyproject.toml .
RUN uv pip install --system --no-cache \
    --index-url "${PYPI_MIRROR}" \
    fastapi "uvicorn[standard]" websockets python-multipart \
    pydantic pydantic-settings \
    langchain langchain-community langgraph \
    chromadb langchain-chroma rank-bm25 \
    psutil aiosqlite sqlmodel \
    httpx python-dotenv structlog anyio aiokafka

RUN pip install --no-cache-dir pynvml || true

COPY app ./app

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=10 --start-period=60s \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
