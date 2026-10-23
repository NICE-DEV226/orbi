"""
Orbi — Handlers Module Commerce (Phase 5).
Catalogue, Panier et Checkout.
Conforme au CdC §4 : Module Boutique/Services complet.
"""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

from src.bot.keyboards import CB_HOME, CB_MODULE_SHOP
from src.core.i18n import t
from src.models.commerce import OrderStatus
from src.models.user import User
from src.services.cart_service import (
    add_to_cart,
    clear_cart,
    get_cart,
    get_cart_count,
    get_cart_total,
    remove_from_cart,
    update_quantity,
)
from src.services.commerce_service import (
    PRODUCTS_PER_PAGE,
    check_and_reduce_stock,
    create_order_from_cart,
    get_catalog_page,
    get_order,
    get_product,
    get_user_orders,
    validate_promo_code,
)

logger = logging.getLogger("orbi.handlers.commerce")

# ── États du Checkout ──
STATE_PROMO = 1
STATE_PAYMENT_METHOD = 2


# ─────────────────────────────────────
# Catalogue
# ─────────────────────────────────────

async def show_catalog(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche une page du catalogue."""
    query = update.callback_query
    await query.answer()

    if not context.user_data: return
    lang = context.user_data.get("lang", "fr")

    # shop:catalog:0 → page 0
    parts = query.data.split(":")
    page = int(parts[2]) if len(parts) > 2 else 0

    products, total = await get_catalog_page(page=page)

    if not products:
        await query.edit_message_text(
            t("commerce.empty_catalog", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_SHOP)]
            ]),
        )
        return

    text = f"🛍️ <b>{t('commerce.catalog', lang)}</b>\n\n"

    buttons = []
    for p in products:
        name = p.get_name(lang)
        desc = p.get_description(lang)
        price_fmt = f"{p.price:,.0f} {p.currency}"
        stock_status = "✅" if p.is_available else "❌ Rupture"

        text += f"🔹 <b>{name}</b> — {price_fmt}\n<i>{desc}</i>\nStock: {stock_status}\n\n"

        if p.is_available:
            buttons.append([
                InlineKeyboardButton(
                    f"🛒 Ajouter {name[:10]}...",
                    callback_data=f"cart_add:{p.id}",
                )
            ])

    # Pagination
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️", callback_data=f"shop:catalog:{page - 1}"))
    if (page + 1) * PRODUCTS_PER_PAGE < total:
        nav_buttons.append(InlineKeyboardButton("➡️", callback_data=f"shop:catalog:{page + 1}"))

    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([
        InlineKeyboardButton(t("commerce.cart", lang), callback_data="shop:cart"),
        InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_SHOP)
    ])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────
# Panier
# ─────────────────────────────────────

async def handle_add_to_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ajoute un produit au panier Redis."""
    query = update.callback_query
    if not context.user_data: return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    product_id = query.data.split(":")[1]
    product = await get_product(product_id)

    if not product or not product.is_available:
        await query.answer("❌ Produit non disponible", show_alert=True)
        return

    await add_to_cart(
        db_user.telegram_id,
        str(product.id),
        product.get_name("fr"),  # Le nom de base pour le récapitulatif
        product.price,
    )

    count = await get_cart_count(db_user.telegram_id)
    await query.answer(f"✅ Ajouté ! ({count} articles au total)")


async def show_cart(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche le contenu du panier."""
    query = update.callback_query
    await query.answer()

    if not context.user_data: return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    cart = await get_cart(db_user.telegram_id)
    if not cart:
        await query.edit_message_text(
            t("commerce.cart_empty", lang),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("commerce.catalog", lang), callback_data="shop:catalog")],
                [InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_SHOP)],
            ]),
        )
        return

    total = await get_cart_total(db_user.telegram_id)

    text = f"🛒 <b>{t('commerce.cart', lang)}</b>\n\n"
    buttons = []

    for item in cart:
        name = item.get("name", "Produit")
        qty = item.get("quantity", 1)
        price = item.get("price", 0)
        sub = price * qty
        pid = item.get("product_id")

        text += f"▪️ {qty}x <b>{name}</b> — {sub:,.0f} XOF\n"

        buttons.append([
            InlineKeyboardButton(f"➖ {name[:10]}", callback_data=f"cart_update:{pid}:{qty - 1}"),
            InlineKeyboardButton(f"➕ {name[:10]}", callback_data=f"cart_update:{pid}:{qty + 1}"),
            InlineKeyboardButton("❌", callback_data=f"cart_remove:{pid}"),
        ])

    text += f"\n💰 <b>Total : {total:,.0f} XOF</b>"

    buttons.append([
        InlineKeyboardButton(t("commerce.checkout", lang), callback_data="shop:checkout_start"),
    ])
    buttons.append([
        InlineKeyboardButton("🗑️ Vider le panier", callback_data="cart_clear"),
        InlineKeyboardButton(t("common.back", lang), callback_data=CB_MODULE_SHOP),
    ])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


async def handle_cart_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Modifie la quantité d'un produit."""
    query = update.callback_query
    if not context.user_data: return
    db_user: User = context.user_data.get("db_user")

    parts = query.data.split(":")
    pid = parts[1]
    new_qty = int(parts[2])

    await update_quantity(db_user.telegram_id, pid, new_qty)
    await show_cart(update, context)


async def handle_cart_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Supprime un produit du panier."""
    query = update.callback_query
    if not context.user_data: return
    db_user: User = context.user_data.get("db_user")
    pid = query.data.split(":")[1]

    await remove_from_cart(db_user.telegram_id, pid)
    await show_cart(update, context)


async def handle_cart_clear(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Vide le panier."""
    query = update.callback_query
    if not context.user_data: return
    db_user: User = context.user_data.get("db_user")

    await clear_cart(db_user.telegram_id)
    await show_cart(update, context)


# ─────────────────────────────────────
# Checkout & Commandes (ConversationHandler)
# ─────────────────────────────────────

async def checkout_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Démarre le flux de paiement : propose d'entrer un code promo."""
    query = update.callback_query
    await query.answer()

    if context.user_data is None: return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    cart = await get_cart(db_user.telegram_id)
    if not cart:
        await query.edit_message_text(t("commerce.cart_empty", lang))
        return ConversationHandler.END

    total = await get_cart_total(db_user.telegram_id)
    context.user_data["_checkout_total"] = total
    context.user_data["_checkout_promo"] = None

    prompt = {
        "fr": f"💰 Total: {total:,.0f} XOF\n\nAvez-vous un code promo ? Saisissez-le maintenant, ou cliquez sur Ignorer.",
        "en": f"💰 Total: {total:,.0f} XOF\n\nDo you have a promo code? Enter it now, or click Skip.",
        "ar": f"💰 الإجمالي: {total:,.0f} XOF\n\nهل لديك رمز ترويجي؟ أدخله الآن أو انقر على تخطي.",
    }

    await query.edit_message_text(
        prompt.get(lang, prompt["fr"]),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("⏭️ Ignorer / Skip", callback_data="checkout_skip_promo")],
            [InlineKeyboardButton(t("common.cancel", lang), callback_data="checkout_cancel")],
        ]),
    )
    return STATE_PROMO


