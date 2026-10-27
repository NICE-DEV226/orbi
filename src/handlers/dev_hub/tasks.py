"""
Orbi Dev dans Telegram — les tâches : liste filtrée, carte d'une exécution, création pas à pas, lancement.

Le parcours « nouvelle tâche » pose une question à la fois (projet, fournisseur, consigne) et saute celles dont la
réponse est évidente (un seul projet, un seul fournisseur). Rien n'est créé avant « Lancer ».
"""

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.bot.screen import edit_screen
from src.core.text import esc
from src.orbi_dev import cards, runner, service
from src.orbi_dev.look import PLUS, PRIMARY, SUCCESS, quote
from src.orbi_dev.models import IntegrationStatus
from src.orbi_dev.notifier import build_keyboard, first_line
from src.orbi_dev.present import STATUS_ICON, provider_name

from .common import (
    CB_CHANGE_PROJECT,
    CB_CHANGE_PROVIDER,
    CB_DISCARD,
    CB_EDIT,
    CB_GO,
    CB_LIST,
    CB_NEW,
    CB_NEW_IN_PROJECT,
    CB_NEW_REPO,
    CB_OPEN,
    CB_PICK_PROJECT,
    CB_PICK_PROVIDER,
    MAX_PROMPT,
    active_providers,
    authorize,
    back,
    button,
    clear_draft,
    draft_of,
    group_of,
    logger,
    recent_runs,
    show,
    title,
)
from .home import build_home, show_home
from .projects import cancel_markup

LIST_SIZE = 8
RUNS_WINDOW = 40


# ─────────────────────────────────────
# Liste et carte
# ─────────────────────────────────────

def _tabs(mode: str, ongoing: int, finished: int):
    def label(name: str, count: int, selected: bool) -> str:
        return f"{'● ' if selected else ''}{name} {count}"

    return [
        button(label("En cours", ongoing, mode == "a"), f"{CB_LIST}:a"),
        button(label("Terminées", finished, mode == "d"), f"{CB_LIST}:d"),
    ]


