# Connecteur Cursor Cloud Agents

Adaptateur : [`src/orbi_dev/connectors/cursor.py`](../../src/orbi_dev/connectors/cursor.py) · Décision : [ADR-0004](../adr/0004-first-agent-provider.md)

Sources : [aperçu de l'API](https://cursor.com/docs/cloud-agent/api/overview), [endpoints](https://cursor.com/docs/cloud-agent/api/endpoints) et la [spécification OpenAPI](https://cursor.com/docs-static/cloud-agents-openapi.yaml) (consultées le 2026-10-23). L'API v1 est en **bêta publique** : elle peut changer.

## Configuration

1. Générer une clé API dans le tableau de bord Cursor (de préférence une clé de **compte de service**, pas une clé personnelle).
2. Définir `SECRETS_ENCRYPTION_KEY` côté Orbi (voir `.env.example`).
3. Connecter l'intégration avec le fournisseur `cursor` : Orbi vérifie la clé par une lecture seule (`GET /v1/agents?limit=1`), puis la chiffre.

## Révocation

La révocation dans Orbi **efface le secret local** et place les exécutions actives en `needs_attention`. Elle ne révoque **pas** la clé chez Cursor (aucune API de révocation n'est exploitée) : supprimez aussi la clé dans le tableau de bord Cursor.

## Capacités déclarées

| Capacité | Opération Cursor |
|---|---|
| Vérifier | `GET /v1/agents?limit=1` |
| Lancer | `POST /v1/agents` avec `agentId` choisi par Orbi (`bc-<uuid>`), `prompt.text`, `repos[]`, `autoCreatePR: true` |
| Suivre | `GET /v1/agents/{id}` puis `GET /v1/agents/{id}/runs/{latestRunId}` |
| Annuler | `POST /v1/agents/{id}/runs/{runId}/cancel` |
| Pull request | `git.branches[].prUrl` du run |

La vérification ne prouve que la validité de la clé : le **lancement et l'annulation ne sont vérifiables qu'en les exécutant** (plan, quota, accès au dépôt). Un échec se présente alors comme une erreur normalisée (`plan_or_quota`, `permission_denied`…).

Non utilisés : flux SSE (le polling suffit, ADR-0003), archivage/suppression, follow-up, serveurs MCP, secrets d'environnement.

## Mapping des statuts

| Run Cursor | RemoteStatus | Statut Orbi |
|---|---|---|
| `CREATING` | pending | `running` (accepté par le fournisseur) |
| `RUNNING` | running | `running` |
| `FINISHED` | succeeded | `succeeded` |
| `ERROR` | failed | `failed` |
| `CANCELLED` | cancelled | `cancelled` |
| `EXPIRED`, ou agent `ARCHIVED` sans run terminé | expired | `timed_out` |

## Mapping des erreurs

Par code fournisseur d'abord, puis par statut HTTP : `unauthorized`/`api_key_not_found`/401 → `auth_invalid` ; `repository_access`/`role_forbidden`/403 → `permission_denied` ; `plan_required`/`usage_limit_exceeded` → `plan_or_quota` ; `rate_limit_exceeded`/429 → `rate_limited` (en-tête `Retry-After` respecté, borné à 30 s) ; `agent_*_not_found`/404 → `not_found` ; `agent_id_conflict`/`agent_busy`/`run_not_cancellable`/409 → `conflict` ; `validation_error`/400 → `invalid_request` ; 5xx → `unavailable`.

## Résilience

- Timeout de 15 s par appel ; 2 retries maximum avec backoff.
- Réessayés : 429, 5xx, erreurs de connexion (requête non envoyée), et un délai dépassé **uniquement pour le lancement**, rendu idempotent par `agentId` : si la première requête avait abouti, la seconde reçoit `409 agent_id_conflict` et l'adaptateur adopte l'agent existant.
- L'annulation n'est jamais réessayée à l'aveugle : le résultat est relu par `GET`.

## Hypothèses et limites connues (non vérifiées avec un compte réel)

- Aucun essai réel n'a été effectué : l'adaptateur est validé par des réponses HTTP simulées conformes à la documentation et à l'OpenAPI.
- Le plan requis et les quotas ne sont pas connus (le code `plan_required` prouve qu'un plan est exigé).
- `autoCreatePR: true` est toujours demandé ; le comportement exact si le dépôt interdit la création de PR n'est pas testé.
- Le champ `git` est « par agent, pas par run » (documentation) : après une relance sur le même agent, `prUrl` peut concerner un run précédent. Orbi crée un agent par tentative, ce qui évite le cas.
- Aucun webhook en v1 : le suivi est du polling (intervalle `ORBI_DEV_REFRESH_INTERVAL`, 30 s par défaut).
- Les conditions d'utilisation et le traitement du code envoyé à Cursor n'ont pas été examinés.

## Tests

`tests/test_orbi_dev_connectors.py` : forme des requêtes, mapping des statuts et erreurs, retries et `Retry-After`, résultat inconnu, absence de secret dans les messages et logs. Aucun test de contrat contre le service réel (pas de sandbox fournie).
