"""
Orbi Dev — Choix cliquables quand l'agent attend une réponse (remote control, ADR-0010).

Les fournisseurs n'exposent pas de « question à choix » structurée : le message de l'agent est du
texte brut. Deux sources de boutons, par ordre de préférence :

1. **Options parsées** — si le dernier message de l'agent (capacité HISTORY) contient une liste
   numérotée ou à puces dans une question (« ? »), chaque item devient un bouton qui renvoie
   exactement son texte. Le callback porte un empreinte du texte : au clic, les options sont
   relues et vérifiées — un fil qui a changé entre-temps refuse le choix au lieu d'envoyer
   autre chose que ce que l'utilisateur a vu.
2. **Réponses génériques** — sinon (pas de liste exploitable, ou fournisseur sans HISTORY comme
   Cursor), trois suggestions courtes. Ce sont des amorces : l'agent peut toujours redemander
   une précision, l'état reconverge vers `needs_attention`.

Rien n'est deviné au-delà : pas de liste → pas de boutons parsés, jamais de texte inventé.
"""

import hashlib
import logging
import re

from telegram import InlineKeyboardButton

from src.orbi_dev import runner, service
from src.orbi_dev.connectors.base import ConnectorError
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ExecutionStatus

logger = logging.getLogger("orbi.dev.choices")

# Préfixes des callbacks (gérés par src/handlers/orbi_dev.py)
CB_OPT = "dv:opt:"  # option parsée : {execution_id}:{index}:{empreinte}
CB_GEN = "dv:gen:"  # réponse générique : {execution_id}:{index}

# Suggestions génériques quand aucune option n'est lisible dans le message de l'agent.
GENERIC_CHOICES = ["Oui, continue.", "Non.", "Explique-moi les options."]

_MAX_OPTIONS = 4
_MAX_OPTION_LEN = 200
_OPTION_LINE = re.compile(r"^\s*(?:\d{1,2}[.)]|[-*•])\s+(.+?)\s*$")
_MD_EDGE = "*_`"


def parse_options(text: str) -> list[str]:
    """Items d'une liste dans une question. Exige un « ? » et au moins deux items — sinon ce
    n'est pas une question à choix (une liste d'étapes ou de fichiers n'en est pas une)."""
    if "?" not in text:
        return []
    options: list[str] = []
    for line in text.splitlines():
        match = _OPTION_LINE.match(line)
        if not match:
            continue
        option = match.group(1).strip().strip(_MD_EDGE).strip()
        if not option or len(option) > _MAX_OPTION_LEN or option.startswith("```"):
            continue
        options.append(option)
        if len(options) >= _MAX_OPTIONS:
            break
    return options if len(options) >= 2 else []


def option_fingerprint(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:6]


async def parsed_options(owner_id: int, execution: Execution) -> list[str]:
    """Options du dernier message de l'agent, ou [] (HISTORY absent, fil illisible, pas de liste)."""
    if not execution.external_id or not await service.execution_history_capable(owner_id, execution):
        return []
    try:
        messages = await runner.get_execution_thread(owner_id, str(execution.id), limit=15)
    except (service.NotFoundError, service.ConflictError, ConnectorError, ValueError) as e:
        logger.info("Fil illisible pour %s : %s", execution.id, type(e).__name__)
        return []
    last_agent = next((m for m in reversed(messages) if m.role == "agent"), None)
    return parse_options(last_agent.text) if last_agent else []


async def agent_choice_buttons(owner_id: int, execution: Execution) -> list[InlineKeyboardButton]:
    """Boutons de choix pour une exécution en `needs_attention` capable d'`INTERACT` ; [] sinon.

    Le coût est borné : un seul appel fournisseur (le fil) par rendu, uniquement tant que
    l'exécution attend une réponse — jamais pendant le polling des états actifs.
    """
    if execution.status != ExecutionStatus.NEEDS_ATTENTION or not execution.external_id:
        return []
    if not await service.execution_interact_capable(owner_id, execution):
        return []
    execution_id = str(execution.id)
    options = await parsed_options(owner_id, execution)
    if options:
        return [
            InlineKeyboardButton(
                option,
                callback_data=f"{CB_OPT}{execution_id}:{index}:{option_fingerprint(option)}",
            )
            for index, option in enumerate(options)
        ]
    return [
        InlineKeyboardButton(choice, callback_data=f"{CB_GEN}{execution_id}:{index}")
        for index, choice in enumerate(GENERIC_CHOICES)
    ]
