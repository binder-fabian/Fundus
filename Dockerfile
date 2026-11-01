# Fundus – Container-Image. Funktioniert mit Docker und Podman.

FROM docker.io/library/python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev
COPY . .
RUN SECRET_KEY=build DATA_DIR=/tmp/build-data .venv/bin/python manage.py collectstatic --noinput


FROM docker.io/library/python:3.12-slim
RUN useradd --system --uid 1000 --user-group --home-dir /app fundus \
    && mkdir /data \
    && chown fundus:fundus /data
COPY --from=build --chown=fundus:fundus /app /app
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data
WORKDIR /app
USER fundus
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["gunicorn", "fundus.wsgi", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
