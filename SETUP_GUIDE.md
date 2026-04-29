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

### 4. Configuration Paiements (Optionnel)

#### Stripe :
1. Créez un compte sur [stripe.com](https://stripe.com)
2. Allez dans Developers > API keys
3. Copiez la clé secrète de test
4. Activez les webhooks pour votre endpoint

```env
STRIPE_SECRET_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
```

#### Orange Money :
1. Contactez Orange pour obtenir les clés API
2. Configurez votre marchand ID

```env
ORANGE_MONEY_API_KEY=votre_cle_api
ORANGE_MONEY_API_SECRET=votre_secret_api
ORANGE_MONEY_MERCHANT_ID=votre_id_marchand
```

#### Wave :
1. Créez un compte développeur Wave
2. Obtenez vos clés API

```env
WAVE_API_KEY=votre_cle_wave
WAVE_WEBHOOK_SECRET=votre_secret_wave
```

### 5. Configuration Services Optionnels

#### OpenAI (pour transcription vocale) :
```env
OPENAI_API_KEY=sk-...
```

#### Taux de change :
```env
EXCHANGE_RATES_API_KEY=votre_cle_api
```

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

### En développement local :
```bash
# 1. Installez les dépendances
pip install -e .

# 2. Démarrez MongoDB et Redis localement
# MongoDB : mongod
# Redis : redis-server

# 3. Lancez le bot
python -m src.main
```

## 🛡️ Sécurité

### Points Critiques :
- **Jamais** partager votre `TELEGRAM_BOT_TOKEN`
- **Jamais** commit votre fichier `.env`
- **Jamais** utiliser des clés de production en développement
- Changez le `JWT_SECRET` pour une chaîne aléatoire longue

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

### Dashboard API :
- Ouvrez `http://localhost:8000/docs` dans votre navigateur
- Testez les endpoints avec l'interface Swagger

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
