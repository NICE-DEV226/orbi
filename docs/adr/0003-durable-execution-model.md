# ADR-0003 — Modèle durable des tâches et exécutions

- **Statut :** proposition technique
- **Date :** 2026-10-23
- **Lié à :** [spécification Orbi](../ORBI_SPECIFICATION.md)

## Contexte

Les appels à des agents, les tests et les déploiements peuvent être longs et échouer de manière ambiguë. Un timeout HTTP ne signifie pas nécessairement que le fournisseur n'a pas exécuté l'action. Le navigateur ou le téléphone peut se déconnecter alors que le travail continue.

## Décision proposée

Séparer trois objets :
1. **Task** : demande utilisateur et critères de réussite.
2. **Execution** : tentative concrète auprès d'un fournisseur.
3. **Event** : changement d'état ou progression observable.

Le statut doit être persisté. L'interface lit cet état et ne constitue pas la source de vérité. Les exécutions longues passent par un worker ou un mécanisme de tâche durable choisi après comparaison des solutions existantes et des besoins d'exploitation.

## États initiaux proposés

`queued`, `awaiting_approval`, `running`, `succeeded`, `failed`, `cancel_requested`, `cancelled`, `timed_out`, `needs_attention`.

La machine à états doit définir les transitions autorisées et distinguer l'état terminal de l'incertitude externe. Si un fournisseur ne confirme pas le résultat, l'exécution peut nécessiter une réconciliation plutôt qu'un retry aveugle.

## Garanties

- Identifiant d'exécution durable.
- Transitions validées côté serveur.
- Retries bornés et seulement sur erreurs réessayables.
- Clé d'idempotence stable pour les opérations concernées.
- Journalisation des tentatives et références externes.
- Gestion explicite des annulations non supportées ou non confirmées.
- Reprise après redémarrage et déconnexion client.
- Pas de promesse « exactly once » sans mécanisme prouvé.

## Options de transport de progression

- **Polling** : simple, robuste, potentiel surcoût de requêtes.
- **SSE** : flux serveur vers client, adapté aux mises à jour unidirectionnelles si le déploiement le permet.
- **WebSocket** : interaction bidirectionnelle, plus de complexité de connexion et d'exploitation.

Le choix est reporté jusqu'à ce que le premier parcours mobile et les contraintes de déploiement soient définis.

## Choix de la queue

Aucun système de queue spécifique n'est choisi dans cet ADR. La décision doit comparer les outils déjà présents, la durabilité, les retries, la visibilité opérationnelle, les exigences de disponibilité et le coût de maintenance. Redis actuellement utilisé comme cache ne doit pas être présumé suffisant comme queue durable sans analyse.

## Critères d'acceptation de la future implémentation

- Une exécution reste consultable après redémarrage du serveur.
- Une perte de connexion du client ne relance pas la tâche.
- Une répétition de commande ne produit pas d'effet externe en double lorsque l'idempotence est applicable.
- Une réponse fournisseur perdue est traitée comme résultat incertain jusqu'à réconciliation.
- Les transitions invalides sont rejetées et testées.
- Les journaux affichés n'exposent aucun secret.
