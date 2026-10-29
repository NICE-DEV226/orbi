# Orbi — Direction produit : copilote DevOps, avec le code au service de l’exploitation

> **Statut :** orientation retenue par le propriétaire le 29 octobre 2026 (ordre de réalisation ci-dessous) ; sa valeur reste à valider par l’usage
> **Mise à jour :** 29 octobre 2026

## En une phrase

**Orbi aide les développeurs et petites équipes à comprendre et traiter les problèmes de livraison et d’exploitation depuis une interface mobile, en reliant le dépôt, les signaux opérationnels et les agents de code, avec une validation humaine avant les actions sensibles.**

Orbi ne cherche pas à devenir un nouvel agent de code, un IDE mobile, un hébergeur cloud ni une plateforme DevOps universelle. Le code est un moyen de résoudre les problèmes d’exploitation : l’agent peut aider à diagnostiquer et proposer un correctif, mais le résultat utile est un service rétabli ou une livraison débloquée, vérifiés par des signaux observables.

## Ordre de réalisation

Décision du propriétaire (29 octobre 2026) : les deux formulations de la direction sont deux étapes d’un même produit, dans cet ordre.

1. **Contrôle mobile d’agents de code (existe).** Lancer une tâche, la suivre et recevoir le résultat ou la pull request depuis Telegram (accueil, `/task`, carte de suivi, alertes), avec le web en appoint pour ce qui ne doit pas passer par un chat (clés d’API). Cette étape est la condition de la suivante : sans elle, pas d’agent à qui confier un correctif. Elle n’est pas encore validée par un parcours réel complet (voir « État de validation du connecteur Jules »).
2. **Un seul signal d’exploitation : l’échec d’une exécution GitHub Actions.** Il déclenche une proposition de correctif confiée à l’agent, après validation humaine, puis la vérification du résultat par la CI elle-même. Conception : [ADR-0009](adr/0009-first-operational-signal-ci-failure.md). Rien n’est construit tant que l’étape 1 n’a pas fait ses preuves avec un compte fournisseur réel.

Un seul signal à la fois : aucun autre outil d’exploitation n’est ajouté avant que celui-ci ait montré une valeur répétée.

## Problème visé

Quand une vérification, une livraison ou un service échoue, le contexte est dispersé entre le dépôt, les journaux, les outils d’intégration continue, l’hébergement et les outils de développement. Le responsable doit identifier ce qui a échoué, trouver la bonne action, puis vérifier qu’elle a fonctionné. Une notification mobile ou un agent accessible à distance ne résout pas, à lui seul, ce parcours de bout en bout.

Orbi veut réduire cette fragmentation pour les personnes qui maintiennent des applications sans disposer nécessairement d’une équipe d’exploitation dédiée.

## Utilisateurs de départ

**Cible à tester :** développeurs indépendants et petites équipes responsables de leurs propres applications et environnements.

Ils doivent pouvoir superviser une livraison ou un incident depuis leur téléphone, sans pour autant effectuer toute l’analyse technique sur un petit écran. Les besoins des grandes organisations — SSO, politiques complexes, conformité, séparation avancée des équipes — ne sont pas la cible du premier incrément.

## Promesse et distinction recherchée

Les fournisseurs proposent déjà leurs propres agents, interfaces web et expériences mobiles. Le contrôle à distance n’est donc **pas**, à lui seul, la différenciation d’Orbi.

La distinction recherchée est un **parcours commun du signal au résultat** :

1. **Repérer** un échec ou recevoir un signal d’exploitation pertinent.
2. **Rassembler** le contexte utile : projet, changement récent, résultat de CI ou état du service.
3. **Comprendre** le problème et présenter une explication exploitable, avec les limites des données disponibles.
4. **Proposer ou préparer** une action adaptée — par exemple demander à Jules de produire un correctif dans une branche et une pull request.
5. **Faire valider** par une personne les opérations qui modifient un système ou présentent un risque.
6. **Vérifier** le résultat avec une preuve observable : vérification CI, état du service ou confirmation de livraison.
7. **Conserver** l’historique de l’incident, des décisions et du résultat.

L’intérêt d’Orbi dépendra de sa capacité à faire mieux que l’enchaînement manuel de ces étapes. Une abstraction multi-fournisseur qui se limite à masquer les différences entre API ne suffit pas : Orbi doit clairement montrer les capacités réellement disponibles et ne jamais prétendre qu’une action a réussi sans confirmation.

## Premier parcours à expérimenter

### Échec de CI → diagnostic → correctif proposé → vérification

1. Un échec de vérification sur un dépôt est signalé à Orbi.
2. Orbi présente le dépôt, le commit concerné et les informations d’échec disponibles.
3. L’utilisateur demande un diagnostic ou confie un correctif à un agent connecté, notamment Jules.
4. Orbi suit l’exécution et rend la pull request et son statut consultables depuis le web ou Telegram.
5. Une personne examine et approuve la suite ; aucune fusion ni mise en production n’est automatique dans ce premier parcours.
6. Orbi affiche le résultat des vérifications qui ont effectivement été exécutées.

