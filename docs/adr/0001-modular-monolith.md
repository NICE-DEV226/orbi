# ADR-0001 — Commencer par un monolithe modulaire

- **Statut :** proposé pour validation
- **Date :** 2026-10-23
- **Décideurs :** à confirmer avec le propriétaire du projet
- **Lié à :** [spécification Orbi](../ORBI_SPECIFICATION.md), [audit initial](../AUDIT_INITIAL.md)

## Contexte

Le dépôt est une application Python/FastAPI existante avec bot Telegram, modèles Beanie/MongoDB, Redis, services métier, dashboard et intégrations. La vision cible ajoute des connecteurs d'agents, des tâches asynchrones, des exécutions, des approbations et des workflows. La taille de l'équipe et la charge future ne justifient pas encore, sur la base des éléments disponibles, une architecture de microservices.

## Décision proposée

Garder une application déployable principale, mais définir des frontières internes stables :

- `identity_access` : identités, sessions, workspaces et autorisations ;
- `projects` : projets, dépôts et configuration ;
- `integrations` : connexions, secrets et capacités ;
- `tasks` : intention utilisateur et critères d'acceptation ;
- `executions` : états, tentatives, journaux et résultats ;
- `approvals` : politiques et validations humaines ;
- `events_audit` : événements opérationnels et audit ;
- `connectors` : adaptateurs propres aux fournisseurs ;
- `legacy_modules` : modules historiques jusqu'à leur décision de conservation ou de retrait.

Ce découpage est conceptuel : il ne prescrit pas immédiatement un renommage massif des répertoires. L'implémentation doit respecter les dépendances existantes et être faite progressivement.

## Options considérées

### A. Réécriture immédiate en microservices
Avantages : déploiements indépendants potentiels et isolation de certains composants.
Inconvénients : complexité opérationnelle, réseau, observabilité distribuée, gestion de données et coût disproportionnés au stade actuel.

### B. Monolithe sans frontières
Avantages : simple à maintenir au départ.
Inconvénients : couplage croissant entre les modules historiques et les nouvelles capacités ; difficile de tester les politiques de façon isolée.

### C. Monolithe modulaire
Avantages : migration progressive, tests locaux, déploiement plus simple et possibilité d'extraire un composant plus tard.
Inconvénients : exige de faire respecter les frontières et les contrats internes.

## Conséquences

- Pas de microservices au MVP sans besoin mesuré.
- Les connecteurs ne contiennent pas la logique métier globale.
- Les services métier ne dépendent pas directement d'un SDK fournisseur.
- Les tests doivent couvrir les contrats entre modules.
- Les extractions futures sont possibles si des exigences mesurables apparaissent.

## Conditions de réexamen

Réexaminer cette décision si les contraintes de charge, de disponibilité, d'isolation, de déploiement indépendant ou de conformité dépassent ce que le monolithe peut fournir de manière raisonnable.
