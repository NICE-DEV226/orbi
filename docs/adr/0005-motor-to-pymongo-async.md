# ADR-0005 — Migrer de Motor vers l'API asynchrone de PyMongo (Beanie 2)

- **Statut :** appliqué dans la PR de migration
- **Date :** 2026-10-23
- **Lié à :** [ADR-0001](0001-modular-monolith.md)

## Contexte

Le projet utilisait Beanie 1.x, qui repose sur Motor. Motor est déprécié depuis le 14 mai 2025 et n'a plus de correctifs ordinaires depuis le 14 mai 2026 (correctifs critiques seulement jusqu'au 14 mai 2027) ; MongoDB recommande l'API asynchrone de PyMongo ([Motor](https://motor.readthedocs.io/en/latest/)). Beanie 2.0 a fait ce changement ([notes de version](https://github.com/BeanieODM/beanie/releases)). La PR Dependabot #17 (beanie 2.2.0) échouait pour cette raison : ce n'était pas un simple bump.

## Décision

Passer à Beanie 2.2 + PyMongo `AsyncMongoClient` et retirer Motor.

## Conséquences

- **Python < 3.14 (levé par l'[ADR-0006](0006-python-3.14.md)).** Beanie 2.2.0 déclare `requires-python <3.14` ; la migration avait d'abord ramené le projet en 3.13. L'ADR-0006 rétablit 3.14 en corrigeant cette métadonnée.
- **Les champs `Field(exclude=True)` ne sont plus persistés** par Beanie 2 (vérifié : le document stocké ne les contient pas). Le texte chiffré des clés d'intégration, qui utilisait ce mécanisme, est donc stocké dans sa propre collection (`orbi_dev_integration_secrets`), hors de tout modèle exposé à l'interface. Sans ce changement, les clés auraient été perdues silencieusement.
- **Le client async est lié à la boucle d'événements qui l'a créé.** En production, un seul client vit dans la boucle d'Uvicorn. En test, toute la session partage une boucle (`asyncio_default_*_loop_scope = "session"`) et le `TestClient` synchrone est remplacé par un client httpx asynchrone.
- **Les tests utilisent un vrai MongoDB.** `mongomock-motor` n'est plus compatible. Les tests exigent donc une instance MongoDB (service dans la CI, `docker run` en local) ; ils échouent avec un message explicite si elle est injoignable. En contrepartie, ils exercent les vrais index uniques et la vraie sémantique de mise à jour atomique.
- Un second client Mongo, créé dans `core/performance.py` mais jamais utilisé ni fermé, a été supprimé.

## Alternatives écartées

- **Rester sur Beanie 1.x / Motor** : support Motor en fin de vie, dette qui grandit.
- **Rester sur Python 3.14 en abandonnant Beanie** : réécriture de toute la couche de données, hors proportion.
