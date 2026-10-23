# ADR-0004 — Sélection du premier fournisseur d'agent de code

- **Statut :** proposition ; à valider par le responsable du projet
- **Date :** 2026-10-23
- **Lié à :** [ADR-0002](0002-integrate-existing-agents.md), [ADR-0003](0003-durable-execution-model.md), [ROADMAP ORBI-DEV-01](../ROADMAP.md)

## Contexte

L'ADR-0002 impose d'intégrer un agent existant avant d'en construire un, et de choisir le premier fournisseur après comparaison de sources officielles. Ce document compare six candidats sur le critère déterminant pour Orbi : **piloter une tâche à distance depuis un serveur** (lancer, suivre, annuler, récupérer la pull request), avec les garanties de l'ADR-0003 (identifiant durable, idempotence, résultat incertain géré par réconciliation).

## Méthode et limites

- Lecture des pages de documentation officielles le 2026-10-23 (liens ci-dessous). Le schéma OpenAPI de Devin a été analysé localement.
- Seul ce que la documentation affirme est classé « confirmé ». Tout le reste est « non confirmé », ce qui ne veut pas dire « absent ».
- **Aucun fournisseur n'a été testé avec un compte réel.** Les prix, quotas et disponibilités par plan n'ont pas été vérifiés, sauf indication contraire.
- La page des endpoints Cursor n'a été lue que sur ses 100 000 premiers caractères (sur ~130 000) ; sa [spécification OpenAPI](https://cursor.com/docs-static/cloud-agents-openapi.yaml) a ensuite été analysée en entier pour confirmer l'URL de base (`https://api.cursor.com`), le format d'`agentId` (`bc-<uuid>`), les codes d'erreur et les en-têtes de limite de débit.

## Comparaison

