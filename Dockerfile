# ── Build : dépendances figées par uv.lock ──
FROM python:3.13.17-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.5 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Runtime ──
FROM python:3.13.17-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Utilisateur non-root
RUN useradd --system --create-home --uid 10001 --shell /usr/sbin/nologin orbi

COPY --from=builder --chown=orbi:orbi /app/.venv /app/.venv
COPY --chown=orbi:orbi src/ ./src/
COPY --chown=orbi:orbi --chmod=755 docker-entrypoint.sh ./

USER orbi

# Liveness uniquement : une panne MongoDB/Redis ne doit pas marquer le conteneur défaillant
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/livez', timeout=5)" || exit 1

EXPOSE 8000

CMD ["./docker-entrypoint.sh"]
