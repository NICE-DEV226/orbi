"""
Orbi Dev dans Telegram — les projets : liste, fiche, ajout d'un dépôt, renommage, branche, retrait.

Ajouter un dépôt crée un projet, et rien n'est créé sans que l'utilisateur ait vu de quoi il s'agit :
adresse collée → vérification sur GitHub → écran de confirmation → création. Les saisies suivantes (nom, branche) suivent
le même principe : lues, validées avec une raison en cas de refus, puis appliquées.
"""

import time

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.text import esc
from src.orbi_dev import service
from src.orbi_dev.github import Lookup, RepoInfo, lookup_repo
from src.orbi_dev.inputs import MAX_NAME, Repo, parse_branch, parse_name, parse_repo
from src.orbi_dev.look import DANGER, PLUS, PRIMARY
from src.orbi_dev.models import Project
from src.orbi_dev.present import ago

from .common import (
    CB_ADD_PROJECT,
    CB_BRANCH,
    CB_DISCARD,
    CB_NEW_IN_PROJECT,
    CB_PROJECT,
    CB_PROJECTS,
    CB_REMOVE,
    CB_REMOVE_OK,
    CB_RENAME,
    CB_REPO_AGAIN,
    CB_REPO_OK,
    authorize,
    back,
    button,
    clear_draft,
    draft_of,
    show,
    title,
)


def cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[button("Annuler", CB_DISCARD)]])


def _branch_label(project: Project) -> str:
    return esc(project.default_branch) if project.default_branch else "par défaut du dépôt"


# ─────────────────────────────────────
# Liste et fiche
# ─────────────────────────────────────

async def show_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    projects = await service.list_projects(owner)
    if projects:
        lines = [title("Projets", "Appuyez sur un projet pour le détail.")]
        rows = [[button(p.name, f"{CB_PROJECT}{p.id}")] for p in projects]
    else:
        lines = [title("Projets"), "Aucun dépôt pour l'instant."]
        rows = []
    rows += [[button(f"{PLUS} Ajouter un dépôt", CB_ADD_PROJECT, PRIMARY)], [back()]]
    await show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


async def render_project(owner: int, project: Project) -> tuple[str, InlineKeyboardMarkup]:
    tasks = [t for t in await service.list_tasks(owner, limit=200) if t.project_id == str(project.id)]
    last = f" · dernière {ago(tasks[0].created_at)}" if tasks else ""
    lines = [
        title(esc(project.name)),
        f"<code>{esc(project.repo_url.removeprefix('https://'))}</code>",
        "",
        f"Branche    <b>{_branch_label(project)}</b>",
        f"Tâches      <b>{len(tasks)}</b>{last}",
    ]
    pid = project.id
    rows = [
        [button(f"{PLUS} Nouvelle tâche ici", f"{CB_NEW_IN_PROJECT}{pid}", PRIMARY)],
        [button("Renommer", f"{CB_RENAME}{pid}"), button("Branche", f"{CB_BRANCH}{pid}")],
        [button("Retirer", f"{CB_REMOVE}{pid}")],
        [back("Projets", CB_PROJECTS)],
    ]
    return "\n".join(lines), InlineKeyboardMarkup(rows)


async def _owned(update: Update, owner: int, prefix: str) -> Project | None:
    """Le projet nommé par le bouton, s'il est à l'utilisateur et encore actif ; sinon une alerte et None."""
    try:
        return await service.get_active_project(owner, update.callback_query.data.removeprefix(prefix))
    except service.NotFoundError:
        await update.callback_query.answer("Ce projet n'existe plus.", show_alert=True)
        return None


async def show_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    project = await _owned(update, owner, CB_PROJECT)
    if project is not None:
        clear_draft(context)
        await show(update, *await render_project(owner, project))


async def _show_sheet(update: Update, owner: int, project: Project) -> None:
    await show(update, *await render_project(owner, project))


# ─────────────────────────────────────
# Ajout d'un dépôt : adresse → vérification → confirmation → création
# ─────────────────────────────────────

REPO_HELP = (
    "Collez l'adresse de sa page GitHub :\n<code>https://github.com/vous/projet</code>\nou simplement <code>vous/projet</code>"
)


