"""
Orbi — Service Paiements (Phase 5).
Intégrations Stripe, Orange Money, Wave.
Conforme au CdC §11.3 : idempotence, timeouts, gestion d'erreurs.
"""

import hashlib
import logging
import time
from typing import Optional

import httpx

from src.core.config import get_settings
from src.models.commerce import Order, OrderStatus, PaymentProvider

logger = logging.getLogger("orbi.services.payment")

# Timeout global pour les appels HTTP vers les providers
PAYMENT_TIMEOUT = 30  # secondes


def generate_idempotency_key(user_id: int, order_id: str) -> str:
    """Génère une clé d'idempotence unique pour une opération de paiement."""
    raw = f"{user_id}:{order_id}:{int(time.time() // 60)}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


# ─────────────────────────────────────
# Stripe
# ─────────────────────────────────────

async def create_stripe_session(order: Order) -> Optional[str]:
    """
    Crée une session Stripe Checkout.
    Retourne l'URL de paiement ou None en cas d'erreur.
    """
    settings = get_settings()
    if not settings.STRIPE_SECRET_KEY:
        logger.error("STRIPE_SECRET_KEY non configuré")
        return None

    try:
        import stripe
        stripe.api_key = settings.STRIPE_SECRET_KEY

        line_items = []
        for item in order.items:
            line_items.append({
                "price_data": {
                    "currency": order.currency.lower(),
                    "product_data": {"name": item.get("name", "Produit Orbi")},
                    "unit_amount": int(item.get("price", 0) * 100),
                },
                "quantity": item.get("quantity", 1),
            })

        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=f"{settings.BASE_URL}/payment/success?order_id={order.order_id}",
            cancel_url=f"{settings.BASE_URL}/payment/cancel?order_id={order.order_id}",
            metadata={
                "order_id": order.order_id,
                "idempotency_key": order.idempotency_key or "",
            },
            idempotency_key=order.idempotency_key,
        )

        # Sauvegarder l'ID de session
        order.payment_session_id = session.id
        order.payment_provider = PaymentProvider.STRIPE
        await order.save()

        logger.info("Session Stripe créée: order=%s, session=%s", order.order_id, session.id)
        return session.url

    except Exception as e:
        logger.error("Erreur Stripe: %s", e, exc_info=True)
        return None


async def verify_stripe_webhook(payload: bytes, signature: str) -> Optional[dict]:
    """Vérifie et parse un webhook Stripe."""
    settings = get_settings()
    try:
        import stripe
        event = stripe.Webhook.construct_event(
            payload, signature, settings.STRIPE_WEBHOOK_SECRET,
        )
        return event
    except Exception as e:
        logger.error("Erreur vérification webhook Stripe: %s", e)
        return None


# ─────────────────────────────────────
# Orange Money
# ─────────────────────────────────────

async def initiate_orange_money_payment(order: Order) -> Optional[str]:
    """
    Initie un paiement Orange Money.
    Retourne l'URL de paiement ou None.
    """
    settings = get_settings()
    if not settings.ORANGE_MONEY_API_KEY:
        logger.error("ORANGE_MONEY_API_KEY non configuré")
        return None

    try:
        async with httpx.AsyncClient(timeout=PAYMENT_TIMEOUT) as client:
            # Étape 1 : Obtenir un token d'accès
            auth_response = await client.post(
                "https://api.orange.com/oauth/v3/token",
                headers={"Authorization": f"Basic {settings.ORANGE_MONEY_API_KEY}"},
                data={"grant_type": "client_credentials"},
            )
            auth_response.raise_for_status()
            access_token = auth_response.json().get("access_token")

            # Étape 2 : Initier le paiement
            payment_response = await client.post(
                "https://api.orange.com/orange-money-webpay/dev/v1/webpayment",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                json={
                    "merchant_key": settings.ORANGE_MONEY_MERCHANT_ID,
                    "currency": order.currency,
                    "order_id": order.order_id,
                    "amount": order.total,
                    "return_url": f"{settings.BASE_URL}/payment/success?order_id={order.order_id}",
                    "cancel_url": f"{settings.BASE_URL}/payment/cancel?order_id={order.order_id}",
                    "notif_url": f"{settings.BASE_URL}/webhook/orange-money",
                    "lang": "fr",
                },
            )
            payment_response.raise_for_status()
            data = payment_response.json()

            payment_url = data.get("payment_url")
            payment_token = data.get("pay_token")

            order.payment_session_id = payment_token
            order.payment_provider = PaymentProvider.ORANGE_MONEY
            await order.save()

            logger.info("Paiement Orange Money initié: order=%s", order.order_id)
            return payment_url

    except httpx.TimeoutException:
        logger.error("Timeout Orange Money: order=%s", order.order_id)
        return None
    except Exception as e:
        logger.error("Erreur Orange Money: %s", e, exc_info=True)
        return None


# ─────────────────────────────────────
# Wave
# ─────────────────────────────────────

async def initiate_wave_payment(order: Order) -> Optional[str]:
    """
    Initie un paiement Wave.
    Retourne l'URL de checkout ou None.
    """
    settings = get_settings()
    if not settings.WAVE_API_KEY:
        logger.error("WAVE_API_KEY non configuré")
        return None

    try:
        async with httpx.AsyncClient(timeout=PAYMENT_TIMEOUT) as client:
            response = await client.post(
                "https://api.wave.com/v1/checkout/sessions",
                headers={
                    "Authorization": f"Bearer {settings.WAVE_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "amount": str(int(order.total)),
                    "currency": order.currency,
                    "error_url": f"{settings.BASE_URL}/payment/cancel?order_id={order.order_id}",
                    "success_url": f"{settings.BASE_URL}/payment/success?order_id={order.order_id}",
                    "client_reference": order.order_id,
                },
            )
            response.raise_for_status()
            data = response.json()

            checkout_url = data.get("wave_launch_url")
            session_id = data.get("id")

            order.payment_session_id = session_id
            order.payment_provider = PaymentProvider.WAVE
            await order.save()

            logger.info("Paiement Wave initié: order=%s", order.order_id)
            return checkout_url

    except httpx.TimeoutException:
        logger.error("Timeout Wave: order=%s", order.order_id)
        return None
    except Exception as e:
        logger.error("Erreur Wave: %s", e, exc_info=True)
        return None


# ─────────────────────────────────────
# Traitement des webhooks de paiement
# ─────────────────────────────────────

async def handle_payment_success(order: Order) -> None:
    """Traite un paiement confirmé (appelé par les webhooks)."""
    from datetime import datetime, timezone

    if order.status == OrderStatus.PAID:
        logger.warning("Double paiement ignoré (idempotent): order=%s", order.order_id)
        return

    order.add_status_change(OrderStatus.PAID, "Paiement confirmé")
    order.paid_at = datetime.now(timezone.utc)
    await order.save()

    logger.info("Paiement confirmé: order=%s, provider=%s", order.order_id, order.payment_provider)


async def handle_payment_cancelled(order: Order) -> None:
    """Traite un paiement annulé."""
    from datetime import datetime, timezone

    order.add_status_change(OrderStatus.CANCELLED, "Paiement annulé par l'utilisateur")
    order.cancelled_at = datetime.now(timezone.utc)
    await order.save()

    logger.info("Paiement annulé: order=%s", order.order_id)
