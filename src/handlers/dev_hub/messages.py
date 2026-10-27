"""
Orbi Dev dans Telegram — messages libres : ce que l'utilisateur écrit quand un parcours lui pose une question.

Un message n'est lu que si un parcours attend une réponse (dépôt, consigne, nouveau nom, branche). Dans ce cas rien ne
reste sans réponse : saisie trop courte ou trop longue, photo ou vocal à la place du texte, saisie restée plus de
15 minutes sans suite, tout reçoit une phrase qui dit quoi faire.
"""

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from src.orbi_dev.inputs import MAX_PROMPT, MIN_PROMPT, clean_text

from .common import DRAFT_TTL, allowed, back, clear_draft, draft_of, is_stale
from .projects import cancel_markup, handle_edit_text, handle_repo_text
from .tasks import advance

STEPS = ("repo", "prompt", "rename", "branch")
WAITING_FOR = {
    "repo": "l'adresse du dépôt",
    "prompt": "la consigne de la tâche",
    "rename": "le nouveau nom",
    "branch": "le nom de la branche",
}


def _waiting(context: ContextTypes.DEFAULT_TYPE) -> dict | None:
    raw = context.user_data.get("dev") if context.user_data else None
    return raw if raw and raw.get("step") in STEPS else None


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not allowed(context):
        return
    raw = _waiting(context)
    if raw is None:
        return
    if is_stale(raw):
        clear_draft(context)
        await update.message.reply_text(
            f"<b>Saisie expirée.</b> Plus de {DRAFT_TTL // 60} minutes se sont écoulées sans suite : recommencez.",
            reply_markup=InlineKeyboardMarkup([[back()]]),
        )
        return

    draft = draft_of(context)
    step = draft["step"]
    owner = update.effective_user.id
    text = clean_text(update.message.text or "")

    if step == "repo":
        await handle_repo_text(update, context, text)
    elif step in ("rename", "branch"):
        await handle_edit_text(update, context, owner, step, text)
    else:
        if len(text) < MIN_PROMPT:
            await update.message.reply_text(
                f"<b>Trop court.</b> Décrivez la tâche en quelques mots au moins ({MIN_PROMPT} caractères).",
                reply_markup=cancel_markup(),
            )
            return
        if len(text) > MAX_PROMPT:
            await update.message.reply_text(
                f"<b>Trop long.</b> {MAX_PROMPT} caractères au plus ({len(text)} reçus). Résumez ou découpez en deux tâches.",
                reply_markup=cancel_markup(),
            )
            return
        draft["prompt"] = text
        await advance(update, context, owner)


async def on_unsupported(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Photo, vocal, fichier, autocollant… alors qu'un parcours attend du texte : on le dit au lieu de se taire."""
    if not allowed(context):
        return
    raw = _waiting(context)
    if raw is None or is_stale(raw):
        return
    await update.message.reply_text(
        f"<b>J'attends du texte</b> : {WAITING_FOR[raw['step']]}. Les images, vocaux et fichiers ne sont pas lus.",
        reply_markup=cancel_markup(),
    )