async def ask_repo(update: Update, context: ContextTypes.DEFAULT_TYPE, *, then_task: bool) -> None:
    draft = draft_of(context)
    draft.clear()
    draft.update(step="repo", then_task=then_task, at=time.monotonic())
    await show(update, f"{title('Quel dépôt ?')}\n{REPO_HELP}", cancel_markup())


async def ask_repo_from_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorize(update, context) is not None:
        await ask_repo(update, context, then_task=False)


async def ask_repo_for_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorize(update, context) is not None:
        await ask_repo(update, context, then_task=True)


async def ask_repo_again(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """« Corriger l'adresse » : même parcours, en gardant le but (ajouter seulement, ou enchaîner sur une tâche)."""
    if await authorize(update, context) is not None:
        await ask_repo(update, context, then_task=bool(draft_of(context).get("then_task")))


def _confirm_text(repo: Repo, info: RepoInfo) -> tuple[str, str]:
    """(texte, libellé du bouton d'ajout) selon ce que GitHub a répondu."""
    name = f"<b>{esc(repo.full_name)}</b>"
    if info.state == Lookup.FOUND:
        branch = repo.branch or info.default_branch
        origin = "indiquée dans l'adresse" if repo.branch else "par défaut"
        lines = [title("Ajouter ce dépôt ?"), name]
        if info.description:
            lines.append(f"<i>{esc(info.description)}</i>")
        lines.append("")
        if branch:
            lines.append(f"Branche    <b>{esc(branch)}</b>  <i>{origin}</i>")
        if info.language:
            lines.append(f"Langage    {esc(info.language)}")
        if info.archived:
            lines += ["", "▲ Ce dépôt est archivé sur GitHub : un agent ne pourra pas y proposer de modification."]
        return "\n".join(lines), "Ajouter"
    if info.state == Lookup.NOT_FOUND:
        lines = [
            title("Dépôt introuvable"),
            f"{name} n'existe pas, ou il est privé.",
            "",
            "S'il est privé, vous pouvez l'ajouter quand même : le fournisseur doit y avoir accès.",
        ]
    else:
        lines = [
            title("Dépôt non vérifié"),
            f"{name}",
            "",
            "GitHub ne répond pas pour le moment, je ne peux pas confirmer que ce dépôt existe.",
        ]
    return "\n".join(lines), "Ajouter quand même"


async def handle_repo_text(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    draft = draft_of(context)
    repo = parse_repo(text)
    if repo is None:
        unknown = title("Je n'ai pas reconnu ce dépôt.")
        await update.message.reply_text(f"{unknown}\n{REPO_HELP}", reply_markup=cancel_markup())
        return
    info = await lookup_repo(repo)
    draft.update(step=None, pending={"url": repo.url, "name": repo.name, "branch": repo.branch}, at=time.monotonic())
    body, add_label = _confirm_text(repo, info)
    rows = [[button(add_label, CB_REPO_OK, PRIMARY if info.state == Lookup.FOUND else None)]]
    if info.state != Lookup.FOUND:
        rows.append([button("Corriger l'adresse", CB_REPO_AGAIN)])
    rows.append([button("Annuler", CB_DISCARD)])
    await update.message.reply_text(body, reply_markup=InlineKeyboardMarkup(rows))


async def create_from_pending(owner: int, pending: dict) -> tuple[Project, bool]:
    """(projet, déjà connu). Même dépôt : réutilisé. Même nom pour un autre dépôt : « proprietaire/depot »."""
    projects = await service.list_projects(owner)
    for project in projects:
        if project.repo_url.lower() == pending["url"].lower():
            return project, True
    name = pending["name"]
    if any(p.name.casefold() == name.casefold() for p in projects):
        name = pending["url"].removeprefix("https://github.com/")[:MAX_NAME]
    return await service.create_project(owner, name, pending["url"], pending["branch"]), False


async def confirm_repo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from .tasks import advance  # tasks dépend de projects (cancel_markup) : import tardif

    owner = await authorize(update, context)
    if owner is None:
        return
    draft = draft_of(context)
    pending = draft.pop("pending", None)
    if not pending:
        await update.callback_query.answer("Cette saisie a expiré : recommencez.", show_alert=True)
        clear_draft(context)
        await show_projects(update, context)
        return
    project, known = await create_from_pending(owner, pending)
    if draft.get("then_task"):
        draft.pop("then_task", None)
        draft["project_id"] = str(project.id)
        await advance(update, context, owner)
        return
    clear_draft(context)
    note = "est déjà dans vos projets" if known else "est ajouté"
    rows = [[button(f"{PLUS} Nouvelle tâche ici", f"{CB_NEW_IN_PROJECT}{project.id}", PRIMARY)],
            [back("Projets", CB_PROJECTS)]]
    await show(update, f"<b>{esc(project.name)}</b> {note}.", InlineKeyboardMarkup(rows))


# ─────────────────────────────────────
# Renommer, changer de branche, retirer
# ─────────────────────────────────────

async def _ask(update: Update, context: ContextTypes.DEFAULT_TYPE, prefix: str, step: str, text) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    project = await _owned(update, owner, prefix)
    if project is None:
        return
    draft = draft_of(context)
    draft.clear()
    draft.update(step=step, edit_id=str(project.id), at=time.monotonic())
    await show(update, text(project), cancel_markup())


async def ask_rename(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, CB_RENAME, "rename", lambda p: (
        f"{title('Nouveau nom', f'Actuel : {esc(p.name)}')}\nUne ligne, {MAX_NAME} caractères au plus."
    ))


async def ask_branch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _ask(update, context, CB_BRANCH, "branch", lambda p: (
        f"{title('Branche de départ', f'Actuelle : {_branch_label(p)}')}\n"
        "Envoyez le nom de la branche (par exemple <code>develop</code>), "
        "ou <code>-</code> pour revenir à la branche par défaut du dépôt."
    ))


async def handle_edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE, owner: int, step: str, text: str) -> None:
    draft = draft_of(context)
    project_id = draft.get("edit_id", "")
    if step == "rename":
        name = parse_name(text)
        if name is None:
            await update.message.reply_text(
                f"<b>Nom invalide.</b> Une seule ligne, {MAX_NAME} caractères au plus.", reply_markup=cancel_markup()
            )
            return
        others = [p for p in await service.list_projects(owner) if str(p.id) != project_id]
        if any(p.name.casefold() == name.casefold() for p in others):
            await update.message.reply_text(
                "<b>Ce nom est déjà pris</b> par un autre projet. Choisissez-en un autre.", reply_markup=cancel_markup()
            )
            return
        changes = {"name": name}
    else:
        branch = parse_branch(text)
        if branch is None:
            await update.message.reply_text(
                "<b>Nom de branche invalide.</b> Lettres, chiffres, <code>. _ - /</code>, sans espace. "
                "Envoyez <code>-</code> pour la branche par défaut.",
                reply_markup=cancel_markup(),
            )
            return
        changes = {"default_branch": branch}
    try:
        project = await service.update_project(owner, project_id, **changes)
    except service.NotFoundError:
        clear_draft(context)
        await update.message.reply_text("Ce projet n'existe plus.", reply_markup=InlineKeyboardMarkup([[back("Projets", CB_PROJECTS)]]))
        return
    clear_draft(context)
    await _show_sheet(update, owner, project)


async def confirm_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    project = await _owned(update, owner, CB_REMOVE)
    if project is None:
        return
    text = (
        f"{title('Retirer ce projet ?')}\n"
        f"<b>{esc(project.name)}</b> disparaît de votre liste.\n"
        "<i>Ses tâches restent consultables et les exécutions en cours continuent.</i>"
    )
    rows = [[button("Retirer", f"{CB_REMOVE_OK}{project.id}", DANGER)], [back(project.name[:20], f"{CB_PROJECT}{project.id}")]]
    await show(update, text, InlineKeyboardMarkup(rows))


async def remove_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    project = await _owned(update, owner, CB_REMOVE_OK)
    if project is None:
        return
    await service.archive_project(owner, str(project.id))
    clear_draft(context)
    await show_projects(update, context)
