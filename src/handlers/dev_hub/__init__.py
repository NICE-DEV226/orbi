"""
Orbi — Orbi Dev dans Telegram : l'accueil des administrateurs.

Tout le parcours se fait dans la conversation : voir l'état de ses tâches, ajouter un dépôt en collant son adresse,
écrire une consigne, confirmer, suivre l'avancement sur une carte qui se met à jour seule. La seule chose qui reste sur
le web est la saisie d'une clé d'API (elle ne doit jamais passer par un chat).

Un module par domaine : `common` (accès, brouillon, boutons), `home` (accueil, connexions, réglages), `tasks`,
`projects`, `messages` (texte libre attendu par un parcours). Ce fichier les assemble.
"""

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, filters

from .common import (
    CB_ADD_PROJECT,
    CB_CHANGE_PROJECT,
    CB_CHANGE_PROVIDER,
    CB_CONNECTIONS,
    CB_DISCARD,
    CB_EDIT,
    CB_GO,
    CB_HOME,
    CB_LIST,
    CB_NEW,
    CB_NEW_IN_PROJECT,
    CB_NEW_REPO,
    CB_NOTIFICATIONS,
    CB_OPEN,
    CB_PICK_PROJECT,
    CB_PICK_PROVIDER,
    CB_PROJECT,
    CB_PROJECTS,
    CB_SETTINGS,
    DRAFT_TTL,
    MAX_PROMPT,
    logger,
)
from .home import ADMIN_COMMANDS, build_home, show_connections, show_home, show_settings, toggle_notifications
from .messages import on_text
from .projects import ask_repo_for_task, ask_repo_from_projects, show_project, show_projects
from .tasks import (
    change_project,
    change_provider,
    discard,
    edit_prompt,
    launch,
    new_task_in_project,
    pick_project,
    pick_provider,
    show_execution,
    show_list,
    start_task,
    task_command,
    tasks_command,
)

__all__ = [
    "ADMIN_COMMANDS", "DRAFT_TTL", "MAX_PROMPT", "ask_repo_for_task", "ask_repo_from_projects", "build_home",
    "change_project", "change_provider", "discard", "edit_prompt", "launch", "new_task_in_project", "on_text",
    "pick_project", "pick_provider", "register_dev_hub_handlers", "show_connections", "show_execution", "show_home",
    "show_list", "show_project", "show_projects", "show_settings", "start_task", "task_command", "tasks_command",
    "toggle_notifications",
]


def register_dev_hub_handlers(application) -> None:
    on = application.add_handler
    private = filters.ChatType.PRIVATE
    on(CommandHandler("dev", show_home, filters=private))
    on(CommandHandler("task", task_command, filters=private))
    on(CommandHandler("tasks", tasks_command, filters=private))
    for pattern, callback in (
        (CB_HOME, show_home), (CB_NEW, start_task), (CB_PROJECTS, show_projects),
        (CB_ADD_PROJECT, ask_repo_from_projects), (CB_NEW_REPO, ask_repo_for_task),
        (CB_CONNECTIONS, show_connections), (CB_SETTINGS, show_settings), (CB_NOTIFICATIONS, toggle_notifications),
        (CB_GO, launch), (CB_EDIT, edit_prompt), (CB_CHANGE_PROJECT, change_project),
        (CB_CHANGE_PROVIDER, change_provider), (CB_DISCARD, discard),
    ):
        on(CallbackQueryHandler(callback, pattern=f"^{pattern}$"))
    on(CallbackQueryHandler(show_list, pattern=f"^{CB_LIST}(:[ad])?$"))
    on(CallbackQueryHandler(show_project, pattern=rf"^{CB_PROJECT}"))
    on(CallbackQueryHandler(new_task_in_project, pattern=rf"^{CB_NEW_IN_PROJECT}"))
    on(CallbackQueryHandler(pick_project, pattern=rf"^{CB_PICK_PROJECT}"))
    on(CallbackQueryHandler(pick_provider, pattern=rf"^{CB_PICK_PROVIDER}"))
    on(CallbackQueryHandler(show_execution, pattern=rf"^{CB_OPEN}"))
    # Groupe 1 : ne retire rien aux autres parcours (support, productivité) qui lisent aussi les messages texte
    on(MessageHandler(filters.TEXT & ~filters.COMMAND & private, on_text), group=1)
    logger.info("Handlers Orbi Dev (Telegram) enregistrés")
