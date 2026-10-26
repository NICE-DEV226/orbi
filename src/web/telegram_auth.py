"""
Orbi — Authentification par Mini App Telegram.

Une Mini App reçoit de Telegram une chaîne `initData` signée. Le serveur la valide avant de faire confiance à
l'identité qu'elle contient (jamais `initDataUnsafe`, côté client). Procédure officielle :
https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app

    data_check_string = champs triés par nom, hors `hash`, au format « clé=valeur », séparés par « \\n »
    secret_key        = HMAC_SHA256(clé="WebAppData", message=<jeton du bot>)
    hash              = hex(HMAC_SHA256(clé=secret_key, message=data_check_string))

La documentation officielle écrit l'ordre des arguments du HMAC de façon contradictoire (texte et pseudo-code) ;
l'implémentation ci-dessous suit la convention utilisée par les bibliothèques de référence et est vérifiée par un
test contre aiogram (voir tests/test_telegram_auth.py).
"""

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

MAX_INIT_DATA_LENGTH = 8192
CLOCK_SKEW_SECONDS = 300  # tolérance si l'horloge de Telegram est en avance sur la nôtre


class InvalidInitDataError(Exception):
    """initData absente, mal formée, falsifiée ou périmée. Le message ne contient jamais de secret."""


@dataclass(frozen=True)
class TelegramUser:
    id: int
    first_name: str
    username: str | None
    language_code: str | None
    auth_date: int
    start_param: str | None


def compute_hash(fields: dict[str, str], bot_token: str) -> str:
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields) if key != "hash")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(
    init_data: str, bot_token: str, *, max_age: int = 3600, now: float | None = None
) -> TelegramUser:
    """Vérifie la signature et la fraîcheur d'`initData` ; retourne l'utilisateur Telegram authentifié."""
    if not bot_token:
        raise InvalidInitDataError("Authentification Telegram non configurée")
    if not init_data or len(init_data) > MAX_INIT_DATA_LENGTH:
        raise InvalidInitDataError("initData absente ou trop longue")

    pairs = parse_qsl(init_data, keep_blank_values=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise InvalidInitDataError("initData invalide (champ dupliqué)")

    received_hash = fields.get("hash", "")
    if not received_hash:
        raise InvalidInitDataError("initData sans signature")
    if not hmac.compare_digest(received_hash.encode(), compute_hash(fields, bot_token).encode()):
        raise InvalidInitDataError("Signature invalide")

    try:
        auth_date = int(fields["auth_date"])
        user = json.loads(fields["user"])
        user_id = int(user["id"])
    except (KeyError, ValueError, TypeError) as e:
        raise InvalidInitDataError("initData incomplète") from e

    current = time.time() if now is None else now
    if auth_date > current + CLOCK_SKEW_SECONDS:
        raise InvalidInitDataError("Date d'authentification dans le futur")
    if current - auth_date > max_age:
        raise InvalidInitDataError("initData périmée : rouvrez l'application depuis Telegram")

    return TelegramUser(
        id=user_id,
        first_name=str(user.get("first_name") or ""),
        username=user.get("username"),
        language_code=user.get("language_code"),
        auth_date=auth_date,
        start_param=fields.get("start_param"),
    )
