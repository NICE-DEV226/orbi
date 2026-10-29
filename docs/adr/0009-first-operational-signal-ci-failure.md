# ADR-0009 — Premier signal d'exploitation : l'échec d'une exécution GitHub Actions

- **Statut :** proposition de conception, non construite ; à valider par le responsable du projet
- **Date :** 2026-10-29
- **Lié à :** [Direction produit](../PRODUCT_DIRECTION.md), [ADR-0002](0002-integrate-existing-agents.md), [ADR-0003](0003-durable-execution-model.md), [ROADMAP phase 5](../ROADMAP.md)

## Contexte

La direction produit retient (29 octobre 2026) deux étapes : le contrôle mobile d'agents (existant), puis **un seul** signal d'exploitation relié à une résolution vérifiable. Le signal choisi est l'échec d'une exécution GitHub Actions, parce que le dépôt reçoit déjà des webhooks GitHub signés (`POST /webhook/github`, HMAC, secret obligatoire) et que la résolution (une pull request de correctif confiée à un agent) est déjà le parcours d'Orbi Dev.

**Condition d'entrée :** le parcours Orbi Dev jusqu'à la pull request doit d'abord être confirmé avec un compte fournisseur réel. Ce document ne change pas cette priorité.

## État du code (observé le 2026-10-29)

- `main.py:/webhook/github` vérifie la signature puis enregistre l'événement en arrière-plan.
- `developer_service.process_github_webhook` ne résume que `push`, `issues`, `pull_request`. Il ne lit ni `workflow_run` ni `check_run`.
- Le `delivery_id` est stocké mais **jamais dédupliqué** : un rejeu est enregistré deux fois.
- Le webhook n'est relié à aucun projet ni propriétaire d'Orbi Dev : un événement n'atteint personne.

## Décision proposée

### Parcours

1. **Recevoir.** Événement `workflow_run` avec `action = completed` et `conclusion = failure` (ou `timed_out`). Signature vérifiée comme aujourd'hui.
2. **Relier.** Retrouver les projets Orbi Dev non retirés dont `repo_url` correspond à `repository.full_name` (comparaison insensible à la casse). Chaque propriétaire concerné reçoit **son** incident ; aucun ne voit celui d'un autre.
3. **Filtrer.** Ne retenir que : la branche par défaut du projet, ou la branche d'une exécution Orbi Dev en cours (voir étape 6). Ignorer les exécutions issues d'un fork (`head_repository` différent du dépôt).
4. **Enregistrer** un incident (`orbi_dev_incidents`) avec une clé unique `(dépôt, run_id, tentative)` : un rejeu ne crée rien.
5. **Prévenir** le propriétaire dans Telegram : projet, workflow, branche, message de commit, lien vers l'exécution. Boutons : **Demander un correctif**, **Ignorer**, **Voir l'exécution**.
6. **Faire valider.** « Demander un correctif » ne lance rien : il ouvre l'écran de confirmation d'Orbi Dev avec la consigne préparée, que l'utilisateur peut modifier. Seul « Lancer » crée la tâche, liée à l'incident.
7. **Vérifier.** Quand l'agent propose une pull request, les `workflow_run` suivants de sa branche sont rattachés à l'exécution. L'incident passe à « vérifié » **uniquement** si la CI de cette branche réussit sur le commit de la pull request. Une déclaration de l'agent ne suffit jamais.

### États de l'incident

`ouvert` → `correctif demandé` → `correctif proposé` (pull request) → `vérifié` (CI verte sur la branche) ; ou `toujours en échec` ; ou `ignoré`. Jamais « résolu » sans preuve de la CI.

### Consigne envoyée à l'agent

Faits seulement, présentés comme des données : dépôt, branche, commit, nom du workflow, lien de l'exécution, et une instruction fixe (« examiner l'échec de ce workflow et proposer un correctif minimal dans une pull request, sans toucher à autre chose »). Le texte venant de GitHub (message de commit, nom de workflow) est cité, jamais interprété comme une instruction.

## Ce que la CI donne réellement, et ce qui reste inconnu

- **Confirmé par la documentation GitHub ([événements](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows), [exécutions de workflow](https://docs.github.com/en/rest/actions/workflow-runs)) :** `workflow_run` expose notamment `action`, `conclusion`, `status`, `head_branch`, `head_sha`, `head_repository`, `pull_requests`, `html_url`, `head_commit.message`.
- **À confirmer avant de coder :** `run_attempt` dans la charge utile ; le contenu de `pull_requests` pour les exécutions issues de forks ; la liste exacte des événements à cocher dans la configuration du webhook.
- **Inconnu, décisif :** les **journaux** d'une exécution ne sont pas dans le webhook, et les récupérer par l'API exige un jeton GitHub, qu'Orbi n'a pas. Le premier incrément se limite donc aux métadonnées, et l'agent doit lire lui-même les journaux. **On ne sait pas si Jules ou Cursor peuvent le faire.** À mesurer sur un cas réel avant toute extension.
- Si les agents ne lisent pas les journaux : option d'un jeton GitHub en lecture seule (permission « Actions : lecture »), stocké comme une clé fournisseur (chiffré, jamais réaffiché). Décision à prendre sur la base de l'expérience, pas avant.

## Sécurité

- Le texte d'un message de commit ou d'un nom de workflow peut être écrit par un tiers (fork, pull request d'un contributeur) : exécutions issues de forks ignorées, texte échappé dans Telegram et cité dans la consigne.
- Aucun lancement automatique : l'utilisateur voit la consigne et appuie sur « Lancer ». Aucune fusion ni déploiement.
- Le secret du webhook est unique (`GITHUB_WEBHOOK_SECRET`) : acceptable pour un opérateur unique, à revoir avant d'ouvrir Orbi Dev à d'autres utilisateurs (chacun aurait son propre secret ou sa propre application GitHub).
- Les incidents suivent la règle d'Orbi Dev : tout accès filtré par `owner_id`.

## Hors périmètre

Autres outils d'intégration continue, observabilité, état d'un service, redémarrage ou déploiement, correctif automatique sans validation, plusieurs dépôts par incident.

## Critères d'acceptation

- Un événement non signé, mal signé ou rejoué ne crée aucun incident ni message.
- Une exécution en échec sur la branche par défaut d'un projet enregistré produit exactement un message, au propriétaire de ce projet et à lui seul.
- Une exécution issue d'un fork, ou d'un dépôt non enregistré, ne produit rien.
- « Demander un correctif » ne crée aucune tâche avant « Lancer ».
- L'incident n'est « vérifié » qu'après une CI verte sur la branche de la pull request ; un échec de cette CI le laisse « toujours en échec ».
- Un test montre qu'un texte de commit hostile (balises, instructions) est échappé dans Telegram et cité dans la consigne.

## Mesure de la valeur (avant d'élargir)

Sur de vrais échecs : le temps entre l'alerte et une pull request verte, la part de correctifs que l'utilisateur garde, les fausses alertes, et si ce parcours apporte quelque chose que l'interface directe du fournisseur ne donne pas déjà (voir [la direction produit](../PRODUCT_DIRECTION.md)).
