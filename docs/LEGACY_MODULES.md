# Orbi — Inventaire des modules historiques

> **Statut :** inventaire initial à compléter  
> **But :** décider sur des preuves, et non par intuition, du sort des modules construits autour du bot Telegram.

## Légende

- **À auditer** : présence du code confirmée, comportement réel non validé.
- **Conserver** : décision prise après évaluation, pas simplement parce que le code existe.
- **Refactoriser** : valeur confirmée, qualité ou architecture à améliorer.
- **Isoler** : utile mais ne doit pas coupler le nouveau noyau.
- **Déprécier** : fonction maintenue temporairement avec trajectoire de retrait.
- **Retirer** : retrait décidé avec vérification des dépendances et migration si nécessaire.

## Inventaire initial

| Module | Emplacements repérés | État initial | Questions à trancher |
|---|---|---|---|
| Bot Telegram / onboarding | `src/bot/`, `src/handlers/onboarding.py`, `src/handlers/menu.py` | À auditer | Telegram reste-t-il une interface principale, un connecteur ou un canal optionnel ? |
| Utilisateurs / profils | `src/models/user.py`, `src/handlers/profile.py`, `src/bot/middlewares/auth.py` | À auditer | Peut-on séparer identité plateforme et identité Telegram sans casser les comptes existants ? |
| Support / tickets / SLA / CSAT | `src/models/ticket.py`, `src/services/ticket_service.py`, `src/handlers/support.py` | À auditer | Est-ce un module métier Orbi à conserver ou un cas d'usage optionnel ? |
| Commerce / catalogue / commandes | `src/models/commerce.py`, `src/services/commerce_service.py`, `src/services/cart_service.py`, `src/handlers/commerce.py` | À auditer | La boutique fait-elle partie du produit cible ou doit-elle rester isolée ? |
| Paiements | `src/services/payment_service.py`, routes dans `src/main.py` | À auditer, sécurité prioritaire | Signatures, idempotence, devise/montant, rapprochement et statut de production ? |
| Communauté / sondages / karma / modération | `src/models/community.py`, `src/services/community_service.py`, `src/handlers/community.py` | À auditer | Cohérence avec les utilisateurs cibles et charge de maintenance ? |
| Productivité / notes / rappels / tâches | `src/models/productivity.py`, `src/services/productivity_service.py`, `src/handlers/productivity.py` | À auditer | Fonctionnalités personnelles à conserver dans le même produit ou à isoler ? |
| API développeur / clés / logs | `src/models/developer.py`, `src/services/developer_service.py`, `src/api/dev.py`, `src/handlers/developer.py` | À auditer, auth prioritaire | Quelles routes sont réellement protégées ? Quelles capacités peuvent être réutilisées pour le nouveau noyau ? |
| Webhooks GitHub | `src/services/developer_service.py`, routes dans `src/main.py` | À auditer, sécurité prioritaire | Signature, secret obligatoire, anti-rejeu, filtrage des événements et limites ? |
| Dashboard admin | `src/web/`, `src/templates/`, `src/api/admin.py` | À auditer, auth prioritaire | Auth réelle, permissions, CSRF, fuite de données et actions privilégiées ? |
| Internationalisation FR/EN/AR | `src/core/i18n.py`, `src/locales/` | À auditer | Garder le support multilingue sur la future interface web/mobile ? |
| Scheduler / notifications | `src/services/scheduler.py`, `src/services/notification_service.py` | À auditer | Fonctionnement multi-instance, doublons, durabilité et préférences ? |
| Infrastructure / cache | `src/core/database.py`, `src/core/redis.py`, `src/core/performance.py` | À auditer | Durabilité, index, shutdown, exposition réseau et responsabilités cache/queue ? |

## Fiche de décision par module

Pour chaque ligne, compléter :

### [Nom du module]

- **Utilisateur et valeur :**
- **Fonctionnalités revendiquées :**
- **Preuves dans le code :**
- **Tests exécutés et résultats :**
- **Dépendances entrantes/sortantes :**
- **Risques de sécurité :**
- **Coût de maintenance estimé :** faible / moyen / élevé, avec justification.
- **Décision :** conserver / refactoriser / isoler / déprécier / retirer.
- **Raison :**
- **Compatibilité et migration :**
- **Critères d'acceptation :**
- **Responsable et statut :**

## Règles de décision

1. Le README et le cahier des charges prouvent une intention, pas une implémentation fonctionnelle.
2. Un test qui utilise des mocks ne prouve pas le contrat d'un fournisseur réel.
3. Une fonction dangereuse ne doit pas rester active uniquement pour préserver la compatibilité.
4. Un module qui n'appartient pas au premier MVP peut rester isolé sans être supprimé immédiatement.
5. Une migration des identités, commandes ou paiements doit protéger l'intégrité des données existantes.
6. Aucun statut « terminé » sans preuve de test ou validation manuelle documentée.
