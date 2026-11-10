# ADR-0010 — Remote control : capacité `INTERACT` et réponse à l'agent depuis Orbi

- **Statut :** proposé
- **Date :** 2026-11-12
- **Lié à :** [ADR-0002](0002-integrate-existing-agents.md), [ADR-0003](0003-durable-execution-model.md), [ADR-0004](0004-first-agent-provider.md)

## Contexte

Orbi suit les agents distants en « fire-and-forget » : lancer, sonder, annuler, récupérer la PR. Or l'industrie a convergé vers un second mode, le **remote control** : piloter une session d'agent qui tourne ailleurs depuis un client distant (téléphone, chat). Cursor (`/remote-control` + app iOS), Claude Code (`claude remote-control`), Copilot CLI (`--remote`) et les API de Jules (`sessions.sendMessage`) et Devin (`POST /sessions/{id}/messages`) exposent tous un canal d'entrée vers une exécution active.

Pour Orbi, cela change la nature de `needs_attention` : aujourd'hui l'état « l'agent attend une réponse » (Jules `AWAITING_USER_FEEDBACK`, déjà mappé sur `WAITING` → `NEEDS_ATTENTION`) est une impasse — l'utilisateur doit ouvrir le site du fournisseur. Avec `INTERACT`, la réponse se donne dans la conversation Telegram ou le panneau web, sans quitter Orbi.

Deux questions à trancher :

1. **Comment modéliser la capacité ?** Tous les fournisseurs ne permettent pas d'écrire à une session en cours.
2. **Où s'arrête la responsabilité d'Orbi ?** Orbi relaie un message ; il ne devient pas l'agent et ne prend pas les décisions à sa place.

## Décision

### 1. `Capability.INTERACT` et `BaseConnector.send_input`

Nouvelle capacité `interact` dans le contrat des connecteurs. `BaseConnector.send_input(external_id, message)` est la seule opération ajoutée : elle envoie un message utilisateur à une exécution existante chez le fournisseur. Par défaut elle lève `ConnectorError(UNSUPPORTED_CAPABILITY)` — jamais de faux succès, comme pour `cancel`.

La capacité est déclarée par le connecteur (`capabilities`) et revérifiée **à l'action** sur le connecteur instancié, pas sur la liste stockée dans `Integration.capabilities` : une intégration connectée avant l'ajapport d'`INTERACT` n'a pas besoin d'être reconnectée.

Côté interface, l'affordance « Répondre » n'est proposée que si le **fournisseur déclaré** supporte `INTERACT` (`registry.provider_capabilities`) et que l'intégration est active — un indice honnête, le garde-fou réel restant la vérification à l'appel.

### 2. `runner.send_input_to_execution`

Une seule porte d'entrée, filtrée par `owner_id` comme tout le domaine :

- exécution terminale, `queued` ou `awaiting_approval` → `ConflictError` (rien ni personne à qui parler encore) ;
- `external_id` absent → `ConflictError` (la session n'existe pas encore chez le fournisseur) ;
- connecteur sans `INTERACT` → `ConnectorError(UNSUPPORTED_CAPABILITY)` ;
- succès → événement `NOTE` « Message envoyé à l'agent » (ajout seul, jamais de contenu dans les logs) et, si l'exécution était `needs_attention`, transition optimiste vers `running` (« Réponse transmise »). Le prochain passage du worker fait converger l'état réel : si le fournisseur attend encore quelque chose (ex. approbation de plan Jules, qui passe par un autre endpoint), il repassera `needs_attention`.
- échec fournisseur → événement `ERROR` avec la catégorie normalisée ; `auth_invalid` marque l'intégration invalide comme les autres opérations.

Le message utilisateur est nettoyé (`clean_text`), borné (1–4000 caractères) et **jamais** journalisé en clair au-delà de son extrait dans l'événement.

### 3. Surfaces

- **Telegram** : bouton « Répondre à l'agent » sur la notification/carte d'une exécution `running` ou `needs_attention` dont le fournisseur supporte `INTERACT`. Il arme le parcours existant (`user_data["dev"]["step"] = "reply"`, TTL 15 min) : le prochain message texte est transmis, puis le brouillon est oublié. Un message non texte reçoit la réponse « j'attends du texte » du mécanisme existant.
- **Web** : formulaire « Répondre à l'agent » (CSRF) dans le panneau d'exécution, visible sous les mêmes conditions.

### 4. Limites assumées

- `sendMessage` Jules reprend la session mais **n'approuve pas un plan** (`AWAITING_PLAN_APPROVAL` a son endpoint `approvePlan`, non exposé ici) : l'agent peut répondre en redemandant l'approbation, et l'état repasse `needs_attention`. Couvrir l'approbation de plan est un incrément ultérieur.
- Un fournisseur sans `INTERACT` garde l'expérience actuelle : notification + lien externe. Le remote control des agents **locaux** (Claude Code `remote-control`, Cursor local, `cursor-agent worker`) — lancer le process local et faire le pont — est hors scope : c'est un connecteur « local » entier, pas une extension de ce contrat.
- Le message transite par les serveurs du fournisseur (comme tout remote control du marché) : les secrets ne doivent jamais y être collés — la consigne Orbi et les règles de rédaction s'appliquent.

## Conséquences

- `needs_attention` devient actionnable dans Orbi pour les fournisseurs compatibles, au lieu d'être une impasse.
- Le journal d'exécution gagne une trace « qui a répondu quoi » (extrait), ce qui rend la boucle signal→décision→exécution encore plus auditable.
- Prochaine étape naturelle : `approvePlan` Jules et, plus tard, un connecteur ACP pour les agents locaux compatibles.
