"""Interface : jetons de design accessibles, ressources auto-hébergées, enveloppe htmx, accessibilité de base."""

import re
from pathlib import Path

import pytest

from src.models.user import User
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ExecutionStatus
from src.web.auth import COOKIE_NAME, create_web_session
from src.web.csrf import csrf_token

STATIC = Path(__file__).resolve().parent.parent / "src" / "static"
CSS = (STATIC / "orbi.css").read_text(encoding="utf-8")
REPO = "https://github.com/acme/demo"


# ── Contraste (WCAG 2.2) ──────────────────────────────────────────────

def _tokens(block: str) -> dict[str, str]:
    return dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", block))


DARK = _tokens(re.search(r":root \{(.*?)\}", CSS, re.S).group(1))
LIGHT_ATTR = {**DARK, **_tokens(re.search(r':root\[data-theme="light"\] \{(.*?)\}', CSS, re.S).group(1))}
LIGHT_MEDIA = {**DARK, **_tokens(re.search(r"@media \(prefers-color-scheme: light\) \{\s*:root:not\(\[data-theme=\"dark\"\]\) \{(.*?)\}", CSS, re.S).group(1))}


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


THEMES = {"sombre": DARK, "clair (data-theme)": LIGHT_ATTR, "clair (système)": LIGHT_MEDIA}
TEXT_PAIRS = [("encre", "nuit"), ("encre", "pont"), ("brume", "nuit"), ("brume", "pont"), ("orbite", "nuit"),
              ("ok", "nuit"), ("ok", "pont"), ("bad", "nuit"), ("bad", "pont"), ("signal-encre", "signal")]


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("fg,bg", TEXT_PAIRS)
def test_text_colours_reach_aa(theme, fg, bg):
    tokens = THEMES[theme]
    assert contrast(tokens[fg], tokens[bg]) >= 4.5, (theme, fg, bg)


@pytest.mark.parametrize("theme", THEMES)
def test_form_control_borders_reach_3_to_1(theme):
    tokens = THEMES[theme]
    assert contrast(tokens["champ"], tokens["nuit"]) >= 3 and contrast(tokens["champ"], tokens["pont"]) >= 3


def test_amber_text_in_light_theme_is_darkened():
    assert contrast("#9a5b00", LIGHT_ATTR["nuit"]) >= 4.5 and "#9a5b00" in CSS


def test_motion_respects_reduced_motion_preference():
    assert "prefers-reduced-motion: reduce" in CSS and "animation: none" in CSS


# ── Fixtures ──────────────────────────────────────────────────────────

async def login(telegram_id=700):
    admin = await User(telegram_id=telegram_id, first_name="Ada", role="admin").insert()
    session_id = await create_web_session(admin)
    return {COOKIE_NAME: session_id}, csrf_token(session_id)


async def execution(status: ExecutionStatus, n: int, owner=700) -> Execution:
    from src.orbi_dev import service

    project = await service.create_project(owner, f"p{n}", REPO)
    integration = await service.create_integration(owner, "fake", "k", label=f"i{n}")
    task = await service.create_task(owner, str(project.id), str(integration.id), f"tâche {n}")
    ex = await service.create_execution(owner, str(task.id))
    await Execution.get_pymongo_collection().update_one({"_id": ex.id}, {"$set": {"status": status.value}})
    return await Execution.get(ex.id)


