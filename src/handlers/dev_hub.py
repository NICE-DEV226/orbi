"""
Orbi — Orbi Dev dans Telegram : l'accueil des administrateurs.

Tout le parcours se fait dans la conversation : voir l'état de ses tâches, ajouter un dépôt en collant son adresse,
écrire une consigne, confirmer, suivre l'avancement sur une carte qui se met à jour seule. La seule chose qui reste sur
le web est la saisie d'une clé d'API (elle ne doit jamais passer par un chat).

Le brouillon d'une tâche en cours de création vit dans `context.user_data["dev"]` : il est oublié au redémarrage du bot
ou après 15 minutes d'inactivité, sans conséquence (rien n'est créé avant « Lancer »). Chaque bouton ne manipule que les
données de celui qui appuie : le service filtre toujours par propriétaire.
"""

import logging
import time

from telegram import BotCommand, BotCommandScopeChat, InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.error import TelegramError
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from src.bot.keyboards import CB_DEV_HOME, CB_MORE
from src.bot.screen import edit_screen
from src.core.config import get_settings
from src.core.text import esc
from src.orbi_dev import cards, runner, service
from src.orbi_dev.access import can_use_orbi_dev
from src.orbi_dev.look import PRIMARY, SUCCESS, btn, quote
from src.orbi_dev.models import Execution, IntegrationStatus, Project, Task
from src.orbi_dev.notifier import build_keyboard, first_line
from src.orbi_dev.present import STATUS_EMOJI, STATUS_INFO, ago, provider_name
from src.orbi_dev.repo import parse_repo

logger = logging.getLogger("orbi.handlers.dev_hub")

CB_HOME = CB_DEV_HOME
CB_NEW = "dv:new"
CB_LIST = "dv:list"
CB_PROJECTS = "dv:projects"
CB_ADD_PROJECT = "dv:addp"
CB_NEW_REPO = "dv:newrepo"
CB_CONNECTIONS = "dv:conn"
CB_PICK_PROJECT = "dv:p:"
CB_PICK_PROVIDER = "dv:i:"
CB_OPEN = "dv:e:"
CB_GO = "dv:go"
CB_EDIT = "dv:edit"
CB_CHANGE_PROJECT = "dv:chp"
CB_CHANGE_PROVIDER = "dv:chi"
CB_DISCARD = "dv:no"

MAX_PROMPT = 8000
DRAFT_TTL = 15 * 60
RECENT = 4
LIST_SIZE = 8

# Menu « / » du champ de saisie, réservé aux administrateurs (les autres ne voient pas des commandes inutilisables)
ADMIN_COMMANDS = [
    BotCommand("start", "Accueil Orbi Dev"),
    BotCommand("task", "Lancer une tâche : /task votre consigne"),
    BotCommand("tasks", "Voir vos tâches"),
    BotCommand("web", "Lien vers l'application web"),
]

NOT_ALLOWED = "🔒 Orbi Dev est réservé aux administrateurs pour l'instant."


# ─────────────────────────────────────
# Accès, brouillon, affichage
# ─────────────────────────────────────

