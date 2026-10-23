# Orbi — Feuille de route d'ingénierie

> **Statut :** proposition de plan, à ajuster après exécution des tests  
> **Date :** 23 octobre 2026  
> **Branche :** `docs/orbi-platform-spec`

Cette feuille de route ordonne les travaux pour réduire les risques avant d'ajouter de nouvelles capacités. Les estimations de durée ne sont pas indiquées : elles seraient spéculatives sans connaître le temps disponible, la taille de l'équipe et les résultats des tests.

## Principes de livraison

- Les éléments P0 bloquants ne sont pas repoussés pour construire de nouvelles fonctionnalités.
- Chaque lot doit être livré dans un PR petit, révisable et testable.
- Un ticket doit avoir des critères d'acceptation et des preuves de validation.
- Les modifications de sécurité ont des tests négatifs, pas seulement un test de succès.
- Ne pas réécrire toute la structure historique pour respecter immédiatement la structure cible.
- Une intégration de fournisseur est choisie après comparaison des API officielles, conditions, prix et capacités.

## Phase 0 — Sécuriser la base existante

### ORBI-SEC-01 — Fermer la connexion de démonstration privilégiée
**Priorité : P0 — Bloquante**

- Localiser toutes les routes et identités de démonstration.
- Supprimer la route `/admin/dev-login` de la configuration de production ou la rendre inaccessible par défaut côté serveur.
- Empêcher la création automatique d'une identité superadmin de démonstration dans tout environnement partagé.
- Ajouter des tests development/production.
- Vérifier la gestion des sessions potentiellement émises précédemment.

**Acceptation :** en mode production, la route ne permet jamais d'obtenir une session privilégiée ; un test automatisé le prouve.

### ORBI-SEC-02 — Corriger les dépendances d'authentification de l'API admin/dev
**Priorité : P0 — Bloquante**

Le code inspecté dans `src/api/admin.py` contient une dépendance `verify_admin_token` qui laisse passer les requêtes même quand le token ne correspond pas à la valeur attendue. `src/api/dev.py` retourne un rôle developer sans authentification effective. Ces fonctions sont des squelettes non sûrs si elles sont exposées.

- Remplacer les mocks par de vraies dépendances d'authentification/autorisation.
- Refuser par défaut lorsque l'identité ou le token n'est pas validé.
- Utiliser des scopes/rôles côté serveur et vérifier l'accès à chaque route.
- Ne jamais coder un secret partagé directement dans le code.
- Écrire des tests pour requête anonyme, token invalide, rôle insuffisant et accès autorisé.

**Acceptation :** les endpoints protégés retournent un refus avec identifiants absents ou invalides ; aucune route privilégiée ne dépend d'un paramètre fictif par défaut.

### ORBI-SEC-03 — Configuration de production fail-closed
**Priorité : P0**

- Refuser le démarrage en production si `JWT_SECRET` garde sa valeur par défaut ou est trop faible.
- Vérifier la présence et la longueur minimale des secrets nécessaires selon les intégrations activées.
- Ajouter des validations Pydantic et tests.
- Documenter le processus de rotation.

**Acceptation :** une configuration de production invalide échoue au démarrage avec un message sans secret.

### ORBI-SEC-04 — Cookies, session et CSRF
**Priorité : P0/P1**

- Paramétrer `Secure` à partir d'une configuration explicite et sûre.
- Vérifier HTTPS et les en-têtes proxy.
- Revoir la rotation de session, l'expiration et la révocation.
- Auditer les routes mutantes pour la protection CSRF.
- Éviter de se déconnecter via GET si une route POST peut être utilisée sans casser le parcours existant.

**Acceptation :** tests des attributs cookie et des protections de session, documentés pour dev/staging/production.

### ORBI-SEC-05 — Webhooks et paiement
**Priorité : P0 — Bloquante avant paiement réel**

> **Mise à jour :** les intégrations de paiement (Stripe, Orange Money, Wave) ont été retirées du code. Ce ticket ne concerne plus que le webhook GitHub (fait) et devra être rouvert si les paiements sont réintroduits.

- Vérifier les signatures selon la documentation officielle actuelle de chaque fournisseur.
- Pour GitHub, refuser les webhooks si le secret n'est pas configuré dans un environnement où ils sont activés ; ne pas traiter l'absence de secret comme une signature valide.
- Vérifier les montants, devises, identifiants de commande et transitions d'état.
- Ajouter la protection anti-rejeu et le traitement idempotent des événements.
- Réconcilier les paiements après timeout ou résultat ambigu.
- Distinguer l'accusé de réception HTTP d'un succès métier.

**Acceptation :** signatures absentes/incorrectes et événements rejoués n'entraînent aucun effet métier ; les cas valides sont traités une seule fois selon les garanties disponibles.

### ORBI-SEC-06 — Health check et exposition des services
**Priorité : P1**

