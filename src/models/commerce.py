"""
Orbi — Modèles Product et Order (Beanie Documents).
Catalogue produits, panier et commandes avec suivi.
"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Optional

from beanie import Document, Indexed
from pydantic import BaseModel, Field


# ─────────────────────────────────────
# Produit
# ─────────────────────────────────────

class Product(Document):
    """Document MongoDB représentant un produit du catalogue."""

    # ── Contenu multilingue ──
    name_fr: str
    name_en: str
    name_ar: str
    description_fr: str = ""
    description_en: str = ""
    description_ar: str = ""

    # ── Commerce ──
    price: float = Field(gt=0)
    currency: str = "XOF"
    stock: int = Field(ge=0, default=0)
    category: str = ""

    # ── Médias ──
    image_file_id: Optional[str] = None  # file_id Telegram permanent

    # ── État ──
    is_active: bool = True

    # ── Notifications de disponibilité ──
    notify_users: list[int] = Field(default_factory=list)  # telegram_ids à notifier

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "products"
        use_state_management = True

    def get_name(self, lang: str = "fr") -> str:
        """Retourne le nom dans la langue demandée."""
        return getattr(self, f"name_{lang}", self.name_fr)

    def get_description(self, lang: str = "fr") -> str:
        """Retourne la description dans la langue demandée."""
        return getattr(self, f"description_{lang}", self.description_fr)

    @property
    def is_available(self) -> bool:
        return self.is_active and self.stock > 0


# ─────────────────────────────────────
# Commande
# ─────────────────────────────────────

class OrderStatus(StrEnum):
    PENDING_PAYMENT = "pending_payment"
    PAID = "paid"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class PaymentProvider(StrEnum):
    STRIPE = "stripe"
    ORANGE_MONEY = "orange_money"
    WAVE = "wave"


class OrderItem(BaseModel):
    """Article dans une commande."""
    product_id: str
    name: str
    price: float
    quantity: int


class Order(Document):
    """Document MongoDB représentant une commande."""

    # ── Identifiant ──
    order_id: Indexed(str, unique=True)  # type: ignore[valid-type]  # Format: ORD-YYYY-NNNNN

    # ── Utilisateur ──
    user_telegram_id: Indexed(int)  # type: ignore[valid-type]
    user_name: str = ""

    # ── Articles ──
    items: list[dict] = Field(default_factory=list)
    # Chaque item : {"product_id": str, "name": str, "price": float, "quantity": int}

    # ── Paiement ──
    subtotal: float = 0.0
    discount: float = 0.0
    total: float = 0.0
    currency: str = "XOF"
    payment_provider: Optional[PaymentProvider] = None
    payment_session_id: Optional[str] = None  # ID session Stripe / référence OM/Wave
    promo_code: Optional[str] = None

    # ── Livraison ──
    shipping_address: Optional[str] = None
    tracking_number: Optional[str] = None

    # ── État ──
    status: OrderStatus = OrderStatus.PENDING_PAYMENT
    is_sandbox: bool = False

    # ── Idempotence ──
    idempotency_key: Optional[str] = None

    # ── Historique des statuts ──
    status_history: list[dict] = Field(default_factory=list)
    # Chaque entrée : {"status": str, "timestamp": datetime, "note": str}

    # ── Timestamps ──
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    paid_at: Optional[datetime] = None
    shipped_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    class Settings:
        name = "orders"
        use_state_management = True

    def add_status_change(self, new_status: OrderStatus, note: str = "") -> None:
        """Enregistre un changement de statut dans l'historique."""
        self.status = new_status
        self.status_history.append({
            "status": new_status.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": note,
        })
        self.updated_at = datetime.now(timezone.utc)


# ─────────────────────────────────────
# Code Promo
# ─────────────────────────────────────

class PromoCodeType(StrEnum):
    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"
    FREE_SHIPPING = "free_shipping"


class PromoCode(Document):
    """Document MongoDB représentant un code promotionnel."""

    code: Indexed(str, unique=True)  # type: ignore[valid-type]
    promo_type: PromoCodeType
    value: float = 0.0  # % ou montant fixe
    min_order_amount: float = 0.0
    max_uses: int = 0  # 0 = illimité
    current_uses: int = 0
    expires_at: Optional[datetime] = None
    is_active: bool = True

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Settings:
        name = "promo_codes"

    @property
    def is_valid(self) -> bool:
        if not self.is_active:
            return False
        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            return False
        return True
