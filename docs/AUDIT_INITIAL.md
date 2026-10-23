# Orbi — Audit initial du dépôt

> **Date :** 23 octobre 2026  
> **Branche inspectée :** `master`  
> **Statut :** audit statique préliminaire — non exhaustif  
> **Référence produit :** [ORBI_SPECIFICATION.md](ORBI_SPECIFICATION.md)

## 1. Résumé exécutif

Le dépôt existant est une application Python orientée Telegram avec API FastAPI, dashboard web, MongoDB/Beanie, Redis, paiements, planification et plusieurs modules métier. Il ne s'agit donc pas d'un dépôt vide. En revanche, son architecture et son contrat produit actuels correspondent surtout à un assistant Telegram universel, tandis que la direction cible consiste à coordonner des outils externes de développement et d'exploitation.

La reprise doit être progressive : conserver les fonctions utiles, vérifier leur comportement réel, corriger les risques avant exposition et introduire les nouvelles capacités dans des frontières modulaires. Il est prématuré de réécrire toute l'application ou de sélectionner une nouvelle base de données sans résultats de tests et exigences mesurées.

**Limite importante :** cet audit est basé sur une lecture statique de fichiers du dépôt. Les tests n'ont pas été exécutés ici, les chemins de déploiement n'ont pas été vérifiés en environnement réel et chaque endpoint n'a pas été inspecté. Les constats ci-dessous ne constituent pas une certification de sécurité.

## 2. Éléments inspectés

- `README.md` — description et architecture revendiquée.
- `cdc.md` — cahier des charges fonctionnel historique, version 4.0, mars 2026.
- `pyproject.toml` — dépendances, versions et configuration de tests/lint.
- `src/main.py` — création de l'application, lifespan, health check et routes de webhook.
- `src/core/config.py` — configuration et valeurs par défaut.
- `src/web/auth.py` — session web, magic link et route de démonstration.
- `src/services/payment_service.py` — intégrations de paiement.
- `tests/test_api.py` — tests d'API et webhooks.
- Arborescence de `src/` et `tests/`.

## 3. Architecture observée

### Stack déclarée

- Python >= 3.12.
- FastAPI et Uvicorn.
- python-telegram-bot 21.x.
- MongoDB via Motor et Beanie.
- Redis.
- Pydantic Settings, PyYAML.
- HTTPX, APScheduler.
- JWT/Jose, Passlib/Bcrypt.
- Prometheus client.
- Pytest, pytest-asyncio, pytest-cov et Ruff en dépendances de développement.

Les contraintes de versions dans `pyproject.toml` ne prouvent pas que les versions installées en production sont identiques ni que les dépendances sont à jour.

### Modules repérés

- `src/api/` : endpoints admin et développeur.
- `src/bot/` et `src/handlers/` : bot Telegram et handlers métier.
- `src/core/` : configuration, base de données, Redis, internationalisation, logs et performance.
- `src/models/` : utilisateur, tickets, commerce, communauté, productivité et développeur.
- `src/services/` : commerce, paiement, tickets, communauté, productivité, notifications, développeur et planification.
- `src/web/` et `src/templates/` : authentification et dashboard.
- `tests/` : tests de base, middlewares et API.

La présence d'un fichier ou d'un module ne confirme pas que toutes les fonctionnalités décrites dans `README.md` ou `cdc.md` sont complètes.

## 4. Constats et risques à vérifier

### A-01 — Route de connexion de démonstration privilégiée

**Preuve observée :** `src/web/auth.py` définit `GET /dev-login`. Le handler crée ou récupère un utilisateur Telegram factice `999999` avec le rôle `superadmin`, crée une session et redirige vers le dashboard. Aucun garde d'accès n'est visible dans ce handler.

**Risque : critique si cette route est accessible dans un environnement exposé.** Un visiteur pourrait obtenir une session privilégiée. Le fait que le endpoint soit nommé « demo » ne constitue pas une protection.

**Action prioritaire :**
1. Vérifier si la route est enregistrée et accessible dans les environnements déployés.
2. La supprimer du chemin de production ou la désactiver par défaut avec un contrôle serveur strict.
3. Ajouter un test qui vérifie que le mode production refuse ce chemin.
4. Invalider toute session ou identité de démonstration existante si elle a pu être créée.
5. Ajouter une revue de toutes les autres routes d'administration.

