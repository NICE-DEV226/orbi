# Connecteur Jules (Google)

Adaptateur : [`src/orbi_dev/connectors/jules.py`](../../src/orbi_dev/connectors/jules.py) · Socle HTTP partagé avec Cursor : [`http.py`](../../src/orbi_dev/connectors/http.py)

Sources : [API Jules](https://developers.google.com/jules/api) et sa [référence REST v1alpha](https://developers.google.com/jules/api/reference/rest) (consultées le 2026-10-27). L'API est **alpha** : Google la décrit comme « expérimentale », les définitions et les clés peuvent changer.

## Configuration

1. Dans Jules (jules.google.com), ouvrir les réglages et créer une **clé d'API** (3 clés au plus par compte).
2. Installer l'**application GitHub de Jules** sur chaque dépôt à confier (sans elle, le dépôt n'apparaît pas dans les sources de Jules).
3. Dans Orbi, page **Connexions** : choisir « Jules (Google) », coller la clé. Orbi la vérifie par une lecture seule, puis la chiffre. Elle n'est jamais réaffichée.
4. Créer un projet avec l'URL `https://github.com/<propriétaire>/<dépôt>` : Jules ne prend en charge que GitHub. Laissez la **branche vide** pour partir de la branche par défaut du dépôt (`main`, `master`…) ; si vous en indiquez une, elle doit exister.

Chaque personne connecte sa propre clé : elle est rattachée à son compte Orbi et n'est utilisée que pour ses tâches.

## Capacités déclarées

| Capacité | Opération Jules |
|---|---|
| Vérifier | `GET /v1alpha/sources?pageSize=1` (en-tête `X-Goog-Api-Key`) |
| Lancer | `GET /v1alpha/sources` pour retrouver le nom de la source du dépôt, puis `POST /v1alpha/sessions` (`prompt`, `title`, `sourceContext.githubRepoContext.startingBranch`, `automationMode: AUTO_CREATE_PR`) |
| Suivre | `GET /v1alpha/sessions/{id}` ; `GET .../activities` pour la raison d'un échec ou le dernier message de l'agent |
| Pull request | `outputs[].pullRequest.url` |
| Annuler | **Non déclarée** : aucune annulation n'est documentée. Orbi masque le bouton « Arrêter » et refuse explicitement la demande. |

## Différences avec Cursor, et ce qu'Orbi en fait

- **Pas d'identifiant choisi par le client.** Un lancement dont la réponse est perdue ne peut pas être « adopté » par un identifiant connu d'avance. Orbi place donc un repère `[orbi:<référence>]` dans le **titre** de la session, ne réessaie jamais un `POST` après un délai dépassé (risque de doublon), et retrouve la session en listant les sessions (`find_by_client_ref`). Introuvable : `needs_attention`, jamais de relance à l'aveugle ; la recherche reprend à chaque passage de suivi.
- **L'agent peut attendre l'utilisateur** (`AWAITING_USER_FEEDBACK`, `AWAITING_PLAN_APPROVAL`, `PAUSED`). Orbi passe l'exécution en « À vérifier », affiche la dernière question de l'agent, envoie la notification Telegram avec un lien vers la session, et reprend le suivi quand vous avez répondu dans Jules.
- **Clé invalide en HTTP 400.** Google renvoie `INVALID_ARGUMENT` (raison `API_KEY_INVALID`), pas 401 : les deux sont reconnus comme « clé refusée ».
- **Quota.** `RESOURCE_EXHAUSTED` est traité comme un quota épuisé (non réessayé), sauf si la réponse indique un délai d'attente (alors limite de débit, réessayée avec ce délai).

## Branche de départ

Constaté lors du premier essai réel : une branche inexistante (`main` sur un dépôt dont la branche par défaut est `master`) fait échouer la session **après** sa création, avec un journal de script de plusieurs dizaines de lignes. Orbi :

- laisse la branche **vide par défaut** (= `githubRepo.defaultBranch` de la source Jules) ;
- refuse avant de créer la session une branche absente de `githubRepo.branches`, en listant les branches connues (si Jules ne liste pas de branches, la valeur est transmise telle quelle) ;
- réduit un journal d'échec à sa phrase d'introduction et à sa dernière ligne `fatal:` / `error:`.

Vérifié avec l'API réelle : le texte d'échec arrive bien dans l'activité `sessionFailed.reason`.

## Mapping des états

| `state` Jules | Orbi |
|---|---|
| `QUEUED` | `running` (accepté) |
| `PLANNING`, `IN_PROGRESS` | `running` |
| `AWAITING_PLAN_APPROVAL`, `AWAITING_USER_FEEDBACK`, `PAUSED` | `needs_attention` |
| `COMPLETED` | `succeeded` (titre de la PR comme résumé, sinon dernier message de l'agent) |
| `FAILED` | `failed` (raison de l'activité `sessionFailed`) |
| autre / inconnu | `running` (journalisé) |

## Hypothèses et limites connues (non vérifiées avec un compte réel)

- **Aucun essai réel n'a été effectué.** L'adaptateur est validé par un faux serveur HTTP écrit d'après la documentation ; la première exécution réelle peut révéler des écarts (alpha).
- Le format exact du nom de source n'est pas supposé : Orbi le lit dans `sources.list` (`name`) en comparant `githubRepo.owner` et `githubRepo.repo` sans tenir compte de la casse.
- On suppose que `sessions.list` renvoie le champ `title` et que le titre fourni à la création est conservé tel quel (nécessaire à la réconciliation après réponse perdue). Sinon la réconciliation échoue proprement en `needs_attention`.
- L'ordre des activités n'est pas documenté : Orbi garde celle dont `createTime` est le plus récent.
- Le nom de la branche n'est pas exposé par l'API : il n'est pas affiché pour Jules.
- Quotas et tarifs : la page officielle de l'API n'en mentionne aucun. Les chiffres vus ailleurs (quotas quotidiens) ne sont pas vérifiés.
- Le code des dépôts est envoyé à Google : relire les conditions d'utilisation de Jules avant de lui confier du code privé.
- Les conditions de révocation : la révoquer dans Orbi efface le secret local mais **pas** la clé chez Google ; supprimez-la aussi dans les réglages de Jules.
