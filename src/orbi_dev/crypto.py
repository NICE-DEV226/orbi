"""
Orbi Dev — Chiffrement des secrets d'intégration (Fernet).

`SECRETS_ENCRYPTION_KEY` accepte une ou plusieurs clés séparées par des virgules : la première
chiffre, toutes peuvent déchiffrer (rotation sans interruption). Sans clé configurée, aucun secret
n'est jamais stocké : l'opération échoue explicitement.
"""

from cryptography.fernet import Fernet, InvalidToken, MultiFernet

from src.core.config import get_settings


class SecretsNotConfiguredError(Exception):
    """SECRETS_ENCRYPTION_KEY absente ou invalide."""


class SecretDecryptionError(Exception):
    """Le secret stocké ne peut pas être déchiffré avec les clés actuelles."""


def _box() -> MultiFernet:
    raw = get_settings().SECRETS_ENCRYPTION_KEY
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise SecretsNotConfiguredError("SECRETS_ENCRYPTION_KEY n'est pas configurée")
    try:
        return MultiFernet([Fernet(k.encode()) for k in keys])
    except (ValueError, TypeError) as e:
        raise SecretsNotConfiguredError("SECRETS_ENCRYPTION_KEY invalide (clé Fernet attendue)") from e


def encrypt_secret(plaintext: str) -> str:
    return _box().encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str) -> str:
    try:
        return _box().decrypt(ciphertext.encode()).decode()
    except InvalidToken as e:
        raise SecretDecryptionError("Secret illisible avec les clés actuelles") from e
