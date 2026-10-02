FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/

RUN groupadd --system app && useradd --system --gid app --home-dir /app app
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY alembic.ini ./alembic.ini
RUN uv sync --frozen --no-dev --no-install-project

COPY README.md ./README.md
COPY apps ./apps
COPY infrastructure ./infrastructure
COPY packages ./packages
COPY services ./services
COPY infrastructure/docker/start-api.sh ./start-api.sh

RUN chmod 0555 /app/start-api.sh && uv sync --frozen --no-dev

RUN chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"

CMD ["/app/start-api.sh"]
