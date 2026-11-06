FROM python:3.11-slim AS builder
WORKDIR /build

# Зависимости для сборки lxml и других пакетов
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus

# Runtime-библиотеки для lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 \
    libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:app backend/ .
RUN mkdir -p media logs data/parser && chown -R app:app media logs data/parser
USER app
EXPOSE 8000

# Файлы метрик прошлого запуска чистим, иначе счётчики сложатся со старыми
CMD ["sh", "-c", "mkdir -p $PROMETHEUS_MULTIPROC_DIR && rm -f $PROMETHEUS_MULTIPROC_DIR/* && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log"]