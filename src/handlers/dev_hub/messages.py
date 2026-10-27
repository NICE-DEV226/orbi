"""
Orbi Dev dans Telegram — messages libres : l'adresse d'un dépôt ou la consigne d'une tâche, quand le parcours les attend.
"""

import time

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.core.text import esc
from src.orbi_dev.look import PLUS, PRIMARY

from .common import CB_NEW, MAX_PROMPT, allowed, back, button, clear_draft, draft_of
from .projects import add_project, cancel_markup
from .tasks import advance


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prend le message uniquement si le parcours attend un dépôt ou une consigne ; sinon ne fait rien."""
    if not allowed(context) or not context.user_data.get("dev"):
        return
    draft = draft_of(context)
    step = draft.get("step")
    if step not in ("repo", "prompt"):
        return
    owner = update.effective_user.id
    text = (update.message.text or "").strip()

    if step == "repo":
        project, known = await add_project(owner, text)
        if project is None:
            await update.message.reply_text(
                "<b>Je n'ai pas reconnu ce dépôt.</b>\nCollez l'adresse de sa page GitHub :\n"
                "<code>https://github.com/vous/projet</code>\nou <code>vous/projet</code>",
                reply_markup=cancel_markup(),
            )
            return
        if draft.get("then_task"):
            draft.pop("step")
            draft["project_id"] = str(project.id)
            draft["at"] = time.monotonic()
            await advance(update, context, owner)
            return
        clear_draft(context)
        note = "est déjà dans vos projets" if known else "est ajouté"
        await update.message.reply_text(
            f"<b>{esc(project.name)}</b> {note}.",
            reply_markup=InlineKeyboardMarkup([[button(f"{PLUS} Nouvelle tâche", CB_NEW, PRIMARY)], [back()]]),
        )
        return

    if not text or len(text) > MAX_PROMPT:
        await update.message.reply_text(
            f"<b>Trop long.</b> Décrivez la tâche en {MAX_PROMPT} caractères au plus ({len(text)} reçus).",
            reply_markup=cancel_markup(),
        )
        return
    draft["prompt"] = text
    await advance(update, context, owner)
