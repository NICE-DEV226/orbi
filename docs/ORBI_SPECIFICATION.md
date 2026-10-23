# Orbi — Spécification produit et technique

> **Statut :** document de cadrage vivant  
> **Version :** 0.1.0 — 23 octobre 2026  
> **Branche de documentation :** `docs/orbi-platform-spec`  
> **Dépôt :** [NICE-DEV226/orbi](https://github.com/NICE-DEV226/orbi)  
> **Langue de référence :** français  
> **Public :** produit, architecture, développement, sécurité, QA et contributeurs

---

## 0. Gouvernance du document

Ce document définit la direction cible d'Orbi et les exigences qui guideront sa reprise. Il ne prétend pas que les fonctionnalités décrites sont déjà implémentées. L'état réel doit être confirmé par l'audit du dépôt et par des tests.

Chaque décision importante doit être classée comme suit :

- **DÉCIDÉ** : confirmé dans le cadrage produit.
- **PROPOSÉ** : recommandation technique qui doit être validée avant implémentation.
- **À INVESTIGUER** : demande une recherche, une preuve de faisabilité ou une inspection du code.
- **HORS PÉRIMÈTRE INITIAL** : volontairement exclu du premier incrément, mais potentiellement envisageable ensuite.

Toute fonctionnalité détaillée dans ce document doit, avant d'être déclarée terminée, disposer de critères d'acceptation vérifiables, de tests adaptés, d'une gestion des erreurs, d'une documentation et de règles de sécurité explicites.

### 0.1 Règles de conception

1. Ne pas construire un agent de code propriétaire tant qu'un besoin non couvert n'est pas démontré.
2. Intégrer d'abord les agents, plateformes et services existants par les interfaces qu'ils supportent officiellement.
3. Ne jamais prétendre qu'une intégration sait exécuter une action que le fournisseur ne permet pas.
4. Séparer l'orchestration métier des connecteurs fournisseurs.
5. Toute action sensible doit être autorisée, traçable et, lorsque requis, approuvée explicitement.
6. Ne jamais confondre une demande utilisateur, une action planifiée, une action exécutée et une action vérifiée.
7. Préférer une architecture modulaire à des microservices prématurés.
8. Ne pas considérer une fonctionnalité comme complète parce que son endpoint ou son écran existe.
9. Garder une voie d'évolution vers plusieurs profils sans imposer toutes les fonctionnalités à tous les utilisateurs.
10. Documenter les coûts opérationnels et les limites des dépendances externes.

---

## 1. Vision produit

### 1.1 Vision

**Orbi est une plateforme unifiée pour piloter des outils, des tâches et des opérations numériques depuis une interface cohérente, sur téléphone ou ordinateur.**

Orbi ne cherche pas à remplacer GitHub, les agents de code, les fournisseurs cloud, les systèmes CI/CD ou les outils métier. Il fournit une couche de coordination entre eux : contexte partagé, orchestration de workflows, permissions, validations humaines, suivi des exécutions, historique et visibilité sur les résultats.

L'utilisateur doit pouvoir demander un résultat, comprendre ce qui va être fait, superviser l'exécution et décider de la suite sans devoir manipuler directement chaque outil sous-jacent.

### 1.2 Problème visé

Les activités de développement et d'exploitation sont réparties entre plusieurs outils. Les interfaces, les permissions, les états des tâches et les journaux sont fragmentés. Le pilotage sur téléphone est souvent limité à des notifications ou à des interfaces qui ne sont pas conçues pour superviser un workflow de bout en bout.

Orbi veut réduire cette fragmentation sans enfermer les utilisateurs dans un fournisseur unique.

### 1.3 Proposition de valeur à valider

- Un point de contrôle cohérent pour les outils connectés.
- Des workflows combinant agents, dépôts, tests, CI/CD, déploiement et alertes.
- Une expérience utilisable depuis un téléphone, avec les détails techniques accessibles quand ils sont nécessaires.
- Des permissions et validations explicites pour les opérations sensibles.
- Une architecture extensible permettant d'ajouter des connecteurs sans réécrire le cœur.

Cette proposition est une hypothèse produit. Elle doit être confrontée aux alternatives existantes et à des utilisateurs réels avant de conclure qu'elle constitue une différenciation suffisante.

### 1.4 Ce qu'Orbi n'est pas

- Pas un nouvel agent de code à développer par défaut.
- Pas un IDE complet pour téléphone dans la première version.
- Pas un fournisseur cloud ou CI/CD obligatoire.
- Pas une interface qui donne automatiquement aux agents un accès global aux dépôts, secrets ou environnements.
- Pas une promesse d'automatisation sans intervention humaine.
- Pas un assemblage de modules indépendants sans identité produit commune.

---

## 2. Utilisateurs et expériences

Orbi doit pouvoir répondre à plusieurs profils sans présenter à chacun un tableau de bord surchargé. Les permissions et les vues dépendent du rôle, des projets auxquels l'utilisateur a accès et des modules activés.

### 2.1 Développeur individuel

**Objectif :** déléguer ou superviser des tâches de développement, examiner les résultats et gérer le passage de la modification à la revue.

Parcours cible :
1. Connecter un dépôt autorisé.
2. Choisir un agent compatible ou une capacité disponible.
3. Décrire une tâche et préciser les contraintes.
4. Voir le plan proposé et confirmer le lancement lorsque nécessaire.
5. Suivre l'état, les journaux et les résultats.
6. Examiner le diff, les tests et la pull request.
7. Approuver ou refuser les étapes suivantes.

### 2.2 Utilisateur mobile

**Objectif :** lancer, surveiller et valider des opérations depuis un téléphone sans devoir réaliser toutes les tâches techniques dans une interface minuscule.

Principes UX :
- Montrer d'abord le statut, le résultat, les blocages et l'action suivante.
- Rendre les journaux et les diffs consultables sans imposer leur lecture à chaque étape.
- Utiliser des confirmations distinctes pour les opérations à risque.
- Ne jamais représenter un lancement comme une réussite finale.
- Permettre de reprendre une exécution après interruption de l'interface.
- Prévoir les connexions instables, les notifications différées et les délais des fournisseurs.

### 2.3 Équipe d'ingénierie

**Objectif :** coordonner les tâches, les agents et les opérations sur des projets partagés.

Besoins : espaces de travail, membres, rôles, assignations, historique, revue, approbations, limites d'utilisation et règles de projet.

### 2.4 Organisation / entreprise

**Objectif :** superviser des opérations répétables avec contrôle d'accès, traçabilité et politiques de sécurité.

Besoins possibles, à valider selon la cible :
- RBAC et séparation des espaces.
- Journal d'audit consultable et exportable.
- Gestion de secrets et des intégrations.
- Politique d'approbation configurable.
- Limites de coûts et de consommation.
- Règles de conservation des données.
- SSO, SCIM, exigences contractuelles et conformité : **hors MVP, à étudier si la demande le justifie**.

### 2.5 Profils historiques

Le dépôt actuel comprend des fonctionnalités de support, commerce, communauté, productivité et développeurs autour de Telegram. Elles ne doivent pas être supprimées automatiquement. L'audit doit classer chacune en : conserver, refactoriser, isoler, déprécier ou retirer. La nouvelle vision doit définir si ces fonctions sont des modules complémentaires d'Orbi, un produit distinct ou une partie de l'historique à archiver.

---

## 3. Périmètre et priorités

### 3.1 Principe de livraison

Orbi peut viser une plateforme large à long terme. En revanche, chaque incrément doit livrer un parcours vertical complet, testable et utile. La largeur du produit n'impose pas de développer toutes les capacités en parallèle.

### 3.2 Phase 0 — Audit et sécurisation

Livrables :
- Cartographie des fonctionnalités réellement implémentées.
- Cartographie des routes, modèles, services, tâches planifiées et intégrations.
- État des tests, dépendances, migrations, configuration et déploiement.
- Registre des risques de sécurité.
- Inventaire des fonctions du cahier des charges historique et leur statut réel.
- Décision documentée sur ce qui sera conservé, refactorisé, remplacé ou abandonné.

**Critères d'acceptation :**
- Chaque fonctionnalité importante a un statut justifié par le code ou un test.
- Les chemins critiques sont associés à des tests reproductibles.
- Les problèmes de sécurité critiques ont une mesure de mitigation avant toute exposition publique.
- Aucun élément décrit comme fonctionnel ne repose uniquement sur le README ou un ancien cahier des charges.

### 3.3 Phase 1 — Noyau de plateforme

Construire les concepts partagés : identité, espaces, projets, intégrations, tâches, exécutions, événements, approbations, politiques et audit.

**Critères d'acceptation :**
- Les objets sont définis avec identifiants, propriétaires, états, contraintes et règles d'accès.
- Les transitions d'état sont validées côté serveur.
- Les actions répétées ne créent pas de doublons lorsque l'idempotence est requise.
- Les changements d'état critiques sont traçables.
- Les tests vérifient les accès autorisés et refusés.

### 3.4 Phase 2 — Première intégration externe

Choisir un agent existant après étude de ses API, de ses interfaces CLI, de ses conditions d'utilisation, de ses tarifs, de ses limites et de sa disponibilité géographique.

**Critères d'acceptation :**
- Connexion et révocation documentées.
- Lancement et suivi des tâches lorsque le fournisseur les permet.
- Erreurs, limites de débit, timeouts et indisponibilités représentés explicitement.
- Les secrets ne sont jamais exposés dans les logs ni au client.
- L'état affiché par Orbi correspond à une réponse vérifiable du fournisseur.
- Les capacités non supportées sont signalées comme telles.

### 3.5 Phase 3 — Parcours mobile de développement

Parcours de référence :
1. L'utilisateur choisit un projet et un dépôt connecté.
2. Il décrit une tâche.
3. Orbi affiche le périmètre, le fournisseur choisi et les permissions nécessaires.
4. L'exécution démarre dans les limites autorisées.
5. Orbi expose le statut, les événements et les erreurs utiles.
6. Le résultat est présenté : lien de pull request, diff, tests, ou explication d'échec.
7. L'utilisateur décide de la suite.

La première version n'a pas besoin d'éditer manuellement tout le code depuis le téléphone. Elle doit permettre un pilotage fiable et une revue claire.

### 3.6 Phase 4 — Tests, CI/CD et déploiement

Étendre le parcours vers des environnements d'exécution, des pipelines et des fournisseurs de déploiement. Les déploiements de production exigent une politique d'approbation explicite, sauf configuration organisationnelle documentée et contrôlée.

### 3.7 Phases ultérieures

- Coordination de plusieurs agents.
- Workflows personnalisés.
- Surveillance de services et gestion d'incidents.
- Espaces d'équipe avancés.
- Modules de productivité, support, commerce ou communauté, selon la validation produit.
- Connecteurs et extensions communautaires avec modèle de permissions strict.

Aucune phase ultérieure n'est considérée comme engagée tant que les phases précédentes n'ont pas été évaluées.

---

## 4. Architecture cible

### 4.1 Principes

**PROPOSÉ :** commencer par un monolithe modulaire, avec des frontières internes nettes. Ne pas introduire de microservices avant d'avoir identifié des besoins mesurables de mise à l'échelle, d'isolation, de déploiement indépendant ou de fiabilité.

La structure exacte doit être déterminée après l'audit. La structure conceptuelle cible est :

- **Interface** : web/mobile web, Telegram si conservé, API publique.
- **Application** : cas d'usage, orchestration de workflows et politiques.
- **Domaine** : entités, invariants et transitions d'état.
- **Connecteurs** : adaptateurs pour agents et fournisseurs externes.
- **Infrastructure** : base de données, file de tâches, cache, stockage et observabilité.
- **Sécurité** : authentification, autorisation, gestion des secrets, audit et approbations.

### 4.2 Responsabilités des couches

#### Interface
- Présenter les données autorisées.
- Envoyer des commandes validées par le serveur.
- Gérer les états de chargement, erreurs et connexions interrompues.
- Ne pas contenir la logique de sécurité faisant autorité.
- Ne jamais décider seule qu'une action est approuvée.

#### API / couche application
- Authentifier la requête.
- Autoriser l'action sur la ressource ciblée.
- Valider l'entrée et la politique applicable.
- Créer une commande ou une exécution durable.
- Déclencher le traitement asynchrone.
- Retourner un identifiant de suivi plutôt que bloquer sur une tâche longue.

#### Domaine
- Définir les états valides et transitions.
- Appliquer les règles d'approbation et d'idempotence.
- Ne pas dépendre directement d'un SDK de fournisseur.
- Émettre des événements métier explicites.

#### Connecteurs
- Encapsuler l'API ou le protocole du fournisseur.
- Convertir les statuts et erreurs vers le modèle commun.
- Appliquer timeouts, limites, reprise contrôlée et redaction des secrets.
- Exposer uniquement les capacités effectivement disponibles.
- Versionner et tester les contrats d'intégration.

#### Workers / exécutions asynchrones
- Exécuter les tâches longues hors du cycle HTTP.
- Prendre en charge la reprise et la déduplication lorsque cela est possible.
- Publier des événements d'avancement.
- Respecter annulation, échéance et limites de ressources.
- Enregistrer les résultats, erreurs et références externes.

### 4.3 Communication et tâches asynchrones

Les tâches d'agents, tests et déploiements peuvent durer plus longtemps qu'une requête HTTP. **PROPOSÉ :** utiliser un mécanisme de tâches durable et des workers, au lieu de conserver une requête ouverte. Le choix de la technologie de queue doit être fait après analyse du volume, du besoin de reprise, des dépendances déjà présentes et des contraintes d'hébergement.

Exigences :
- Identifiant d'exécution stable.
- États et timestamps persistés.
- Retry avec backoff uniquement pour les erreurs réessayables.
- Limite du nombre de tentatives et file d'échec si nécessaire.
- Idempotency key pour les opérations qui créent des effets externes.
- Délais d'expiration et stratégie d'annulation documentés.
- Aucune garantie de livraison « exactement une fois » sans mécanisme démontré ; préférer une livraison au moins une fois avec traitement idempotent quand c'est adapté.

### 4.4 Données et stockage

Le dépôt utilise actuellement MongoDB/Beanie et Redis. Ne pas migrer automatiquement de base de données au nom d'une architecture idéale. L'audit doit déterminer si le modèle actuel convient aux relations, contraintes, transactions, requêtes et besoins d'audit du produit cible.

Séparer conceptuellement :
- données de domaine ;
- états d'exécution ;
- secrets et références de secrets ;
- journaux d'audit ;
- événements techniques et métriques ;
- cache et données temporaires.

Les logs ne remplacent pas les données métier persistées.

---

## 5. Modèle de domaine initial

Les entités ci-dessous sont conceptuelles. Le schéma définitif, les relations et les index doivent être établis après l'audit et avant les migrations.

### 5.1 User / Identity

Représente une identité authentifiée.

Champs conceptuels : identifiant interne, identifiants externes liés, statut, dates de création et de modification, préférences non sensibles.

Règles :
- Les identifiants externes sont uniques dans leur fournisseur.
- La révocation d'une identité ou d'une session doit être prise en charge.
- Les secrets d'authentification ne sont jamais sérialisés dans les réponses publiques.
- Une identité n'accorde pas automatiquement accès à tous les projets.

### 5.2 Workspace

Espace de travail individuel ou partagé.

Champs conceptuels : identifiant, nom, propriétaire, statut, paramètres et timestamps.

Règles :
- Toute ressource de workspace doit être filtrée par autorisation côté serveur.
- Les changements de propriétaire et de membres sont auditables.
- La suppression doit définir le comportement des exécutions, intégrations et données associées.

### 5.3 Membership / Role

Associe un utilisateur à un workspace avec un rôle et, si nécessaire, des permissions spécifiques.

**PROPOSÉ :** démarrer avec des rôles limités et documentés, puis ajouter des permissions fines selon les cas réels. Éviter une matrice RBAC arbitrairement complexe au MVP.

### 5.4 Project

Regroupe un dépôt, des environnements, des intégrations et des workflows.

Champs conceptuels : identifiant, workspace, nom, description, statut, paramètres, références externes.

Un projet ne doit pas stocker un token fournisseur en clair dans ses métadonnées.

### 5.5 Integration

Représente une connexion à un fournisseur externe.

Champs conceptuels : fournisseur, type de connexion, propriétaire, scopes accordés, statut, date de connexion, date de dernière vérification, référence sécurisée du secret.

Règles :
- Les permissions demandées doivent être minimales.
- Les jetons sont stockés dans un système de secrets ou un stockage chiffré adapté.
- Les secrets ne sont montrés qu'au moment autorisé et jamais relus en clair via une API ordinaire.
- Révocation, expiration et reconnexion sont des états de première classe.
- Les scopes réellement accordés sont enregistrés.

### 5.6 Capability

Décrit une capacité normalisée réellement supportée par une intégration : lancer une tâche, consulter son état, annuler, récupérer une pull request, obtenir des journaux, lancer un pipeline, déclencher un déploiement, etc.

Ne pas supposer que tous les fournisseurs implémentent toutes les capacités. Les capacités doivent être découvertes, configurées ou vérifiées selon les mécanismes supportés par le fournisseur.

### 5.7 Task

Représente l'intention de travail demandée par l'utilisateur.

Champs conceptuels : identifiant, projet, auteur, description, contraintes, priorité, statut, intégration choisie, dates, références de résultat.

La tâche est distincte de ses tentatives d'exécution. Une tâche peut nécessiter plusieurs exécutions, une revue humaine ou une correction.

### 5.8 Execution

Représente une tentative concrète d'exécution d'une tâche ou d'une opération.

Champs conceptuels : identifiant, tâche, type, fournisseur, statut, timestamps, échéance, identifiant externe, compteurs de tentatives, résultats, erreurs normalisées, lien de suivi.

États minimaux proposés :
- `queued`
- `awaiting_approval`
- `running`
- `succeeded`
- `failed`
- `cancel_requested`
- `cancelled`
- `timed_out`
- `needs_attention`

La liste définitive doit tenir compte des capacités des fournisseurs. Les transitions illégales sont rejetées côté serveur.

### 5.9 Approval

Représente une décision humaine ou organisationnelle nécessaire avant une opération.

Champs conceptuels : action ciblée, demandeur, approbateur autorisé, statut, justification, dates, politique appliquée et empreinte de l'action approuvée.

Une approbation est liée à une action précise. Si le contenu ou le périmètre change de façon significative, l'approbation précédente ne doit pas autoriser implicitement la nouvelle action.

### 5.10 Event / AuditRecord

Deux concepts distincts :
- **Événement opérationnel** : changement de statut, progression, résultat technique.
- **Enregistrement d'audit** : qui a demandé, autorisé ou exécuté une action, sur quelle ressource, à quel moment et avec quel résultat.

Les journaux d'audit doivent être protégés contre la modification non autorisée. La politique de rétention et les accès doivent être documentés.

---

## 6. Contrat des connecteurs

### 6.1 Objectif

Permettre à Orbi de communiquer avec des fournisseurs hétérogènes sans propager leurs particularités dans tout le domaine métier.

### 6.2 Types de connecteurs

1. **API officielle** : préférée lorsqu'elle expose les capacités nécessaires avec une authentification et des conditions adaptées.
2. **Application Git / intégration de dépôt** : pour les dépôts, branches, pull requests et événements.
3. **CLI dans un environnement contrôlé** : pour les outils installés sur un worker ou un environnement distant, sous réserve de licence et de sécurité.
4. **Webhook** : pour recevoir les événements entrants avec validation cryptographique et protection contre les répétitions.
5. **Connecteur manuel / lien externe** : solution de repli si l'action ne peut pas être automatisée proprement.

Un connecteur peut combiner plusieurs modes. L'intégration ne doit pas contourner les conditions d'utilisation du fournisseur ou automatiser une interface d'une manière interdite.

### 6.3 Interface conceptuelle

Le contrat exact sera traduit en types et interfaces après sélection du premier fournisseur. Il devra couvrir les opérations prises en charge, par exemple :

- décrire le fournisseur et sa version d'adaptateur ;
- vérifier la connexion ;
- exposer les capacités supportées ;
- lancer une opération autorisée ;
- obtenir l'état et les résultats ;
- récupérer des journaux ou références ;
- demander l'annulation lorsque supportée ;
- révoquer ou désactiver l'intégration.

Les opérations non supportées retournent une erreur de capacité explicite et documentée, pas un succès simulé.

### 6.4 Modèle d'erreurs normalisé

Chaque connecteur doit mapper les erreurs externes vers des catégories communes, au minimum :
- authentification invalide ou expirée ;
- permission insuffisante ;
- capacité non supportée ;
- limite de débit ;
- indisponibilité temporaire ;
- timeout ;
- ressource introuvable ;
- requête invalide ;
- conflit d'état ;
- erreur fournisseur inconnue.

Les détails sensibles du fournisseur ne sont pas exposés aux utilisateurs sans filtrage.

### 6.5 Résilience

- Définir un timeout pour chaque appel réseau.
- Ne réessayer que les erreurs identifiées comme réessayables.
- Respecter les indications de limite de débit du fournisseur.
- Utiliser une stratégie de backoff bornée avec jitter si approprié.
- Éviter les retries automatiques sur une opération non idempotente dont le résultat est inconnu.
- Prévoir une vérification de l'état avant de relancer une opération incertaine.
- Mesurer taux d'erreur, latence et consommation par connecteur.
- Permettre de désactiver un connecteur défaillant sans arrêter toute la plateforme.

### 6.6 Ajout d'un nouveau connecteur

Un connecteur n'est accepté que s'il fournit :
- documentation de configuration et de révocation ;
- déclaration des capacités supportées ;
- mapping des statuts et erreurs ;
- gestion des timeouts, quotas et secrets ;
- tests unitaires avec réponses simulées ;
- tests de contrat ou sandbox quand le fournisseur en fournit une ;
- tests d'intégration non destructifs ;
- limites connues et conditions d'utilisation ;
- stratégie de versionnement et de dépréciation.

---

## 7. Gestion du cycle de développement logiciel

### 7.1 Connexion à un dépôt

Exigences :
- Autorisation explicite de l'utilisateur ou de l'organisation.
- Scopes minimaux selon les opérations nécessaires.
- Liste des dépôts accessibles et possibilité de retirer l'accès.
- Contrôle d'accès à chaque lecture ou écriture.
- Gestion des dépôts supprimés, renommés ou devenus inaccessibles.
- Aucun token de dépôt envoyé au navigateur ou inclus dans les prompts visibles.

### 7.2 Création d'une tâche de code

Une demande peut contenir une description, des critères d'acceptation, des fichiers ou modules concernés, des contraintes et un niveau de risque.

Avant lancement, Orbi doit afficher les éléments disponibles : dépôt, branche cible ou stratégie de branche, agent, permissions, limite de temps ou de consommation si supportée, et actions prévues.

Orbi ne doit pas promettre qu'un agent respecte parfaitement une demande. Les résultats doivent être examinés et testés.

### 7.3 Exécution de l'agent

- Isoler les tâches entre elles lorsque le fournisseur ou l'environnement le permet.
- Ne pas injecter des secrets dans un prompt par défaut.
- Traiter le contenu du dépôt, les issues et les sorties d'outils comme des données non fiables.
- Empêcher qu'une instruction trouvée dans un fichier ou une sortie d'agent modifie silencieusement les politiques d'Orbi.
- Enregistrer les événements de progression utiles sans journaliser de données sensibles.
- Limiter durée, nombre de tentatives et consommation lorsque le fournisseur offre ces contrôles.
- Distinguer « agent terminé » de « tâche validée ».

### 7.4 Diff et revue

Présenter autant que possible :
- fichiers modifiés ;
- résumé des changements ;
- diff ou lien vers le diff ;
- résultats des tests et commandes exécutées ;
- erreurs et avertissements ;
- référence de branche ou pull request ;
- limites de vérification.

Un résumé généré par l'agent n'est pas une preuve que les changements sont corrects.

### 7.5 Tests et CI

Orbi peut déclencher des tests locaux dans un environnement isolé ou un pipeline externe. La méthode dépend du dépôt et des outils autorisés.

- Afficher les tests réellement exécutés et leur résultat.
- Distinguer tests non exécutés, ignorés, échoués et réussis.
- Conserver les liens ou références vers les rapports.
- Ne pas interpréter l'absence de test comme une réussite.
- Éviter de relancer un pipeline coûteux sans politique ou confirmation lorsque nécessaire.

### 7.6 Merge et déploiement

Le MVP doit privilégier la création de branche et de pull request plutôt que l'écriture directe sur la branche principale.

Les opérations suivantes sont considérées comme sensibles :
- merge ;
- modification des secrets ou permissions ;
- changement d'infrastructure ;
- déploiement en production ;
- migration destructive ;
- suppression de ressources.

Elles nécessitent une politique d'autorisation explicite et, par défaut, une approbation humaine distincte de la demande initiale.

---

## 8. Exécution distante et environnements

### 8.1 Décision ouverte

Orbi peut s'appuyer sur les environnements d'exécution des fournisseurs au départ, puis ajouter des environnements contrôlés par Orbi si cela apporte une valeur mesurable. La décision dépend du coût, de l'isolation, de la compatibilité, de la latence, de la maintenance et du contrôle nécessaire.

### 8.2 Exigences minimales si Orbi exécute du code

- Isolation entre utilisateurs, projets et exécutions.
- Limites CPU, mémoire, durée, stockage et réseau.
- Environnements éphémères ou nettoyage vérifiable.
- Politique explicite d'accès réseau sortant.
- Aucun accès implicite au socket Docker de l'hôte ou aux secrets du système.
- Protection contre l'évasion de sandbox et les accès inter-tenants.
- Traçabilité de la création et de la destruction des environnements.
- Gestion des dépendances non fiables.
- Interruption et nettoyage après timeout ou annulation.
- Tests de sécurité spécifiques avant exposition à des utilisateurs externes.

**HORS MVP :** construire une plateforme multi-tenant d'exécution de code à usage général avant d'avoir démontré qu'un fournisseur externe ne suffit pas.

---

## 9. Sécurité et modèle de menace

La sécurité fait partie du produit. L'agent et le code qu'il manipule sont des composants non fiables du point de vue des privilèges.

### 9.1 Actifs à protéger

- comptes et sessions ;
- tokens OAuth et clés API ;
- code source privé ;
- secrets de déploiement ;
- environnements d'exécution ;
- données d'équipe ;
- historiques et journaux ;
- ressources cloud et systèmes de production.

### 9.2 Menaces principales

- accès non autorisé entre utilisateurs ou workspaces ;
- vol de token ou secret exposé dans un log ;
- prompt injection via README, issue, commit, dépendance ou sortie d'outil ;
- exécution de commandes malveillantes ;
- exfiltration de code ou secrets par le réseau ;
- webhook forgé ou rejoué ;
- confusion d'identité ou privilèges excessifs ;
- coût provoqué par des exécutions en boucle ;
- action destructive déclenchée par une mauvaise interprétation ;
- fuite de données via télémétrie ou outils tiers.

### 9.3 Contrôles obligatoires

- Authentification et autorisation côté serveur pour chaque ressource.
- Scopes minimaux et révocation des intégrations.
- Chiffrement en transit ; protection des secrets au repos.
- Redaction des secrets dans logs, erreurs et traces.
- Validation des signatures des webhooks selon le protocole officiel du fournisseur.
- Protection contre les répétitions et idempotence pour les événements et commandes concernés.
- Rate limiting et limites de consommation.
- Cookies de session sécurisés en production, avec attributs appropriés.
- Protection CSRF si l'authentification par cookie et le modèle de requête l'exigent.
- Politique CORS restrictive.
- Gestion des dépendances et mises à jour de sécurité.
- Audit des opérations privilégiées.
- Sauvegardes et procédure de restauration testée.
- Aucun endpoint de connexion de démonstration privilégié ne doit être accessible en production.

### 9.4 Approbations sensibles

Une approbation doit être :
- liée à une action et une ressource précises ;
- donnée par un utilisateur autorisé ;
- horodatée et auditée ;
- invalidée si le contenu de l'action change de façon importante ;
- protégée contre les doubles soumissions ;
- distincte du simple fait qu'un agent recommande l'action.

### 9.5 Sécurité héritée du dépôt

Le cadrage précédent a identifié des points à réexaminer dans le code historique, notamment une route de connexion de démonstration privilégiée et la vérification de signatures de webhooks de paiement. Ces éléments doivent être revérifiés dans la branche actuelle et traités comme des risques potentiellement critiques jusqu'à preuve du contraire. Ce document ne constitue pas un audit de sécurité terminé.

---

## 10. API et conventions

### 10.1 Principes

- Versionner les endpoints publics.
- Définir schémas d'entrée et de sortie explicites.
- Utiliser des erreurs stables et documentées.
- Appliquer l'autorisation avant de retourner des informations sur l'existence d'une ressource privée.
- Paginer les collections.
- Définir les limites de taille des requêtes.
- Ne pas exposer les modèles de base de données directement comme contrats publics.
- Utiliser des identifiants de corrélation pour suivre une requête et ses exécutions.

### 10.2 Commandes longues

Une requête qui démarre une tâche longue doit retourner rapidement une référence de tâche/exécution, avec un état initial et un moyen de suivre la progression. Le transport de progression — polling, SSE ou WebSocket — est **à choisir après analyse** des interfaces et de l'infrastructure. Une interruption de connexion client ne doit pas annuler implicitement le travail en cours.

### 10.3 Idempotence

Les commandes qui créent un effet externe ou une ressource doivent définir si une clé d'idempotence est nécessaire. Le serveur doit documenter la durée de conservation de cette clé et le comportement lors d'une répétition avec un contenu identique ou différent.

### 10.4 Webhooks sortants

- Signer les payloads avec un secret par destination ou un mécanisme équivalent.
- Inclure un identifiant d'événement stable et un timestamp.
- Définir timeout, retry, backoff et politique d'échec.
- Ne pas envoyer de secrets ni de données personnelles non nécessaires.
- Permettre la rotation du secret et la désactivation de la destination.
- Empêcher les URL internes ou métadonnées cloud d'être utilisées pour contourner le réseau : protection SSRF obligatoire lors de la configuration d'URL webhook.

---

## 11. Observabilité et exploitation

### 11.1 Logs structurés

Les logs doivent contenir, selon le contexte : timestamp, niveau, service, environnement, request ID, execution ID, connecteur et code d'erreur normalisé.

Ils ne doivent pas contenir de tokens, mots de passe, clés privées, corps sensibles de dépôt ou contenu privé complet par défaut.

### 11.2 Métriques

Indicateurs initiaux proposés :
- nombre de tâches créées et exécutées ;
- taux de réussite et d'échec par connecteur ;
- latence des appels fournisseurs ;
- durée des exécutions ;
- taille et âge de la file de tâches ;
- nombre de retries et timeouts ;
- approbations en attente ;
- consommation/coûts disponibles par fournisseur ;
- erreurs d'authentification et de permission ;
- disponibilité des dépendances critiques.

Ne pas étiqueter les métriques par des valeurs à cardinalité non bornée comme des IDs de tâche.

### 11.3 Alertes

Définir des alertes sur les échecs anormaux, les files bloquées, l'expiration des intégrations, les quotas approchés et les incidents de sécurité. Les seuils doivent être déterminés à partir des premiers usages mesurés, pas choisis arbitrairement.

### 11.4 Sauvegarde et reprise

Documenter les données à sauvegarder, la fréquence, la rétention, les objectifs de reprise et les tests de restauration. Une sauvegarde non restaurée en test n'est pas une garantie suffisante.

---

## 12. Qualité, tests et critères de livraison

### 12.1 Pyramide de tests

- **Unitaires** : logique métier, transitions d'état, permissions et mapping d'erreurs.
- **Intégration** : base de données, queue, stockage de secrets et workers.
- **Contrat** : format et comportement attendu des connecteurs.
- **API** : statuts, schémas, authentification, autorisation, pagination et erreurs.
- **Sécurité** : accès inter-workspaces, CSRF, SSRF, webhooks, secrets et actions privilégiées.
- **End-to-end** : parcours de l'utilisateur depuis la création d'une tâche jusqu'au résultat.
- **Résilience** : timeout, retries, arrêt du worker, réponse fournisseur inconnue et reconnexion.
- **UX mobile** : affichage des états, reprise, erreurs réseau et confirmations.

### 12.2 Definition of Done

Une fonctionnalité est terminée seulement si :
- le comportement attendu est décrit ;
- les règles d'autorisation sont appliquées côté serveur ;
- les états d'erreur et limites sont traités ;
- les tests sont ajoutés et réussissent ;
- les logs n'exposent pas de secrets ;
- la documentation est à jour ;
- les migrations et la compatibilité sont considérées ;
- les critères d'acceptation sont vérifiés ;
- les métriques nécessaires existent pour les opérations critiques ;
- les capacités non prises en charge sont documentées.

Une couverture globale de tests ne suffit pas à prouver la qualité. La priorité porte sur les chemins critiques et les invariants de sécurité.

---

## 13. Dépendances, coûts et risques fournisseur

Chaque intégration externe doit être documentée avec :
- propriétaire et URL de documentation officielle ;
- mécanisme d'authentification ;
- scopes nécessaires ;
- capacités prises en charge ;
- tarifs, quotas et limites connus ;
- disponibilité géographique et conditions d'éligibilité pertinentes ;
- politique de conservation des données ;
- conditions d'utilisation et restrictions d'automatisation ;
- stratégie en cas d'indisponibilité ou de changement d'API ;
- facilité de migration vers un autre fournisseur.

Orbi doit éviter de dépendre d'une capacité propriétaire non documentée sans plan de sortie. Les prix et conditions étant susceptibles de changer, ils doivent être vérifiés au moment de chaque intégration, et non copiés une fois pour toutes dans la spécification.

---

## 14. Choix techniques à prendre après audit

Les décisions suivantes ne doivent pas être présentées comme déjà tranchées :

| Sujet | État | Critère de décision |
|---|---|---|
| Monolithe modulaire ou services séparés | Proposition : monolithe modulaire | Taille de l'équipe, isolation et besoins de déploiement |
| MongoDB ou autre stockage | À investiguer | Modèle de domaine, transactions, requêtes et coût de migration |
| Redis et queue durable | À investiguer | Besoins de reprise, tâches longues, complexité d'exploitation |
| API REST et progression temps réel | À investiguer | UX mobile, coût d'infrastructure et simplicité |
| Premier agent intégré | À investiguer | API/CLI officielle, qualité, coût, sécurité et disponibilité |
| Fournisseur d'exécution | À investiguer | Isolation, quotas, coût, compatibilité et conditions |
| Web/mobile web/Telegram | À décider après parcours cible | Accessibilité, contraintes d'interface et coût de maintenance |
| Authentification et gestion de secrets | À investiguer | Menaces, fournisseurs existants et exigences d'organisation |
| Modules historiques | À auditer | Usage, qualité, cohérence produit et coût de maintenance |

---

## 15. Stratégie de validation produit

La complexité technique ne prouve pas la valeur utilisateur. Avant d'investir dans des intégrations multiples, valider le problème auprès de développeurs, responsables techniques et utilisateurs mobiles.

Questions à explorer :
- Quelle opération souhaitent-ils lancer depuis leur téléphone ?
- Quels outils utilisent-ils déjà ?
- Où perdent-ils du temps entre agent, dépôt, tests et déploiement ?
- Quelles actions ne veulent-ils jamais automatiser sans approbation ?
- Ont-ils le droit de connecter leurs dépôts et fournisseurs à un service tiers ?
- Quel niveau de visibilité attendent-ils sur les coûts, les logs et les résultats ?
- Quelle intégration utiliserait-on chaque semaine, et pourquoi ?
- Que fait Orbi que l'interface actuelle des outils ne fait pas suffisamment bien ?

Ne pas inventer de témoignages, de partenaires, de résultats, de traction ou de gains de productivité. Les hypothèses et les résultats observés doivent rester séparés.

---

## 16. Plan de travail immédiat

### Étape A — Audit du dépôt
- Examiner la structure et les dépendances.
- Lire les modèles, services, routes, handlers et tests.
- Exécuter les tests et vérifier leur couverture réelle.
- Examiner Docker, variables d'environnement, CI et instructions de déploiement.
- Vérifier les risques de sécurité identifiés dans l'ancien cadrage.
- Produire un rapport de statut : implémenté, partiel, absent, dangereux, obsolète.

### Étape B — Découpage fonctionnel
Pour chaque fonction historique :
- but et utilisateur ;
- état réel ;
- dépendances ;
- risques ;
- décision conserver/refactoriser/retirer ;
- critères d'acceptation ;
- estimation relative et ordre de priorité.

### Étape C — Étude comparative des intégrations
Comparer quelques agents existants et outils de développement/déploiement avec des sources officielles récentes. Évaluer capacité d'intégration, permissions, coût, limites, disponibilité et risque de verrouillage fournisseur.

### Étape D — ADRs
Écrire des *Architecture Decision Records* pour les décisions structurantes : modèle d'exécution, queue, base de données, connecteurs, identité, secrets, événements et approbations. Chaque ADR doit contenir contexte, options, décision, conséquences et statut.

### Étape E — Première tranche verticale
Implémenter un parcours complet et limité : connecter un dépôt, demander une tâche à un agent existant, suivre l'exécution, récupérer un résultat vérifiable et afficher celui-ci sur une interface utilisable sur téléphone. Les opérations de production restent hors de cette première tranche.

---

## 17. Registre initial des risques

| ID | Risque | Gravité initiale | Mesure |
|---|---|---:|---|
| R-01 | Ancien périmètre trop large et état réel incertain | Élevée | Audit avant refonte |
| R-02 | Accès privilégié exposé ou contrôle d'accès insuffisant | Critique si confirmé | Vérifier, corriger et tester avant déploiement |
| R-03 | Webhook non authentifié ou mal vérifié | Critique si confirmé | Vérifier signatures et protection anti-rejeu |
| R-04 | Fuite de secrets vers agents, logs ou navigateur | Critique | Minimisation, stockage sécurisé, redaction et tests |
| R-05 | Exécution de code non fiable avec privilèges excessifs | Critique | Environnement isolé et politiques de ressources |
| R-06 | Dépendance forte à un fournisseur d'agent | Élevée | Connecteurs interchangeables et contrats communs |
| R-07 | Coûts incontrôlés d'exécutions ou retries | Élevée | Quotas, limites, budgets et observabilité |
| R-08 | Interface mobile trop complexe | Moyenne à élevée | Tester un parcours étroit avec des utilisateurs |
| R-09 | Fonctions historiques abandonnées sans décision | Moyenne | Inventaire et décision documentée |
| R-10 | États d'exécution incohérents après timeout | Élevée | Machine à états, réconciliation et idempotence |

La gravité est une estimation initiale, pas une évaluation issue d'un audit terminé.

---

## 18. Glossaire

- **Agent de code** : outil externe qui peut analyser, modifier ou tester du code selon ses capacités.
- **Connecteur** : composant qui permet à Orbi de communiquer avec un fournisseur.
- **Adaptateur** : traduction entre l'interface spécifique d'un fournisseur et le contrat interne d'Orbi.
- **Tâche** : intention de travail exprimée par un utilisateur.
- **Exécution** : tentative concrète de réaliser une tâche ou une opération.
- **Workflow** : enchaînement d'étapes et de décisions entre plusieurs capacités.
- **Approbation** : décision explicite autorisant une action précise.
- **Capability** : opération réellement supportée par un connecteur.
- **RBAC** : contrôle d'accès basé sur les rôles.
- **SSRF** : vulnérabilité où un service est poussé à effectuer des requêtes vers des ressources internes ou non autorisées.
- **Idempotence** : propriété qui permet de répéter une opération sans créer plusieurs effets indésirables.
- **ADR** : document court enregistrant une décision d'architecture et ses conséquences.

---

## 19. Historique des versions

| Version | Date | Changements |
|---|---|---|
| 0.1.0 | 2026-10-23 | Première spécification cible : vision plateforme, intégrations externes, modèle de domaine, sécurité, qualité et plan d'audit |

## 20. Décision de synthèse

La direction retenue est de faire d'Orbi une plateforme de coordination extensible, qui se connecte en priorité aux agents et outils existants plutôt que de construire immédiatement les siens. Son cœur doit gérer les projets, intégrations, tâches, exécutions, permissions, approbations et événements. Le premier objectif de développement est un parcours complet et vérifiable, pilotable depuis un téléphone, avant d'étendre la plateforme aux équipes, au déploiement et aux autres modules.

**Ce document est une spécification initiale, pas une preuve de faisabilité complète.** Les choix définitifs dépendront de l'audit du dépôt, de l'étude des fournisseurs et de la validation du besoin utilisateur.