**État :** risque identifié dans le code inspecté ; correctif non appliqué par cet audit.

### A-02 — Cookie de session sans attribut Secure explicite

**Preuve observée :** dans `src/web/auth.py`, le cookie défini après validation du magic link utilise `secure=False` et `httponly=True`, `samesite="lax"`.

**Risque : élevé en production HTTPS** si le cookie peut être envoyé sur HTTP ou si le déploiement ne force pas HTTPS.

**Action :** configurer `Secure` selon l'environnement et le déploiement, vérifier HTTPS côté reverse proxy, compléter la politique de session et tester les attributs de cookie. Revoir également la rotation de session, l'expiration et la protection CSRF des opérations qui modifient l'état.

**État :** problème de configuration visible ; correctif non appliqué.

### A-03 — Tests webhook insuffisants ou permissifs

**Preuve observée :** `tests/test_api.py` inclut des tests Stripe, Orange Money, Wave et GitHub. Le test Stripe avec signature invalide attend une réponse HTTP 200 et un statut `ignored`. Les tests Orange Money et Wave montrés construisent une charge utile de succès et vérifient la réponse du handler, mais ne démontrent pas à eux seuls la validation cryptographique ni la résistance aux rejeux.

**Risque : élevé à critique selon le code de production.** Un test peut passer alors qu'un événement non authentifié est accepté ou qu'un paiement est traité deux fois.

**Action :**
- tester explicitement l'absence de signature, la signature incorrecte et la charge utile altérée ;
- vérifier le contrat officiel de chaque fournisseur ;
- tester les événements répétés, les mauvais identifiants de commande, les montants/devise incohérents et les transitions d'état impossibles ;
- vérifier qu'un paiement n'est marqué payé qu'après une preuve serveur fiable ;
- tester la sémantique de réponse HTTP exigée par le fournisseur sans traiter silencieusement un événement invalide comme un succès métier.

**État :** qualité de couverture insuffisamment démontrée ; comportement exact à auditer dans chaque handler.

### A-04 — Clé d'idempotence de paiement générée par fenêtre temporelle

**Preuve observée :** `generate_idempotency_key` dans `src/services/payment_service.py` inclut `int(time.time() // 60)` dans le hachage.

**Risque :** la clé peut changer selon la minute ; elle ne constitue donc pas nécessairement une identité stable d'une même opération au-delà de cette fenêtre. La garantie d'idempotence doit être alignée sur l'identité durable de la tentative de paiement.

**Action :** définir la clé à partir d'un identifiant d'opération persistant, enregistrer la tentative avant l'appel externe, définir les états « résultat inconnu » et « réconciliation », et tester les retries après timeout. Vérifier les contraintes du fournisseur.

**État :** conception à revoir ; aucun changement appliqué.

### A-05 — Configuration de sécurité avec valeur JWT par défaut faible

**Preuve observée :** `src/core/config.py` définit `JWT_SECRET = "change-me-in-production"` comme valeur par défaut.

**Risque : élevé si la configuration de production peut démarrer avec cette valeur.**

**Action :** rendre le secret obligatoire en production, échouer au démarrage si la valeur par défaut ou une valeur insuffisante est utilisée, documenter la rotation et vérifier tous les usages du JWT. Ajouter un test de validation de configuration.

**État :** valeur par défaut visible ; chemins de déploiement à vérifier.

### A-06 — Exposition possible d'informations internes via health check

**Preuve observée :** `src/main.py` construit le résultat de `/health` avec les messages d'exception de MongoDB et Redis dans les champs de service.

**Risque : moyen à élevé selon l'exposition du endpoint.** Les exceptions peuvent divulguer des détails internes, des hôtes ou des informations de connexion.

**Action :** retourner un statut public minimal et conserver les détails dans les logs protégés. Séparer un endpoint de readiness interne si nécessaire.

**État :** détail visible dans le code inspecté ; correctif non appliqué.

### A-07 — Gestion d'arrêt à vérifier

**Preuve observée :** le lifespan démarre le bot et le scheduler dans un bloc de gestion d'exception, puis appelle `stop_scheduler()` et `stop_bot(bot_app)` après le `yield`.

