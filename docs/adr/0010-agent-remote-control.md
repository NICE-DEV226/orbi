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
- **Web** : **aucune surface de remote control** — décision produit : Orbi est telegram-first, la conversation avec l'agent vit dans Telegram (bouton, puis texte libre, comme les remote controls du marché). Le panneau web reste la vue de consultation (statut, PR, journal) ; les routes `/executions/{id}/message` et `/executions/{id}/thread` n'existent pas.

### 3bis. Fil de discussion (capacité `HISTORY`)

Répondre à l'aveugle ne suffit pas : l'utilisateur doit voir ce que l'agent a dit. `BaseConnector.list_messages(external_id, limit)` lit le fil de la session — `RemoteMessage(role, text, at)` — déclarée par une capacité `history` distincte d'`INTERACT` (un fournisseur peut exposer l'un sans l'autre).

- **Devin** : `GET /v3/organizations/{org}/sessions/{id}/messages` (`source: user|devin` → `user|agent`).
- **Jules** : `GET /v1alpha/sessions/{id}/activities` — `agentMessaged`/`userMessaged` → messages, `progressUpdated`/`planGenerated`/`planApproved` → jalons système.
- **Cursor** : non déclaré — l'API v1 n'expose que `runs/{id}/stream` (SSE), pas de liste de messages en REST.
- **Fake** : fil simulé (`[ask]` ajoute la question de l'agent).

`runner.get_execution_thread` est en lecture seule : autorisé même sur une exécution terminée, sans restriction d'état tant qu'une session externe existe. Côté interface, le fil est **chargé à la demande** — bouton « Fil de discussion » en réponse à la carte Telegram — jamais dans le polling : zéro appel fournisseur supplémentaire tant que l'utilisateur ne l'ouvre pas.

### 3ter. Choix cliquables (`choices.py`)

Les fournisseurs n'exposent pas de question à choix structurée : le message de l'agent est du texte brut. Quand une exécution est `needs_attention` et que le fournisseur déclare `INTERACT`, la carte/notification propose des boutons :

- **Options parsées** (si `HISTORY` est déclaré) : le dernier message de l'agent contient une liste numérotée ou à puces **dans une question** (« ? » requis, ≥ 2 items, ≤ 4, ≤ 200 caractères) → chaque item devient un bouton. Le callback porte une empreinte SHA-1 tronquée du texte ; au clic, le fil est relu et l'option vérifiée — un fil changé entre-temps refuse le choix plutôt que d'envoyer autre chose que ce que l'utilisateur a vu.
- **Réponses génériques** sinon (pas de liste lisible, ou fournisseur sans `HISTORY` comme Cursor) : « Oui, continue. », « Non. », « Explique-moi les options. » — des amorces, l'agent peut redemander une précision.

Après un choix envoyé, les boutons de choix sont retirés du message (anti double-envoi) et la carte est rafraîchie. Le texte libre (« Répondre à l'agent ») reste toujours disponible en complément.

### 3quater. Mode conversation (`chat.py`)

« Répondre à l'agent » reste le mode **une réponse** ; le bouton « Discuter » ouvre un **mode conversation persistant** : tant qu'il est actif, tout texte libre du propriétaire est transmis à l'exécution la plus récemment active (`RUNNING`/`NEEDS_ATTENTION`, session fournisseur, `INTERACT`) — résolution à chaque envoi, donc la conversation suit automatiquement le dernier agent quand plusieurs tournent. « Quitter la discussion » désarme.

- **État dans Redis** (`orbi_dev:chat:{owner}`, JSON `anchor` + `exec`), pas dans `user_data` : il survit au redémarrage et reste lisible par le worker — qui n'a pas accès aux données de contexte Telegram.
- **Remontée des réponses** : à chaque passage du worker (`ORBI_DEV_REFRESH_INTERVAL`), `push_replies` relit le fil (`HISTORY`) des discussions ouvertes et pousse les nouveaux messages `agent` dans le chat, ancrés par une empreinte `role + SHA-1(texte)` du dernier message vu — aucun doublon, aucun historique renvoyé à l'armement. Sans `HISTORY` (Cursor), l'envoi fonctionne mais rien ne remonte : dégradé honnête.
- **Succès silencieux côté envoi** : pas d'accusé de réception — l'agent répond dans le fil, comme une vraie conversation ; les erreurs sont toujours explicites.

### 4. Limites assumées

- `sendMessage` Jules reprend la session mais **n'approuve pas un plan** (`AWAITING_PLAN_APPROVAL` a son endpoint `approvePlan`, non exposé ici) : l'agent peut répondre en redemandant l'approbation, et l'état repasse `needs_attention`. Couvrir l'approbation de plan est un incrément ultérieur.
- Un fournisseur sans `INTERACT` garde l'expérience actuelle : notification + lien externe. Le remote control des agents **locaux** (Claude Code `remote-control`, Cursor local, `cursor-agent worker`) — lancer le process local et faire le pont — est hors scope : c'est un connecteur « local » entier, pas une extension de ce contrat.
- Le message transite par les serveurs du fournisseur (comme tout remote control du marché) : les secrets ne doivent jamais y être collés — la consigne Orbi et les règles de rédaction s'appliquent.

## Conséquences

- `needs_attention` devient actionnable dans Orbi pour les fournisseurs compatibles, au lieu d'être une impasse.
- Le journal d'exécution gagne une trace « qui a répondu quoi » (extrait), ce qui rend la boucle signal→décision→exécution encore plus auditable.
- Prochaine étape naturelle : `approvePlan` Jules et, plus tard, un connecteur ACP pour les agents locaux compatibles.
