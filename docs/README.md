# Orbi — Documentation d'ingénierie

Documentation de cadrage pour la reprise progressive du dépôt. Les documents décrivent la cible et les travaux proposés ; ils ne certifient pas que le code actuel est conforme.

## Documents

- [Direction produit](PRODUCT_DIRECTION.md) — contrôle mobile d'agents d'abord, puis un premier signal d'échec de CI ; périmètre, parcours visé et écart avec les capacités actuelles.
- [Spécification produit et technique](ORBI_SPECIFICATION.md) — vision, architecture, exigences et critères d'acceptation.
- [Audit initial du dépôt](AUDIT_INITIAL.md) — constats statiques, risques et limites de l'audit.
- [Feuille de route d'ingénierie](ROADMAP.md) — priorités, phases, lots de travail et critères de sortie.
- [Inventaire des modules historiques](LEGACY_MODULES.md) — cartographie initiale et modèle de décision.
- [ADR-0001 : monolithe modulaire](adr/0001-modular-monolith.md) — proposition d'architecture.
- [ADR-0002 : intégration d'agents existants](adr/0002-integrate-existing-agents.md) — stratégie des connecteurs.
- [ADR-0003 : modèle durable d'exécution](adr/0003-durable-execution-model.md) — tâches, exécutions et événements.
- [ADR-0004 : premier fournisseur d'agent](adr/0004-first-agent-provider.md) — comparaison sourcée et choix proposé.
- [ADR-0005 : Motor → PyMongo async](adr/0005-motor-to-pymongo-async.md) — migration Beanie 2.
- [ADR-0006 : Python 3.14](adr/0006-python-3.14.md) — correction de la métadonnée de Beanie.
- [ADR-0007 : Mini App Telegram](adr/0007-telegram-mini-app.md) — accès web depuis Telegram, cookies, limites.
- [ADR-0008 : interface Jinja + htmx](adr/0008-web-ui-jinja-htmx.md) — un seul shell, sans framework CSS ni CDN.
- [ADR-0009 : premier signal d'exploitation, l'échec de CI](adr/0009-first-operational-signal-ci-failure.md) — conception proposée, questions ouvertes.
- [Design de l'interface](DESIGN.md) — anneau d'orbite, jetons, typographie, règles d'écriture.

## Statut

Les décisions d'architecture sont des propositions tant que leur statut ne précise pas qu'elles sont approuvées. Le premier fournisseur d'agents est proposé dans l'ADR-0004 (à valider) ; les choix définitifs de stockage/queue restent ouverts. L'audit est préliminaire et doit être complété par l'exécution des tests et la vérification des routes sensibles.

## Ordre de lecture

1. Direction produit.
2. Spécification.
3. Audit initial.
4. Feuille de route.
5. Inventaire historique.
6. ADR selon le sujet.
