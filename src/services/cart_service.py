"""
Orbi — Service Panier (Cart) via Redis (Phase 5).
Le panier est stocké entièrement dans Redis avec un TTL de 24h.
Conforme au CdC §4 : Panier géré par Redis.
"""

import json
import logging
from typing import Optional

from src.core.redis import get_redis

logger = logging.getLogger("orbi.services.cart")

CART_KEY_PREFIX = "orbi:cart:"
CART_TTL_SECONDS = 86400  # 24 heures


def _cart_key(telegram_id: int) -> str:
    return f"{CART_KEY_PREFIX}{telegram_id}"


async def get_cart(telegram_id: int) -> list[dict]:
    """Récupère le panier complet d'un utilisateur."""
    redis = get_redis()
    raw = await redis.get(_cart_key(telegram_id))
    if not raw:
        return []
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


async def add_to_cart(
    telegram_id: int,
    product_id: str,
    name: str,
    price: float,
    quantity: int = 1,
) -> list[dict]:
    """
    Ajoute un produit au panier. Si déjà présent, incrémente la quantité.
    Retourne le panier mis à jour.
    """
    cart = await get_cart(telegram_id)

    # Cherche si le produit est déjà dans le panier
    for item in cart:
        if item["product_id"] == product_id:
            item["quantity"] += quantity
            await _save_cart(telegram_id, cart)
            return cart

    # Nouvel article
    cart.append({
        "product_id": product_id,
        "name": name,
        "price": price,
        "quantity": quantity,
    })
    await _save_cart(telegram_id, cart)
    return cart


async def remove_from_cart(telegram_id: int, product_id: str) -> list[dict]:
    """Supprime un produit du panier."""
    cart = await get_cart(telegram_id)
    cart = [item for item in cart if item["product_id"] != product_id]
    await _save_cart(telegram_id, cart)
    return cart


async def update_quantity(
    telegram_id: int,
    product_id: str,
    quantity: int,
) -> list[dict]:
    """Met à jour la quantité d'un produit. Si 0, le supprime."""
    if quantity <= 0:
        return await remove_from_cart(telegram_id, product_id)

    cart = await get_cart(telegram_id)
    for item in cart:
        if item["product_id"] == product_id:
            item["quantity"] = quantity
            break
    await _save_cart(telegram_id, cart)
    return cart


async def clear_cart(telegram_id: int) -> None:
    """Vide entièrement le panier."""
    redis = get_redis()
    await redis.delete(_cart_key(telegram_id))


async def get_cart_total(telegram_id: int) -> float:
    """Calcule le total du panier."""
    cart = await get_cart(telegram_id)
    return sum(item["price"] * item["quantity"] for item in cart)


async def get_cart_count(telegram_id: int) -> int:
    """Nombre total d'articles dans le panier."""
    cart = await get_cart(telegram_id)
    return sum(item["quantity"] for item in cart)


async def _save_cart(telegram_id: int, cart: list[dict]) -> None:
    """Persiste le panier dans Redis avec TTL."""
    redis = get_redis()
    if cart:
        await redis.set(_cart_key(telegram_id), json.dumps(cart, ensure_ascii=False), ex=CART_TTL_SECONDS)
    else:
        await redis.delete(_cart_key(telegram_id))