def _allowed(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return can_use_orbi_dev((context.user_data or {}).get("db_user"))


def _draft(context: ContextTypes.DEFAULT_TYPE) -> dict:
    draft = context.user_data.setdefault("dev", {})
    if draft and time.monotonic() - draft.get("at", 0) > DRAFT_TTL:
        draft.clear()
    draft["at"] = time.monotonic()
    return draft


def _clear(context: ContextTypes.DEFAULT_TYPE) -> None:
    context.user_data.pop("dev", None)


async def _authorize(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int | None:
    """Retourne l'identifiant du propriétaire, ou répond « réservé » et retourne None."""
    query = update.callback_query
    if query is not None:
        await query.answer()
    if not _allowed(context):
        if query is not None:
            await query.answer(NOT_ALLOWED, show_alert=True)
        elif update.effective_message is not None:
            await update.effective_message.reply_text(NOT_ALLOWED)
        return None
    return update.effective_user.id


async def _show(update: Update, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    """Sous un bouton : remplace l'écran ; après une commande ou un message : écrit un nouveau message."""
    if update.callback_query is not None:
        await edit_screen(update.callback_query, text, markup)
    else:
        await update.effective_message.reply_text(text, reply_markup=markup)


def _button(label: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    return btn(label, data, style=style)


def _web_button(label: str, path: str, style: str | None = None) -> InlineKeyboardButton | None:
    """Ouvre une page de l'application web comme Mini App (Telegram exige une URL https publique)."""
    settings = get_settings()
    if not settings.public_https:
        return None
    return InlineKeyboardButton(label, web_app=WebAppInfo(url=f"{settings.BASE_URL.rstrip('/')}{path}"), style=style)


def _connections_button(style: str | None = None) -> InlineKeyboardButton:
    return _web_button("🔑 Connexions", "/dev/integrations", style) or _button("🔑 Connexions", CB_CONNECTIONS, style)


def _home_button() -> InlineKeyboardButton:
    return _button("← Orbi Dev", CB_HOME)


# ─────────────────────────────────────
# Données de l'accueil
# ─────────────────────────────────────

async def _active_providers(owner: int):
    return [i for i in await service.list_integrations(owner) if i.status == IntegrationStatus.ACTIVE]


async def _recent_runs(owner: int, limit: int) -> list[tuple[Task, Execution, str]]:
    """Dernière exécution de chacune des tâches les plus récentes, avec le nom de leur projet."""
    projects = {str(p.id): p.name for p in await service.list_projects(owner)}
    runs = []
    for task in await service.list_tasks(owner, limit=limit * 3):
        executions = await service.list_executions(owner, task_id=str(task.id), limit=1)
        if executions:
            runs.append((task, executions[0], projects.get(task.project_id, "projet supprimé")))
        if len(runs) == limit:
            break
    return runs


def _run_line(task: Task, execution: Execution, project: str) -> str:
    emoji = STATUS_EMOJI[execution.status]
    return (
        f"{emoji} <b>{esc(project)}</b>  {esc(first_line(task.prompt, 36))}\n"
        f"      <i>{STATUS_INFO[execution.status][0]} · {ago(execution.updated_at)}</i>"
    )


async def build_home(owner: int) -> tuple[str, InlineKeyboardMarkup]:
    projects = await service.list_projects(owner)
    providers = await _active_providers(owner)

    if not providers or not projects:
        steps = [
            (bool(providers), "Connecter un fournisseur", "Jules ou Cursor"),
            (bool(projects), "Ajouter un dépôt", "l'adresse GitHub suffit"),
        ]
        lines = ["🤖 <b>Orbi Dev</b>", "<i>Confiez des tâches de code à un agent, depuis Telegram.</i>", ""]
        next_step = next((i for i, (done, _, _) in enumerate(steps) if not done), len(steps))
        for i, (done, title, hint) in enumerate(steps + [(False, "Lancer une première tâche", "en une phrase")]):
            mark = "✅" if done else "⬜"
            lines.append(f"{mark} <b>{title}</b>  <i>{hint}</i>" if i == next_step else f"{mark} {title}")
        text = "\n".join(lines)
        rows = []
        if not providers:
            rows.append([_connections_button(PRIMARY)])
        if not projects:
            rows.append([_button("📁 Ajouter un dépôt", CB_NEW_REPO, PRIMARY if providers else None)])
        elif providers:
            rows.append([_button("✏️ Nouvelle tâche", CB_NEW, PRIMARY)])
        rows.append([_button("⋯ Plus", CB_MORE)])
        return text, InlineKeyboardMarkup(rows)

    runs = await _recent_runs(owner, RECENT)
    groups = [STATUS_INFO[e.status][3] for _, e, _ in runs]
    active, attention = groups.count("active"), groups.count("attention")
    if active or attention:
        parts = ([f"🔄 <b>{active}</b> en cours"] if active else []) + (
            [f"⚠️ <b>{attention}</b> à vérifier"] if attention else []
        )
        headline = "    ".join(parts)
    else:
        headline = "😌 Rien en cours."
    lines = ["🤖 <b>Orbi Dev</b>", "", headline]
    if runs:
        lines += ["", "<b>Récentes</b>"] + [_run_line(*run) for run in runs]
    else:
        lines += ["", "<i>Aucune tâche pour l'instant. Écrivez </i><code>/task</code><i> suivi de votre consigne.</i>"]

    app = _web_button("📱 Application", "/dev/")
    rows = [
        [_button("✏️ Nouvelle tâche", CB_NEW, PRIMARY)],
        [_button("📋 Tâches", CB_LIST), _button("📁 Projets", CB_PROJECTS)],
        [_connections_button()] + ([app] if app else []),
        [_button("⋯ Plus", CB_MORE)],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


# ─────────────────────────────────────
# Écrans de consultation
# ─────────────────────────────────────

async def _sync_commands(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> None:
    try:
        await context.bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id))
    except TelegramError as error:  # un confort : ne jamais empêcher l'accueil de s'afficher
        logger.warning("Menu des commandes non mis à jour : %s", error)


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    _clear(context)
    if update.callback_query is None:  # une commande tapée : bon moment pour afficher le menu des commandes
        await _sync_commands(context, update.effective_chat.id if update.effective_chat else owner)
    await _show(update, *await build_home(owner))


async def show_connections(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sans URL https publique, pas de Mini App : on explique comment ouvrir la page des clés."""
    if await _authorize(update, context) is None:
        return
    text = (
        "🔑 <b>Connexions</b>\n\n"
        "Les clés d'API se saisissent dans l'application web, <b>jamais dans ce chat</b>.\n\n"
        "Envoyez /web pour recevoir votre lien de connexion, puis ouvrez <b>Connexions</b>."
    )
    await _show(update, text, InlineKeyboardMarkup([[_home_button()]]))


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    runs = await _recent_runs(owner, LIST_SIZE)
    if not runs:
        text = "📋 <b>Tâches</b>\n\n<i>Aucune tâche pour l'instant.</i>"
        rows = [[_button("✏️ Nouvelle tâche", CB_NEW, PRIMARY)], [_home_button()]]
    else:
        text = "📋 <b>Tâches</b>\n\n<i>Appuyez sur une tâche pour la suivre.</i>"
        rows = [
            [_button(f"{STATUS_EMOJI[e.status]} {project} · {first_line(t.prompt, 28)}", f"{CB_OPEN}{e.id}")]
            for t, e, project in runs
        ]
        rows.append([_home_button()])
    await _show(update, text, InlineKeyboardMarkup(rows))


async def show_execution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    try:
        execution = await service.get_execution(owner, update.callback_query.data.removeprefix(CB_OPEN))
    except service.NotFoundError:
        await update.callback_query.answer("Tâche introuvable.", show_alert=True)
        return
    text, _ = await cards.render(execution)
    keyboard = build_keyboard(execution)
    rows = [list(row) for row in keyboard.inline_keyboard] if keyboard else []
    rows.append([_button("← Tâches", CB_LIST)])
    await _show(update, text, InlineKeyboardMarkup(rows))


async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    projects = await service.list_projects(owner)
    lines = ["📁 <b>Projets</b>", ""]
    lines += [f"<b>{esc(p.name)}</b>\n<code>{esc(p.repo_url.removeprefix('https://'))}</code>" for p in projects] or [
        "<i>Aucun dépôt pour l'instant.</i>"
    ]
    rows = [[_button("➕ Ajouter un dépôt", CB_ADD_PROJECT, PRIMARY)], [_home_button()]]
    await _show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


# ─────────────────────────────────────
# Ajout d'un dépôt
# ─────────────────────────────────────

def _cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button("Annuler", CB_DISCARD)]])


async def _ask_repo(update: Update, context: ContextTypes.DEFAULT_TYPE, *, then_task: bool) -> None:
    draft = _draft(context)
    draft.clear()
    draft.update(step="repo", then_task=then_task, at=time.monotonic())
    text = (
        "📁 <b>Quel dépôt ?</b>\n\n"
        "Collez son adresse GitHub :\n"
        "<code>https://github.com/vous/projet</code>\n"
        "ou simplement <code>vous/projet</code>."
    )
    await _show(update, text, _cancel_markup())


async def ask_repo_from_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _authorize(update, context) is not None:
        await _ask_repo(update, context, then_task=False)


async def ask_repo_for_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await _authorize(update, context) is not None:
        await _ask_repo(update, context, then_task=True)


async def _add_project(owner: int, text: str) -> tuple[Project | None, bool]:
    """(projet, déjà connu). Un dépôt déjà ajouté est réutilisé, jamais dupliqué."""
    repo = parse_repo(text)
    if repo is None:
        return None, False
    for project in await service.list_projects(owner):
        if project.repo_url.lower() == repo.url.lower():
            return project, True
    return await service.create_project(owner, repo.name, repo.url, repo.branch), False


# ─────────────────────────────────────
# Création d'une tâche
# ─────────────────────────────────────

async def _last_used(owner: int) -> tuple[str | None, str | None]:
    """Projet et fournisseur de la dernière tâche : valeurs par défaut de /task."""
    tasks = await service.list_tasks(owner, limit=1)
    return (tasks[0].project_id, tasks[0].integration_id) if tasks else (None, None)


def _choice_markup(rows: list[list[InlineKeyboardButton]], extra: list[InlineKeyboardButton] | None = None):
    rows = rows + ([extra] if extra else []) + [[_button("Annuler", CB_DISCARD)]]
    return InlineKeyboardMarkup(rows)


async def _advance(update: Update, context: ContextTypes.DEFAULT_TYPE, owner: int) -> None:
    """Pose la prochaine question du parcours, ou la confirmation quand tout est connu."""
    draft = _draft(context)
    providers = await _active_providers(owner)
    projects = await service.list_projects(owner)

    if not providers or not projects:
        _clear(context)
        text, markup = await build_home(owner)
        await _show(update, text, markup)
        return

    if "project_id" not in draft:
        if len(projects) == 1:
            draft["project_id"] = str(projects[0].id)
        else:
            last_project, _ = await _last_used(owner)
            ordered = sorted(projects, key=lambda p: str(p.id) != last_project)
            rows = [
                [_button(f"📁 {p.name}", f"{CB_PICK_PROJECT}{p.id}", PRIMARY if n == 0 else None)]
                for n, p in enumerate(ordered)
            ]
            text = "📁 <b>Quel projet ?</b>\n\n<i>Le dernier utilisé est en premier.</i>"
            await _show(update, text, _choice_markup(rows, [_button("➕ Autre dépôt", CB_NEW_REPO)]))
            return

    if "integration_id" not in draft:
        if len(providers) == 1:
            draft["integration_id"] = str(providers[0].id)
        else:
            _, last_integration = await _last_used(owner)
            ordered = sorted(providers, key=lambda i: str(i.id) != last_integration)
            rows = [
                [_button(f"🤖 {i.label or provider_name(i.provider)}", f"{CB_PICK_PROVIDER}{i.id}",
                         PRIMARY if n == 0 else None)]
                for n, i in enumerate(ordered)
            ]
            await _show(update, "🤖 <b>Quel fournisseur ?</b>", _choice_markup(rows))
            return

    if not draft.get("prompt"):
        draft["step"] = "prompt"
        project = next((p for p in projects if str(p.id) == draft["project_id"]), None)
        name = esc(project.name) if project else "ce projet"
        text = (
            f"✏️ <b>Que faut-il faire sur {name} ?</b>\n\n"
            "Décrivez la tâche en un message.\n<i>Plus c'est précis (fichier, comportement attendu), meilleur est le résultat.</i>"
        )
        await _show(update, text, _cancel_markup())
        return

    draft["step"] = None
    project = next((p for p in projects if str(p.id) == draft["project_id"]), None)
    provider = next((i for i in providers if str(i.id) == draft["integration_id"]), None)
    if project is None or provider is None:  # supprimé ou révoqué entre-temps
        draft.pop("project_id", None) if project is None else draft.pop("integration_id", None)
        await _advance(update, context, owner)
        return
    prompt = draft["prompt"]
    shown = prompt if len(prompt) <= 1500 else prompt[:1499] + "…"
    text = (
        "▶️ <b>Lancer cette tâche ?</b>\n\n"
        f"📁 <b>{esc(project.name)}</b>    🤖 {esc(provider.label or provider_name(provider.provider))}\n\n"
        f"{quote(esc(shown))}"
    )
    change = [_button("📁 Projet", CB_CHANGE_PROJECT)]
    if len(providers) > 1:
        change.append(_button("🤖 Fournisseur", CB_CHANGE_PROVIDER))
    rows = [
        [_button("▶️ Lancer", CB_GO, SUCCESS)],
        [_button("✏️ Modifier", CB_EDIT)] + change,
        [_button("Annuler", CB_DISCARD)],
    ]
    await _show(update, text, InlineKeyboardMarkup(rows))


async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    _clear(context)
    await _advance(update, context, owner)


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/task consigne` : le projet et le fournisseur de la dernière tâche, puis confirmation. Sans texte : le parcours."""
    owner = await _authorize(update, context)
    if owner is None:
        return
    _clear(context)
    prompt = " ".join(context.args or []).strip() if context.args else ""
    # Le texte d'origine garde ses retours à la ligne
    if update.message and update.message.text and prompt:
        prompt = update.message.text.partition(" ")[2].strip() or prompt
    if len(prompt) > MAX_PROMPT:
        await update.message.reply_text(f"Consigne trop longue ({len(prompt)} caractères, {MAX_PROMPT} au plus).")
        return
    draft = _draft(context)
    if prompt:
        draft["prompt"] = prompt
        project_id, integration_id = await _last_used(owner)
        projects = {str(p.id) for p in await service.list_projects(owner)}
        providers = {str(i.id) for i in await _active_providers(owner)}
        if project_id in projects:
            draft["project_id"] = project_id
        if integration_id in providers:
            draft["integration_id"] = integration_id
    await _advance(update, context, owner)


async def pick_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    project_id = update.callback_query.data.removeprefix(CB_PICK_PROJECT)
    try:
        await service.get_project(owner, project_id)
    except service.NotFoundError:
        await update.callback_query.answer("Ce projet n'existe plus.", show_alert=True)
        return
    _draft(context)["project_id"] = project_id
    await _advance(update, context, owner)


async def pick_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    integration_id = update.callback_query.data.removeprefix(CB_PICK_PROVIDER)
    try:
        integration = await service.get_integration(owner, integration_id)
    except service.NotFoundError:
        integration = None
    if integration is None or integration.status != IntegrationStatus.ACTIVE:
        await update.callback_query.answer("Cette connexion n'est plus active.", show_alert=True)
        return
    _draft(context)["integration_id"] = integration_id
    await _advance(update, context, owner)


async def change_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    _draft(context).pop("project_id", None)
    await _advance(update, context, owner)


async def change_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    _draft(context).pop("integration_id", None)
    await _advance(update, context, owner)


async def edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await _authorize(update, context)
    if owner is None:
        return
    _draft(context).pop("prompt", None)
    await _advance(update, context, owner)


async def discard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Annuler revient à l'accueil : l'écran ne reste jamais sans issue."""
    await show_home(update, context)


async def _launch_safely(owner_id: int, execution_id: str) -> None:
    try:
        await runner.launch_execution(owner_id, execution_id)
    except Exception:
        logger.exception("Lancement %s en échec", execution_id)


async def launch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """« Lancer » : crée la tâche, démarre l'exécution, et l'écran de confirmation devient la carte de suivi."""
    owner = await _authorize(update, context)
    if owner is None:
        return
    query = update.callback_query
    draft = _draft(context)
    if not all(draft.get(key) for key in ("project_id", "integration_id", "prompt")):
        await query.answer("Ce brouillon a expiré : recommencez avec « Nouvelle tâche ».", show_alert=True)
        await show_home(update, context)
        return
    _clear(context)  # avant tout : un deuxième clic ne relance pas
    try:
        task = await service.create_task(owner, draft["project_id"], draft["integration_id"], draft["prompt"])
        execution = await service.create_execution(owner, str(task.id))
    except (service.NotFoundError, service.ConflictError):
        await query.answer("Ce projet ou cette connexion n'est plus disponible.", show_alert=True)
        await show_home(update, context)
        return
    context.application.create_task(_launch_safely(owner, str(execution.id)))
    text, markup = await cards.render(execution)
    await edit_screen(query, text, markup)
    await cards.attach(execution, query.message.chat_id, query.message.message_id)


# ─────────────────────────────────────
# Messages libres : dépôt ou consigne attendus
# ─────────────────────────────────────

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prend le message uniquement si le parcours attend un dépôt ou une consigne ; sinon ne fait rien."""
    if not _allowed(context) or not context.user_data.get("dev"):
        return
    draft = _draft(context)
    step = draft.get("step")
    if step not in ("repo", "prompt"):
        return
    owner = update.effective_user.id
    text = (update.message.text or "").strip()

    if step == "repo":
        project, known = await _add_project(owner, text)
        if project is None:
            await update.message.reply_text(
                "🤔 <b>Je n'ai pas reconnu ce dépôt.</b>\n\nCollez l'adresse de sa page GitHub :\n"
                "<code>https://github.com/vous/projet</code>\nou <code>vous/projet</code>.",
                reply_markup=_cancel_markup(),
            )
            return
        if draft.get("then_task"):
            draft.pop("step")
            draft["project_id"] = str(project.id)
            await _advance(update, context, owner)
            return
        _clear(context)
        note = "déjà dans vos projets" if known else "ajouté"
        await update.message.reply_text(
            f"✅ <b>{esc(project.name)}</b> {note}.",
            reply_markup=InlineKeyboardMarkup([[_button("✏️ Nouvelle tâche", CB_NEW, PRIMARY)], [_home_button()]]),
        )
        return

    if not text or len(text) > MAX_PROMPT:
        await update.message.reply_text(
            f"✂️ <b>Trop long.</b> Décrivez la tâche en {MAX_PROMPT} caractères au plus ({len(text)} reçus).",
            reply_markup=_cancel_markup(),
        )
        return
    draft["prompt"] = text
    await _advance(update, context, owner)


# ─────────────────────────────────────
# Commandes et enregistrement
# ─────────────────────────────────────

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_list(update, context)


def register_dev_hub_handlers(application) -> None:
    on = application.add_handler
    on(CommandHandler("dev", show_home, filters=filters.ChatType.PRIVATE))
    on(CommandHandler("task", task_command, filters=filters.ChatType.PRIVATE))
    on(CommandHandler("tasks", tasks_command, filters=filters.ChatType.PRIVATE))
    for pattern, callback in (
        (CB_HOME, show_home), (CB_NEW, start_task), (CB_LIST, show_list), (CB_PROJECTS, show_projects),
        (CB_ADD_PROJECT, ask_repo_from_projects), (CB_NEW_REPO, ask_repo_for_task), (CB_CONNECTIONS, show_connections),
        (CB_GO, launch), (CB_EDIT, edit_prompt), (CB_CHANGE_PROJECT, change_project),
        (CB_CHANGE_PROVIDER, change_provider), (CB_DISCARD, discard),
    ):
        on(CallbackQueryHandler(callback, pattern=f"^{pattern}$"))
    on(CallbackQueryHandler(pick_project, pattern=rf"^{CB_PICK_PROJECT}"))
    on(CallbackQueryHandler(pick_provider, pattern=rf"^{CB_PICK_PROVIDER}"))
    on(CallbackQueryHandler(show_execution, pattern=rf"^{CB_OPEN}"))
    # Groupe 1 : ne retire rien aux autres parcours (support, productivité) qui lisent aussi les messages texte
    on(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.PRIVATE, on_text), group=1)
    logger.info("Handlers Orbi Dev (Telegram) enregistrés")
