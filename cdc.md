> **Document historique (v4.0, mars 2026).** Il décrit le périmètre initial d'un assistant Telegram universel et n'est plus à jour : le module **Commerce/paiements a été supprimé**, **Communauté est optionnel**, et la direction du produit est **Orbi Dev**. La référence actuelle est la [spécification](docs/ORBI_SPECIFICATION.md) et la [feuille de route](docs/ROADMAP.md).

ORBI
Assistant Universel Telegram
@OrbiBot  ·  Français  ·  English  ·  العربية
Support  ·  Commerce  ·  Communauté  ·  Productivité  ·  Développeurs
Document	Cahier des Charges — Fonctionnalités Complètes
Version	4.0 — Mars 2026
Stack	Python 3.12 · python-telegram-bot v21 · FastAPI · MongoDB · Redis · Docker
Paiements	Stripe (cartes internationales) · Orange Money · Wave
Langues	Français (FR) · English (EN) · العربية (AR) — détection automatique + changement à tout moment
Navigation	100% boutons inline — aucune commande à mémoriser pour l'utilisateur final
Modules	5 modules complets à parité : Support · Commerce · Communauté · Productivité · Développeurs
Principe	Produit final complet — chaque fonctionnalité est active, traduite et robuste aux erreurs


1. Principes Fondamentaux du Produit
1.1 Vision
Orbi est un assistant Telegram universel qui centralise cinq univers fonctionnels dans une interface conversationnelle unifiée. Un utilisateur n'a jamais besoin de taper une commande : tout s'opère via des boutons inline dynamiques organisés en menus contextuels. Le bot s'adapte automatiquement à la langue de l'utilisateur dès le premier contact et maintient cette cohérence dans chaque réponse, notification et message d'erreur.

1.2 Navigation 100% Boutons — Principe Fondamental
Aucune commande textuelle n'est requise de l'utilisateur final. Chaque action est accessible via un bouton inline. Les menus sont contextuels, hiérarchiques et toujours accompagnés d'un bouton "← Retour". Les seules commandes existantes sont des raccourcis optionnels pour les utilisateurs avancés.

Architecture de navigation :
•Menu Principal → 5 modules accessibles via boutons depuis n'importe où dans la conversation.
•Chaque module a son propre sous-menu avec toutes ses fonctions listées en boutons.
•Bouton "← Retour" présent à chaque niveau pour revenir au niveau supérieur.
•Bouton "🏠 Accueil" toujours accessible pour revenir au menu principal.
•Les formulaires multi-étapes (création ticket, commande) affichent la progression et permettent de revenir en arrière.
•Les confirmations d'action affichent toujours un bouton "Confirmer" et un bouton "Annuler".
•Les listes longues (produits, tickets, tâches) ont des boutons de pagination "← Précédent" / "Suivant →".
•Les actions destructives (annuler commande, supprimer note) demandent toujours une confirmation.

1.3 Internationalisation — Principe Fondamental
Chaque chaîne de texte visible par l'utilisateur (messages, boutons, erreurs, notifications) existe en FR, EN et AR. L'arabe est affiché en RTL natif via Telegram. Le bot détecte la langue Telegram de l'utilisateur au premier contact et l'applique immédiatement. L'utilisateur peut changer de langue à tout moment depuis son profil.

