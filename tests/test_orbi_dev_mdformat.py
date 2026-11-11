"""Markdown léger → HTML Telegram : gras, code inline, blocs pré, titres, barré — toujours échappé."""

from src.orbi_dev.mdformat import to_telegram_html


def test_bold_and_inline_code():
    assert to_telegram_html("voici **important** et `x = 1`") == "voici <b>important</b> et <code>x = 1</code>"


def test_fenced_block_becomes_pre_with_escaped_content():
    out = to_telegram_html("corrige :\n```python\nif a < b:\n    print(\"<ok>\")\n```")
    assert '<pre>if a &lt; b:\n    print("&lt;ok&gt;")</pre>' in out
    assert "```" not in out


def test_headers_become_bold_lines():
    out = to_telegram_html("## Plan\n- étape")
    assert "<b>Plan</b>" in out and "##" not in out


def test_html_is_escaped_everywhere():
    out = to_telegram_html("<script>alert(1)</script> et **<b>x</b>**")
    assert "<script>" not in out and "&lt;script&gt;" in out
    # le gras markdown fonctionne, mais un <b> littéral reste du texte échappé
    assert "<b>&lt;b&gt;x&lt;/b&gt;</b>" in out


def test_strikethrough_and_plain_text_untouched():
    assert to_telegram_html("ceci ~~ancien~~ reste") == "ceci <s>ancien</s> reste"
    assert to_telegram_html("rien à convertir") == "rien à convertir"


def test_unclosed_fence_stays_literal():
    assert to_telegram_html("```python\ncode sans fin") == "```python\ncode sans fin"


def test_snake_case_is_not_italicized():
    # pas d'italique : les identifiants ne doivent jamais être mangés
    assert to_telegram_html("utilise get_execution_thread ici") == "utilise get_execution_thread ici"
