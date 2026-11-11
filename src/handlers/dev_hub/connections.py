"""
Orbi Dev dans Telegram — connexions fournisseurs : liste, ajout d'une clé, révocation.

Toute la gestion vit ici, sans passer par le web : choisir un fournisseur, envoyer sa clé API
(le message est effacé du chat après lecture — une clé ne reste pas dans l'historique), puis
Orbi la vérifie chez le fournisseur avant de la chiffrer et la stocker. La révocation est locale
(secret effacé, exécutions actives passées en « à vérifier ») ; la clé reste à supprimer chez le
fournisseur — aucune API de révocation n'est exploitée.
"""

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.text import esc
from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import ConnectorError
from src.orbi_dev.connectors.registry import available_providers
from src.orbi_dev.inputs import clean_text
from src.orbi_dev.look import DANGER, PRIMARY
from src.orbi_dev.models import IntegrationStatus
from src.orbi_dev.present import PROVIDER_HELP, capabilities, provider_name

from .common import (
    CB_CONN_ADD,
    CB_CONN_PICK,
    CB_CONN_REVOKE,
    CB_CONN_REVOKE_OK,
    CB_CONNECTIONS,
    authorize,
    back,
    button,
    draft_of,
    logger,
    show,
    title,
)
from .projects import cancel_markup

MAX_KEY_LEN = 400
STATE_LINES = {
    IntegrationStatus.ACTIVE: "● Actif",
    IntegrationStatus.INVALID: "▲ Clé refusée par le fournisseur",
    IntegrationStatus.REVOKED: "⊘ Révoquée",
}


async def connections_view(owner: int) -> tuple[str, InlineKeyboardMarkup]:
    """Écran « Connexions » : fournisseurs branchés, ajout et révocation — tout dans Telegram."""
    integrations = [i for i in await service.list_integrations(owner) if i.status in STATE_LINES]
    lines = [title("Connexions", "Les clés sont chiffrées et jamais réaffichées.")]
    rows: list[list] = []
    for integration in integrations:
        name = esc(integration.label or provider_name(integration.provider))
        what = capabilities(integration.capabilities)
        lines.append(f"<b>{name}</b>  <i>{esc(provider_name(integration.provider))}</i>")
        lines.append(f"      {STATE_LINES[integration.status]}" + (f" · {esc(what)}" if what else ""))
        if integration.status != IntegrationStatus.REVOKED:
            rows.append([button("Révoquer", f"{CB_CONN_REVOKE}{integration.id}")])
    if not integrations:
        lines.append("Aucun fournisseur connecté.")
    rows.append([button("Ajouter une connexion", CB_CONN_ADD, PRIMARY)])
    rows.append([back()])
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def show_connect_providers(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Écran « ajouter une connexion » : un bouton par fournisseur disponible."""
    owner = await authorize(update, context)
    if owner is None:
        return
    providers = available_providers()
    lines = [
        title("Ajouter une connexion", "Choisissez le fournisseur, puis envoyez sa clé API."),
        "",
    ]
    for provider in providers:
        help_text = PROVIDER_HELP.get(provider)
        lines.append(f"<b>{provider_name(provider)}</b>" + (f" — {esc(help_text)}" if help_text else ""))
        lines.append("")
    rows = [[button(provider_name(p), f"{CB_CONN_PICK}{p}", PRIMARY if i == 0 else None)] for i, p in enumerate(providers)]
    rows.append([back("Connexions", CB_CONNECTIONS)])
    await show(update, "\n".join(lines).rstrip(), InlineKeyboardMarkup(rows))


async def pick_connect_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Arme la saisie de la clé pour le fournisseur choisi."""
    owner = await authorize(update, context)
    if owner is None:
        return
    provider = update.callback_query.data.removeprefix(CB_CONN_PICK)
    if provider not in available_providers():
        await update.callback_query.answer("Fournisseur indisponible.", show_alert=True)
        return
    draft_of(context).update({"step": "apikey", "conn_provider": provider})
    help_text = PROVIDER_HELP.get(provider, "")
    await show(
        update,
        title(
            f"Clé {provider_name(provider)}",
            "Envoyez la clé API en un seul message. "
            "Elle est vérifiée puis chiffrée — le message sera effacé de ce chat.\n\n"
            + (help_text if help_text else "")
        ),
        cancel_markup(),
    )


async def handle_apikey_text(
    update: Update, context: ContextTypes.DEFAULT_TYPE, owner: int, text: str
) -> None:
    """« apikey » : vérifie et enregistre la clé, puis efface le message qui la contenait."""
    draft = draft_of(context)
    provider = draft.pop("conn_provider", None)
    draft.pop("step", None)
    chat_id = update.effective_chat.id
    bot = context.bot

    async def say(text_html: str, markup=None) -> None:
        await bot.send_message(chat_id=chat_id, text=text_html, reply_markup=markup)

    if provider not in available_providers():
        await say("Ce parcours de connexion a expiré : recommencez depuis « Connexions ».")
        return
    key = clean_text(text)
    if not key or "\n" in key or len(key) > MAX_KEY_LEN or len(key) < 8:
        await say(
            "<b>Clé invalide.</b> Envoyez-la en un seul message (lettres, chiffres et symboles, "
            "8 caractères au moins)."
        )
        return

    # La clé ne reste pas dans l'historique du chat : le message est effacé au plus vite.
    try:
        await update.message.delete()
    except Exception:
        logger.debug("Message de clé non effaçable", exc_info=True)

    try:
        await runner.connect_integration(owner, provider, key)
    except ConnectorError as e:
        await say(f"<b>Connexion refusée.</b> {esc(e.message)}")
        return
    except Exception:
        logger.exception("Connexion %s en échec", provider)
        await say("<b>Connexion impossible.</b> Réessayez dans un instant.")
        return

    view_text, markup = await connections_view(owner)
    await say(f"<b>{provider_name(provider)} connecté.</b>\n\n" + view_text, markup)


async def confirm_revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Confirmation avant de révoquer une connexion."""
    owner = await authorize(update, context)
    if owner is None:
        return
    integration_id = update.callback_query.data.removeprefix(CB_CONN_REVOKE)
    try:
        integration = await service.get_integration(owner, integration_id)
    except service.NotFoundError:
        await update.callback_query.answer("Connexion introuvable.", show_alert=True)
        return
    name = esc(integration.label or provider_name(integration.provider))
    await show(
        update,
        title(
            f"Révoquer {name} ?",
            "La clé est effacée d'Orbi et les exécutions en cours passent en « à vérifier ». "
            "Pensez à supprimer la clé dans le tableau de bord du fournisseur.",
        ),
        InlineKeyboardMarkup([
            [button("Révoquer", f"{CB_CONN_REVOKE_OK}{integration_id}", DANGER),
             button("Annuler", CB_CONNECTIONS)],
        ]),
    )


async def revoke(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Révoque la connexion après confirmation."""
    owner = await authorize(update, context)
    if owner is None:
        return
    integration_id = update.callback_query.data.removeprefix(CB_CONN_REVOKE_OK)
    try:
        await runner.revoke_integration(owner, integration_id)
    except service.NotFoundError:
        await update.callback_query.answer("Connexion introuvable.", show_alert=True)
        return
    view_text, markup = await connections_view(owner)
    await show(update, "<b>Connexion révoquée.</b>\n\n" + view_text, markup)
