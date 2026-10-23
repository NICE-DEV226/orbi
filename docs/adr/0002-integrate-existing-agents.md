# ADR-0002 — Intégrer les agents de code existants avant d'en créer un

- **Statut :** direction produit décidée ; fournisseur technique à sélectionner
- **Date :** 2026-10-23
- **Lié à :** [spécification Orbi](../ORBI_SPECIFICATION.md)

## Contexte

Orbi veut permettre de piloter des tâches de développement et des opérations depuis une interface unifiée, y compris sur téléphone. Il existe déjà des agents et plateformes de développement. Construire un agent propriétaire en premier dupliquerait des capacités et détournerait les efforts du problème d'orchestration.

## Décision

Orbi doit intégrer en priorité des agents et outils existants via leurs interfaces officiellement supportées. Orbi construit son propre agent ou composant d'exécution uniquement si une lacune concrète est démontrée et si le coût, la sécurité, la maintenance et l'avantage utilisateur sont justifiés.

## Exigences pour sélectionner le premier fournisseur

Comparer au minimum :
- API/SDK officielle, CLI officielle ou intégration Git supportée ;
- capacité à créer et suivre une tâche à distance ;
- accès aux dépôts et scopes requis ;
- retour d'état, journaux, diff ou pull request ;
- annulation et reprise lorsque disponibles ;
- isolation de l'environnement et permissions ;
- coût, quotas, limites de débit et latence ;
- conditions d'utilisation, stockage et entraînement éventuel sur les données ;
- disponibilité dans les pays et moyens de paiement pertinents ;
- stabilité, versionnement et risque de verrouillage ;
- comportement en cas de timeout où le résultat externe est inconnu.

Les conclusions doivent citer des documents officiels actuels et distinguer les capacités confirmées des capacités supposées.

## Contrat d'intégration

Le domaine Orbi consomme des capacités normalisées et ne dépend pas des objets internes du fournisseur. Chaque adaptateur déclare les capacités réellement disponibles et mappe les erreurs. Les secrets sont gérés séparément et les appels sont autorisés côté serveur.

L'interface ne doit jamais afficher une capacité comme disponible si le compte connecté, le plan ou les scopes ne la permettent pas.

## Lacunes justifiant éventuellement du développement interne

Le développement d'un composant propre peut être envisagé si les tests montrent par exemple :
- aucun fournisseur ne permet le workflow requis ;
- la supervision multi-fournisseurs est impossible avec les API disponibles ;
- l'observabilité, les politiques ou les approbations doivent être ajoutées par Orbi ;
- une exigence de sécurité ou de portabilité ne peut pas être satisfaite autrement ;
- le coût ou les restrictions des fournisseurs empêchent le produit d'être viable.

Une lacune doit être documentée avec scénario, preuve, alternatives évaluées, coût d'implémentation et critères de succès. « Nous pouvons le coder nous-mêmes » n'est pas une justification suffisante.

## Conséquences

- La première tranche produit est l'orchestration et la supervision, pas la création d'un modèle de code.
- Orbi peut rester agnostique du fournisseur tant que les capacités communes sont définies.
- Les capacités propriétaires sont exposées explicitement plutôt que masquées par une abstraction trompeuse.
- Le plan de sortie d'un fournisseur doit être examiné avant de s'appuyer sur une capacité critique.

## Conditions de réexamen

Réexaminer si le marché, les API ou les conditions des fournisseurs changent, ou si la validation utilisateur révèle un besoin que les intégrations ne peuvent pas satisfaire.
