# ADR-0007 — Orbi Dev comme Mini App Telegram (lien magique conservé en repli)

- **Statut :** appliqué (authentification et points d'entrée) ; l'interface unifiée et les notifications suivent
- **Date :** 2026-10-26
- **Lié à :** [ADR-0001](0001-modular-monolith.md), [ADR-0003](0003-durable-execution-model.md)

## Contexte

Les utilisateurs d'Orbi sont déjà dans Telegram. L'accès au web passait par un lien magique, inatteignable en pratique : la page de connexion citait une commande `/web` qui n'existait pas et aucun bouton ne menait au panneau d'administration.

## Décision

1. **Mini App Telegram** : Orbi Dev s'ouvre depuis Telegram (bouton du menu principal, bouton à côté du champ de saisie pour le superadmin) et l'utilisateur est identifié par la signature de Telegram, sans lien ni mot de passe.
2. **Lien magique conservé** pour un navigateur ordinaire, désormais atteignable par `/web`.
3. **Rendu serveur (Jinja) avec htmx**, interface unique intégrant l'administration (décisions prises avec le responsable du projet ; mises en œuvre dans les PR suivantes).

## Authentification Mini App

`POST /admin/telegram-login` reçoit l'`initData` brute et la valide côté serveur ([procédure officielle](https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app)) : signature HMAC-SHA256 dérivée du jeton du bot, fraîcheur (`TELEGRAM_INITDATA_MAX_AGE`, 1 h par défaut), pas de champ dupliqué, taille bornée, comparaison en temps constant. Le compte doit exister (ouvert via le bot), ne pas être banni et avoir un rôle administrateur : mêmes règles que le lien magique. Une redirection `next` n'accepte que des chemins internes connus.

La documentation officielle écrit l'ordre des arguments du HMAC de façon contradictoire (texte et pseudo-code). La convention retenue (`HMAC(clé="WebAppData", message=jeton)`) a été **confirmée par aiogram** (`check_webapp_signature` accepte nos signatures et refuse celles d'un autre jeton) ; un vecteur de test figé, validé de la même façon, protège contre toute dérive.

## Cookies et iframe

Telegram Web charge la Mini App dans une iframe d'un autre site : un cookie `SameSite=Lax` n'y serait pas renvoyé. La session ouverte par la Mini App utilise donc `SameSite=None; Secure; Partitioned` (en https seulement) ; le cookie du lien magique reste `Lax`. Toutes les écritures restent protégées par le jeton CSRF lié à la session. En contrepartie, un en-tête `Content-Security-Policy: frame-ancestors` n'autorise l'encadrement que par notre origine et les domaines Telegram.

## Conséquences et limites

- **Telegram exige une URL https publique** pour les Mini Apps et les boutons-liens. Avec `BASE_URL=http://localhost`, ces boutons n'apparaissent pas ; le lien reste affiché dans le texte du message.
- **Non vérifié avec un vrai client Telegram** : aucun bot ni domaine public n'était disponible. Sont testés : la validation (dont un vecteur confirmé par une bibliothèque indépendante), l'endpoint, les cookies, les en-têtes, les boutons et commandes. À essayer sur téléphone, sur Telegram Desktop et sur Telegram Web, en particulier le comportement du cookie partitionné dans l'iframe.
- Le script `telegram-web-app.js` est chargé depuis `telegram.org` (recommandé par Telegram, sans contrôle d'intégrité possible).
- Une `initData` interceptée reste utilisable pendant sa durée de validité : d'où la valeur courte par défaut.

## Condition de réexamen

Si le cookie partitionné ne fonctionne pas dans Telegram Web, passer à un jeton porté par un en-tête (htmx permet de l'ajouter à chaque requête).