| Critère | Cursor Cloud Agents v1 | Devin API v3 | Copilot cloud agent (REST) | Jules API | Claude Code (tâches planifiées, déclencheur API) | Codex cloud |
|---|---|---|---|---|---|---|
| Lancer une tâche par API | ✅ `POST /v1/agents` | ✅ `POST /v3/organizations/{org_id}/sessions` | ✅ `POST /agents/repos/{owner}/{repo}/tasks` | ✅ `POST /v1alpha/sessions` | ✅ `POST /v1/claude_code/routines/{id}/fire` (tâche préconfigurée dans l'interface ; seul champ libre : `text`) | ❓ aucune API documentée trouvée (mention d'une CLI sans détail) |
| Suivre l'état par API | ✅ `GET /v1/agents/{id}`, `GET …/runs/{runId}`, flux SSE avec reprise `Last-Event-ID` | ✅ `GET …/sessions/{devin_id}` ; `status` (`new`, `claimed`, `running`, `exit`, `error`, `suspended`, `resuming`) + `status_detail` | ✅ `GET /agents/repos/{owner}/{repo}/tasks/{task_id}` ; 8 états | ✅ `GET /v1alpha/sessions/{id}` ; 8 états | ❌ aucune lecture d'état documentée (la réponse donne l'URL de session) | ❓ |
| Annuler | ✅ `POST …/runs/{runId}/cancel` (409 `run_not_cancellable` si terminé) | ✅ `DELETE …/sessions/{devin_id}` (« Terminate ») | ❓ état `cancelled` existe, aucun endpoint d'annulation trouvé | ❌ aucun endpoint d'annulation (seulement `DELETE` de session) | ❌ | ❓ |
| Résultat (PR / branche) | ✅ `git.branches[].prUrl`, `branch`, `result` | ✅ `pull_requests`, `structured_output` | ✅ `artifacts` (`pull`/`branch`) ; PR créée si `create_pull_request` | ✅ `outputs[].pullRequest.url` | ❓ via la session web | ❓ |
| Idempotence de création | ✅ `agentId` choisi par le client ; doublon → `409 agent_id_conflict` | ❓ non documentée | ❓ | ❓ | ❓ | ❓ |
| Authentification serveur-à-serveur | ✅ clé de compte de service (Bearer) ; jetons utilisateur d'1 h | ✅ utilisateur de service `cog_…` (Bearer) | ⚠️ jeton utilisateur (PAT fin ou GitHub App « user-to-server ») ; **jetons d'installation non supportés** | ✅ clé API (`x-goog-api-key`) | ✅ jeton Bearer propre à la tâche | ❓ |
| Webhooks / push | ❌ pas en v1 (présents en v0) | ❓ | ❓ | ❓ | n/a | ❓ |
| Stabilité annoncée | ⚠️ « public beta, APIs may change » | ✅ v3 courante ; v1/v2 en dépréciation | ⚠️ « public preview, subject to change » | ⚠️ chemin `v1alpha` | ⚠️ « research preview » ; en-tête bêta daté | ❓ |
| Plan / coût | ⚠️ un plan spécifique est exigé (code d'erreur `plan_required` dans l'OpenAPI) mais non précisé ; quotas : `usage_limit_exceeded`, en-têtes `Retry-After` / `X-RateLimit-*` sur 429 ; tarifs non indiqués | ❓ API non mentionnée dans les plans lus (Free 0 $, Pro 20 $/mois, Max 200 $/mois, Teams ≥ 80 $/mois) | ⚠️ Copilot Business ou Enterprise requis | ❓ quotas non indiqués | ⚠️ plan Pro/Max/Team/Enterprise ; 30 déclenchements/heure par tâche | ❓ |

Légende : ✅ confirmé par la doc officielle · ⚠️ confirmé avec réserve · ❌ confirmé absent de la doc lue · ❓ non confirmé.

### Sources

- Cursor : [aperçu de l'API](https://cursor.com/docs/cloud-agent/api/overview), [endpoints](https://cursor.com/docs/cloud-agent/api/endpoints), [spécification OpenAPI](https://cursor.com/docs-static/cloud-agents-openapi.yaml)
- Devin : [aperçu](https://docs.devin.ai/api-reference/overview), [spécification OpenAPI v3](https://docs.devin.ai/v3-openapi.json), [plans self-serve](https://docs.devin.ai/admin/billing/self-serve.md)
- GitHub Copilot : [API REST des tâches d'agent](https://docs.github.com/en/rest/agent-tasks/agent-tasks)
- Jules : [aperçu de l'API](https://jules.google/docs/api/reference/overview/), [sessions](https://jules.google/docs/api/reference/sessions/)
- Claude Code : [tâches planifiées et déclencheur API](https://code.claude.com/docs/en/routines)
- Codex : [Codex cloud](https://learn.chatgpt.com/docs/cloud)

## Décision proposée

**Premier connecteur : Cursor Cloud Agents API v1.**

Raisons, par ordre d'importance :

1. **Seul candidat dont la documentation couvre tout le cycle exigé** : lancement, état, flux de progression, annulation, résultat PR, archivage.
2. **L'idempotence correspond à l'ADR-0003.** Orbi génère l'`agentId` avant l'appel réseau et le persiste ; un timeout ambigu se résout par `GET` sur cet identifiant ou par `409 agent_id_conflict`, sans relance aveugle.
3. **Authentification adaptée à un serveur** (clé de compte de service), contrairement à Copilot qui exige des jetons utilisateur.
4. L'absence de webhooks est compatible avec le polling retenu dans l'ADR-0003.

Deuxième candidat, à implémenter seulement pour prouver que l'interface n'est pas façonnée sur Cursor : **Devin API v3** (cycle complet confirmé, version courante), idempotence et prix de l'API à vérifier.

## Risques et conditions de validation

- **API en bêta publique** : changements possibles. L'adaptateur isole le fournisseur derrière une interface ; une garde de version et des tests de contrat limitent la casse.
- **Plan et tarification non confirmés.** L'API exige un plan (`plan_required`) sans dire lequel, et les tarifs ne sont pas documentés dans les pages lues. Avant de déclarer le connecteur terminé, vérifier avec une vraie clé : plan requis, coût d'un agent, quotas, comportement `429`.
- **Adaptateur écrit d'après la documentation, sans compte réel.** Le gate de sortie de la phase 3 (« un parcours bout-en-bout prouvé avec un fournisseur réel ou sandbox ») n'est donc **pas** atteint tant qu'un essai réel n'a pas eu lieu sur un dépôt de test. Le fournisseur factice local ne le remplace pas.
- **Verrouillage fournisseur** : réduit par l'interface commune, mais les capacités propriétaires doivent rester exposées explicitement (ADR-0002).
- **Conditions d'utilisation et traitement des données** (stockage du code, entraînement) : non examinés ici ; à lire avant d'envoyer du code privé.

## Alternatives écartées pour la première tranche

- **Copilot cloud agent** : jetons utilisateur uniquement, plan Business/Enterprise, annulation non confirmée, API en préversion.
- **Jules** : API alpha, pas d'annulation.
- **Claude Code (tâches planifiées)** : on peut déclencher mais pas lire l'état par API ; le produit est conçu autour de tâches préconfigurées dans l'interface.
- **Codex cloud** : aucune API de pilotage trouvée dans la documentation lue ; à réexaminer (SDK, App Server et GitHub Action existent mais n'ont pas été étudiés).

## Conséquences

- ORBI-DEV-02 et ORBI-DEV-03 s'appuient sur cette décision ; l'interface de connecteur reste indépendante du fournisseur.
- Si la validation réelle échoue (plan inaccessible, coût prohibitif, API instable), le connecteur Devin devient le premier sans modifier le domaine.

## Conditions de réexamen

Réexaminer si une API de fournisseur change de statut (bêta → stable, ou dépréciation), si les conditions d'utilisation interdisent l'usage prévu, ou si l'essai réel révèle un écart avec la documentation.