async def handle_promo_code(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Traite le code promo saisi."""
    if not context.user_data: return
    lang = context.user_data.get("lang", "fr")
    code = update.message.text.strip().upper()

    promo = await validate_promo_code(code)
    if not promo:
        err = {"fr": "❌ Code invalide ou expiré.", "en": "❌ Invalid or expired code.", "ar": "❌ رمز غير صالح أو منتهي الصلاحية."}
        await update.message.reply_text(
            err.get(lang, err["fr"]),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⏭️ Ignorer / Skip", callback_data="checkout_skip_promo")],
                [InlineKeyboardButton(t("common.cancel", lang), callback_data="checkout_cancel")],
            ]),
        )
        return STATE_PROMO

    context.user_data["_checkout_promo"] = code
    return await show_payment_methods(update, context)


async def skip_promo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """L'utilisateur n'a pas de code promo."""
    query = update.callback_query
    await query.answer()
    return await show_payment_methods(update, context, from_query=True)


async def show_payment_methods(update: Update, context: ContextTypes.DEFAULT_TYPE, from_query: bool = False) -> int:
    """Affiche le récapitulatif final et la confirmation de commande."""
    if not context.user_data: return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    cart = await get_cart(db_user.telegram_id)
    subtotal = await get_cart_total(db_user.telegram_id)
    promo_code = context.user_data.get("_checkout_promo")

    discount = 0.0
    if promo_code:
        from src.services.commerce_service import calculate_discount
        promo = await validate_promo_code(promo_code)
        if promo:
            discount = calculate_discount(promo, subtotal)

    total = max(0, subtotal - discount)

    text = f"💳 <b>{t('commerce.checkout', lang)}</b>\n\n"
    for item in cart:
        text += f"▪️ {item.get('quantity')}x {item.get('name')} — {item.get('price') * item.get('quantity'):,.0f}\n"

    text += f"\nSous-total: {subtotal:,.0f} XOF\n"
    if discount > 0:
        text += f"Remise ({promo_code}): -{discount:,.0f} XOF\n"
    text += f"\n💰 <b>TOTAL: {total:,.0f} XOF</b>\n\n"
    text += "Le paiement en ligne n'est pas encore disponible : la commande sera enregistrée en attente."

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Confirmer la commande", callback_data="pay:confirm")],
        [InlineKeyboardButton(t("common.cancel", lang), callback_data="checkout_cancel")],
    ])

    if from_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

    return STATE_PAYMENT_METHOD


async def process_payment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Crée la commande (en attente de paiement : aucun fournisseur de paiement n'est branché)."""
    query = update.callback_query
    await query.answer("Création de la commande...")

    if not context.user_data: return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    cart = await get_cart(db_user.telegram_id)
    if not cart:
        await query.edit_message_text("Panier vide.")
        return ConversationHandler.END

    promo_code = context.user_data.pop("_checkout_promo", None)
    context.user_data.pop("_checkout_total", None)

    # 1. Vérification du stock
    unavailable = await check_and_reduce_stock(cart)
    if unavailable:
        items_str = ", ".join(unavailable)
        err = {
            "fr": f"❌ Stock insuffisant pour : {items_str}. Veuillez modifier votre panier.",
            "en": f"❌ Insufficient stock for: {items_str}. Please modify your cart.",
            "ar": f"❌ مخزون غير كافٍ لـ: {items_str}. يرجى تعديل سلة التسوق الخاصة بك.",
        }
        await query.edit_message_text(
            err.get(lang, err["fr"]),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🛒", callback_data="shop:cart")]]),
        )
        return ConversationHandler.END

    try:
        # 2. Création de la commande en base
        order = await create_order_from_cart(db_user, cart, promo_code)

        # 3. Vider le panier
        await clear_cart(db_user.telegram_id)

        # 4. Confirmer à l'utilisateur
        msg = {
            "fr": f"✅ Commande <b>{order.order_id}</b> enregistrée.\n\nLe paiement en ligne n'est pas encore disponible ; la commande reste en attente de paiement.",
            "en": f"✅ Order <b>{order.order_id}</b> recorded.\n\nOnline payment is not available yet; the order stays pending payment.",
            "ar": f"✅ تم تسجيل الطلب <b>{order.order_id}</b>.\n\nالدفع عبر الإنترنت غير متاح بعد؛ يبقى الطلب قيد انتظار الدفع.",
        }

        await query.edit_message_text(
            msg.get(lang, msg["fr"]),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
            ]),
            parse_mode="HTML"
        )

    except Exception as e:
        logger.error("Erreur checkout: %s", e, exc_info=True)
        await query.edit_message_text(
            t("common.error", lang),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)]]),
        )

    return ConversationHandler.END