1.4 Robustesse — Principe Fondamental
Toute fonctionnalité gère ses cas d'erreur et edge cases de manière visible et explicite :
•Timeout de session (30 minutes d'inactivité) : message informatif localisé, état conservé si possible.
•Erreur réseau ou service externe indisponible : message d'erreur avec suggestion de réessayer, jamais de crash silencieux.
•Action sur un objet qui n'existe plus (ticket fermé, produit retiré) : message explicatif avec alternatives.
•Dépassement de quota (trop de messages, trop de tickets ouverts) : message clair avec la limite et la suggestion.
•Double-action (double-clic sur "Commander") : idempotence garantie, une seule opération créée.
•Erreurs de validation (champ vide, format invalide) : message d'aide localisé, demande de correction.


2. Onboarding & Navigation Globale
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Premier contact	À la toute première interaction, le bot détecte la langue Telegram de l'utilisateur. Si elle est parmi FR/EN/AR, elle est appliquée directement. Sinon, un sélecteur de langue s'affiche en 3 langues simultanément pour que chacun reconnaisse la sienne.	Boutons inline : 🇫🇷 Français · 🇬🇧 English · 🇸🇦 العربية. Après sélection, le menu principal s'affiche immédiatement dans la langue choisie.	La langue est sauvegardée en base de données. Elle persiste entre les sessions. Un utilisateur qui revient plus tard retrouve sa langue sans re-sélection.
Message de bienvenue	Après la sélection de langue (ou directement pour les utilisateurs existants), un message de bienvenue personnalisé avec le prénom Telegram de l'utilisateur introduit les 5 modules disponibles. Concis, chaleureux, traduit.	Le menu principal s'affiche immédiatement sous le message de bienvenue avec 5 boutons de module + 1 bouton Mon Profil.	Pour les utilisateurs existants qui refont /start, le message de bienvenue est plus court (pas de redécouverte). Le menu s'affiche directement.
Menu Principal	Interface centrale d'Orbi. Accessible depuis n'importe quel état de la conversation. Affiche les 5 modules + accès au profil. Chaque bouton montre le nom du module et son icône.	Boutons : 🎧 Support · 🛍️ Boutique · 👥 Communauté · ⚡ Productivité · 👨‍💻 Développeurs · 👤 Mon Profil. Bouton 🏠 Accueil disponible dans tous les sous-menus.	Si l'utilisateur est banni, seul un message d'information s'affiche, sans accès aux fonctions.
Mon Profil	Page profil de l'utilisateur affichant : prénom, langue actuelle, rôle, date d'inscription, statistiques (nb commandes, nb tickets, points karma). Options de personnalisation accessibles depuis cette page.	Boutons : ✏️ Changer de langue · 🔔 Notifications · 🕐 Fuseau horaire · 📊 Mes statistiques · ← Retour.	Les modifications de profil sont sauvegardées immédiatement et confirmées par un message.
Changement de langue	Disponible depuis Mon Profil à tout moment. L'interface bascule instantanément dans la nouvelle langue, y compris le message de confirmation lui-même.	Boutons inline : 🇫🇷 Français · 🇬🇧 English · 🇸🇦 العربية. Bouton ← Annuler.	La nouvelle langue est sauvegardée en DB et en cache Redis (TTL 10 min). Toutes les interactions suivantes utilisent la nouvelle langue.
Préférences notifications	L'utilisateur choisit quelles notifications il souhaite recevoir : confirmations de commandes, réponses tickets, annonces communauté, morning brief.	Boutons toggle (✅/❌) pour chaque type de notification. Bouton Sauvegarder. Bouton ← Retour.	Les préférences sont respectées par le service de notification. Un utilisateur qui désactive les annonces ne les reçoit plus, même lors des broadcasts.
Fuseau horaire	L'utilisateur configure son fuseau horaire pour les rappels, le morning brief et les heures affichées. Liste des fuseaux avec recherche par nom de ville.	Champ de saisie libre pour la ville ou le fuseau (ex: "Paris", "UTC+1"). Bouton ← Retour.	Le fuseau est utilisé pour tous les calculs de temps personnels. Par défaut : UTC.
Utilisateur banni	Si un administrateur a banni l'utilisateur, toute interaction affiche un message expliquant le ban, sa raison, et les informations de contact pour contester si applicable.	Aucun bouton fonctionnel. Seul un bouton "Contacter le support" si cette option est activée.	Le ban est vérifié à chaque interaction via le middleware d'authentification. Pas de bypass possible.


3. Module Support & Service Client
🎧 Support — Tickets · Agents · SLA · CSAT · Réponses rapides

3.1 Gestion des Tickets
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Créer un ticket	L'utilisateur ouvre un ticket via le menu Support. Un formulaire guidé en plusieurs étapes collecte : la catégorie du problème, le sujet (titre court), la description détaillée. Un récapitulatif est présenté avant la soumission. Après confirmation, le ticket est créé avec un numéro unique (TKT-YYYY-NNNNN) et une deadline SLA calculée selon la priorité.	Étape 1 → Boutons catégorie : 💳 Facturation · 🔧 Technique · 💬 Général · ⚠️ Réclamation · 📋 Autre. Étape 2 → Saisie sujet (texte). Étape 3 → Saisie description (texte). Étape 4 → Récapitulatif + boutons Confirmer / ← Modifier.	Maximum 3 tickets ouverts simultanément par utilisateur. Sujet : 5 à 100 caractères. Description : minimum 20 caractères. En cas de dépassement de quota, message explicatif avec le nombre de tickets actuellement ouverts.
Priorité automatique	La priorité d'un ticket est déterminée automatiquement à la création selon la catégorie et les mots-clés détectés dans la description. L'utilisateur n'a pas à choisir une priorité lui-même — c'est transparent.	Aucune interaction utilisateur. La priorité s'affiche dans la confirmation de création : ex. "Priorité : Haute — Réponse sous 4h".	Priorités : Urgente (1h SLA), Haute (4h), Moyenne (24h), Basse (72h). Mots-clés urgents : paiement bloqué, fraude, accès impossible, urgent. Catégorie Réclamation → automatiquement Haute.
Répondre à un agent	Quand un agent répond à un ticket, l'utilisateur reçoit une notification Telegram avec le message de l'agent. Il peut répondre directement depuis Telegram via un bouton.	Notification avec boutons : 💬 Répondre · ✅ Marquer comme résolu · 📋 Voir le ticket complet.	La réponse est ajoutée à l'historique du ticket. L'agent est notifié immédiatement. Les pièces jointes (photos, documents) sont acceptées.
Historique du ticket	L'utilisateur peut consulter l'historique complet d'un ticket : tous les messages échangés avec les agents, les changements de statut, la date de création et la deadline SLA restante.	Menu Support → Mes Tickets → sélectionner un ticket → Historique complet. Boutons : 💬 Répondre · ✅ Fermer · ← Retour à mes tickets.	L'historique affiche les messages dans l'ordre chronologique avec le rôle de l'expéditeur (Vous / Agent). Les messages longs sont tronqués avec un bouton "Voir plus".
Fermer un ticket	L'utilisateur peut fermer son ticket à tout moment s'il considère son problème résolu, sans attendre la réponse de l'agent.	Bouton ✅ Fermer le ticket → confirmation avec boutons Confirmer / Annuler.	Un ticket fermé ne peut plus recevoir de réponses. Son statut passe à "Fermé" et il n'est plus comptabilisé dans le quota des 3 tickets ouverts.
Évaluation CSAT	24 heures après la résolution d'un ticket, le bot envoie automatiquement une demande d'évaluation de la satisfaction. L'utilisateur note son expérience de 1 à 5 étoiles.	Notification avec boutons : ⭐ · ⭐⭐ · ⭐⭐⭐ · ⭐⭐⭐⭐ · ⭐⭐⭐⭐⭐ · Ignorer.	Si l'utilisateur n'évalue pas après 48h, un rappel est envoyé une seule fois. Après le second rappel sans réponse, le ticket est définitivement fermé. L'évaluation est anonymisée dans les statistiques agrégées.
Escalade automatique	Si le bot ne comprend pas la demande de l'utilisateur après 3 tentatives consécutives dans la même session, il propose automatiquement de créer un ticket et de le connecter à un agent humain.	Après la 3ème incompréhension → message d'escalade + boutons : 🎧 Créer un ticket maintenant · ← Continuer seul.	Le ticket créé par escalade est automatiquement catégorisé "Général" avec priorité Moyenne. Le contexte de la conversation (les 3 derniers messages) est joint automatiquement comme description.

3.2 Alertes & SLA
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
SLA et deadlines	Chaque ticket a une deadline de réponse selon sa priorité. Le système surveille en permanence les tickets proches de leur deadline et déclenche des alertes automatiques vers le canal admin Telegram.	Aucune interaction utilisateur. Visible dans la liste des tickets (temps restant affiché).	Vérification toutes les 5 minutes. Alerte à 30 minutes avant expiration. Double alerte si dépassement de 2x le SLA. Escalade de priorité automatique si dépassement.
Notifications de statut	L'utilisateur est notifié à chaque changement de statut de son ticket : prise en charge par un agent, demande d'informations supplémentaires, résolution.	Notifications automatiques avec boutons contextuels selon le nouveau statut.	Notifications désactivables depuis les préférences. Si l'utilisateur a désactivé les notifications tickets, seules les réponses directes lui parviennent.


4. Module Commerce & Paiements
🛍️ Commerce — Catalogue · Panier · Commandes · Stripe · Orange Money · Wave

4.1 Catalogue & Produits
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Catalogue produits	Affichage du catalogue organisé par catégories. Chaque page affiche 6 produits avec photo, nom traduit dans la langue de l'utilisateur, prix et disponibilité. Navigation par pagination et filtrage par catégorie.	Boutons : [Catégorie 1] [Catégorie 2] ... puis liste produits avec [Voir →] par produit. Navigation : ← Page précédente · Page suivante → · 🏠 Accueil.	Les produits hors-stock sont affichés avec un badge "Indisponible". Le cache du catalogue est actualisé toutes les 5 minutes. En cas de catalogue vide, message informatif avec retour au menu.
Fiche produit	Page détaillée d'un produit : photo principale, nom complet traduit, description complète traduite, prix, stock disponible, catégorie. L'utilisateur peut ajouter au panier directement depuis cette page.	Boutons : 🛒 Ajouter au panier · ❤️ Mettre en favori · ← Retour au catalogue.	Si le produit est hors-stock, le bouton "Ajouter au panier" est remplacé par "🔔 Me notifier quand disponible". Si le produit est désactivé après l'affichage, un message d'erreur explicatif s'affiche au clic.
Alerte disponibilité	L'utilisateur peut s'inscrire pour être notifié quand un produit hors-stock devient disponible.	Bouton 🔔 Me notifier quand disponible depuis la fiche produit. Un seul clic, confirmation immédiate.	Notification envoyée dès que le stock repasse au-dessus de 0. L'inscription est annulée automatiquement après notification ou après 30 jours.
Recherche produits	L'utilisateur peut rechercher un produit par son nom. La recherche est multilingue : elle fonctionne quelle que soit la langue de saisie.	Bouton 🔍 Rechercher depuis le catalogue → saisie du terme → résultats affichés en liste.	Minimum 2 caractères pour déclencher la recherche. Si aucun résultat, suggestion d'élargir la recherche ou de parcourir les catégories.

4.2 Panier & Commande
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Gestion du panier	Le panier persiste pendant 2 heures après le dernier ajout. L'utilisateur peut consulter son panier à tout moment, modifier les quantités, retirer des articles et voir le sous-total mis à jour en temps réel.	Boutons par article : ➕ · ➖ · 🗑️ Retirer. Boutons panier : 🛒 Commander · 🗑️ Vider le panier · ← Catalogue.	Maximum 20 articles différents dans le panier. Quantité maximale par article = stock disponible. Si le stock a changé depuis l'ajout, alerte lors de la révision du panier.
Codes promo	L'utilisateur peut saisir un code promo lors du checkout. Le code est validé immédiatement et la remise est affichée dans le récapitulatif avant confirmation.	Étape checkout → Bouton 🎟️ J'ai un code promo → saisie → validation instantanée avec affichage de la remise.	Types de remise : pourcentage, montant fixe, livraison gratuite. Contraintes : date d'expiration, nombre d'utilisations, montant minimum de commande. Message d'erreur spécifique si le code est expiré, épuisé ou invalide.
Processus de commande	Checkout en 4 étapes : récapitulatif du panier + code promo → saisie de l'adresse de livraison → choix du provider de paiement → récapitulatif final + confirmation. Chaque étape permet de revenir à la précédente.	Étape 1 : récap + bouton ← Modifier panier. Étape 2 : formulaire adresse. Étape 3 : boutons 💳 Stripe · 📱 Orange Money · 🌊 Wave. Étape 4 : récap total + Confirmer / Annuler.	La commande n'est créée en base que lors de la confirmation finale. Le double-clic sur "Confirmer" est protégé par idempotence. Timeout de 30 minutes sur le processus complet — le panier est préservé.
Paiement Stripe	Pour les paiements par carte bancaire internationale. L'utilisateur est redirigé vers une page Stripe Checkout sécurisée. Après paiement, retour automatique vers Telegram avec la confirmation.	Bouton 💳 Payer par carte → lien Stripe envoyé dans le chat. Bouton ← Annuler le paiement disponible tant que le paiement n'est pas complété.	Toutes les devises supportées par Stripe. Paiement 3D Secure si requis par la banque. Timeout de paiement : 30 minutes. En cas d'échec, message explicatif avec proposition de réessayer ou de choisir un autre provider.
Paiement Orange Money	Pour les paiements mobile money Orange dans les pays d'Afrique de l'Ouest. L'utilisateur est guidé vers la page de paiement Orange Money.	Bouton 📱 Payer avec Orange Money → lien de paiement envoyé avec instructions. Bouton ← Annuler disponible.	Le token OAuth2 Orange est géré en interne (rafraîchi automatiquement). La vérification du paiement est faite via webhook. En cas d'indisponibilité du service Orange, message avec suggestion d'un autre provider.
Paiement Wave	Pour les paiements Wave CI/SN. L'utilisateur est redirigé vers l'interface Wave pour compléter le paiement.	Bouton 🌊 Payer avec Wave → lien Wave envoyé. Bouton ← Annuler disponible.	La confirmation de paiement est reçue par webhook avec vérification HMAC. Idempotence garantie : un paiement Wave confirmé deux fois ne crée pas deux confirmations de commande.
Confirmation de commande	Après paiement confirmé, notification Telegram automatique avec récapitulatif complet : numéro de commande, liste des articles, montant total, provider de paiement utilisé.	Notification avec boutons : 📦 Suivre ma commande · 🎧 Contacter le support.	La notification est envoyée avec retry automatique en cas d'échec. Si l'utilisateur a bloqué le bot, l'erreur est loguée sans crash.

4.3 Suivi des Commandes
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Mes commandes	Liste de toutes les commandes de l'utilisateur avec statut coloré, numéro, date et montant total. Accès depuis le menu Commerce.	Menu Commerce → 📦 Mes commandes → liste paginée. Bouton [Voir →] par commande. Navigation pagination.	Les statuts sont traduits dans la langue de l'utilisateur. Code couleur : 🟡 En attente · 🔵 Payée · 🟠 En préparation · 🟣 Expédiée · 🟢 Livrée · 🔴 Annulée.
Détail commande	Page de détail d'une commande : articles commandés avec photos miniatures, adresse de livraison, provider de paiement, numéro de suivi si disponible, historique des changements de statut.	Boutons selon le statut : 🚚 Suivre le colis (si numéro de suivi disponible) · 🎧 Support · ❌ Annuler la commande (si statut le permet) · ← Retour.	L'annulation n'est possible que si la commande est au statut "Payée" ou "En préparation". Au-delà, seul le support peut intervenir.
Notifications de statut	À chaque changement de statut d'une commande (préparation → expédiée → livrée), l'utilisateur reçoit une notification Telegram automatique avec les détails mis à jour.	Notifications automatiques avec boutons contextuels selon le statut.	Notifications désactivables depuis les préférences. Le numéro de suivi est inclus dans la notification d'expédition si disponible.
Annuler une commande	L'utilisateur peut annuler une commande en cours avant expédition. Une confirmation est requise. Le remboursement est initié automatiquement via le provider de paiement utilisé.	Bouton ❌ Annuler la commande → confirmation avec récapitulatif du montant à rembourser + boutons Confirmer l'annulation / ← Revenir.	Annulation impossible si la commande est déjà expédiée. Le remboursement Stripe est traité sous 5-10 jours ouvrés. Orange Money et Wave selon leurs délais respectifs. Notification de confirmation du remboursement envoyée.


5. Module Communauté & Groupes
👥 Communauté — Sondages · Karma · Modération · Annonces · Bienvenue · Classements

Les fonctions communauté sont disponibles en chat privé (gestion) et actives automatiquement dans les groupes Telegram où Orbi est ajouté comme administrateur. La modération automatique ne s'active que si Orbi a les droits admin dans le groupe.

5.1 Sondages & Votes
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Créer un sondage	L'administrateur crée un sondage interactif via le menu Communauté. Il saisit la question, puis les options une par une. Il peut configurer l'anonymat des votes et une durée de fermeture automatique.	Menu Communauté → 📊 Créer un sondage → saisie question → saisie options (bouton + Ajouter une option · ✅ Terminer la création) → paramètres (anonyme/public, durée) → Publier.	Minimum 2 options, maximum 8. Question : maximum 255 caractères. Options : maximum 100 caractères chacune. Durée : 1h, 6h, 24h, 7j ou personnalisée.
Voter à un sondage	Les membres votent en cliquant sur un bouton inline sous le sondage. Les résultats s'affichent en temps réel sur les boutons (pourcentage et nombre de votes).	Boutons inline dynamiques sur le message du sondage. Exemple : "Option A ✅ 45% (9)" · "Option B 33% (6)" · "Option C 22% (4)". Bouton 📊 Voir les résultats complets.	Un seul vote par utilisateur. Le vote peut être changé en cliquant sur une autre option. En mode anonyme, les noms des votants ne sont pas affichés dans les résultats. Vote impossible après fermeture.
Fermeture et résultats	Un sondage peut être fermé manuellement par son créateur ou automatiquement à l'expiration du timer. Un message de résultats finaux est envoyé dans le groupe.	Bouton 🔒 Fermer le sondage (pour le créateur seulement). Message de résultats automatique avec graphique textuel des pourcentages.	Après fermeture, les boutons de vote disparaissent et seuls les résultats restent affichés. Les résultats sont archivés et consultables depuis le menu Communauté.

5.2 Système Karma
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Donner du karma	Les membres peuvent attribuer un point de karma à un autre membre en réponse à un message jugé utile, via une commande courte ou un bouton réaction configurable.	Bouton ⭐ +Karma disponible sur chaque message (configurable par l'admin groupe) ou via répondre à un message avec "+karma".	Maximum 3 karma donnés par utilisateur par jour, réinitialisé à minuit UTC. L'auto-attribution est détectée et refusée silencieusement. Les bots ne peuvent pas recevoir de karma.
Classement hebdomadaire	Chaque lundi matin à 9h UTC, Orbi publie automatiquement le classement des 10 membres ayant reçu le plus de karma dans la semaine écoulée.	Message automatique dans le groupe avec 🥇🥈🥉 et points. Bouton 📊 Voir le classement complet.	Le classement est calculé sur les 7 derniers jours glissants. En cas d'égalité, le membre le plus ancien dans le groupe est classé premier.
Solde karma	Chaque utilisateur peut consulter son solde total de karma et son historique depuis son profil.	Menu Mon Profil → 📊 Mes statistiques → affichage karma total et rang dans le groupe.	Le karma est attaché à un groupe spécifique si utilisé en groupe. En chat privé, c'est un karma global Orbi.

5.3 Modération
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Modération automatique spam	Détection automatique de comportements abusifs : messages identiques répétés (3 messages identiques en 10 secondes), flood (10 messages en 30 secondes), liens non autorisés, mentions excessives (plus de 5 mentions par message).	Invisible pour l'utilisateur normal. L'action se déclenche automatiquement. Un message d'avertissement est envoyé à l'utilisateur concerné dans la langue du groupe.	La chaîne de sanctions progresse : 1er avertissement → message, 2ème avertissement → message renforcé, 3ème → mute 1 heure, 4ème → ban. Chaque action est loguée avec la raison.
Avertissement manuel	Un administrateur peut émettre un avertissement manuel contre un membre avec une raison explicite. L'utilisateur est notifié en privé avec la raison.	Commande admin → ou bouton contextuel sur un message → ⚠️ Avertir · raison · Confirmer.	L'historique des avertissements est consultable par les admins. Les avertissements expirent après 30 jours d'inactivité.
Mute	Silencer temporairement un membre pour une durée configurable. Le membre ne peut plus envoyer de messages dans le groupe pendant la durée du mute.	Bouton admin 🔇 Mute → saisie durée (ou boutons : 1h · 6h · 24h · 7j · Personnalisée) · raison → Confirmer.	Le membre est notifié en privé de son mute avec la durée et la raison. Le mute se lève automatiquement à l'expiration. Un admin peut lever le mute manuellement.
Ban et Unban	Exclure définitivement un membre du groupe. L'admin peut également débannir un utilisateur.	Bouton admin 🚫 Bannir → raison → Confirmer. Pour unban : menu admin → 🔓 Débannir → saisie username ou ID.	Le ban est enregistré en base avec l'admin responsable, la raison et la date. Un ban peut être global (bot entier) ou limité à un groupe spécifique.
Logs de modération	Historique complet de toutes les actions de modération dans un groupe, consultable par les admins depuis le dashboard ou le bot.	Menu admin Communauté → 📋 Logs modération → liste chronologique avec filtres (type d'action, membre, admin).	Les logs sont conservés 90 jours. Exportables en CSV depuis le dashboard admin web.

5.4 Annonces & Communication
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Annonces groupes	Les administrateurs Orbi peuvent envoyer une annonce vers un ou plusieurs groupes où Orbi est actif. L'annonce est rédigée depuis le dashboard web ou via le menu admin du bot.	Menu admin → 📢 Nouvelle annonce → rédaction FR/EN/AR → sélection groupes cibles → Planifier / Envoyer maintenant.	Supporte le formatage HTML (gras, italique, lien, code). Une annonce planifiée dans le passé est refusée. Accusé de livraison par groupe.
Message de bienvenue	Pour chaque groupe, un message de bienvenue personnalisé est envoyé automatiquement aux nouveaux membres. Le template est configurable par groupe depuis le dashboard.	Automatique, invisible pour les admins après configuration. Variables disponibles dans le template : {name}, {group}, {rules_link}, {member_count}.	Le message de bienvenue est supprimé automatiquement après 5 minutes pour ne pas polluer le groupe. Si Orbi n'a pas les droits de suppression, le message reste.
Règles du groupe	Les admins peuvent définir les règles du groupe, affichables à la demande par n'importe quel membre.	Bouton 📋 Règles du groupe disponible dans le menu Communauté et dans le message de bienvenue.	Les règles sont configurables depuis le dashboard admin. Longueur maximale : 2000 caractères. Supportent le formatage basique.


6. Module Productivité & Outils
⚡ Productivité — Tâches · Rappels · Notes · Traduction · Devises · Brief · Outils

Toutes les données de productivité sont strictement personnelles — un utilisateur ne voit que ses propres tâches, notes et rappels. Aucun partage entre utilisateurs.

6.1 Tâches & Rappels
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Créer une tâche	L'utilisateur crée une tâche avec un titre, une description optionnelle et une date d'échéance optionnelle. La date est saisie en langage naturel dans la langue de l'utilisateur.	Menu Productivité → ✅ Nouvelle tâche → saisie titre → saisie date (optionnel, avec exemples : "demain", "lundi prochain", "25/04") → saisie description (optionnel) → Confirmer.	Maximum 50 tâches actives par utilisateur. Formats de date compris en FR : "demain", "lundi", "dans 3 jours", "25 avril". EN : "tomorrow", "next monday". AR : "غداً". Tâche sans date = pas de rappel automatique.
Liste des tâches	Affichage de toutes les tâches actives de l'utilisateur, organisées par date d'échéance. Les tâches en retard sont affichées en premier avec un indicateur visuel.	Menu Productivité → 📋 Mes tâches → liste avec bouton ✅ Terminer par tâche. Boutons filtres : Toutes · En retard · Aujourd'hui · Cette semaine.	Les tâches terminées disparaissent de la liste principale. Elles sont archivées et consultables via "Tâches terminées". Les tâches en retard ont un indicateur 🔴.
Rappels automatiques	Si une tâche a une date d'échéance, deux rappels sont envoyés automatiquement : la veille à 20h (heure du fuseau de l'utilisateur) et le jour J à 9h.	Automatiques et invisibles. L'utilisateur reçoit des notifications avec boutons ✅ Marquer comme faite · 📅 Reporter · ← Fermer.	Les rappels respectent le fuseau horaire configuré dans le profil. Si l'utilisateur a désactivé les notifications de tâches, les rappels ne sont pas envoyés.
Rappels ponctuels	/remind ou via le menu : créer un rappel one-shot à une date et heure précises, sans créer de tâche.	Menu Productivité → ⏰ Nouveau rappel → saisie message → saisie date et heure.	Maximum 20 rappels actifs par utilisateur. Un rappel passé à la création est refusé avec suggestion. Après envoi du rappel, il est automatiquement supprimé.
Modifier / Supprimer une tâche	L'utilisateur peut modifier le titre, la description ou la date d'une tâche existante, ou la supprimer définitivement.	Depuis la liste des tâches → bouton ✏️ Modifier · 🗑️ Supprimer sur chaque tâche. Suppression avec confirmation.	La modification d'une tâche annule les rappels existants et en replanifie de nouveaux si une nouvelle date est définie.

6.2 Notes & Mémoire
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Créer une note	L'utilisateur crée une note textuelle avec un titre et un contenu. Les hashtags dans le contenu sont automatiquement extraits comme tags pour faciliter la recherche.	Menu Productivité → 📝 Nouvelle note → saisie titre → saisie contenu (texte ou vocal).	Notes illimitées. Les hashtags #tag sont extraits automatiquement. Les notes sont chiffrées au repos dans la base de données.
Note vocale → texte	L'utilisateur envoie un message vocal directement dans le chat. Orbi transcrit automatiquement l'audio en texte via Whisper et crée une note avec la transcription.	L'utilisateur envoie un message vocal → Orbi répond "🎤 Transcription en cours..." → Note créée avec la transcription + boutons ✏️ Modifier · 🗑️ Supprimer.	Durée maximum : 3 minutes. Langues reconnues : FR, EN, AR (détection automatique). Si le service de transcription est indisponible, message d'erreur explicatif avec la note non créée (pas de perte de données).
Consulter mes notes	Affichage des notes récentes de l'utilisateur avec titre, début du contenu et tags.	Menu Productivité → 📋 Mes notes → liste des 10 dernières notes. Navigation pagination. Bouton sur chaque note : 👁️ Lire · ✏️ Modifier · 🗑️ Supprimer.	La liste est triée par date de modification décroissante.
Recherche dans les notes	Recherche full-text dans le titre et le contenu de toutes ses notes. La recherche par tag (#tag) est également supportée.	Menu Productivité → 🔍 Rechercher dans mes notes → saisie terme.	Minimum 2 caractères pour déclencher la recherche. La recherche inclut le titre, le contenu et les tags. Si aucun résultat, message avec suggestion d'élargir la recherche.
Modifier une note	L'utilisateur peut modifier le titre ou le contenu d'une note existante.	Depuis la note → bouton ✏️ Modifier → choix : ✏️ Modifier le titre · ✏️ Modifier le contenu → saisie → Sauvegarder.	Les tags sont recalculés automatiquement après modification du contenu.

6.3 Outils Utilitaires
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Traduction rapide	Traduction de texte entre les trois langues du bot (FR, EN, AR). L'utilisateur envoie ou saisit un texte, choisit la langue cible, et reçoit la traduction. La langue source est détectée automatiquement.	Menu Productivité → 🌐 Traduire → saisie du texte → boutons langue cible : FR · EN · AR → résultat affiché avec bouton 📋 Copier.	Via LibreTranslate (auto-hébergé, open source, respect de la vie privée). Cache 1 heure sur les traductions identiques pour les termes fréquents. Si le service est indisponible, message d'erreur clair.
Conversion de devises	Conversion de montants entre devises. L'utilisateur saisit le montant et les devises, reçoit le taux et le montant converti. Affichage également des taux principaux.	Menu Productivité → 💱 Convertir des devises → saisie montant → boutons devise source → boutons devise cible → résultat avec taux.	Taux mis à jour toutes les heures via API (cache Redis). Devises supportées : USD, EUR, XOF, XAF, MAD, DZD, GBP, GHS, NGN, KES, et toutes les devises ISO 4217 majeures. Devise inconnue → liste des devises disponibles.
Calcul rapide	Calculatrice intégrée supportant les opérations de base et quelques fonctions mathématiques avancées.	Menu Productivité → 🧮 Calculatrice → saisie de l'expression (ex: "450 * 1.2 - 30") → résultat immédiat.	Opérations supportées : + - * / puissance, racine carrée, log, sin, cos, tan. Expressions limitées à 200 caractères. Les tentatives d'injection de code sont bloquées.
Heure dans le monde	L'utilisateur saisit le nom d'une ville et obtient l'heure locale actuelle dans cette ville, ainsi que le décalage avec son propre fuseau configuré.	Menu Productivité → 🌍 Heure dans le monde → saisie nom de ville → résultat.	Utilise les données de fuseau horaire IANA. Si la ville est ambiguë (plusieurs résultats), affiche une liste de sélection.
Morning Brief	Résumé quotidien personnalisé envoyé chaque matin à l'heure configurée par l'utilisateur. Contient : tâches du jour, rappels du jour, taux de change des devises favorites, optionnellement la météo.	Menu Mon Profil → 🌅 Morning Brief → toggle activer/désactiver · saisie heure · sélection devises à afficher.	Respecte le fuseau horaire du profil. Le brief est envoyé même si toutes les sources (taux, météo) ne sont pas disponibles — les sections indisponibles sont omises avec une note.


7. Module Développeurs
👨‍💻 Développeurs — API Keys · Webhooks · Sandbox · Logs · Documentation

Ce module est destiné aux développeurs et équipes techniques qui souhaitent intégrer Orbi dans leurs applications ou systèmes. Accessible via le menu principal → 👨‍💻 Développeurs. Les fonctionnalités sont en anglais technique mais les messages d'erreur restent localisés.

7.1 API Keys & Authentification
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Créer une API Key	Le développeur crée une clé API avec un nom descriptif, un environnement (production ou sandbox) et une sélection de scopes (permissions). La clé complète est affichée une seule et unique fois après création — elle ne peut jamais être récupérée.	Menu Développeurs → 🔑 Mes API Keys → ➕ Créer une clé → saisie nom → choix environnement (Production/Sandbox) → sélection scopes (cases à cocher) → Créer → affichage clé avec bouton 📋 Copier.	Maximum 10 clés actives par utilisateur. La clé est stockée uniquement sous forme de hash SHA256. Préfixe affiché pour identification : orbi_sk_prod_xxxx... Format des scopes listé ci-dessous.
Scopes disponibles	Les scopes définissent les permissions d'une clé API. Chaque endpoint vérifie le scope requis et retourne HTTP 403 avec la liste des scopes manquants si insuffisant.	Affichage lors de la création avec description de chaque scope : ✅ read:users · ✅ write:broadcast · ✅ manage:webhooks · ✅ read:orders · ✅ write:orders · ✅ read:analytics · ✅ sandbox.	Un scope mal défini lors de la création ne peut pas être modifié. Il faut révoquer la clé et en créer une nouvelle avec les bons scopes.
Lister ses clés	Vue de toutes les clés actives avec : nom, préfixe, environnement, scopes, date de création, dernière utilisation, compteur de requêtes.	Menu Développeurs → 🔑 Mes API Keys → liste des clés avec bouton [Détails →] par clé.	Seul le préfixe est affiché (pas la clé complète). Clé jamais utilisée depuis 90 jours → badge "Inutilisée".
Révoquer une clé	Le développeur peut désactiver définitivement une clé API. Les requêtes avec une clé révoquée reçoivent HTTP 401 immédiatement.	Depuis le détail d'une clé → 🗑️ Révoquer cette clé → confirmation → clé désactivée.	La révocation est immédiate et irréversible. La clé reste visible dans la liste avec le statut "Révoquée" pendant 30 jours pour référence.
Rate limiting par clé	Chaque clé a une limite de requêtes par minute configurable. Les headers de réponse indiquent la limite, le quota restant et le temps de reset.	Menu Développeurs → 🔑 Mes API Keys → Détails d'une clé → ⚙️ Configurer le rate limit → saisie valeur (req/min).	Valeur par défaut : 60 req/min en production, 120 req/min en sandbox. Dépassement → HTTP 429 avec header Retry-After. En cas de dépassement extrême (1000 req/min pendant 5 min), suspension temporaire automatique.

7.2 Webhooks Sortants
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Créer un webhook	Le développeur enregistre une URL externe à notifier lors d'événements Orbi spécifiques. Il configure un secret pour vérifier les signatures, et sélectionne les événements à écouter.	Menu Développeurs → 🔗 Mes Webhooks → ➕ Créer un webhook → saisie nom → saisie URL → saisie secret → sélection événements (cases à cocher) → Créer.	URL doit être HTTPS en production. Un test de connectivité est effectué à la création (ping). Si l'URL est inaccessible, avertissement mais création autorisée. Maximum 10 webhooks actifs par utilisateur.
Événements disponibles	Liste complète des événements pour lesquels un webhook peut être déclenché.	Affichage lors de la sélection : order.paid · order.shipped · order.cancelled · order.refunded · ticket.created · ticket.resolved · ticket.closed · user.banned · broadcast.sent · product.out_of_stock.	Chaque événement est décrit avec le payload JSON type qu'il envoie. La documentation auto-générée (Swagger) détaille chaque payload.
Livraison des webhooks	Pour chaque événement, Orbi envoie un POST HTTP vers l'URL avec le payload JSON signé. La signature est dans le header X-Orbi-Signature (HMAC SHA256 du body avec le secret).	Invisible pour le développeur côté bot. Consultable dans les logs webhooks.	5 tentatives de livraison avec délais exponentiels : immédiat, 1 min, 5 min, 15 min, 1h. 5xx → retry. 4xx → pas de retry. Timeout : 30 secondes par tentative. 10 échecs consécutifs → désactivation automatique du webhook + notification Telegram au développeur.
Tester un webhook	Le développeur peut envoyer un payload de test vers son webhook pour vérifier que sa configuration de réception fonctionne correctement.	Menu Développeurs → 🔗 Mes Webhooks → sélectionner webhook → 🧪 Envoyer un test → choix de l'événement à simuler → résultat affiché (code HTTP reçu, durée).	Le payload de test est clairement marqué comme test (champ "is_test": true). La livraison de test ne compte pas dans le compteur d'échecs.
Logs des webhooks	Historique des 100 dernières tentatives de livraison par webhook avec : date, événement, code HTTP reçu, durée, statut (succès/échec).	Menu Développeurs → 🔗 Mes Webhooks → Détails → 📋 Voir les logs.	Logs conservés 30 jours. Exportables en CSV depuis le dashboard admin. Le payload envoyé et la réponse reçue sont consultables pour chaque tentative.
Activer / Désactiver	Le développeur peut activer ou désactiver un webhook sans le supprimer.	Depuis la liste des webhooks → toggle ✅/❌ par webhook.	Un webhook désactivé ne reçoit aucune livraison. Les événements qui se produisent pendant la désactivation ne sont pas rattrappés.

7.3 Mode Sandbox
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Environnement sandbox	Un environnement de test complètement isolé de la production. Toutes les opérations effectuées avec une clé sandbox (scope: sandbox) utilisent des données de test séparées et n'affectent jamais les données réelles.	Menu Développeurs → 🧪 Sandbox → vue des données sandbox (commandes, users de test). Bouton 🗑️ Réinitialiser le sandbox.	Les données sandbox sont clairement identifiées (flag is_sandbox=true). Un utilisateur normal ne voit jamais les données sandbox. Une clé sandbox utilisée sur un endpoint de production retourne HTTP 403 explicite.
Commandes sandbox automatiques	En mode sandbox, les commandes créées progressent automatiquement à travers tous les statuts pour simuler le cycle complet, sans intervention humaine.	Après création d'une commande sandbox → les statuts changent automatiquement toutes les 30 secondes : pending_payment → paid → processing → shipped → delivered. Chaque transition déclenche les webhooks configurés.	Le développeur peut aussi faire progresser manuellement une commande sandbox via un bouton dédié pour tester des statuts spécifiques.
Paiements sandbox	En mode sandbox, les paiements Stripe acceptent les numéros de carte de test Stripe. Les paiements Orange Money et Wave sont simulés sans appels réels aux APIs de paiement.	Formulaire de paiement sandbox avec numéros de test pré-remplis pour chaque provider.	Aucun débit réel n'est possible depuis le sandbox. Les webhooks de paiement sandbox sont envoyés vers les webhooks configurés pour permettre les tests end-to-end.
Réinitialiser le sandbox	Le développeur peut supprimer toutes ses données sandbox d'un seul coup pour repartir proprement.	Menu Développeurs → 🧪 Sandbox → 🗑️ Réinitialiser → confirmation → toutes les données sandbox du compte supprimées.	Irreversible. Ne supprime pas les clés API ni les webhooks. Ne touche pas aux données de production.

7.4 Logs & Monitoring
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Logs des requêtes API	Historique des 100 dernières requêtes API effectuées avec les clés de l'utilisateur : méthode, endpoint, code HTTP, durée, timestamp, clé utilisée.	Menu Développeurs → 📊 Logs API → liste chronologique. Filtres : code HTTP (2xx/4xx/5xx) · endpoint · clé · période.	Logs conservés 30 jours. Le corps des requêtes et réponses n'est pas loggué en production pour des raisons de confidentialité (seulement les métadonnées). En sandbox, le corps complet est loggué.
Statistiques d'utilisation	Vue synthétique de l'utilisation de l'API : requêtes totales par jour, répartition par endpoint, taux d'erreur, latence moyenne.	Menu Développeurs → 📈 Statistiques → graphiques sur 7j/30j.	Données agrégées, pas de données personnelles. Mise à jour toutes les heures.
Documentation API	Documentation interactive de l'API REST Orbi, auto-générée par FastAPI. Inclut tous les endpoints, les paramètres, les exemples de requêtes et réponses, et les codes d'erreur.	Menu Développeurs → 📖 Documentation API → lien vers /docs (Swagger UI) et /redoc (ReDoc).	La documentation liste explicitement les scopes requis pour chaque endpoint. En production, l'accès à la documentation peut être restreint par authentification basique (configurable).


8. Administration & Dashboard Web
⚙️ Admin — Dashboard · Utilisateurs · Tickets · Commandes · Analytics · Config

Le dashboard admin est une interface web accessible depuis navigateur. Il est distinct du bot Telegram mais utilise la même base de données. Authentification par JWT avec session cookie sécurisé.

8.1 Pages du Dashboard
Fonctionnalité	Description détaillée	UX — Navigation Boutons	Règles & Contraintes
Accueil & KPIs	/admin/ — Vue d'ensemble en temps réel avec les indicateurs clés : utilisateurs actifs (24h et 7j), messages traités aujourd'hui, tickets ouverts/résolus, revenus du jour et des 7 derniers jours, score CSAT moyen, graphique d'activité sur 30 jours (Chart.js).	Boutons de navigation vers chaque section. Indicateurs cliquables pour accéder au détail. Refresh automatique toutes les 60 secondes.	En cas d'erreur DB, les dernières valeurs cachées sont affichées avec un badge "Données potentiellement périmées".
Gestion Utilisateurs	/admin/users — Table paginée de tous les utilisateurs avec : prénom, username, langue, rôle, statut (actif/banni), date d'inscription, nombre de commandes et tickets.	Recherche full-text. Filtres : langue, rôle, statut. Actions par utilisateur : Voir profil complet · Ban/Unban (avec raison) · Changer rôle · Exporter CSV.	Export CSV limité à 10 000 lignes par batch. Ban d'un admin nécessite le rôle superadmin. Actions loguées avec l'identité de l'admin.
Centre de Support	/admin/tickets — File de tous les tickets organisés par statut avec indicateur SLA coloré (vert = dans les temps, orange = proche limite, rouge = dépassé). Assignation des tickets aux agents.	Filtres : statut, priorité, agent assigné, date, catégorie. Par ticket : Répondre (éditeur inline) · Changer statut · Changer priorité · Assigner · Voir historique complet.	Réponse rapide avec templates multilingues. La réponse est envoyée via Telegram au client en temps réel. SLA dépassé → badge rouge + alerte sonore.
Gestion Commandes	/admin/orders — Liste de toutes les commandes avec statut, provider de paiement, montant, date.	Filtres : statut, provider paiement, date, montant. Par commande : Voir détail · Changer statut · Envoyer notification manuelle · Initier remboursement (Stripe) · Exporter.	Remboursement Stripe impossible si >30 jours (message d'erreur Stripe remonté). Changements de statut déclenchent les webhooks développeurs configurés.
Catalogue Produits	/admin/products — Grille des produits avec photo miniature, stock, prix, statut actif.	Actions : ➕ Nouveau produit · ✏️ Modifier · 🗑️ Supprimer · Activer/Désactiver. Formulaire de création/modification avec upload image, saisie nom/description en FR/EN/AR, prix, stock.	Stock ne peut pas être négatif. Prix doit être > 0. La photo est envoyée au bot Telegram qui la stocke et retourne un file_id permanent.
Broadcasts	/admin/broadcasts — Historique des broadcasts avec stats : envoyés/lus/échoués.	Créer : éditeur de texte riche FR/EN/AR · ciblage (tous, par langue, par rôle) · planification (datetime) · aperçu avant envoi.	Broadcast dans le passé refusé. Envoi en masse respecte le rate limit Telegram (30 messages/seconde via queue). Broadcast planifié annulable jusqu'à 5 minutes avant l'heure.
Analytics	/admin/analytics — Tableaux de bord avec graphiques Chart.js : croissance des utilisateurs, volume de messages, tunnel de conversion commerce (vues → panier → achat), revenus par provider, satisfaction CSAT.	Sélecteur de période : 7j, 30j, 90j, personnalisée. Comparaison N vs N-1. Export CSV des données brutes.	Données agrégées par jour. Pas de données personnelles dans les exports.
Modération	/admin/moderation — Logs de toutes les actions de modération, liste des utilisateurs bannis/mutés, avertissements actifs.	Filtres par groupe, type d'action, admin responsable. Actions : Débannir · Annuler un warn · Configurer les seuils d'auto-modération.	Annuler un warn d'un autre admin nécessite le rôle superadmin.
Développeurs (vue admin)	/admin/developer — Vue superadmin de toutes les clés API et webhooks créés par les utilisateurs, avec statistiques d'utilisation globales.	Désactiver une clé abusive · Voir les logs d'erreurs · Statistiques d'utilisation par endpoint.	Accessible uniquement au rôle superadmin.
Configuration	/admin/config — Paramètres globaux du bot : SLA par priorité, rate limits, messages de bienvenue par défaut, intégrations activées/désactivées.	Formulaires d'édition pour chaque paramètre. Bouton Tester la connexion pour chaque service externe (Stripe, Orange Money, Wave, LibreTranslate).	Chaque modification de configuration est loguée avec l'identité de l'admin et la valeur précédente. Changements critiques demandent une confirmation.


9. API REST — Référence Complète
L'API REST est consommée par le dashboard admin (JWT Bearer) et par les développeurs tiers (API Key avec scopes). Chaque endpoint précise le mode d'authentification requis.

9.1 Webhooks Entrants
POST /webhook/telegram	Reçoit les updates Telegram. Vérifie le header X-Telegram-Bot-Api-Secret-Token. Délègue au moteur python-telegram-bot. Retourne HTTP 200 immédiatement.
POST /webhook/payment/stripe	Reçoit les événements Stripe. Vérifie la signature HMAC du header stripe-signature. Traite checkout.session.completed pour confirmer les commandes.
POST /webhook/payment/orange	Reçoit les notifications Orange Money. Vérifie le hash MD5. Confirme les commandes payées.
POST /webhook/payment/wave	Reçoit les notifications Wave. Vérifie la signature HMAC SHA256. Confirme les commandes payées.

9.2 Endpoints Administration (Auth: JWT)
GET /api/v1/users	Liste paginée. Params: page, limit, lang, role, is_banned, search.
GET /api/v1/users/{id}	Profil complet + statistiques de l'utilisateur.
PATCH /api/v1/users/{id}	Modifier : language, role, is_banned, ban_reason.
GET /api/v1/tickets	Liste filtrée. Params: status, priority, assigned_to, date_from, date_to.
POST /api/v1/tickets/{id}/reply	Envoyer une réponse agent. Notifie l'utilisateur via Telegram immédiatement.
PATCH /api/v1/tickets/{id}	Modifier statut, priorité, assignation.
GET /api/v1/orders	Liste filtrée. Params: status, provider, date_from, date_to, user_id.
PATCH /api/v1/orders/{id}	Modifier statut. Déclenche webhooks développeurs et notification Telegram.
GET /api/v1/products	Liste catalogue complète avec stock.
POST /api/v1/products	Créer un produit. Body multipart avec image.
PATCH /api/v1/products/{id}	Modifier un produit. Activer/désactiver.
DELETE /api/v1/products/{id}	Désactiver définitivement un produit (soft delete).
POST /api/v1/broadcast	Envoyer un broadcast. Body: {message_fr, message_en, message_ar, target_lang, target_role, scheduled_at?}.
GET /api/v1/analytics/dashboard	KPIs 7j : users actifs, messages, tickets, revenus, CSAT.
GET /api/v1/analytics/funnel	Tunnel de conversion commerce.
GET /api/v1/analytics/revenue	Revenus par période, provider, devise.

9.3 Endpoints Développeurs (Auth: API Key + Scope)
GET /api/v1/dev/keys	Lister ses clés API (préfixes seulement). Auth: JWT.
POST /api/v1/dev/keys	Créer une API Key. Body: {name, environment, scopes[]}. La clé est retournée UNE SEULE FOIS.
DELETE /api/v1/dev/keys/{prefix}	Révoquer une clé. Auth: JWT.
GET /api/v1/dev/webhooks	Lister ses webhooks. Auth: JWT.
POST /api/v1/dev/webhooks	Créer un webhook. Body: {name, url, secret, events[]}. Auth: JWT.
POST /api/v1/dev/webhooks/{id}/test	Envoyer un payload de test. Auth: JWT.
DELETE /api/v1/dev/webhooks/{id}	Supprimer un webhook. Auth: JWT.
GET /api/v1/dev/logs	Logs des 100 dernières requêtes API. Filtres: status, endpoint. Auth: JWT.
GET /api/v1/dev/sandbox/orders	Lister les commandes sandbox. Auth: API Key scope:sandbox.
POST /api/v1/dev/sandbox/orders/{id}/advance	Avancer manuellement le statut d'une commande sandbox. Auth: API Key scope:sandbox.
DELETE /api/v1/dev/sandbox/reset	Réinitialiser toutes les données sandbox du compte. Auth: JWT.
GET /health	Health check : DB, Redis, Bot. HTTP 200 si OK, 503 sinon. Public.
GET /metrics	Métriques Prometheus. Accès restreint réseau interne.
GET /docs	Swagger UI auto-générée. Protégé en production.
GET /redoc	ReDoc auto-générée.


10. Infrastructure & Déploiement
10.1 Services
Bot Telegram	Process python-telegram-bot v21 en mode polling (dev) ou webhook (prod). Un seul process, async natif.
API FastAPI	Process Uvicorn avec 2 workers en production. Sert les webhooks entrants, l'API REST et le dashboard admin.
MongoDB 7	Base de données principale. Données persistantes : utilisateurs, tickets, commandes, produits, notes, tâches, clés API, webhooks, logs.
Redis 7	Cache (langues, taux de change, traductions, catalogue), sessions de conversation (ConversationHandler), rate limiting (sliding window), file d'attente notifications, panier (TTL 2h).
LibreTranslate	Service de traduction auto-hébergé, open source. Langues chargées : FR, EN, AR uniquement pour optimiser la mémoire.
APScheduler	Scheduler intégré au process bot pour : vérification SLA toutes les 5 min, morning briefs, rappels tâches, classements karma hebdomadaires, CSAT 24h après résolution.

10.2 Variables d'Environnement Requises
TELEGRAM_BOT_TOKEN	Token BotFather. Obligatoire.
TELEGRAM_WEBHOOK_URL	URL HTTPS publique en production (ex: https://orbi.example.com).
TELEGRAM_WEBHOOK_SECRET	Secret arbitraire pour vérifier les updates Telegram.
ADMIN_CHAT_ID	ID du canal/groupe Telegram pour les alertes système admin.
MONGODB_URI	URI de connexion MongoDB.
MONGODB_DB	Nom de la base de données (ex: orbi_prod).
REDIS_URL	URL de connexion Redis.
JWT_SECRET	Clé secrète longue et aléatoire pour les tokens JWT admin.
STRIPE_SECRET_KEY	Clé API Stripe (sk_live_... ou sk_test_... pour les tests).
STRIPE_WEBHOOK_SECRET	Secret de signature webhook Stripe (whsec_...).
ORANGE_MONEY_API_KEY	Clé API Orange Money West Africa.
ORANGE_MONEY_API_SECRET	Secret Orange Money pour la vérification des webhooks.
ORANGE_MONEY_MERCHANT_ID	ID marchand Orange Money.
WAVE_API_KEY	Clé API Wave.
WAVE_WEBHOOK_SECRET	Secret HMAC pour la vérification des webhooks Wave.
OPENAI_API_KEY	Clé OpenAI pour la transcription vocale Whisper.
EXCHANGE_RATES_API_KEY	Clé pour l'API de taux de change.
BASE_URL	URL publique complète du serveur (ex: https://orbi.example.com).
ENVIRONMENT	production · staging · development


11. Guide de Construction — Antigravity
Règle absolue : chaque fonctionnalité demandée doit être complète, traduite en FR/EN/AR, avec gestion de tous les cas d'erreur listés dans ce CdC. Aucune fonctionnalité placeholder, aucun "TODO", aucun "à implémenter plus tard".

11.1 Ordre de Construction
1.Phase 0 — Fondations : structure du projet, config, MongoDB/Beanie, Redis, Docker.
2.Phase 1 — Middlewares : i18n (détection langue + t()), auth (rôles + ban), rate limiting, logging structuré.
3.Phase 2 — Modèles : tous les modèles Beanie (User, Ticket, Product, Order, Poll, Task, Note, ApiKey, WebhookConfig).
4.Phase 3 — Onboarding & Navigation : /start, sélecteur langue, menu principal 5 modules, profil utilisateur.
5.Phase 4 — Module Support : création ticket, ConversationHandler guidé, SLA, escalade, CSAT, alertes APScheduler.
6.Phase 5 — Module Commerce : catalogue paginé, panier Redis, checkout, Stripe + Orange Money + Wave, notifications.
7.Phase 6 — Module Communauté : sondages, karma, modération auto + manuelle, annonces, bienvenue.
8.Phase 7 — Module Productivité : tâches + rappels APScheduler, notes + Whisper, traduction LibreTranslate, outils.
9.Phase 8 — Module Développeurs : API Keys, webhooks sortants avec retry, sandbox, logs, rate limit par clé.
10.Phase 9 — API REST FastAPI : tous les endpoints admin + dev, JWT auth, API Key auth, Prometheus.
11.Phase 10 — Dashboard Admin : 10 pages Jinja2/Bootstrap 5, auth cookie JWT, Chart.js.
12.Phase 11 — Tests : services (80%+ couverture), handlers critiques, API endpoints.
13.Phase 12 — Déploiement : docker-compose production, registration webhook Telegram, checklist pre-prod.

11.2 Prompts Antigravity — Un par Phase
Chaque prompt doit référencer la section du CdC correspondante et demander l'implémentation COMPLÈTE avec tous les cas d'erreur listés dans les tableaux de fonctionnalités.

Format de prompt recommandé pour chaque phase :
Implémente [Phase X] du projet Orbi selon la section [N] du CdC v4. La fonctionnalité doit être complète : handlers + services + modèles + traductions FR/EN/AR dans locales/. La navigation est 100% boutons inline (aucune commande textuelle requise de l'utilisateur). Chaque cas d'erreur listé dans les tableaux de fonctionnalités doit être géré explicitement avec un message localisé. Les timeouts de session sont à 30 minutes avec message d'information. Fournis également les tests pytest-asyncio pour les services créés.

11.3 Points de Vigilance pour Antigravity
•Navigation boutons : vérifier que CHAQUE action est accessible via un bouton inline. Aucune commande textuelle requise de l'utilisateur dans les flux normaux.
•Traductions : vérifier que chaque chaîne visible (message, bouton label, message d'erreur, notification) a sa clé dans fr.yml, en.yml et ar.yml.
•Idempotence : vérifier que les opérations de paiement et de création de commande sont protégées contre les doubles soumissions.
•Robustesse services externes : chaque appel HTTP vers Stripe, Orange Money, Wave, Whisper, LibreTranslate, et l'API de taux de change doit avoir un timeout et une gestion d'erreur explicite.
•Retry notifications : le service de notification doit gérer les RetryAfter de l'API Telegram sans crasher.
•Désactivation auto webhooks : 10 échecs consécutifs → désactivation automatique + notification Telegram au développeur.
•Clés API : la clé n'est jamais stockée en clair — uniquement son hash SHA256. Elle est affichée une seule fois.
•Sandbox isolation : données sandbox jamais visibles par les utilisateurs normaux.
•Rate limit sliding window : implémenté avec Redis sorted sets, pas avec des compteurs simples.
•Morning brief partial : si une source de données est indisponible, le brief s'envoie quand même sans cette section.


ORBI — Cahier des Charges v4.0 — Produit Complet — 5 Modules — Mars 2026