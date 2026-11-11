"""
Markdown léger → HTML Telegram, pour le texte des agents (fils de discussion, réponses poussées).

Les agents écrivent en markdown (`**gras**`, `` `code` ``, ` ```blocs``` ``, `## titres`, `~~barré~~`)
mais Telegram n'a ni couleurs ni markdown : on convertit en entities HTML. Volontairement minimal et
prudent — pas d'italique (les `snake_case` et listes `* item` le rendraient faux), et le contenu
est toujours échappé avant transformation pour ne jamais produire de HTML injecté.
"""

import re
from html import escape

_FENCE = re.compile(r"```[^\n`]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]+)`")
_HEADER = re.compile(r"(?m)^#{1,6}[ \t]+(.+?)[ \t]*$")
_BOLD = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
_PLACEHOLDER = re.compile(r"\x00(\d+)\x00")


def to_telegram_html(text: str) -> str:
    """Convertit le markdown courant d'un agent en HTML Telegram valide (entités échappées)."""
    stashed: list[tuple[str, str]] = []

    def stash(kind: str, inner: str) -> str:
        stashed.append((kind, escape(inner, quote=False)))
        return f"\x00{len(stashed) - 1}\x00"

    # 1. Blocs ``` et code inline d'abord : leur contenu est figé (échappé) avant le reste.
    body = _FENCE.sub(lambda m: stash("pre", m.group(1).strip("\n")), text)
    body = _INLINE_CODE.sub(lambda m: stash("code", m.group(1)), body)
    # 2. Échappement du texte restant, puis transformations markdown → entités Telegram.
    body = escape(body, quote=False)
    body = _HEADER.sub(lambda m: f"<b>{m.group(1)}</b>", body)
    body = _BOLD.sub(lambda m: f"<b>{m.group(1)}</b>", body)
    body = _STRIKE.sub(lambda m: f"<s>{m.group(1)}</s>", body)
    # 3. Réinjection des zones figées.
    def restore(m: re.Match) -> str:
        kind, inner = stashed[int(m.group(1))]
        return f"<{kind}>{inner}</{kind}>"

    return _PLACEHOLDER.sub(restore, body)