async def cancel_checkout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Annule le checkout et renvoie au panier."""
    query = update.callback_query
    await query.answer()

    context.user_data.pop("_checkout_promo", None)
    context.user_data.pop("_checkout_total", None)

    await show_cart(update, context)
    return ConversationHandler.END


# ─────────────────────────────────────
# Historique des Commandes
# ─────────────────────────────────────

async def show_my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Affiche l'historique des commandes."""
    query = update.callback_query
    await query.answer()

    if not context.user_data: return
    lang = context.user_data.get("lang", "fr")
    db_user: User = context.user_data.get("db_user")

    orders = await get_user_orders(db_user.telegram_id)

    if not orders:
        txt = {"fr": "📦 Vous n'avez aucune commande.", "en": "📦 You have no orders.", "ar": "📦 ليس لديك طلبات."}
        await query.edit_message_text(
            txt.get(lang, txt["fr"]),
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton(t("commerce.catalog", lang), callback_data="shop:catalog")],
                [InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)],
            ]),
        )
        return

    status_flags = {
        OrderStatus.PENDING_PAYMENT: "⏳",
        OrderStatus.PAID: "💸",
        OrderStatus.PROCESSING: "⚙️",
        OrderStatus.SHIPPED: "🚚",
        OrderStatus.DELIVERED: "✅",
        OrderStatus.CANCELLED: "❌",
        OrderStatus.REFUNDED: "↩️",
    }

    text = f"📦 <b>{t('commerce.my_orders', lang)}</b>\n\n"
    buttons = []

    for order in orders:
        flag = status_flags.get(order.status, "❓")
        date_str = order.created_at.strftime("%d/%m/%Y")
        text += f"{flag} <b>{order.order_id}</b> — {order.total:,.0f} XOF ({date_str})\n"
        buttons.append([
            InlineKeyboardButton(
                f"{flag} {order.order_id}",
                callback_data=f"order_view:{order.order_id}",
            )
        ])

    buttons.append([InlineKeyboardButton(t("common.home", lang), callback_data=CB_HOME)])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(buttons))


