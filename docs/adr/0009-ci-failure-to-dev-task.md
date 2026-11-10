# ADR-0009 — Du signal CI à la tâche Orbi Dev : corrélation, approbation, anti-rejeu

- **Statut :** proposé
- **Date :** 2026-11-10
- **Lié à :** [ADR-0003](0003-durable-execution-model.md), [ADR-0004](0004-first-agent-provider.md), [PRODUCT_DIRECTION.md](../PRODUCT_DIRECTION.md), [ROADMAP.md](../ROADMAP.md) (Phase 5)

## Contexte

La direction produit retient comme premier parcours « échec CI → diagnostic → correctif proposé → vérification ». Le socle existe : machine à états des exécutions (ADR-0003), connecteurs d'agents, suivi par worker, interface Telegram. Ce qui manque est **l'entrée du signal** : aujourd'hui `/webhook/github` ne fait que journaliser les événements (`github_webhook_logs`), sans lien avec les projets Orbi Dev.

Trois questions doivent être tranchées avant d'implémenter :

1. **Comment un événement GitHub retrouve le bon projet Orbi Dev ?** `Project.repo_url` est une URL https libre ; rien ne relie `repository.full_name` du payload à un projet.
2. **Une exécution doit-elle démarrer seule ?** Le principe produit exige une validation humaine avant les actions sensibles ; lancer un agent de code facture du quota fournisseur et produit du code.
3. **Comment traiter les rejets et les doublons ?** `delivery_id` est stocké mais jamais vérifié : un webhook rejoué crée aujourd'hui un doublon de log sans effet ; le jour où le webhook crée des tâches, ce devient un risque réel.

## Décision

### 1. Corrélation par `Project.github_repo`

Chaque `Project` porte un champ `github_repo` (`owner/repo`, minuscules), dérivé de `repo_url` à la création et complété par une migration pour les projets existants. Il vaut `None` pour les dépôts non GitHub (le modèle accepte toute URL https ; le webhook GitHub ne peut de toute façon concerner qu'un dépôt GitHub).

Un événement `check_run` / `check_suite` / `workflow_run` terminé en échec est routé vers **tous** les projets actifs dont `github_repo` correspond à `repository.full_name`. Si plusieurs propriétaires suivent le même dépôt, chacun reçoit sa propre tâche : les exécutions, secrets et notations restent cloisonnées par `owner_id` (invariant existant du service).

Cette approche est volontairement minimale : un projet = un dépôt. Une table de liaison projet↔installation GitHub n'est justifiée que si le besoin « GitHub App » apparaît (voir alternatives).

### 2. Approbation humaine obligatoire

L'événement CI crée une `Task` puis une `Execution` en statut `awaiting_approval` (état déjà prévu par la machine à états, ADR-0003) — jamais de lancement automatique. Le propriétaire reçoit une carte Telegram « Échec CI sur `<repo>` — commit `<sha>` » avec Confirmer / Ignorer. Confirmer fait passer l'exécution en `queued` et déclenche `launch_execution` ; ignorer annule.

Le prompt transmis à l'agent est un **template Orbi**, pas le payload brut : dépôt, commit, URL du check run, nom du workflow. Les journaux CI ne sont jamais collés dans le prompt (taille, contenu non fiable) ; l'agent est renvoyé vers l'URL du check run quand il a besoin du détail.

### 3. Anti-rejeu et déduplication métier

- **Anti-rejeu transport** : index unique (partiel, `delivery_id > ""`) sur `github_webhook_logs.delivery_id`, posé par migration après déduplication de l'historique — pas dans `Settings` Beanie, dont la création d'index précéderait la migration et bloquerait le démarrage sur un historique déjà dupliqué. Un `duplicate key` signifie « déjà vu » → accusé 200 sans traitement. (Le webhook doit rester idempotent : GitHub rejoue les événements non acquittés.)
- **Dédup métier** : la `Task` créée porte un `source_ref` (`ci:<owner/repo>@<sha>:<check_name>`). Une tâche `open` avec le même `source_ref` fait rejeter la création — un même commit qui échoue sur 3 workflows donne 3 tâches distinctes, mais un webhook rejoué ne duplique rien.
- **Portée** : seuls les événements `check_run`, `check_suite` et `workflow_run` en conclusion d'échec sont routés ; les autres restent du simple journal (comportement actuel).

## Alternatives écartées

- **GitHub App / installation** : le modèle officiel pour des bots multi-dépôts (webhooks par installation, tokens d'installation). Justifié à terme, mais exige un enregistrement d'application, une UI d'installation et un flux OAuth — disproportionné pour un premier parcours à un seul dépôt par projet. Le webhook repository suffit ; la migration vers une App reste possible car la corrélation (`owner/repo`) ne change pas.
- **Polling de l'API GitHub Checks** : pas de webhook à configurer, mais latence (minutes), quota API et complexité de suivi par commit. Le webhook est déjà en place et vérifié par signature.
- **Table de liaison dédiée** (`repo_links`) : utile seulement si un projet pouvait pointer vers plusieurs dépôts ou si le même dépôt devait être suivi sous plusieurs identités. Le premier parcours n'en a pas besoin ; le champ `github_repo` peut migrer vers une table sans changer le contrat externe.
- **Lancement automatique de l'agent** : rejeté — coût fournisseur, code non demandé, contraire au principe « validation humaine avant action » de PRODUCT_DIRECTION.md. L'état `awaiting_approval` existe précisément pour cela.

## Conséquences

- Un seul événement CI peut créer jusqu'à N tâches (une par propriétaire du dépôt) : voulu, chaque propriétaire garde son cloisonnement.
- Les projets créés avant cette décision sont rattrapés par la migration de backfill ; un projet sans `github_repo` (dépôt non GitHub ou URL non reconnue) ne reçoit jamais de tâche CI — comportement sûr par défaut.
- La vérification du correctif (check run vert sur la branche de la PR) est un incrément ultérieur : ce premier lot s'arrête à « tâche approuvée → exécution suivie → PR liée ».
- Limite connue : les forks et les PR depuis des branches externes ne sont pas distingués ; un échec CI sur une PR contribuée crée quand même une tâche sur le dépôt suivi. À affiner si le bruit le justifie.