- Ne pas renvoyer les exceptions internes de MongoDB/Redis dans la réponse publique.
- Vérifier si MongoDB et Redis doivent publier des ports sur l'hôte dans les fichiers Compose ; les retirer ou limiter leur exposition si inutile.
- Documenter les endpoints internes, les métriques et la documentation OpenAPI selon l'environnement.
- Revoir les valeurs de configuration Compose par rapport au fichier `.env.example`.

**Acceptation :** endpoint public minimal, aucun secret/détail interne dans la réponse, ports non nécessaires non exposés par défaut.

## Phase 1 — Tests reproductibles

### ORBI-QA-01 — Reproduire l'environnement
- Installer les dépendances dans un environnement propre.
- Vérifier les commandes pytest et Ruff.
- Documenter les services requis.
- Corriger les tests qui ne fonctionnent qu'avec une configuration implicite.
- Séparer tests unitaires, intégration et tests nécessitant MongoDB/Redis.

### ORBI-QA-02 — Tests de sécurité critiques
- Accès inter-utilisateurs/workspaces.
- Authentification API et dashboard.
- Validation des signatures et anti-rejeu des webhooks.
- Secrets dans les logs et réponses.
- Idempotence des paiements et commandes.
- Arrêt propre et échec partiel du démarrage.

### ORBI-QA-03 — CI
- Installer les dépendances.
- Exécuter Ruff.
- Exécuter les tests unitaires.
- Exécuter les tests d'intégration avec services contrôlés lorsque possible.
- Publier des résultats de test et bloquer la fusion si les checks requis échouent.

**Gate de sortie :** rapport des tests réellement exécutés, avec les échecs et limites documentés. Ne pas déclarer la base saine avant cette étape.

## Phase 2 — Décider du sort des modules historiques

- Remplir `LEGACY_MODULES.md`.
- Associer à chaque capacité les fichiers, tests, dépendances et risques.
- Décider conserver/refactoriser/isoler/déprécier/retirer.
- Ne pas lancer un refactoring massif avant ces décisions.

**Gate de sortie :** aucune suppression de module sans décision documentée et vérification de ses dépendances.

## Phase 3 — Premier vertical Orbi Dev

### ORBI-DEV-01 — Sélection du fournisseur
Comparer au moins deux options à partir de sources officielles récentes. La comparaison doit couvrir API/CLI, création et suivi de tâche, résultats, scopes, prix, quotas, disponibilité géographique, conditions, isolation et annulation.

**Livrable :** tableau comparatif sourcé et ADR de sélection. Aucun fournisseur n'est préchoisi dans cette feuille de route.

### ORBI-DEV-02 — Modèle interne minimal
- Projet.
- Intégration.
- Tâche.
- Exécution.
- Événement.
- Résultat et référence externe.

Ne créer que les modèles et services nécessaires au premier parcours.

### ORBI-DEV-03 — Connecteur unique
- Vérifier l'intégration.
- Déclarer les capacités.
- Lancer une tâche.
- Suivre l'état.
- Normaliser les erreurs.
- Enregistrer le résultat.
- Révoquer la connexion.

### ORBI-DEV-04 — Interface mobile de suivi
- Liste des tâches/exécutions.
- Détail d'une exécution.
- Statut et erreurs.
- Lien vers diff ou pull request.
- Reprise après rechargement.
- Aucun déploiement de production dans cette tranche.

**Gate de sortie :** un parcours bout-en-bout prouvé avec un dépôt de test et un fournisseur réel ou sandbox, sans exposer de secrets.

> **État (2026-10-23) :** DEV-01 à DEV-04 sont implémentés (ADR-0004, `src/orbi_dev/`, `src/web/dev.py`). Le parcours est prouvé de bout en bout contre une vraie pile MongoDB/Redis avec le **fournisseur factice** uniquement. Le gate n'est **pas** atteint : aucun essai n'a été fait avec un compte fournisseur réel (voir `docs/connectors/cursor.md`).

## Phase 4 — Workflow sécurisé de revue

- Afficher diff et tests.
- Créer une pull request si supporté.
- Ajouter approbations avant les actions sensibles.
- Auditer chaque lancement et décision.
- Tester les changements de périmètre après approbation.

## Phase 5 — CI/CD, opérations et équipes

Uniquement après validation du parcours initial :
- intégration CI ;
- suivi de déploiement ;
- observabilité de services ;
- incidents et notifications ;
- membres et rôles avancés ;
- workflows composés ;
- autres modules historiques si leur valeur est confirmée.

Les opérations de production restent derrière des politiques explicites, une revue et une approbation tant qu'une politique automatisée sûre n'a pas été conçue et validée.

## Critères de sortie globaux

Une phase est terminée si :
- ses critères d'acceptation sont satisfaits ;
- les tests et résultats sont publiés ;
- les risques résiduels sont connus ;
- la documentation est à jour ;
- aucun secret n'est exposé ;
- les limitations et capacités non supportées sont indiquées ;
- le responsable du projet a validé le passage à la phase suivante.
