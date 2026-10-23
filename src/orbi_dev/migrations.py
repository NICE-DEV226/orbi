"""
Orbi Dev — Migrations de données idempotentes, exécutées au démarrage (scripts/init_db.py).

Avant la migration vers Beanie 2, le texte chiffré d'une clé était stocké dans le document `Integration`
(champ `secret_ciphertext`). Il vit désormais dans `IntegrationSecret` ; cette migration déplace les anciennes
valeurs puis supprime le champ, afin qu'aucun secret ne reste dans un document exposé ni après une révocation.
"""

import logging

from src.orbi_dev.models import Integration, IntegrationSecret

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
