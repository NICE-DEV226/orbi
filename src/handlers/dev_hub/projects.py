"""
Orbi Dev dans Telegram — les projets : liste, fiche, ajout d'un dépôt en collant son adresse.
"""

import time

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.text import esc
from src.orbi_dev import service
from src.orbi_dev.look import PLUS, PRIMARY
from src.orbi_dev.models import Project
from src.orbi_dev.present import ago
from src.orbi_dev.repo import parse_repo

from .common import (
    CB_ADD_PROJECT,
    CB_DISCARD,
    CB_NEW_IN_PROJECT,
    CB_PROJECT,
    CB_PROJECTS,
    authorize,
    back,
    button,
    draft_of,
    show,
    title,
)


def cancel_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[button("Annuler", CB_DISCARD)]])


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


async def show_project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    owner = await authorize(update, context)
    if owner is None:
        return
    try:
        project = await service.get_project(owner, update.callback_query.data.removeprefix(CB_PROJECT))
    except service.NotFoundError:
        await update.callback_query.answer("Ce projet n'existe plus.", show_alert=True)
        return
    tasks = [t for t in await service.list_tasks(owner, limit=200) if t.project_id == str(project.id)]
    last = f" · dernière {ago(tasks[0].created_at)}" if tasks else ""
    lines = [
        title(esc(project.name), ""),
        f"<code>{esc(project.repo_url.removeprefix('https://'))}</code>",
        "",
        f"Branche    <b>{esc(project.default_branch) if project.default_branch else 'par défaut du dépôt'}</b>",
        f"Tâches      <b>{len(tasks)}</b>{last}",
    ]
    rows = [[button(f"{PLUS} Nouvelle tâche ici", f"{CB_NEW_IN_PROJECT}{project.id}", PRIMARY)], [back("Projets", CB_PROJECTS)]]
    await show(update, "\n".join(lines), InlineKeyboardMarkup(rows))


# ─────────────────────────────────────
# Ajout d'un dépôt
# ─────────────────────────────────────

async def ask_repo(update: Update, context: ContextTypes.DEFAULT_TYPE, *, then_task: bool) -> None:
    draft = draft_of(context)
    draft.clear()
    draft.update(step="repo", then_task=then_task, at=time.monotonic())
    text = (
        f"{title('Quel dépôt ?', 'Collez son adresse GitHub.')}\n"
        "<code>https://github.com/vous/projet</code>\nou simplement <code>vous/projet</code>"
    )
    await show(update, text, cancel_markup())


async def ask_repo_from_projects(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorize(update, context) is not None:
        await ask_repo(update, context, then_task=False)


async def ask_repo_for_task(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if await authorize(update, context) is not None:
        await ask_repo(update, context, then_task=True)


async def add_project(owner: int, text: str) -> tuple[Project | None, bool]:
    """(projet, déjà connu). Un dépôt déjà ajouté est réutilisé, jamais dupliqué."""
    repo = parse_repo(text)
    if repo is None:
        return None, False
    for project in await service.list_projects(owner):
        if project.repo_url.lower() == repo.url.lower():
            return project, True
    return await service.create_project(owner, repo.name, repo.url, repo.branch), False
