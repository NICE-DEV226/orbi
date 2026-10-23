"""
Orbi — Service Commerce (Phase 5).
Catalogue paginé, commandes, codes promo.
"""

import hashlib
import logging
from datetime import UTC, datetime

from src.models.commerce import Order, OrderStatus, Product, PromoCode
from src.models.user import User

logger = logging.getLogger("orbi.services.commerce")

PRODUCTS_PER_PAGE = 5


async def generate_order_id() -> str:
    """Génère un ID de commande unique : ORD-YYYY-NNNNN."""
    now = datetime.now(UTC)
    year = now.strftime("%Y")
    count = await Order.find(
        Order.order_id >= f"ORD-{year}-",
        Order.order_id <= f"ORD-{year}-99999",
    ).count()
    return f"ORD-{year}-{count + 1:05d}"


# ─────────────────────────────────────
# Catalogue
# ─────────────────────────────────────

async def get_catalog_page(
    page: int = 0,
    category: str | None = None,
    search: str | None = None,
) -> tuple[list[Product], int]:
    """
    Retourne une page du catalogue + nombre total de produits.
    """
    query_filter = {"is_active": True}
    if category:
        query_filter["category"] = category
    # La recherche par texte sera enrichie avec un index text MongoDB

    total = await Product.find(query_filter).count()
    products = await Product.find(query_filter).skip(page * PRODUCTS_PER_PAGE).limit(PRODUCTS_PER_PAGE).to_list()

    return products, total


async def get_product(product_id: str) -> Product | None:
    """Récupère un produit par son ID."""
    from beanie import PydanticObjectId
    try:
        return await Product.get(PydanticObjectId(product_id))
    except Exception:
        return None


# ─────────────────────────────────────
# Commandes
# ─────────────────────────────────────

async def create_order_from_cart(
    user: User,
    cart_items: list[dict],
    promo_code: str | None = None,
) -> Order:
    """Crée une commande à partir du panier."""
    order_id = await generate_order_id()
    subtotal = sum(item["price"] * item["quantity"] for item in cart_items)
    discount = 0.0

    # Appliquer le code promo si fourni
    if promo_code:
        promo = await validate_promo_code(promo_code)
        if promo:
            discount = calculate_discount(promo, subtotal)

    total = max(0, subtotal - discount)

    order = Order(
        order_id=order_id,
        user_telegram_id=user.telegram_id,
        user_name=user.display_name,
        items=cart_items,
        subtotal=subtotal,
        discount=discount,
        total=total,
        promo_code=promo_code if discount > 0 else None,
        idempotency_key=generate_idempotency_key(user.telegram_id, order_id),
    )

    order.add_status_change(OrderStatus.PENDING_PAYMENT, "Commande créée")
    await order.insert()

    # Incrémente le compteur de commandes
    user.total_orders += 1
    user.touch()
    await user.save()

    logger.info("Commande créée: %s (user=%d, total=%.2f)", order_id, user.telegram_id, total)
    return order


async def get_user_orders(telegram_id: int, limit: int = 10) -> list[Order]:
    """Récupère les commandes d'un utilisateur."""
    return await Order.find(
        Order.user_telegram_id == telegram_id,
    ).sort(-Order.created_at).limit(limit).to_list()


def generate_idempotency_key(user_id: int, order_id: str) -> str:
    """Clé d'idempotence stable : dérivée uniquement de l'identité de la commande."""
    return hashlib.sha256(f"{user_id}:{order_id}".encode()).hexdigest()[:32]


async def get_order(order_id: str) -> Order | None:
    """Récupère une commande par son ID."""
    return await Order.find_one(Order.order_id == order_id)


# ─────────────────────────────────────
# Codes Promo
# ─────────────────────────────────────

async def validate_promo_code(code: str) -> PromoCode | None:
    """Vérifie la validité d'un code promo."""
    promo = await PromoCode.find_one(PromoCode.code == code.upper())
    if promo and promo.is_valid:
        return promo
    return None


def calculate_discount(promo: PromoCode, subtotal: float) -> float:
    """Calcule le montant de la remise."""
    if subtotal < promo.min_order_amount:
        return 0.0

    if promo.promo_type == "percentage":
        return round(subtotal * promo.value / 100, 2)
    elif promo.promo_type == "fixed_amount":
        return min(promo.value, subtotal)
    return 0.0


async def apply_promo_code(promo: PromoCode) -> None:
    """Incrémente le compteur d'utilisation du code promo."""
    promo.current_uses += 1
    await promo.save()


# ─────────────────────────────────────
# Stock
# ─────────────────────────────────────

async def check_and_reduce_stock(cart_items: list[dict]) -> list[str]:
    """
    Vérifie la disponibilité du stock et le réduit.
    Retourne la liste des produits indisponibles.
    """
    unavailable = []

    for item in cart_items:
        product = await get_product(item["product_id"])
        if not product or product.stock < item["quantity"]:
            unavailable.append(item.get("name", item["product_id"]))
        else:
            product.stock -= item["quantity"]
            product.updated_at = datetime.now(UTC)
            await product.save()

            # Si stock à 0, notifier les utilisateurs inscrits
            if product.stock == 0 and product.notify_users:
                logger.info("Produit en rupture: %s — %d utilisateurs à notifier", product.get_name(), len(product.notify_users))

    return unavailable
