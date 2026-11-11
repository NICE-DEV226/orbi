# Connecteur Devin

Adaptateur : [`src/orbi_dev/connectors/devin.py`](../../src/orbi_dev/connectors/devin.py) · Socle HTTP partagé : [`http.py`](../../src/orbi_dev/connectors/http.py)

Source : [API Devin v3](https://docs.devin.ai/api-reference/v3) et sa [spécification OpenAPI](https://docs.devin.ai/v3-openapi.yaml) (consultées le 2026-11-10).

## Configuration

1. Dans Devin, ouvrir **Settings → Devin API** et créer une clé (service user `cog_…` de préférence, ou jeton personnel).
2. Permissions requises : `UseDevinSessions` pour créer des sessions, `ManageOrgSessions` pour leur envoyer des messages, `ViewOrgSessions` pour les lister.
3. Dans Orbi, page **Connexions** : choisir « Devin », coller la clé. Orbi la vérifie par `GET /v3/self` (lecture seule), puis la chiffre. Elle n'est jamais réaffichée.

**L'organisation est détectée automatiquement** : `GET /v3/self` renvoie `org_id` (service user) ou `devin_sessions_org_id` (jeton personnel). Aucune organisation à saisir. Si la clé n'est rattachée à aucune organisation utilisable, la connexion est refusée avec un message explicite.

## Capacités déclarées

| Capacité | Opération Devin v3 |
|---|---|
| Vérifier | `GET /v3/self` — prouve la clé sans créer de session ni consommer d'ACU |
| Lancer | `POST /v3/organizations/{org}/sessions` avec `devin_id` choisi par Orbi (`devin-<uuid>`), `prompt`, `repos[]` |
| Suivre | `GET /v3/organizations/{org}/sessions/{id}` |
| Annuler | `DELETE /v3/organizations/{org}/sessions/{id}` — seule forme d'annulation documentée (« terminate session ») |
| Répondre (remote control, ADR-0010) | `POST /v3/organizations/{org}/sessions/{id}/messages` (`message`) — une session suspendue est relancée automatiquement |
| Pull request | `pull_requests[].pr_url` |

## Mapping des statuts

| Statut Devin | `status_detail` | RemoteStatus |
|---|---|---|
| `new`, `claimed` | — | pending |
| `running`, `resuming` | `working`… | running |
| `running` | `waiting_for_user`, `waiting_for_approval`, `inactivity`, `user_request` | waiting |
| `exit` | — | succeeded |
| `error` | — | failed |
| `suspended` | — | waiting (un message relance la session) |
| inconnu | — | pending (journalisé) |

Devin n'a pas d'état « cancelled » : un `DELETE` accepté est traduit en `cancelled` côté Orbi. Le worker ne repolle plus une exécution terminée.

## Mapping des erreurs

Corps `ProblemDetail` (RFC 9457 : `title`, `detail`, `error_code`), traduit sans jamais reprendre le corps brut : 401 → `auth_invalid` ; 403 → `permission_denied` (`error_code: user_frozen`) ; 404/410 → `not_found` ; 409 → `conflict` (`migrated_session`) ; 422/400 → `invalid_request` ; 429 → `rate_limited` (`Retry-After` borné à 30 s) ; 5xx → `unavailable`.

## Résilience

- Timeout de 15 s ; 2 retries maximum avec backoff.
- **Lancement** : `devin_id` étant choisi par Orbi et passé en paramètre de création, un `POST` rejoué après un délai dépassé ne crée pas de doublon (`retry_unknown=True`).
- **Messages et annulation** : jamais réessayés après un résultat incertain — un message Devin n'est pas documenté idempotent.
- `GET /v3/self` est mis en cache pour la durée de vie du connecteur (une instance par opération du runner).

## Hypothèses et limites connues (non vérifiées avec un compte réel)

- Aucun essai réel n'a été effectué : l'adaptateur est validé par des réponses HTTP simulées conformes à l'OpenAPI.
- Le format exact attendu par `repos[]` (URL complète vs `owner/repo`) n'est pas documenté dans le schéma ; Orbi envoie l'URL du projet telle quelle.
- `GET /sessions/{id}` n'expose ni branche ni résumé de fin : `summary` et `branch` restent vides, la PR est lue dans `pull_requests[]`.
- Les sessions suspendues apparaissent en « waiting » : un message les relance, mais rien ne le fait automatiquement — l'utilisateur reste maître.

## Tests

`tests/test_orbi_dev_devin.py` : découverte d'organisation (service user et jeton personnel), formes exactes des requêtes, mapping des statuts et erreurs `ProblemDetail`, rejet des identifiants de session dangereux, absence de retry aveugle sur les messages, sanitization des détails fournisseur. Aucun test de contrat contre le service réel.
