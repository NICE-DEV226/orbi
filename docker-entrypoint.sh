#!/bin/bash
set -e

echo "Démarrage du conteneur Orbi..."

# Possibilité d'attendre la base de données ici (MongoDB)
# par exemple en utilisant un script python de ping.

echo "Initialisation de la base de données..."
python -m src.scripts.init_db

echo "Lancement de l'application..."
exec uvicorn src.main:app --host 0.0.0.0 --port 8000
