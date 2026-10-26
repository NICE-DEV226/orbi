# Orbi — Design de l'interface web

Interface unique en rendu serveur (Jinja) avec htmx, ouverte depuis Telegram (Mini App) ou un navigateur. Décisions : [ADR-0007](adr/0007-telegram-mini-app.md) et [ADR-0008](adr/0008-web-ui-jinja-htmx.md).

## Ce que l'interface doit faire comprendre en deux secondes
Quels agents travaillent, lesquels ont besoin de la personne, et où est la pull request. L'objet central est une **exécution** : elle a un état, une histoire et un résultat.

## L'idée visuelle : l'anneau d'orbite
Chaque exécution est représentée par un anneau (clin d'œil au nom Orbi). **La forme porte l'état**, pas seulement la couleur, donc la lecture reste possible en daltonisme et en plein soleil :

| État | Forme |
|---|---|
| En cours | arc qui tourne sur un anneau pâle |
| Terminé | anneau fermé avec une coche |
| Échec | anneau rompu avec une croix |
| À vérifier, attend votre accord | anneau avec un point posé dessus (couleur ambre) |
| En attente | anneau en pointillés |
| Annulé | anneau avec un tiret |
| Trop long | demi-anneau avec une aiguille |

C'est le seul endroit où le design prend un risque ; tout le reste est volontairement calme : lignes plates séparées par des filets (pas de cartes identiques), un seul accent réservé.

## Jetons (`src/static/orbi.css`)
| Rôle | Sombre | Clair |
|---|---|---|
| Fond (`--nuit`) | `#15132b` | `#f6f4fc` |
| Surface (`--pont`) | `#1e1c3a` | `#ffffff` |
| Texte (`--encre`) | `#eeeaf9` | `#1b1838` |
| Texte secondaire (`--brume`) | `#a29fc4` | `#5e5a86` |
| Bordure de champ (`--champ`) | `#7a75a8` | `#7d78a8` |
| Signal (`--signal`) : action principale, ce qui demande l'humain | `#ffb84d` | `#ffb84d` (texte : `#9a5b00`) |
| En cours / Validé / Échec | `#8ea2ff` / `#6fe3b0` / `#ff7b86` | `#4a5fd6` / `#137a52` / `#c4303f` |

Le thème suit Telegram (`colorScheme`) dans la Mini App, sinon la préférence du système. **Le contraste est vérifié par un test** (`tests/test_ui_design.py`) : texte ≥ 4,5:1, bordures de champs ≥ 3:1, dans les deux thèmes.

## Typographie
Une seule famille, **Atkinson Hyperlegible Next** (OFL, auto-hébergée dans `src/static/fonts/`), conçue pour la lisibilité sur petit écran. Poids 400 / 600 / 700 / 800, interligne 1,5, lignes limitées à 62 caractères pour la prose. Monospace système uniquement pour les noms de branches et le code.

## Composants
- **Ligne** (`.row`) : anneau, titre sur deux lignes au plus, méta en texte courant, chevron. Les groupes (« À vérifier », « En cours », « Récentes ») viennent du serveur.
- **Feuille** (`.sheet`) : la seule surface surélevée, réservée au résultat d'une exécution (pull request) et à la connexion.
- **Journal** (`.log`) : historique vertical ; le nœud le plus récent prend la couleur de l'état.
- **Barre du bas** (téléphone) : Tâches, Projets, Support, Réglages. **Colonne de gauche** (≥ 56 rem) : tout est directement accessible.

## Règles d'écriture
Phrases normales en français courant, jamais le vocabulaire du système (« L'agent a démarré », pas « lancé chez le fournisseur »). Les actions gardent le même nom partout (« Nouvelle tentative »). Une erreur dit ce qui s'est passé et quoi faire ; un écran vide propose l'action suivante. Pas de majuscules espacées, pas de séparateurs « · », pas de flèches dans les libellés.

## Mouvement
Un seul mouvement spontané : l'arc des exécutions en cours. Il s'arrête si la personne demande moins de mouvement (`prefers-reduced-motion`).

## Interdits (vérifiés par des tests)
Aucune ressource tierce (CDN) hormis le script officiel de Telegram ; htmx sans `eval` ni `<script>` dans les fragments et sans copie des pages dans le stockage local ; toute page authentifiée est servie avec `Cache-Control: no-store` ; chaque champ a un `label` ; les icônes sont décoratives (`aria-hidden`).