**Ce parcours est une cible, pas une capacité déjà implémentée de bout en bout.** Le dépôt actuel possède un flux de tâche et d’exécution d’agent, mais l’ingestion d’échecs CI, la corrélation avec une livraison, le diagnostic d’exploitation et la vérification du service restent à construire ou à confirmer.

### État de validation du connecteur Jules

Au 27 octobre 2026, le propriétaire indique avoir testé Jules avec un compte réel et trouvé le parcours presque fonctionnel. Cette information vient du propriétaire du projet ; elle n’a pas été reproduite indépendamment pendant la préparation de ce document. Les tests automatisés du dépôt vérifient principalement les contrats simulés. Il faut conserver cette distinction dans la documentation et compléter les critères de validation à partir des résultats réels observés.

## Périmètre initial

### À privilégier

- Un seul scénario opérationnel étroit, utile et répétable.
- Des signaux issus d’outils déjà utilisés par la cible, sélectionnés après validation du besoin.
- Un diagnostic en lecture seule avant toute action modificatrice.
- L’agent de code comme outil de correction facultatif, pas comme produit entier.
- Une validation humaine explicite avant fusion, redémarrage, modification d’infrastructure ou déploiement.
- Des états clairs : réussi, échoué, en attente, non vérifié.
- Des notifications mobiles concises avec un lien vers les détails nécessaires.

### À ne pas entreprendre au premier incrément

- Une plateforme générique couvrant tous les clouds, CI, observabilité et fournisseurs.
- Des commandes arbitraires ou un accès SSH privilégié à des serveurs.
- Des déploiements de production autonomes ou des changements d’infrastructure sans approbation.
- La coordination de nombreux agents ou la création d’un agent propriétaire.
- Une offre complète pour tous les profils professionnels.
- La transformation immédiate des modules historiques du bot en une suite de produits intégrés.

## Principes de sécurité et de confiance

- Les intégrations commencent en lecture seule lorsqu’elle suffit au diagnostic.
- Les clés et jetons ne sont jamais inclus dans les prompts, les notifications ou les journaux par défaut.
- Une action est décrite avant son exécution ; une approbation concerne cette action précise.
- Les opérations sensibles restent protégées par des permissions côté serveur et une confirmation explicite.
- Les échecs, les délais dépassés et les résultats inconnus ne sont pas présentés comme des réussites.
- Chaque action doit pouvoir être reliée à son auteur, son projet, son exécution et son résultat.
- Le système distingue les données observées des conclusions suggérées par un agent.

## Comment décider si la direction fonctionne

Avant d’élargir le produit, observer avec quelques utilisateurs de la cible :

- s’ils utilisent réellement le parcours pour un problème réel, et s’ils y reviennent ;
- le temps et les changements d’outils nécessaires pour passer du signal au diagnostic ;
- si le diagnostic et le résultat de l’agent sont compréhensibles et vérifiables ;
- les étapes où l’utilisateur reprend la main ou abandonne ;
- les fausses alertes, actions inutiles ou informations manquantes ;
- si le parcours apporte une valeur que l’interface directe du fournisseur ne donne pas déjà.

Ne pas déclarer la proposition validée sur la seule base de tests logiciels, d’une intégration qui répond ou d’une démonstration. La répétition d’un usage utile et la confiance accordée au résultat sont les preuves importantes.

## Écart entre la direction et le produit actuel

| Domaine | État observable dans le dépôt | Direction visée |
|---|---|---|
| Agents | Connecteurs Jules, Cursor et factice ; lancement et suivi d’exécutions | Utiliser l’agent comme étape d’un parcours de résolution |
| Interface | Bot Telegram comme interface principale (accueil, nouvelle tâche, carte de suivi, alertes) et web mobile pour les clés ; Orbi Dev est réservé aux administrateurs | Interface de supervision concise pour l’opérateur responsable |
| État et historique | Tâches, exécutions, événements, notifications et références de PR | Historique d’incidents reliant signal, décision, changement et vérification |
| Intégration CI / exploitation | Webhook GitHub historique pour certains événements ; pas de parcours CI/incidents établi par le code inspecté | Détection et contextualisation d’un scénario d’échec limité |
| Vérification | Suivi de l’état du fournisseur et lien éventuel vers une PR | Résultat de CI ou état de service observé après le correctif |
| Actions opérationnelles | Pas de fusion ou déploiement automatique dans l’interface Orbi Dev actuelle | Actions limitées, autorisées et approuvées explicitement, plus tard |
| Utilisateurs | Identité Telegram ; Orbi Dev accessible aux administrateurs | Commencer avec développeurs seuls/petites équipes, puis valider le besoin d’équipe |

## Prochaine décision produit

Le signal d’entrée est choisi : un échec **GitHub Actions** ([ADR-0009](adr/0009-first-operational-signal-ci-failure.md), proposition à valider). Restent à trancher dans cet ADR les données réellement accessibles sans jeton GitHub, la méthode de diagnostic, les actions permises et la preuve de réussite. Ne pas ajouter d’autres intégrations opérationnelles tant que ce parcours n’a pas démontré une valeur répétée.
