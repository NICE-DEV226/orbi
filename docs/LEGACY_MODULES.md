# Orbi — Inventaire des modules historiques

> **Statut :** inventaire initial à compléter  
> **But :** décider sur des preuves, et non par intuition, du sort des modules construits autour du bot Telegram.

## Légende

- **À auditer** : présence du code confirmée, comportement réel non validé.
- **Conserver** : décision prise après évaluation, pas simplement parce que le code existe.
- **Refactoriser** : valeur confirmée, qualité ou architecture à améliorer.
- **Isoler** : utile mais ne doit pas coupler le nouveau noyau.
- **Déprécier** : fonction maintenue temporairement avec trajectoire de retrait.
- **Retirer** : retrait décidé avec vérification des dépendances et migration si nécessaire.

## Méthode et preuves

Mesures du 23 octobre 2026 sur `master` (après les lots sécurité, qualité et infra), environnement propre : 72 tests passent, ruff sans erreur, `pip-audit` sans vulnérabilité connue. La couverture est mesurée avec `pytest --cov=src` (MongoDB et Redis simulés). Le bot Telegram a été construit hors ligne avec un faux token (`create_bot_application`) : la construction réussit, 5 commandes (`/start`, `/ping`, `/test`, `/addgroup`, `/addchannel`) et 78 handlers au groupe 0 sont enregistrés, sans commande dupliquée.

**Limites :** aucun handler n'a été exercé contre l'API Telegram réelle, ni contre un vrai MongoDB (mongomock n'est pas MongoDB). Une couverture de 0 % signifie « aucune preuve automatisée », pas « cassé ». Les colonnes « Recommandation » sont des propositions argumentées ; les décisions appartiennent au responsable du projet.

## Inventaire avec preuves

| Module | Code (lignes) | Couverture | Constats vérifiés | Recommandation |
|---|---|---|---|---|
| Noyau bot : `bot/app.py`, middlewares, onboarding, menu, profil | ~1 100 | middlewares 54-96 %, handlers 0 % | Le bot se construit. Un bug réel corrigé (création d'un nouvel utilisateur impossible). `rate_limit` bien testé (96 %). | **Conserver** ; ajouter des tests de handlers |
| Identité utilisateur | 96 (modèle) | modèle 100 % | Identité = `telegram_id` unique. Pas de séparation identité plateforme / identité Telegram. | **Refactoriser** quand le web deviendra un canal principal |
| Support / tickets / SLA / CSAT | 620 (handler) + 213 + 121 | handler 0 %, service 29 %, modèle 100 % | Le plus gros handler. SLA et CSAT dépendent du scheduler (non testé). | **Isoler** (module optionnel) |
| Commerce / catalogue / panier | 521 + 178 + 115 + 187 | handler 0 %, services 0-36 % | Les paiements ont été retirés : une commande reste « en attente de paiement » indéfiniment. Aucun lien avec Orbi Dev/Ops. | **Déprécier** : module désactivable, puis retrait si inutilisé |
| Paiements | — | — | Stripe, Orange Money et Wave retirés du code (lot 2). Le modèle `Order` garde `payment_provider` et `payment_session_id`. | **Retiré** ; nettoyer les champs si le commerce est retiré |
| Communauté / sondages / karma / modération | 328 + 352 + 201 + 182 | handlers 0 %, service 0 % | `group_management` enregistre un `MessageHandler` sur **tout le texte** des groupes pour la modération anti-spam : coût et sujet de confidentialité. | **Isoler** et rendre opt-in par groupe |
| Productivité (notes, rappels, tâches) | 355 + 162 + 107 | handler 0 %, service 0 % | Rappels via le scheduler (non testé). | **Isoler** |
| API et panneau développeur | 578 (`developer_real`) + 184 (`developer`) + 65 (`api/dev`) | `api/dev` 78 %, handlers 0 % | `developer_real` est surtout un squelette : les actions `restart`, `clear_cache`, `debug_db`… répondent « Fonctionnalité en développement », les métriques sont des valeurs par défaut en dur (« 256MB », « 15% »). Le panneau crée des clés API (`ApiKey`) qu'**aucune route ne valide** : l'API utilise des tokens d'environnement. L'aide affiche des routes inexistantes (`/api/v1/users`, `/orders`). `developer.py` (événements GitHub, stats, erreurs) est réel et recoupe en partie `developer_real`. | **Refactoriser** : garder les parties réelles de `developer.py`, retirer les écrans factices |
| Webhook GitHub | 187 (service) | 47 % | Signature obligatoire et testée (lot 1). Le `delivery_id` est stocké mais **jamais dédupliqué** : un rejeu est enregistré deux fois. Seuls `push`, `issues`, `pull_request` sont résumés. | **Conserver** : première brique d'Orbi Dev ; ajouter la déduplication |
| Dashboard web et API admin | 126 + 151 + 78 | auth 84 %, router 54 %, admin API 56 % | Auth par lien magique testée. **Bug réel corrigé :** le bot envoyait `/admin/magic-login/<id>` alors que la route est `/admin/auth/<token>` (404) ; un test de bout en bout couvre maintenant le parcours. KPI `revenue_7d` codé en dur (`1250.00`) et liste de diffusions fictive ; `POST /broadcast` ne fait rien (« wip »). | **Refactoriser** : retirer les données factices, brancher ou supprimer la diffusion |
| i18n FR/EN/AR | 119 + 3×155 | 58 % | 3 fichiers de traduction de même taille (155 lignes). | **Conserver** |
| Scheduler / notifications | 183 + 78 | 0 % | APScheduler dans le process : avec plusieurs instances, chaque job s'exécute en double. Non durable (ADR-0003). | **Refactoriser** avant de bâtir l'exécution durable dessus |
| Infra / cache : `database`, `redis`, `performance` | 99 + 68 + 345 | 61 % / 50 % / 31 % | `performance.py` (345 lignes) est une couche de cache maison peu testée dont l'usage réel n'est pas prouvé. | **Conserver** `database`/`redis` ; **à auditer** `performance` |
| Code mort ou de débogage : `handlers/demo.py`, `handlers/admin.py`, `handlers/test.py` | 220 + 50 + 34 | 0 % | `demo.py` et `admin.py` ne sont importés nulle part (vérifié par recherche). `admin.py` double `admin_auth.py`. `test.py` expose publiquement `/test` et `/ping`. | **Retirer** |

## Fiche de décision par module

Pour chaque ligne, compléter :

### [Nom du module]

- **Utilisateur et valeur :**
- **Fonctionnalités revendiquées :**
- **Preuves dans le code :**
- **Tests exécutés et résultats :**
- **Dépendances entrantes/sortantes :**
- **Risques de sécurité :**
- **Coût de maintenance estimé :** faible / moyen / élevé, avec justification.
- **Décision :** conserver / refactoriser / isoler / déprécier / retirer.
- **Raison :**
- **Compatibilité et migration :**
- **Critères d'acceptation :**
- **Responsable et statut :**

## Règles de décision

1. Le README et le cahier des charges prouvent une intention, pas une implémentation fonctionnelle.
2. Un test qui utilise des mocks ne prouve pas le contrat d'un fournisseur réel.
3. Une fonction dangereuse ne doit pas rester active uniquement pour préserver la compatibilité.
4. Un module qui n'appartient pas au premier MVP peut rester isolé sans être supprimé immédiatement.
5. Une migration des identités, commandes ou paiements doit protéger l'intégrité des données existantes.
6. Aucun statut « terminé » sans preuve de test ou validation manuelle documentée.