**Risque :** si le démarrage partiel échoue avant que les références ou ressources attendues soient initialisées, l'arrêt peut échouer ou ne pas nettoyer toutes les ressources. Le comportement dépend de l'implémentation des fonctions appelées.

**Action :** tester les scénarios d'échec au démarrage et de shutdown, utiliser des références initialisées explicitement et garantir le nettoyage de chaque ressource ouverte.

**État :** hypothèse à vérifier ; pas de conclusion définitive sans lecture et tests des fonctions de lifecycle.

### A-08 — Cahier des charges historique très large

**Preuve observée :** `cdc.md` vise la parité complète de cinq modules — support, commerce, communauté, productivité et développeurs — et décrit de nombreux flux Telegram, paiements, notifications et règles de navigation.

**Risque :** maintenance coûteuse, priorité diffuse et confusion entre capacité documentée et capacité réellement testée.

**Action :** établir une matrice fonctionnelle par module, vérifier chaque flux dans le code et les tests, puis décider de conserver, refactoriser, isoler ou déprécier. Ne pas supprimer automatiquement ces modules.

**État :** périmètre documentaire confirmé ; statut réel des fonctions à inventorier.

### A-09 — Tests API ne prouvent pas le comportement complet

**Preuve observée :** les tests inspectés se concentrent sur des endpoints et des mocks. Les appels externes sont simulés dans les tests montrés.

**Risque :** tests verts possibles sans validation des contrats réels, autorisations, états persistés ou comportements de reprise.

**Action :** compléter la suite par des tests de permissions, de transitions d'état, d'idempotence, de contrats fournisseurs, de reprise après timeout et de sécurité. Exécuter réellement la suite en environnement reproductible avant de déclarer un état de référence.

**État :** échantillon de tests inspecté ; couverture globale non mesurée.

## 5. Matrice de statut initiale

| Domaine | État constaté | Prochaine action |
|---|---|---|
| Bot Telegram et handlers | Code présent | Vérifier les parcours et erreurs |
| API FastAPI | Routes enregistrées | Inventorier contrats, auth et permissions |
| Dashboard web | Templates et routes présents | Audit session, CSRF et accès |
| MongoDB/Beanie | Connexion et modèles présents | Vérifier index, migrations et invariants |
| Redis | Connexion et usages présents | Vérifier TTL, atomicité et disponibilité |
| Paiements | Code fournisseur présent | Audit signatures, idempotence et transitions |
| API développeur/webhooks | Modules présents | Vérifier scopes, HMAC, rejeu et quotas |
| Tests | Plusieurs fichiers présents | Exécuter, analyser les mocks et combler les trous |
| Orbi Dev/Ops cible | Non confirmé dans l'arborescence inspectée | Définir noyau puis premier connecteur |
| Isolation d'exécution distante | Non identifiée dans l'arborescence inspectée | Ne pas construire avant validation du besoin |

## 6. Ordre recommandé

1. **P0 — Sécurité de déploiement :** route de démo privilégiée, secrets de configuration, cookies, webhooks et endpoint health.
2. **P1 — Base de qualité :** environnement reproductible, exécution complète des tests, lint, rapport des échecs et couverture des chemins critiques.
3. **P2 — Inventaire métier :** matrice des fonctions historiques avec preuve par code/test.
4. **P3 — Architecture cible :** ADR de modularité, connecteurs et modèle d'exécution.
5. **P4 — Premier parcours Orbi Dev :** intégration d'un fournisseur existant, suivi d'exécution et affichage du résultat sans déploiement de production.

## 7. Ce qui reste à faire pour un audit complet

- Lire chaque route et service sensible, y compris `src/api/admin.py`, `src/api/dev.py`, les middlewares et les fonctions de vérification de webhooks.
- Inspecter `docker-compose.yml`, `Dockerfile`, `.env.example` et la configuration CI.
- Exécuter les tests avec dépendances disponibles et enregistrer les résultats exacts.
- Tester les accès avec utilisateurs autorisés et non autorisés.
- Vérifier les versions de dépendances et produire un rapport de vulnérabilités reproductible.
- Examiner la gestion des données personnelles, la rétention et les sauvegardes.
- Construire la matrice du cahier des charges historique.

Aucune de ces actions ne doit être considérée comme accomplie par la simple rédaction de ce rapport.
