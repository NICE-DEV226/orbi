"""
Orbi — Échappement du texte non fiable inséré dans les messages Telegram.

Le bot envoie ses messages en `parse_mode="HTML"` (Defaults). Tout texte saisi par un utilisateur ou reçu d'un tiers
(nom, sujet de ticket, titre de tâche, message de commit…) doit passer par `esc()` avant d'être placé dans un message :
sinon il peut injecter des liens ou des balises, ou faire rejeter le message par Telegram (« can't parse entities »).
"""

import html


def esc(value: object) -> str:
    """Échappe `&`, `<` et `>` (suffisant pour le HTML de Telegram)."""
    return html.escape("" if value is None else str(value), quote=False)
