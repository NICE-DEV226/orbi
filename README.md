<div align="center">
  <img src="logo.png" alt="Orbi Logo" width="400"/>

  # Orbi — Assistant Universel Telegram

  **Bot Telegram intelligent × API REST × Dashboard Admin**

  [![Python](https://img.shields.io/badge/Python-3.12-blue?logo=python&logoColor=white)](https://python.org)
  [![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
  [![MongoDB](https://img.shields.io/badge/MongoDB-7.0-47A248?logo=mongodb&logoColor=white)](https://mongodb.com)
  [![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
  [![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker&logoColor=white)](https://docker.com)
  [![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

  *Support client · E-commerce · Communauté · Productivité · API Développeurs*

</div>

---

## Présentation

**Orbi** est une plateforme hybride pensée pour les marchés africains (XOF, Orange Money, Wave) et au-delà. Elle centralise en un seul bot Telegram :

- Un **système de support** avec tickets, SLA et satisfaction client (CSAT)
- Une **boutique en ligne** avec catalogue multilingue et passerelles de paiement
- Des outils de **productivité personnelle** (tâches, rappels, notes, Pomodoro)
- Un espace **communautaire** (sondages, karma, modération automatique)
- Un portail **développeur** avec API Keys, webhooks sortants et sandbox
- Un **dashboard d'administration** web temps réel

Tout cela en **3 langues** : Français, Anglais, Arabe — automatiquement détectées et persistées.

---

## Fonctionnalités

### 🎧 Support & Ticketing
- Création de tickets guidée par conversation (catégorie → sujet → description)
- Détection automatique de priorité par mots-clés et catégorie
- **SLA** : Urgent (1h), Haute (4h), Moyenne (24h), Basse (72h)
- Alertes SLA en temps réel à l'admin (APScheduler, toutes les 5 min)
- Enquêtes de satisfaction **CSAT** (1-5 étoiles) avec rappels automatiques
- Escalade vers un agent humain

### 🛍️ E-commerce
- Catalogue multilingue (FR/EN/AR) avec images Telegram
- Panier éphémère stocké dans **Redis**
- Codes promo (pourcentage, montant fixe, livraison gratuite)
- Checkout via **Stripe**, **Orange Money** et **Wave**
- Suivi de commande en temps réel avec historique des statuts
- Notification de disponibilité produit (alerte stock)

### 👥 Communauté
- **Sondages interactifs** avec résultats en temps réel
- Système de **karma** avec classement
- **Modération automatique** : anti-spam, anti-flood, filtrage liens et mentions
- Messages de bienvenue personnalisables et règles de groupe

### ⚡ Productivité
- Gestionnaire de **tâches** avec priorités et dates d'échéance
- **Rappels** ponctuels et récurrents
- **Notes** personnelles avec extraction automatique de hashtags et transcription vocale (Whisper)
- **Timer Pomodoro** via Redis
- **Traduction** (LibreTranslate), **conversion de devises** et **calculatrice**

### 👨‍💻 API Développeurs
- Génération de **clés API** avec scopes granulaires
- **Webhooks sortants** signés HMAC-SHA256 avec retry automatique
- **Réception GitHub webhooks** (push, PR, issues…)
- Mode **Sandbox** pour les tests
- Logs complets des appels API

### 🖥️ Dashboard Admin Web
- KPIs temps réel (utilisateurs actifs, tickets ouverts, commandes du jour)
- Gestion des utilisateurs avec recherche
- File d'attente du support avec détail des tickets
- Interface de diffusion de messages (broadcast)
- Authentification sécurisée via **JWT**

---

## Architecture technique

```
Orbi/
├── src/
│   ├── main.py                    # Entry point FastAPI + lifespan
│   ├── core/
│   │   ├── config.py              # Settings pydantic-settings
│   │   ├── database.py            # Connexion MongoDB / Beanie
│   │   ├── redis.py               # Connexion Redis
│   │   ├── i18n.py                # Chargement YAML traductions
│   │   ├── logging.py             # Logging structuré
│   │   └── performance.py         # Index MongoDB, cache, connection pooling
│   ├── bot/
│   │   ├── app.py                 # Création bot (webhook/polling)
│   │   ├── keyboards.py           # Inline keyboards centralisés
│   │   └── middlewares/           # Logging → Auth → i18n → Rate Limit
│   ├── handlers/                  # 15+ handlers Telegram (phases 3-8)
│   ├── models/                    # Documents Beanie MongoDB
│   │   ├── user.py                # User, UserRole, NotificationPreferences
│   │   ├── ticket.py              # Ticket, SLA, CSAT
│   │   ├── commerce.py            # Product, Order, PromoCode
│   │   ├── community.py           # Poll, KarmaLog, GroupConfig
│   │   ├── productivity.py        # Task, Reminder, Note
│   │   └── developer.py           # ApiKey, WebhookConfig, ApiRequestLog…
│   ├── services/                  # Logique métier
│   │   ├── ticket_service.py
│   │   ├── commerce_service.py
│   │   ├── cart_service.py
│   │   ├── payment_service.py     # Stripe, Orange Money, Wave
│   │   ├── community_service.py
│   │   ├── productivity_service.py
│   │   ├── developer_service.py
│   │   ├── notification_service.py
│   │   └── scheduler.py           # APScheduler jobs
│   ├── api/                       # REST API routers
│   │   ├── admin.py               # /api/v1/admin/*
│   │   └── dev.py                 # /api/v1/dev/*
│   ├── web/                       # Dashboard HTML
│   │   ├── router.py              # Vues Jinja2
│   │   └── auth.py                # Auth JWT web
│   ├── locales/                   # Traductions YAML
│   │   ├── fr.yml
│   │   ├── en.yml
│   │   └── ar.yml
│   └── templates/                 # Templates Jinja2
│       ├── base.html
│       ├── dashboard.html
│       ├── users.html
│       ├── tickets.html
│       ├── broadcasts.html
│       └── login.html
├── tests/
│   ├── conftest.py
│   ├── test_basic.py
│   ├── test_api.py
│   └── test_middlewares.py
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── .env.example
```

### Flux des middlewares bot

Chaque message Telegram passe par 4 middlewares exécutés en `group=-10` (avant tous les handlers) :

```
Message entrant
      │
      ▼
  LoggingMiddleware      → Log de la requête entrante
      │
      ▼
  AuthMiddleware         → Chargement/création User en DB, vérif. ban
      │   ✗ banni → ApplicationHandlerStop
      ▼
  I18nMiddleware         → Injection langue + t() dans context.user_data
      │
      ▼
  RateLimitMiddleware    → Sliding window Redis (30 req / 60s)
      │   ✗ dépassé → ApplicationHandlerStop
      ▼
  Handler métier
```

---

## Stack

| Composant | Technologie | Version |
|---|---|---|
| Langage | Python | 3.12 |
| Framework Web | FastAPI + Uvicorn | 0.115 / 0.30 |
| Bot Telegram | python-telegram-bot | 21.x |
| ODM MongoDB | Beanie + Motor | 1.26 / 3.6 |
| Cache | Redis (aioredis + hiredis) | 5.x |
| Scheduler | APScheduler | 3.10 |
| Paiements | Stripe | 10-11.x |
| Templates | Jinja2 | 3.1 |
| Auth | python-jose + passlib/bcrypt | — |
| Config | pydantic-settings | 2.5 |
| Monitoring | prometheus-client | 0.20 |
| Linter | ruff | 0.6 |
| Tests | pytest + pytest-asyncio + httpx | — |

---

## Prérequis

- **Docker** et **Docker Compose**
- Un **token de bot Telegram** (via [@BotFather](https://t.me/BotFather))
- (Optionnel) Clés Stripe, Orange Money, Wave, OpenAI (Whisper)

---

## Démarrage rapide

### Avec Docker (recommandé)

```bash
# 1. Cloner le dépôt
git clone https://github.com/NICE-DEV226/orbi.git
cd orbi

# 2. Configurer les variables d'environnement
cp .env.example .env
# Éditer .env et renseigner TELEGRAM_BOT_TOKEN, ADMIN_CHAT_ID, etc.

# 3. Lancer l'infrastructure complète
docker compose up --build -d

# 4. Vérifier que tout tourne
docker compose logs -f bot
```

Le script `docker-entrypoint.sh` attribue automatiquement le rôle `superadmin` à `ADMIN_CHAT_ID` au premier démarrage.

### En développement local

```bash
# Créer l'environnement virtuel et installer les dépendances
python -m venv .venv
source .venv/Scripts/activate  # Windows : .venv\Scripts\activate
pip install -e ".[dev]"

# Démarrer MongoDB et Redis (via Docker ou en local)
docker run -d -p 27017:27017 mongo:7.0
docker run -d -p 6379:6379 redis:7-alpine

# Configurer les variables d'environnement
cp .env.example .env

# Lancer l'application
uvicorn src.main:app --reload
```

---

## Variables d'environnement

| Variable | Description | Requis |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | Token du bot Telegram | ✅ |
| `ADMIN_CHAT_ID` | Telegram ID de l'administrateur | ✅ |
| `MONGODB_URI` | URI de connexion MongoDB | ✅ |
| `REDIS_URL` | URL Redis | ✅ |
| `JWT_SECRET` | Clé secrète JWT dashboard | ✅ |
| `TELEGRAM_WEBHOOK_URL` | URL publique pour les webhooks (prod) | — |
| `TELEGRAM_WEBHOOK_SECRET` | Secret de validation webhook | — |
| `STRIPE_SECRET_KEY` | Clé secrète Stripe | — |
| `STRIPE_WEBHOOK_SECRET` | Secret webhook Stripe | — |
| `ORANGE_MONEY_API_KEY` | Clé API Orange Money | — |
| `WAVE_API_KEY` | Clé API Wave | — |
| `OPENAI_API_KEY` | Clé OpenAI (transcription vocale Whisper) | — |
| `EXCHANGE_RATES_API_KEY` | Clé API taux de change | — |
| `LIBRETRANSLATE_URL` | URL LibreTranslate | — |
| `ENVIRONMENT` | `development` / `staging` / `production` | — |
| `LOG_LEVEL` | Niveau de log (`INFO`, `DEBUG`…) | — |

Voir `.env.example` pour la liste complète.

---

## Endpoints API

| Méthode | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Health check (MongoDB, Redis) |
| `GET` | `/docs` | Swagger UI (dev seulement) |
| `GET` | `/redoc` | ReDoc |
| `GET` | `/api/v1/admin/users` | Liste paginée des utilisateurs |
| `GET` | `/api/v1/admin/tickets` | File de tickets (filtrable) |
| `POST` | `/api/v1/admin/broadcast` | Diffusion de message |
| `POST` | `/webhook/stripe` | Webhook paiement Stripe |
| `POST` | `/webhook/orange-money` | Webhook Orange Money |
| `POST` | `/webhook/wave` | Webhook Wave |
| `POST` | `/webhook/github` | Webhook événements GitHub |
| `GET` | `/admin/` | Dashboard (authentification requise) |
| `GET` | `/admin/users` | Gestion utilisateurs |
| `GET` | `/admin/tickets` | Gestion tickets |
| `GET` | `/admin/broadcasts` | Diffusion messages |

---

## Lancer les tests

```bash
# Tous les tests
pytest

# Avec couverture
pytest --cov=src --cov-report=html

# Tests unitaires seulement
pytest -m unit

# Verbose
pytest -v
```

---

## Infrastructure Docker

```yaml
services:
  bot:           # FastAPI + Bot Telegram — port 8000
  mongodb:       # MongoDB 7.0
  redis:         # Redis 7 Alpine
  libretranslate # Traduction locale (optionnel)
```

Tous les services disposent d'un **healthcheck** et d'une politique de redémarrage automatique (`restart: always`).

---

## Modèles de données MongoDB

| Collection | Document | Description |
|---|---|---|
| `users` | `User` | Profils Telegram, rôles, préférences |
| `tickets` | `Ticket` | Tickets support avec SLA et CSAT |
| `products` | `Product` | Catalogue multilingue |
| `orders` | `Order` | Commandes avec historique statuts |
| `promo_codes` | `PromoCode` | Codes promotionnels |
| `polls` | `Poll` | Sondages communautaires |
| `karma_logs` | `KarmaLog` | Attributions de karma |
| `group_configs` | `GroupConfig` | Configuration des groupes Telegram |
| `tasks` | `Task` | Tâches personnelles |
| `reminders` | `Reminder` | Rappels one-shot |
| `notes` | `Note` | Notes avec hashtags et audio |
| `api_keys` | `ApiKey` | Clés API développeurs |
| `webhook_configs` | `WebhookConfig` | Webhooks sortants |
| `webhook_deliveries` | `WebhookDelivery` | Logs de livraison webhooks |
| `api_request_logs` | `ApiRequestLog` | Logs requêtes API |
| `error_logs` | `ErrorLog` | Erreurs applicatives |
| `github_webhook_logs` | `GithubWebhookLog` | Événements GitHub reçus |

---

## Commandes utiles

```bash
# Logs du bot en temps réel
docker compose logs -f bot

# Accéder au shell MongoDB
docker exec -it orbi_mongo mongosh

# Accéder au shell Redis
docker exec -it orbi_redis redis-cli

# Linter
ruff check src/

# Formater le code
ruff format src/
```

---

## Licence

Ce projet est distribué sous licence **MIT**. Voir le fichier [LICENSE](LICENSE) pour plus de détails.

---

<div align="center">
  Fait avec ❤️ — <strong>Orbi</strong> · Assistant Universel Telegram
</div>
