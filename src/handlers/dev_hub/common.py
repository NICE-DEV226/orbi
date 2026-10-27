"""
Orbi Dev dans Telegram — socle commun : callbacks, accès, brouillon, boutons, données partagées.

Le brouillon d'une tâche en cours de création vit dans `context.user_data["dev"]` : il est oublié au redémarrage du bot
ou après 15 minutes d'inactivité, sans conséquence (rien n'est créé avant « Lancer »). Chaque bouton ne manipule que les
données de celui qui appuie : le service filtre toujours par propriétaire.
"""

import logging
import time

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.ext import ContextTypes

from src.bot.keyboards import CB_DEV_HOME
from src.bot.screen import edit_screen
from src.core.config import get_settings
from src.core.text import esc
from src.orbi_dev import service
from src.orbi_dev.access import can_use_orbi_dev
from src.orbi_dev.inputs import MAX_PROMPT, MIN_PROMPT  # noqa: F401 (réexportés)
from src.orbi_dev.look import BACK, btn
from src.orbi_dev.models import Execution, IntegrationStatus, Task
from src.orbi_dev.notifier import first_line
from src.orbi_dev.present import STATUS_ICON, STATUS_INFO, ago

logger = logging.getLogger("orbi.handlers.dev_hub")

# ── Écrans ──
CB_HOME = CB_DEV_HOME
CB_LIST = "dv:list"  # + ":a" (en cours) ou ":d" (terminées)
CB_PROJECTS = "dv:projects"
CB_PROJECT = "dv:pr:"  # + id : fiche d'un projet
CB_CONNECTIONS = "dv:conn"
CB_SETTINGS = "dv:set"
CB_NOTIFICATIONS = "dv:notif"
CB_OPEN = "dv:e:"  # + id d'exécution

# ── Parcours « nouvelle tâche » ──
CB_NEW = "dv:new"
CB_NEW_IN_PROJECT = "dv:pn:"  # + id de projet
CB_ADD_PROJECT = "dv:addp"
CB_NEW_REPO = "dv:newrepo"
CB_REPO_AGAIN = "dv:repoagain"  # corriger l'adresse saisie
CB_REPO_OK = "dv:repook"  # confirmer l'ajout du dépôt en attente
CB_RENAME = "dv:prn:"  # + id de projet
CB_BRANCH = "dv:prb:"
CB_REMOVE = "dv:prd:"
CB_REMOVE_OK = "dv:prx:"
CB_PICK_PROJECT = "dv:p:"
CB_PICK_PROVIDER = "dv:i:"
CB_GO = "dv:go"
CB_EDIT = "dv:edit"
CB_CHANGE_PROJECT = "dv:chp"
CB_CHANGE_PROVIDER = "dv:chi"
CB_DISCARD = "dv:no"

DRAFT_TTL = 15 * 60

NOT_ALLOWED = "Orbi Dev est réservé aux administrateurs pour l'instant."


# ─────────────────────────────────────
# Accès et brouillon
# ─────────────────────────────────────

def allowed(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return can_use_orbi_dev((context.user_data or {}).get("db_user"))


def is_stale(draft: dict) -> bool:
    return bool(draft) and time.monotonic() - draft.get("at", 0) > DRAFT_TTL


def draft_of(context: ContextTypes.DEFAULT_TYPE) -> dict:
    draft = context.user_data.setdefault("dev", {})
    if is_stale(draft):
        draft.clear()
    draft["at"] = time.monotonic()
    return draft


def clear_draft(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("dev", None)


async def authorize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Retourne l'identifiant du propriétaire, ou répond « réservé » et retourne None."""
    query = update.callback_query
    if query is not None:
        await query.answer()
    if not allowed(context):
        if query is not None:
            await query.answer(NOT_ALLOWED, show_alert=True)
        elif update.effective_message is not None:
            await update.effective_message.reply_text(NOT_ALLOWED)
        return None
    return update.effective_user.id


# ─────────────────────────────────────
# Affichage et boutons
# ─────────────────────────────────────

async def show(update: Update, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Sous un bouton : remplace l'écran ; après une commande ou un message : écrit un nouveau message."""
    if update.callback_query is not None:
        await edit_screen(update.callback_query, text, markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


def button(label: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    return btn(label, data, style=style)


def web_button(label: str, path: str, style: str | None = None) -> InlineKeyboardButton | None:
    """Ouvre une page de l'application web comme Mini App (Telegram exige une URL https publique)."""
    settings = get_settings()
    if not settings.public_https:
        return None
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=f"{settings.BASE_URL.rstrip('/')}{path}"), style=style)


def back(label: str = "Accueil", target: str = CB_HOME) -> InlineKeyboardButton:
    """Dernière ligne de chaque écran : toujours une issue."""
    return button(f"{BACK} {label}", target)


def title(text: str, hint: str = "") -> str:
    """En-tête d'écran : titre en gras, puis une ligne d'aide en italique."""
    return f"<b>{text}</b>\n<i>{hint}</i>\n" if hint else f"<b>{text}</b>\n"


# ─────────────────────────────────────
# Données partagées
# ─────────────────────────────────────

async def active_providers(owner: int):
    return [i for i in await service.list_integrations(owner) if i.status == IntegrationStatus.ACTIVE]


async def recent_runs(owner: int, limit: int) -> list[tuple[Task, Execution, str]]:
    """Dernière exécution des tâches les plus récentes (deux requêtes), avec le nom de leur projet."""
    projects = {str(p.id): p.name for p in await service.list_projects(owner)}
    latest: dict[str, Execution] = {}
    for execution in await service.list_executions(owner, limit=limit * 5):  # du plus récent au plus ancien
        latest.setdefault(execution.task_id, execution)
    runs = []
    for task in await service.list_tasks(owner, limit=limit * 2):
        if str(task.id) in latest:
            runs.append((task, latest[str(task.id)], projects.get(task.project_id, "projet supprimé")))
        if len(runs) == limit:
            break
    return runs


def group_of(execution: Execution) -> str:
    """« active », « attention » ou « done » : le vocabulaire du web."""
    return STATUS_INFO[execution.status][3]


def run_line(task: Task, execution: Execution, project: str) -> str:
    return (
        f"{STATUS_ICON[execution.status]} <b>{esc(project)}</b>  {esc(first_line(task.prompt, 36))}\n"
        f"      <i>{STATUS_INFO[execution.status][0]} · {ago(execution.updated_at)}</i>"
    )
