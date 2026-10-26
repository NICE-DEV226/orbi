"""Dashboard admin : pages rendues avec de vraies données, sans valeur inventée ni contrôle inerte."""

import pytest

from src.models.ticket import Ticket
from src.models.user import User
from src.orbi_dev.models import Execution
from src.orbi_dev.state import ExecutionStatus
from src.web.auth import COOKIE_NAME, create_web_session


async def admin_cookies():
    admin = await User(telegram_id=900, first_name="Root", role="admin").insert()
    return {COOKIE_NAME: await create_web_session(admin)}


async def make_ticket(**kwargs) -> Ticket:
    data = {
        "ticket_id": "TKT-2026-00001", "user_telegram_id": 4242, "category": "technical",
        "subject": "Panne du bot", "description": "Il ne répond plus",
    }
    ticket = Ticket(**{**data, **kwargs})
    await ticket.insert()
    return ticket


class TestTickets:
    async def test_detail_page_renders_with_real_mongo_datetimes(self, aclient):
        """Régression : la page plantait (datetime naïf de MongoDB moins datetime avec fuseau)."""
        ticket = await make_ticket()

        r = await aclient.get(f"/admin/tickets?id={ticket.id}", cookies=await admin_cookies())

        assert r.status_code == 200
        assert "Panne du bot" in r.text and "Il ne répond plus" in r.text

    async def test_shows_the_telegram_id_of_the_author(self, aclient):
        ticket = await make_ticket()
        html = (await aclient.get(f"/admin/tickets?id={ticket.id}", cookies=await admin_cookies())).text
        assert "4242" in html

    async def test_no_inert_controls_or_phantom_reply_form(self, aclient):
        ticket = await make_ticket()
        html = (await aclient.get(f"/admin/tickets?id={ticket.id}", cookies=await admin_cookies())).text
        assert "/reply" not in html  # la route n'existe pas
        for label in ("Marquer Résolu", "Filtrer", "Fermer"):
            assert label not in html

    async def test_list_page_without_selection(self, aclient):
        await make_ticket()
        r = await aclient.get("/admin/tickets", cookies=await admin_cookies())
        assert r.status_code == 200 and "Panne du bot" in r.text


class TestDashboardHome:
    async def test_kpis_are_computed_from_the_database(self, aclient):
        await User(telegram_id=1, first_name="A").insert()
        await User(telegram_id=2, first_name="B").insert()
        await User(telegram_id=3, first_name="C", is_banned=True).insert()
        await make_ticket()
        for i, (status, pr) in enumerate([(ExecutionStatus.RUNNING, None), (ExecutionStatus.SUCCEEDED, "https://github.com/a/b/pull/1")]):
            await Execution(
                owner_id=1, task_id=f"t{i}", integration_id="i", provider="fake", status=status,
                idempotency_key=f"k{i}", client_ref=f"c{i}", pr_url=pr,
            ).insert()

        html = (await aclient.get("/admin/", cookies=await admin_cookies())).text

        # 2 non bannis + l'admin de la session = 3 ; 1 ticket ouvert ; 1 exécution en cours ; 1 PR
        for label, value in [("Utilisateurs (non bannis)", 3), ("Tickets ouverts", 1),
                             ("Exécutions Orbi Dev en cours", 1), ("Pull requests proposées", 1)]:
            block = html.split(label)[1].split("</h2>")[0]
            assert f">{value}" in block, (label, block)

    async def test_no_invented_numbers_nor_phantom_chart(self, aclient):
        html = (await aclient.get("/admin/", cookies=await admin_cookies())).text
        assert "1250.00" not in html
        assert "Chart" not in html and "activityChart" not in html
        assert "Exporter CSV" not in html


class TestUsersPage:
    async def test_no_fake_pagination_or_inert_actions(self, aclient):
        await User(telegram_id=10, first_name="Ada").insert()
        html = (await aclient.get("/admin/users", cookies=await admin_cookies())).text
        assert "Ada" in html
        assert "Suivant" not in html and "Précédent" not in html
        assert "bi-pencil" not in html and "Exporter CSV" not in html

    @pytest.mark.parametrize("q", ["(", ".*", "[a-", "a" * 500])
    async def test_search_treats_input_literally(self, aclient, q):
        r = await aclient.get("/admin/users", params={"q": q}, cookies=await admin_cookies())
        assert r.status_code == 200


class TestRemovedSurface:
    @pytest.mark.parametrize("path", ["/admin/broadcasts", "/admin/commerce", "/admin/config"])
    async def test_removed_pages_are_gone(self, aclient, path):
        r = await aclient.get(path, cookies=await admin_cookies())
        assert r.status_code in (404, 405)

    async def test_navigation_has_no_dead_links(self, aclient):
        html = (await aclient.get("/admin/", cookies=await admin_cookies())).text
        for dead in ("/admin/broadcasts", "/admin/commerce", "/admin/config"):
            assert dead not in html

    async def test_do_nothing_api_endpoints_are_removed(self, aclient, monkeypatch):
        from src.core.config import get_settings

        monkeypatch.setenv("ADMIN_API_TOKEN", "tok")
        monkeypatch.setenv("DEV_API_TOKEN", "dev")
        get_settings.cache_clear()
        h = {"Authorization": "Bearer tok"}
        assert (await aclient.post("/api/v1/admin/broadcast", json={"text": "x"}, headers=h)).status_code in (404, 405)
        assert (await aclient.post(
            "/api/v1/dev/test-log", params={"service": "s", "message": "m"}, headers={"Authorization": "Bearer dev"}
        )).status_code in (404, 405)
