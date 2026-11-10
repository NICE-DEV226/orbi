"""
Orbi Dev — Migrations de données idempotentes, exécutées au démarrage (scripts/init_db.py).

Avant la migration vers Beanie 2, le texte chiffré d'une clé était stocké dans le document `Integration`
(champ `secret_ciphertext`). Il vit désormais dans `IntegrationSecret` ; cette migration déplace les anciennes
valeurs puis supprime le champ, afin qu'aucun secret ne reste dans un document exposé ni après une révocation.
"""

import logging
import re
from datetime import UTC, datetime

from pymongo import ASCENDING

from src.orbi_dev.models import Integration, IntegrationSecret, Project
from src.orbi_dev.service import _github_repo

logger = logging.getLogger("orbi.dev.migrations")

LEGACY_FIELD = "secret_ciphertext"


async def migrate_legacy_secrets() -> int:
    """Déplace les `secret_ciphertext` hérités vers `IntegrationSecret`. Idempotent ; retourne le nombre traité."""
    collection = Integration.get_pymongo_collection()
    migrated = 0
    async for doc in collection.find({LEGACY_FIELD: {"$exists": True}}):
        integration_id = str(doc["_id"])
        ciphertext = doc.get(LEGACY_FIELD)
        if ciphertext and doc.get("status") != "revoked":
            already = await IntegrationSecret.find_one(IntegrationSecret.integration_id == integration_id)
            if already is None:  # d'abord copier, ensuite effacer : un arrêt au milieu ne perd rien
                await IntegrationSecret(
                    integration_id=integration_id, owner_id=doc["owner_id"], ciphertext=ciphertext
                ).insert()
        await collection.update_one({"_id": doc["_id"]}, {"$unset": {LEGACY_FIELD: ""}})
        migrated += 1
    if migrated:
        logger.info("Secrets d'intégration migrés vers leur collection dédiée : %d", migrated)
    return migrated


DEV_NOTIFICATIONS_MARKER = "enable_dev_run_notifications_v1"


async def enable_dev_run_notifications_once() -> int:
    """
    Active « fin d'exécution Orbi Dev » chez les utilisateurs déjà inscrits, une seule fois.

    Le marqueur est posé de façon atomique : un utilisateur qui désactive ensuite la notification ne la retrouve pas
    au démarrage suivant. Retourne le nombre d'utilisateurs modifiés (0 si la migration a déjà eu lieu).
    """
    from src.core.database import get_database
    from src.models.user import NotificationPreferences, User

    marker = await get_database()["orbi_dev_migrations"].update_one(
        {"_id": DEV_NOTIFICATIONS_MARKER}, {"$setOnInsert": {"applied_at": datetime.now(UTC)}}, upsert=True
    )
    if marker.upserted_id is None:
        return 0
    result = await User.get_pymongo_collection().update_many(
        {}, {"$addToSet": {"enabled_notifications": NotificationPreferences.DEV_RUNS.value}}
    )
    logger.info("Notifications Orbi Dev activées pour %d utilisateur(s)", result.modified_count)
    return result.modified_count


_GITHUB_URL = re.compile(r"^https://github\.com/")


async def backfill_github_repo() -> int:
    """
    Remplit `Project.github_repo` (« owner/repo ») pour les projets GitHub créés avant le champ (ADR-0009).
    Idempotent : seuls les documents sans valeur sont visités, et un dépôt non GitHub garde None.
    """
    updated = 0
    collection = Project.get_pymongo_collection()
    async for doc in collection.find(
        {"repo_url": {"$regex": _GITHUB_URL.pattern}, "github_repo": None}
    ):
        github_repo = _github_repo(doc["repo_url"])
        if github_repo is None:
            continue
        await collection.update_one({"_id": doc["_id"]}, {"$set": {"github_repo": github_repo}})
        updated += 1
    if updated:
        logger.info("Projets rattachés à leur dépôt GitHub : %d", updated)
    return updated


async def dedupe_github_webhook_logs() -> int:
    """
    Garde la plus ancienne occurrence de chaque `delivery_id` du journal GitHub (les suivantes sont des
    redéliveries ou des doublons sans information nouvelle), puis pose l'index unique qui rend le webhook
    idempotent (ADR-0009).

    L'index n'est pas déclaré dans `GithubWebhookLog.Settings` : `init_beanie` le créerait avant cette
    migration et un historique contenant des doublons empêcherait le démarrage. Index partiel : les
    `delivery_id` vides (absents du en-tête) ne sont pas dédupliqués.
    """
    from src.models.developer import GithubWebhookLog

    collection = GithubWebhookLog.get_pymongo_collection()
    duplicates = await collection.aggregate(
        [
            {"$match": {"delivery_id": {"$gt": ""}}},
            {"$sort": {"received_at": 1}},
            {"$group": {"_id": "$delivery_id", "ids": {"$push": "$_id"}, "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
        ]
    )
    stale_ids: list = []
    async for dup in duplicates:
        stale_ids.extend(dup["ids"][1:])
    removed = 0
    if stale_ids:
        result = await collection.delete_many({"_id": {"$in": stale_ids}})
        removed = result.deleted_count
    if removed:
        logger.info("Journal webhooks GitHub : %d doublon(s) de livraison supprimé(s)", removed)
    await collection.create_index(
        [("delivery_id", ASCENDING)],
        unique=True,
        partialFilterExpression={"delivery_id": {"$gt": ""}},
    )
    return removed


async def run_migrations() -> None:
    """Toutes les migrations Orbi Dev, idempotentes ; appelées au démarrage de l'application et par scripts/init_db.py."""
    await migrate_legacy_secrets()
    await enable_dev_run_notifications_once()
    await backfill_github_repo()
    await dedupe_github_webhook_logs()
