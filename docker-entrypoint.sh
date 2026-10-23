#!/bin/sh
set -eu

echo "Démarrage du conteneur Orbi..."

# Amorçage du premier admin (avec nouvelles tentatives si MongoDB démarre encore)
python -m src.scripts.init_db

exec uvicorn src.main:app --host 0.0.0.0 --port 8000 --proxy-headers