# ─────────────────────────────────────
# Registration
# ─────────────────────────────────────

def register_commerce_handlers(application) -> None:
    """Enregistre tous les handlers du module Commerce."""
    # Catalogue
    application.add_handler(CallbackQueryHandler(show_catalog, pattern=r"^shop:catalog"))

    # Panier
    application.add_handler(CallbackQueryHandler(show_cart, pattern=r"^shop:cart$"))
    application.add_handler(CallbackQueryHandler(handle_add_to_cart, pattern=r"^cart_add:"))
    application.add_handler(CallbackQueryHandler(handle_cart_update, pattern=r"^cart_update:"))
    application.add_handler(CallbackQueryHandler(handle_cart_remove, pattern=r"^cart_remove:"))
    application.add_handler(CallbackQueryHandler(handle_cart_clear, pattern=r"^cart_clear$"))

    # Checkout Flow
    checkout_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(checkout_start, pattern=r"^shop:checkout_start$")],
        states={
            STATE_PROMO: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_promo_code),
                CallbackQueryHandler(skip_promo, pattern=r"^checkout_skip_promo$"),
                CallbackQueryHandler(cancel_checkout, pattern=r"^checkout_cancel$"),
            ],
            STATE_PAYMENT_METHOD: [
                CallbackQueryHandler(process_payment, pattern=r"^pay:"),
                CallbackQueryHandler(cancel_checkout, pattern=r"^checkout_cancel$"),
            ],
        },
        fallbacks=[CallbackQueryHandler(cancel_checkout, pattern=r"^checkout_cancel$")],
        per_message=False,
    )
    application.add_handler(checkout_conv)

    # Commandes
    application.add_handler(CallbackQueryHandler(show_my_orders, pattern=r"^shop:my_orders$"))

    logger.info("Handlers commerce enregistrés")
