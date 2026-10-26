# ADR-0008 — Interface web : un seul shell Jinja + htmx, sans framework CSS

- **Statut :** appliqué
- **Date :** 2026-10-26
- **Lié à :** [ADR-0007](0007-telegram-mini-app.md), [DESIGN.md](../DESIGN.md)

## Contexte

Le web comportait deux produits collés : un dashboard d'administration (Bootstrap, barre latérale fixe de 250 px, inutilisable sur téléphone, sans navigation) et l'interface Orbi Dev (gabarit mobile séparé), avec Bootstrap et ses icônes chargés depuis un CDN, du JavaScript d'interrogation écrit à la main et un point d'API JSON uniquement destiné à cette page. Le responsable du projet a décidé d'**intégrer l'administration dans la même interface** et de **conserver le rendu serveur avec htmx**.

## Décision

1. **Un seul shell** (`layout.html`) pour tout le web : Orbi Dev et l'administration deviennent des sections (Tâches, Projets, Connexions, Support, Utilisateurs, Système) ; le tableau de bord de compteurs devient la page Système.
2. **Rendu serveur Jinja + htmx.** Les mises à jour en direct sont des **fragments** HTML qui s'interrogent eux-mêmes tant qu'une exécution est active, puis cessent (aucun JavaScript applicatif). `hx-boost` donne la navigation sans rechargement. Le point d'API JSON d'interrogation est supprimé.
3. **Aucun framework CSS, aucun CDN** : une feuille de style écrite à la main, la police et htmx (version épinglée, licence BSD-0) auto-hébergés, des icônes SVG intégrées.
4. **htmx durci** : `allowEval=false`, `allowScriptTags=false`, `historyCacheSize=0` (htmx copie sinon les pages visitées dans le stockage local). Le jeton CSRF accompagne chaque requête htmx dans l'en-tête `X-CSRF-Token` (le champ de formulaire reste accepté, et les formulaires fonctionnent sans JavaScript).
5. Toute page ou fragment authentifié est servi avec `Cache-Control: no-store`.

## Alternatives écartées
- **Application React/Vue** : plus de liberté visuelle, mais une chaîne de construction, une API à concevoir et la sécurité des sessions à refaire, pour une application faite surtout de listes, de formulaires et d'état.
- **Garder Bootstrap** : le rendu générique ne porte aucune identité et alourdit la page.

## Conséquences et limites
- Les fragments tant que l'exécution est active génèrent une requête toutes les 3 s (page de détail) ou 4 s (liste) : acceptable pour un usage individuel, à remplacer par un flux serveur (SSE) si le nombre d'utilisateurs simultanés grandit.
- Les scripts intégrés aux pages (intégration Telegram, connexion automatique) empêchent une politique CSP stricte sur `script-src` ; passer à des scripts avec nonce est une évolution possible.
- Le rendu a été vérifié en captures (Firefox sans fenêtre, thèmes clair et sombre, téléphone et ordinateur), pas dans un vrai client Telegram.
