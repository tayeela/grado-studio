FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    GRADO_CLOUD=1 \
    GRADO_STUDIO_DATA_DIR=/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 grado \
    && mkdir -p /app /data \
    && chown -R grado:grado /app /data

WORKDIR /app
COPY requirements-cloud.txt ./
RUN pip install --no-cache-dir -r requirements-cloud.txt

COPY --chown=grado:grado core ./core
COPY --chown=grado:grado apps/studio ./apps/studio
COPY --chown=grado:grado apps/wizard ./apps/wizard

USER grado
VOLUME ["/data"]
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health', timeout=3)"

CMD ["python", "apps/studio/server.py", "--cloud"]
