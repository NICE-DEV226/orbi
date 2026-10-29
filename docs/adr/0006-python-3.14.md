# ADR-0006 — Python 3.14 malgré la borne `<3.14` de Beanie

- **Statut :** appliqué ; risque accepté et borné (voir ci-dessous)
- **Date :** 2026-10-26
- **Lié à :** [ADR-0005](0005-motor-to-pymongo-async.md)

## Contexte

Beanie 2.x (dernière version : 2.2.0, août 2026) déclare `Requires-Python: <3.14,>=3.10`. L'image Docker de production et le choix de l'équipe visent Python 3.14. Sources amont consultées le 2026-10-26 :

- l'[issue #1357](https://github.com/BeanieODM/beanie/issues/1357) « Support for python 3.14 » a été fermée par le robot d'inactivité, sans résolution ;
- les PR #1257, #1321, #1362 (« Allow Python 3.14 ») ont toutes été **fermées sans fusion** ; la #1362 affirme que « la bibliothèque fonctionne avec Python 3.14 mais ne peut pas être installée à cause de la borne supérieure » ; la #1321 signale un correctif nécessaire dans le contrôleur de **migrations** de Beanie (annotations différées, PEP 649), que ce projet n'utilise pas.

Il n'y a donc aucune date de support officiel.

## Décision

Utiliser Python 3.14 en **corrigeant uniquement la métadonnée** de Beanie 2.2.0 via `[[tool.uv.dependency-metadata]]` dans `pyproject.toml` (`requires-python = ">=3.10"`, dépendances inchangées). Le lockfile garde exactement les mêmes versions de paquets ; seul le calcul de compatibilité change. Pas de fork, pas de paquet tiers.

## Preuves

- Les 308 tests (dont ceux qui exercent les vrais index uniques, les mises à jour atomiques et le parcours Orbi Dev) passent sur **3.12, 3.13 et 3.14**, contre un vrai MongoDB, installés depuis le lockfile.
- L'image Docker construite sur `python:3.14.9-slim` démarre et passe les contrôles de santé (voir la PR).

## Conséquence pratique

Sur Python 3.14, **`pip install` échoue** (pip applique la borne `<3.14` de Beanie et ignore la correction de `uv`). Le projet s'installe avec `uv sync` (lockfile) : c'est ce que font le `Dockerfile` et la CI, qui teste ainsi exactement les versions verrouillées. `pip` reste possible en 3.12 et 3.13.

## Risques et limites

- **Non supporté par les mainteneurs.** Un défaut propre à 3.14 serait à notre charge. Les tests couvrent ce que le projet utilise ; ils ne couvrent pas les modules de Beanie que nous n'importons pas (notamment les **migrations Beanie** : ne pas les utiliser en 3.14 tant que #1321 n'est pas résolu).
- **Garde-fou automatique.** L'override est limité à `beanie 2.2.0`. Quand Dependabot proposera une autre version, `uv lock` échouera sur 3.14 si elle garde la borne `<3.14` : la CI le montrera au lieu de laisser passer silencieusement.
- **Projet amont peu actif** (« Is beanie dead? » dans l'issue). Si Beanie reste bloqué, le plan de repli est de rester sur 3.13 (supporté jusqu'en 2029) ou d'évaluer un autre ODM / PyMongo direct.

## Condition de sortie

Supprimer le bloc `dependency-metadata` dès qu'une version de Beanie déclare officiellement 3.14. À réexaminer si un défaut spécifique à 3.14 est observé en production.

## Piège : les PR Dependabot qui touchent `uv.lock`

Dependabot régénère `uv.lock` avec son propre `uv`, qui n'applique pas notre bloc `dependency-metadata` : le lockfile qu'il propose perd la section `[manifest]` (le correctif Beanie) et change de révision, donc l'étape `uv lock --check` de la CI échoue (constaté sur la PR #38, mise à jour de FastAPI). Le code n'est pas en cause. Pour une telle PR : refaire la mise à jour en local avec `uv lock --upgrade-package <paquet>==<version>`, vérifier que le diff ne contient que ce paquet, lancer la suite et ouvrir une PR ; la PR Dependabot se ferme d'elle-même une fois la version fusionnée.

