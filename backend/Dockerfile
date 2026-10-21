FROM python:3.11-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROMETHEUS_MULTIPROC_DIR=/tmp/prometheus
RUN useradd --create-home --uid 1000 app
WORKDIR /app
COPY --from=builder /install /usr/local
COPY --chown=app:app . .
RUN mkdir -p media logs data/parser && chown -R app:app media logs data/parser
USER app
EXPOSE 8000
# Файлы метрик прошлого запуска чистим, иначе счётчики сложатся со старыми
CMD ["sh", "-c", "mkdir -p $PROMETHEUS_MULTIPROC_DIR && rm -f $PROMETHEUS_MULTIPROC_DIR/* && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --no-access-log"]
