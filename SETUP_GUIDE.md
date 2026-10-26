# ─────────────────────────────────────────────
# Orbi - Guide de Configuration des Credentials
# ─────────────────────────────────────────────

## 🚀 Étapes de Configuration

### 1. Créer votre fichier .env
```bash
cp .env.example .env
```

### 2. Configuration Telegram (OBLIGATOIRE)

#### Obtenir un Token de Bot Telegram :
1. Parlez à **@BotFather** sur Telegram
2. Envoyez `/newbot`
3. Donnez un nom à votre bot (ex: "Orbi Assistant")
4. Donnez un username (ex: "orbi_bot")
5. Copiez le token reçu (format: `123456789:ABCdefGHIjklMNOpqrsTUVwxyz`)

#### Trouver votre Telegram ID :
1. Parlez à **@userinfobot** sur Telegram
2. Il vous donnera votre ID numérique

#### Configuration dans .env :
```env
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
ADMIN_CHAT_ID=123456789
```

### 3. Configuration Base de Données

#### MongoDB (automatique avec Docker) :
```env
MONGODB_URI=mongodb://mongodb:27017/orbi
MONGODB_DB=orbi
```

#### Redis (automatique avec Docker) :
```env
REDIS_URL=redis://redis:6379/0
```

### 4. Orbi Dev (agents de code distants)

Orbi Dev chiffre les clés fournisseur : générez une clé de chiffrement et placez-la dans `.env`.

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

```env
SECRETS_ENCRYPTION_KEY=<la clé générée>
```

Sans cette clé, aucune clé fournisseur ne peut être enregistrée (l'application l'indique explicitement). Pour la rotation, listez plusieurs clés séparées par des virgules : la première chiffre, toutes déchiffrent.

#### Accéder à l'interface web (rôle `admin` ou `superadmin` requis)

- **Depuis Telegram (Mini App)** : bouton « 🤖 Orbi Dev » du menu principal (ou à côté du champ de saisie pour le superadmin). Connexion automatique, sans lien. **Nécessite `BASE_URL` en https public** (domaine ou tunnel) : Telegram refuse les Mini Apps sur `http://localhost`.
- **Depuis un navigateur** : envoyez `/web` au bot ; il répond avec un lien à usage unique valable 10 minutes. En développement (`http://localhost:8000`), le lien est dans le texte du message.
- `/admin` ouvre le panneau d'administration du bot.

Le compte doit d'abord exister : envoyez `/start` au bot, puis (premier superadmin) lancez l'application avec `ADMIN_CHAT_ID` renseigné.

### 5. Module Communauté (optionnel)

Désactivé par défaut. Pour l'activer (sondages, karma, modération des groupes) :

```env
ENABLE_COMMUNITY=true
```

Attention : la modération lit le texte de **tous** les messages des groupes où le bot est présent.

## 🔧 Démarrage Rapide

### Avec Docker (recommandé) :
```bash
# 1. Configurez votre .env
cp .env.example .env
# Éditez .env avec vos credentials

# 2. Démarrez l'infrastructure
docker compose up --build -d

# 3. Vérifiez les logs
docker compose logs -f bot
```

Points d'exploitation :
- `TELEGRAM_BOT_TOKEN` et `JWT_SECRET` (32 caractères minimum) sont obligatoires ; Compose refuse de démarrer sans eux.
- Le port 8000 n'écoute que sur `127.0.0.1` par défaut (`BIND_ADDR`) : placez un reverse proxy HTTPS devant.
- `GET /livez` (process vivant, utilisé par le HEALTHCHECK Docker) et `GET /health` (readiness MongoDB + Redis).
- `GET /metrics` (Prometheus) exige `Authorization: Bearer $METRICS_API_TOKEN` ; sans token configuré, il répond 503.
- Le premier superadmin est créé depuis `ADMIN_CHAT_ID` uniquement s'il n'existe aucun superadmin ; un redémarrage ne modifie jamais les rôles.
- Orbi Dev : `SECRETS_ENCRYPTION_KEY` est requise pour enregistrer une clé fournisseur ; le suivi des exécutions tourne en arrière-plan (`ORBI_DEV_REFRESH_INTERVAL`).
- Le module Communauté est désactivé par défaut (`ENABLE_COMMUNITY`).
- MongoDB et Redis ne sont pas authentifiés et restent sur le réseau Docker interne : ne publiez pas leurs ports.
- Dépendances figées par `uv.lock` : après avoir modifié `pyproject.toml`, lancez `uv lock` et commitez le résultat.

### Lancer les tests

Les tests utilisent un **vrai MongoDB** (Redis est simulé). Démarrez une instance jetable puis lancez pytest :

```bash
docker run -d --rm --name orbi_test_mongo -p 127.0.0.1:27017:27017 mongo:7.0.45
uv sync --all-extras
TELEGRAM_BOT_TOKEN=test uv run pytest
```

> **Installer avec `uv`.** Sur Python 3.14, `pip install` échoue car Beanie y déclare une borne `<3.14` que le lockfile corrige (ADR-0006). `uv sync` installe exactement les versions verrouillées ; `pip` reste utilisable en 3.12 et 3.13.

Pour une autre instance, définissez `MONGODB_TEST_URI` (une base jetable y est créée puis supprimée). Python 3.12 à 3.14 (Beanie 2 ne déclare pas encore 3.14 mais y fonctionne : voir ADR-0006).

### En développement local :
```bash
# 1. Installez les dépendances (versions verrouillées)
uv sync

# 2. Démarrez MongoDB et Redis localement
# MongoDB : mongod
# Redis : redis-server

# 3. Lancez l'application
uvicorn src.main:app --reload
```

## 🛡️ Sécurité

### Points Critiques :
- **Jamais** partager votre `TELEGRAM_BOT_TOKEN`
- **Jamais** commit votre fichier `.env`
- **Jamais** utiliser des clés de production en développement
- Changez le `JWT_SECRET` pour une chaîne aléatoire d'au moins 32 caractères (la production refuse de démarrer sinon)

### Génération de secrets sécurisés :
```bash
# JWT Secret
openssl rand -hex 32

# Webhook Secret
openssl rand -hex 16
```

## 📊 Vérification de Configuration

### Health Check :
```bash
curl http://localhost:8000/health
```

### Test du bot :
1. Envoyez `/start` à votre bot sur Telegram
2. Vous devriez recevoir le message de bienvenue

### Documentation de l'API :
- Hors production, `http://localhost:8000/docs` expose l'interface Swagger

## 🔧 Dépannage

### Problèmes Communs :

#### Bot ne répond pas :
- Vérifiez que `TELEGRAM_BOT_TOKEN` est correct
- Vérifiez que votre ID est dans `ADMIN_CHAT_ID`
- Consultez les logs : `docker compose logs bot`

#### Erreur MongoDB :
- Vérifiez que MongoDB est démarré
- Vérifiez la connexion dans les logs

#### Erreur Redis :
- Vérifiez que Redis est démarré
- Vérifiez l'URL Redis

## 📞 Support

Si vous rencontrez des problèmes :
1. Consultez les logs Docker
2. Vérifiez votre configuration .env
3. Utilisez le health check API
4. Contactez le support technique

---

**Important** : Gardez vos credentials secrets et ne les partagez jamais !
