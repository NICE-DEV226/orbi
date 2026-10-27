"""
Orbi Dev dans Telegram — l'accueil et ses écrans de niveau 1 : tableau d'état, connexions, réglages.

Structure du bot pour un administrateur :

    Accueil ─┬─ + Nouvelle tâche   (tasks.py)
             ├─ Tâches             (tasks.py)       → carte d'une exécution
             ├─ Projets            (projects.py)    → fiche d'un projet
             ├─ Connexions         (ici)
             └─ Réglages           (ici)            → autres modules (menu historique)
"""

from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardMarkup, Update
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from src.bot.keyboards import CB_MORE
from src.core.text import esc
from src.models.user import NotificationPreferences
from src.orbi_dev import service
from src.orbi_dev.look import PLUS, PRIMARY
from src.orbi_dev.models import IntegrationStatus
from src.orbi_dev.present import STATUS_ICON, capabilities, provider_name

from .common import (
    CB_CONNECTIONS,
    CB_LIST,
    CB_NEW,
    CB_NEW_REPO,
    CB_NOTIFICATIONS,
    CB_PROJECTS,
    CB_SETTINGS,
    active_providers,
    authorize,
    back,
    button,
    clear_draft,
    group_of,
    logger,
    recent_runs,
    run_line,
    show,
    title,
    web_button,
)

RECENT = 4

# Menu « / » du champ de saisie, réservé aux administrateurs (les autres ne voient pas des commandes inutilisables)
ADMIN_COMMANDS = [
    BotCommand("start", "Accueil Orbi Dev"),
    BotCommand("task", "Lancer une tâche : /task votre consigne"),
    BotCommand("tasks", "Voir vos tâches"),
    BotCommand("web", "Lien vers l'application web"),
]


def connections_button(style: str | None = None):
    """Mini App quand l'URL publique est en https, sinon l'écran qui explique comment ouvrir la page web."""
    return web_button("Connexions", "/dev/integrations", style) or button("Connexions", CB_CONNECTIONS, style)


async def build_home(owner: int) -> tuple[str, InlineKeyboardMarkup]:
    projects = await service.list_projects(owner)
    providers = await active_providers(owner)

    if not providers or not projects:
        steps = [
            (bool(providers), "Connecter un fournisseur", "Jules ou Cursor"),
            (bool(projects), "Ajouter un dépôt", "l'adresse GitHub suffit"),
            (False, "Lancer une première tâche", "en une phrase"),
        ]
        next_step = next(i for i, (done, _, _) in enumerate(steps) if not done)
        lines = [title("Orbi Dev", "Confiez des tâches de code à un agent, depuis Telegram.")]
        for i, (done, name, hint) in enumerate(steps):
            mark = "✓" if done else "○"
            lines.append(f"{mark} <b>{name}</b>  <i>{hint}</i>" if i == next_step else f"{mark} {name}")
        rows = []
        if not providers:
            rows.append([connections_button(PRIMARY)])
        if not projects:
            rows.append([button(f"{PLUS} Ajouter un dépôt", CB_NEW_REPO, PRIMARY if providers else None)])
        elif providers:
            rows.append([button(f"{PLUS} Nouvelle tâche", CB_NEW, PRIMARY)])
        rows.append([button("Réglages", CB_SETTINGS)])
        return "\n".join(lines), InlineKeyboardMarkup(rows)

    runs = await recent_runs(owner, RECENT)
    groups = [group_of(e) for _, e, _ in runs]
    active, attention = groups.count("active"), groups.count("attention")
    counters = ([f"{STATUS_ICON['running']} <b>{active}</b> en cours"] if active else []) + (
        [f"{STATUS_ICON['needs_attention']} <b>{attention}</b> à vérifier"] if attention else []
    )
    lines = [title("Orbi Dev", "Vos agents de code, depuis Telegram."), "    ".join(counters) or "Rien en cours."]
    if runs:
        lines += ["", "<b>Récentes</b>"] + [run_line(*run) for run in runs]
    else:
        lines += ["", "<i>Aucune tâche pour l'instant. Écrivez </i><code>/task</code><i> suivi de votre consigne.</i>"]

    rows = [
        [button(f"{PLUS} Nouvelle tâche", CB_NEW, PRIMARY)],
        [button("Tâches", CB_LIST), button("Projets", CB_PROJECTS)],
        [button("Connexions", CB_CONNECTIONS), button("Réglages", CB_SETTINGS)],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def sync_commands(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    try:
        await context.bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id))
    except TelegramError as error:  # un confort : ne jamais empêcher l'accueil de s'afficher
        logger.warning("Menu des commandes non mis à jour : %s", error)


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    clear_draft(context)
    if update.callback_query is None:  # une commande tapée : bon moment pour afficher le menu des commandes
        await sync_commands(context, update.effective_chat.id if update.effective_chat else owner)
    await show(update, *await build_home(owner))


# ─────────────────────────────────────
# Connexions
# ─────────────────────────────────────

STATE_LINES = {
    IntegrationStatus.ACTIVE: "● Actif",
    IntegrationStatus.INVALID: "▲ Clé refusée par le fournisseur",
}


async def show_connections(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    integrations = [i for i in await service.list_integrations(owner) if i.status in STATE_LINES]
    lines = [title("Connexions", "Les clés se saisissent sur la page web, jamais dans ce chat.")]
    for integration in integrations:
        name = esc(integration.label or provider_name(integration.provider))
        what = capabilities(integration.capabilities)
        lines.append(f"<b>{name}</b>  <i>{esc(provider_name(integration.provider))}</i>")
        lines.append(f"      {STATE_LINES[integration.status]}" + (f" · {esc(what)}" if what else ""))
    if not integrations:
        lines.append("Aucun fournisseur connecté.")

    manage = web_button("Gérer les clés", "/dev/integrations", PRIMARY)
    rows = [[manage]] if manage else []
    if manage is None:
        lines += ["", "Envoyez /web pour recevoir votre lien de connexion, puis ouvrez <b>Connexions</b>."]
    rows.append([back()])
    await show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


# ─────────────────────────────────────
# Réglages
# ─────────────────────────────────────

def _alerts_enabled(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return NotificationPreferences.DEV_RUNS in context.user_data["db_user"].enabled_notifications


async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorize(update, context) is None:
        return
    enabled = _alerts_enabled(context)
    lines = [
        title("Réglages"),
        f"Alertes de fin de tâche    <b>{'activées' if enabled else 'désactivées'}</b>",
        "<i>Un message vous prévient quand une tâche se termine, échoue ou demande de l'attention.</i>",
    ]
    rows = [[button("Désactiver les alertes" if enabled else "Activer les alertes", CB_NOTIFICATIONS)]]
    app = web_button("Application web", "/dev/")
    if app:
        rows.append([app])
    rows.append([button("Autres modules", CB_MORE)])
    rows.append([back()])
    await show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def toggle_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorize(update, context) is None:
        return
    user = context.user_data["db_user"]
    if NotificationPreferences.DEV_RUNS in user.enabled_notifications:
        user.enabled_notifications.remove(NotificationPreferences.DEV_RUNS)
    else:
        user.enabled_notifications.append(NotificationPreferences.DEV_RUNS)
    user.touch()
    await user.save()
    await show_settings(update, context)