async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    runs = await recent_runs(owner, RUNS_WINDOW)
    ongoing = [r for r in runs if group_of(r[1]) in ("active", "attention")]
    finished = [r for r in runs if group_of(r[1]) == "done"]

    data = update.callback_query.data if update.callback_query else ""
    mode = "d" if data.endswith(":d") else "a" if data.endswith(":a") else ("a" if ongoing else "d")
    shown = (ongoing if mode == "a" else finished)[:LIST_SIZE]

    lines = [title("Tâches", "Appuyez sur une tâche pour la suivre." if shown else "")]
    if not shown:
        lines.append("Rien ici pour l'instant." if runs else "Aucune tâche pour l'instant.")
    rows = [_tabs(mode, len(ongoing), len(finished))] if runs else []
    rows += [
        [button(f"{STATUS_ICON[e.status]} {project} · {first_line(t.prompt, 28)}", f"{CB_OPEN}{e.id}")]
        for t, e, project in shown
    ]
    if not runs:
        rows.append([button(f"{PLUS} Nouvelle tâche", CB_NEW, PRIMARY)])
    rows.append([back()])
    await show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def show_execution(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
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
    rows.append([back("Tâches", CB_LIST)])
    await show(update, text, InlineKeyboardMarkup(rows))


# ─────────────────────────────────────
# Création pas à pas
# ─────────────────────────────────────

async def _last_used(owner: int) -> tuple[str | None, str | None]:
    """Projet et fournisseur de la dernière tâche : valeurs par défaut de /task."""
    tasks = await service.list_tasks(owner, limit=1)
    return (tasks[0].project_id, tasks[0].integration_id) if tasks else (None, None)


def _choice_markup(rows, extra=None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(rows + ([extra] if extra else []) + [[button("Annuler", CB_DISCARD)]])


async def advance(update: Update, context: ContextTypes.DEFAULT_TYPE, owner: int) -> None:
    """Pose la prochaine question du parcours, ou la confirmation quand tout est connu."""
    draft = draft_of(context)
    providers = await active_providers(owner)
    projects = await service.list_projects(owner)

    if not providers or not projects:  # rien à confier tant que la base n'est pas posée : retour à « pour commencer »
        clear_draft(context)
        await show(update, *await build_home(owner))
        return

    if "project_id" not in draft:
        if len(projects) == 1:
            draft["project_id"] = str(projects[0].id)
        else:
            last_project, _ = await _last_used(owner)
            ordered = sorted(projects, key=lambda p: str(p.id) != last_project)
            rows = [
                [button(p.name, f"{CB_PICK_PROJECT}{p.id}", PRIMARY if n == 0 else None)] for n, p in enumerate(ordered)
            ]
            text = title("Quel projet ?", "Le dernier utilisé est en premier.")
            await show(update, text, _choice_markup(rows, [button(f"{PLUS} Autre dépôt", CB_NEW_REPO)]))
            return

    if "integration_id" not in draft:
        if len(providers) == 1:
            draft["integration_id"] = str(providers[0].id)
        else:
            _, last_integration = await _last_used(owner)
            ordered = sorted(providers, key=lambda i: str(i.id) != last_integration)
            rows = [
                [button(i.label or provider_name(i.provider), f"{CB_PICK_PROVIDER}{i.id}", PRIMARY if n == 0 else None)]
                for n, i in enumerate(ordered)
            ]
            await show(update, title("Quel fournisseur ?"), _choice_markup(rows))
            return

    project = next((p for p in projects if str(p.id) == draft["project_id"]), None)
    provider = next((i for i in providers if str(i.id) == draft["integration_id"]), None)
    if project is None or provider is None:  # supprimé ou révoqué entre-temps
        draft.pop("project_id" if project is None else "integration_id", None)
        await advance(update, context, owner)
        return

    if not draft.get("prompt"):
        draft["step"] = "prompt"
        hint = "Décrivez la tâche en un message. Plus c'est précis (fichier, comportement attendu), meilleur est le résultat."
        await show(update, title(f"Que faut-il faire sur {esc(project.name)} ?", hint), cancel_markup())
        return

    draft["step"] = None
    prompt = draft["prompt"]
    shown = prompt if len(prompt) <= 1500 else prompt[:1499] + "…"
    text = (
        f"{title('Lancer cette tâche ?')}\n"
        f"<b>{esc(project.name)}</b>  ·  {esc(provider.label or provider_name(provider.provider))}\n\n"
        f"{quote(esc(shown))}"
    )
    change = [button("Projet", CB_CHANGE_PROJECT)]
    if len(providers) > 1:
        change.append(button("Fournisseur", CB_CHANGE_PROVIDER))
    rows = [
        [button("Lancer", CB_GO, SUCCESS)],
        [button("Modifier", CB_EDIT)] + change,
        [button("Annuler", CB_DISCARD)],
    ]
    await show(update, text, InlineKeyboardMarkup(rows))


async def start_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    clear_draft(context)
    await advance(update, context, owner)


async def new_task_in_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Depuis la fiche d'un projet : le projet est déjà choisi."""
    owner = await authorize(update, context)
    if owner is None:
        return
    project_id = update.callback_query.data.removeprefix(CB_NEW_IN_PROJECT)
    try:
        await service.get_active_project(owner, project_id)
    except service.NotFoundError:
        await update.callback_query.answer("Ce projet n'existe plus.", show_alert=True)
        return
    clear_draft(context)
    draft_of(context)["project_id"] = project_id
    await advance(update, context, owner)


async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/task consigne` : le projet et le fournisseur de la dernière tâche, puis confirmation. Sans texte : le parcours."""
    owner = await authorize(update, context)
    if owner is None:
        return
    clear_draft(context)
    prompt = " ".join(context.args or []).strip() if context.args else ""
    if update.message and update.message.text and prompt:  # le texte d'origine garde ses retours à la ligne
        prompt = update.message.text.partition(" ")[2].strip() or prompt
    if len(prompt) > MAX_PROMPT:
        await update.message.reply_text(f"Consigne trop longue ({len(prompt)} caractères, {MAX_PROMPT} au plus).")
        return
    draft = draft_of(context)
    if prompt:
        draft["prompt"] = prompt
        project_id, integration_id = await _last_used(owner)
        projects = {str(p.id) for p in await service.list_projects(owner)}
        providers = {str(i.id) for i in await active_providers(owner)}
        if project_id in projects:
            draft["project_id"] = project_id
        if integration_id in providers:
            draft["integration_id"] = integration_id
    await advance(update, context, owner)


async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_list(update, context)


async def pick_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    project_id = update.callback_query.data.removeprefix(CB_PICK_PROJECT)
    try:
        await service.get_active_project(owner, project_id)
    except service.NotFoundError:
        await update.callback_query.answer("Ce projet n'existe plus.", show_alert=True)
        return
    draft_of(context)["project_id"] = project_id
    await advance(update, context, owner)


async def pick_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
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
    draft_of(context)["integration_id"] = integration_id
    await advance(update, context, owner)


async def _change(update: Update, context: ContextTypes.DEFAULT_TYPE, key: str) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    draft_of(context).pop(key, None)
    await advance(update, context, owner)


async def change_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _change(update, context, "project_id")


async def change_provider(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _change(update, context, "integration_id")


async def edit_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _change(update, context, "prompt")


async def discard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Annuler revient à l'accueil : l'écran ne reste jamais sans issue."""
    await show_home(update, context)


# ─────────────────────────────────────
# Lancement
# ─────────────────────────────────────

async def _launch_safely(owner_id: int, execution_id: str) -> None:
    try:
        await runner.launch_execution(owner_id, execution_id)
    except Exception:
        logger.exception("Lancement %s en échec", execution_id)


async def launch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """« Lancer » : crée la tâche, démarre l'exécution, et l'écran de confirmation devient la carte de suivi."""
    owner = await authorize(update, context)
    if owner is None:
        return
    query = update.callback_query
    draft = draft_of(context)
    if not all(draft.get(key) for key in ("project_id", "integration_id", "prompt")):
        await query.answer("Ce brouillon a expiré : recommencez avec « Nouvelle tâche ».", show_alert=True)
        await show_home(update, context)
        return
    clear_draft(context)  # avant tout : un deuxième clic ne relance pas
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
