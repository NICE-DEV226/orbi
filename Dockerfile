# ── Build ──
FROM python:3.12-slim AS builder

WORKDIR /build

# Installer les dépendances système pour la compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install .

# ── Runtime ──
FROM python:3.12-slim

WORKDIR /app

# Copier les dépendances installées
COPY --from=builder /install /usr/local

# Copier le code source
COPY src/ ./src/

# Variables d'environnement Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Utilisateur non-root
RUN useradd --create-home --shell /bin/bash orbi
USER orbi

# Copier le script de démarrage
COPY docker-entrypoint.sh .
# Le script doit appartenir à root pour le chmod et ensuite étre exécuté
USER root
RUN chmod +x docker-entrypoint.sh

# Revenir à l'utilisateur non-root
USER orbi

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# Démarrage avec le script d'initialisation
CMD ["./docker-entrypoint.sh"]