@pytest.fixture(autouse=True)
def _encryption_key(monkeypatch):
    from cryptography.fernet import Fernet

    from src.core.config import get_settings

    monkeypatch.setenv("SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode())
    get_settings.cache_clear()


# ── Ressources auto-hébergées ─────────────────────────────────────────

class TestStaticAssets:
    @pytest.mark.parametrize("path,kind", [
        ("/static/orbi.css", "text/css"), ("/static/vendor/htmx-2.0.4.min.js", "javascript"),
        ("/static/fonts/AtkinsonHyperlegibleNext-latin.woff2", "font/woff2"),
    ])
    async def test_assets_are_served(self, aclient, path, kind):
        r = await aclient.get(path)
        assert r.status_code == 200 and kind in r.headers["content-type"]

    async def test_every_page_declares_an_existing_favicon(self, aclient):
        """Sans icône déclarée, le navigateur réclame /favicon.ico et reçoit un 404 à chaque ouverture."""
        cookies, _ = await login()
        assert 'rel="icon" href="/static/favicon.svg"' in (await aclient.get("/admin/login")).text
        for path in ("/dev/", "/dev/projects", "/admin/"):
            html = (await aclient.get(path, cookies=cookies)).text
            assert 'rel="icon" href="/static/favicon.svg"' in html, path
        assert (await aclient.get("/static/favicon.svg")).status_code == 200

    @pytest.mark.parametrize("path", ["/static/../main.py", "/static/%2e%2e/main.py", "/static/../../.env"])
    async def test_no_path_traversal(self, aclient, path):
        assert (await aclient.get(path)).status_code == 404

    async def test_licences_of_bundled_files_ship_with_them(self):
        assert (STATIC / "fonts" / "OFL-AtkinsonHyperlegibleNext.txt").exists()
        assert (STATIC / "vendor" / "htmx-LICENSE.txt").exists()

    async def test_pages_depend_on_no_third_party_cdn(self, aclient):
        cookies, _ = await login()
        await execution(ExecutionStatus.RUNNING, 1)
        for path in ("/dev/", "/dev/tasks/new", "/dev/projects", "/dev/integrations", "/admin/", "/admin/users",
                     "/admin/tickets", "/admin/system"):
            html = (await aclient.get(path, cookies=cookies)).text
            for banned in ("jsdelivr", "bootstrap", "googleapis", "unpkg", "cdnjs", "gstatic"):
                assert banned not in html.lower(), (path, banned)
            hosts = set(re.findall(r'<script[^>]+src="https?://([^/"]+)', html))
            assert hosts <= {"telegram.org"}, (path, hosts)  # seule exception : le script officiel de Telegram


# ── Enveloppe, htmx et accessibilité ──────────────────────────────────

class TestShell:
    async def test_htmx_is_hardened_and_carries_the_csrf_token(self, aclient):
        cookies, token = await login()
        html = (await aclient.get("/dev/", cookies=cookies)).text
        assert 'hx-boost="true"' in html
        assert f"&#34;X-CSRF-Token&#34;: &#34;{token}&#34;" in html or f'"X-CSRF-Token": "{token}"' in html or token in html
        config = re.search(r'name="htmx-config" content=\'(.*?)\'', html).group(1)
        assert '"allowEval": false' in config and '"allowScriptTags": false' in config and '"historyCacheSize": 0' in config

    async def test_landmarks_language_and_skip_link(self, aclient):
        cookies, _ = await login()
        html = (await aclient.get("/dev/", cookies=cookies)).text
        assert '<html lang="fr">' in html and html.count("<main") == 1 and 'href="#main"' in html
        assert html.count("<h1") == 1
        assert 'aria-label="Navigation principale"' in html and 'aria-current="page"' in html

    @pytest.mark.parametrize("path", ["/dev/tasks/new", "/dev/projects", "/dev/integrations", "/admin/users"])
    async def test_every_form_field_has_a_label(self, aclient, path):
        cookies, _ = await login()
        await execution(ExecutionStatus.SUCCEEDED, 1)
        html = (await aclient.get(path, cookies=cookies)).text
        labelled = set(re.findall(r'<label[^>]*for="([^"]+)"', html))
        for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", html):
            if 'type="hidden"' in tag:
                continue
            field_id = re.search(r'id="([^"]+)"', tag)
            assert field_id and field_id.group(1) in labelled, (path, tag)

    async def test_buttons_and_icons_are_announced_correctly(self, aclient):
        cookies, _ = await login()
        await execution(ExecutionStatus.RUNNING, 1)
        html = (await aclient.get("/dev/", cookies=cookies)).text
        assert 'class="icon' in html and "<svg" in html
        assert all('aria-hidden="true"' in svg for svg in re.findall(r"<svg\b[^>]*>", html) if "width=\"0\"" not in svg)

    async def test_the_mini_app_follows_telegram_theme_and_back_button(self, aclient):
        cookies, _ = await login()
        html = (await aclient.get("/dev/", cookies=cookies)).text
        assert "telegram-web-app.js" in html and "colorScheme" in html and "BackButton" in html


class TestEveryStateHasARing:
    async def test_every_execution_status_renders_in_the_list(self, aclient):
        cookies, _ = await login()
        for n, status in enumerate(ExecutionStatus):
            await execution(status, n)
        r = await aclient.get("/dev/", cookies=cookies)
        assert r.status_code == 200
        assert r.text.count('class="row"') == len(ExecutionStatus)
        assert r.text.count('class="ring ') >= len(ExecutionStatus)

    @pytest.mark.parametrize("status", list(ExecutionStatus))
    async def test_every_execution_status_renders_in_the_detail(self, aclient, status):
        cookies, _ = await login()
        ex = await execution(status, 1)
        r = await aclient.get(f"/dev/executions/{ex.id}", cookies=cookies)
        assert r.status_code == 200 and "ring-lg" in r.text


class TestHtmxFragments:
    async def test_fragments_are_not_full_pages(self, aclient):
        cookies, _ = await login()
        ex = await execution(ExecutionStatus.RUNNING, 1)
        for path in ("/dev/runs", f"/dev/executions/{ex.id}/panel"):
            html = (await aclient.get(path, cookies=cookies)).text
            assert "<html" not in html and "<nav" not in html, path

    async def test_polling_continues_while_active_and_stops_when_done(self, aclient):
        cookies, _ = await login()
        running = await execution(ExecutionStatus.RUNNING, 1)
        done = await execution(ExecutionStatus.SUCCEEDED, 2)
        assert 'hx-trigger="every 3s"' in (await aclient.get(f"/dev/executions/{running.id}/panel", cookies=cookies)).text
        assert "hx-trigger" not in (await aclient.get(f"/dev/executions/{done.id}/panel", cookies=cookies)).text

    async def test_list_polls_only_while_something_is_active(self, aclient):
        cookies, _ = await login()
        await execution(ExecutionStatus.SUCCEEDED, 1)
        assert 'hx-trigger="every 4s"' not in (await aclient.get("/dev/runs", cookies=cookies)).text
        await execution(ExecutionStatus.RUNNING, 2)
        assert 'hx-trigger="every 4s"' in (await aclient.get("/dev/runs", cookies=cookies)).text

    async def test_user_search_swaps_only_the_rows(self, aclient):
        cookies, _ = await login()
        await User(telegram_id=11, first_name="Grace", role="user").insert()
        fragment = await aclient.get("/admin/users?q=Gra", cookies=cookies, headers={"HX-Request": "true", "HX-Target": "user-rows"})
        page = await aclient.get("/admin/users?q=Gra", cookies=cookies)
        assert "Grace" in fragment.text and "<html" not in fragment.text
        assert "<html" in page.text and "Grace" in page.text


class TestCsrfThroughHtmx:
    async def test_header_token_is_enough(self, aclient):
        cookies, token = await login()
        ex = await execution(ExecutionStatus.RUNNING, 1)
        r = await aclient.post(f"/dev/executions/{ex.id}/refresh", cookies=cookies,
                               headers={"X-CSRF-Token": token, "HX-Request": "true", "HX-Target": "run-panel"})
        assert r.status_code == 200 and 'id="run-panel"' in r.text and "<html" not in r.text

    async def test_wrong_or_foreign_header_is_refused(self, aclient):
        cookies, token = await login()
        _, other = await login(telegram_id=701)
        ex = await execution(ExecutionStatus.RUNNING, 1)
        for bad in ("x" * 64, other, ""):
            r = await aclient.post(f"/dev/executions/{ex.id}/cancel", cookies=cookies, headers={"X-CSRF-Token": bad})
            assert r.status_code == 403, bad
        assert (await Execution.get(ex.id)).status == ExecutionStatus.RUNNING

    async def test_without_htmx_the_actions_still_work_and_redirect(self, aclient):
        cookies, token = await login()
        ex = await execution(ExecutionStatus.RUNNING, 1)
        r = await aclient.post(f"/dev/executions/{ex.id}/refresh", cookies=cookies, data={"csrf_token": token})
        assert r.status_code == 303 and r.headers["location"] == f"/dev/executions/{ex.id}"
