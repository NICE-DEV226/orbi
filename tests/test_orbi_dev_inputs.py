"""Lire ce que l'utilisateur colle ou écrit, et vérifier un dépôt sur GitHub : formats acceptés, refus motivés, aucune surprise."""

import httpx
import pytest
from pydantic import ValidationError

from src.orbi_dev.github import Lookup, lookup_repo
from src.orbi_dev.inputs import Repo, clean_text, parse_branch, parse_name, parse_repo, valid_branch
from src.orbi_dev.models import Project


class TestParseRepo:
    @pytest.mark.parametrize("text", [
        "Voilà le dépôt https://github.com/acme/demo merci",
        "(https://github.com/acme/demo)",
        "<https://github.com/acme/demo>.",
        "regarde github.com/acme/demo/tree/main svp",
        "Mon dépôt :\nhttps://github.com/acme/demo\nà utiliser",
    ])
    def test_finds_an_address_inside_a_sentence(self, text):
        repo = parse_repo(text)
        assert repo is not None and repo.url == "https://github.com/acme/demo"

    def test_branch_comes_from_the_tree_path(self):
        assert parse_repo("https://github.com/acme/demo/tree/feat/login").branch == "feat/login"

    @pytest.mark.parametrize("text", [
        "bonjour tout le monde", "et/ou ceci cela", "https://evil.example/acme/demo", "https://github.com.evil.example/a/b",
        "https://github.com/acme", "javascript:alert(1)", "x" * 3000,
    ])
    def test_refuses_what_is_not_a_github_repo(self, text):
        # « et/ou » seul serait lu comme `proprietaire/depot` ; dans une phrase, il ne l'est pas
        assert parse_repo(text) is None

    def test_full_name(self):
        assert Repo("demo", "https://github.com/acme/demo", "").full_name == "acme/demo"


class TestBranch:
    @pytest.mark.parametrize("name", ["main", "master", "feature/login-2", "release_1.2", "v1.0.0", "fix+hotfix"])
    def test_valid(self, name):
        assert valid_branch(name) and parse_branch(name) == name

    @pytest.mark.parametrize("name", [
        "", "a b", "a..b", "-rf", "/x", "x/", "x//y", "x.lock", "x.", "$(id)", "a;b", "a`b`", "a\nb", "é", "x" * 101, "@{u}",
    ])
    def test_invalid(self, name):
        assert not valid_branch(name) and parse_branch(name) is None

    @pytest.mark.parametrize("word", ["-", "défaut", "Default", "par défaut"])
    def test_default_words_mean_the_repo_default(self, word):
        assert parse_branch(word) == ""


class TestCleanText:
    def test_control_and_bidi_characters_are_removed(self):
        assert clean_text("a\x00b‮c​d\x1b") == "abcd"

    def test_newlines_are_kept_but_not_piled_up(self):
        assert clean_text("a\r\nb\n\n\n\n\nc") == "a\nb\n\nc"

    def test_name_is_one_short_line(self):
        assert parse_name("  Mon site ") == "Mon site"
        assert parse_name("") is None and parse_name("a\nb") is None and parse_name("x" * 61) is None


class TestModelRules:
    """Les mêmes règles valent pour le web : le modèle refuse ce que le bot refuse."""

    def test_branch_is_validated(self):
        with pytest.raises(ValidationError):
            Project(owner_id=1, name="p", repo_url="https://github.com/a/b", default_branch="a b; rm")
        assert Project(owner_id=1, name="p", repo_url="https://github.com/a/b", default_branch="").default_branch == ""

    def test_name_is_validated(self):
        with pytest.raises(ValidationError):
            Project(owner_id=1, name="deux\nlignes", repo_url="https://github.com/a/b")


def client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


REPO = Repo("demo", "https://github.com/acme/demo", "")


class TestGitHubLookup:
    async def test_found_reads_default_branch(self):
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={
                "default_branch": "master", "description": "Un dépôt", "language": "Python", "archived": False,
            })

        info = await lookup_repo(REPO, client(handler))
        assert info.state == Lookup.FOUND and info.default_branch == "master" and info.language == "Python"
        assert str(seen[0].url) == "https://api.github.com/repos/acme/demo"
        assert "authorization" not in {k.lower() for k in seen[0].headers}  # aucune clé GitHub n'est envoyée

    async def test_404_means_missing_or_private(self):
        assert (await lookup_repo(REPO, client(lambda r: httpx.Response(404)))).state == Lookup.NOT_FOUND

    @pytest.mark.parametrize("status", [403, 429, 500, 502, 301])
    async def test_rate_limit_and_errors_prove_nothing(self, status):
        assert (await lookup_repo(REPO, client(lambda r: httpx.Response(status)))).state == Lookup.UNKNOWN

    async def test_network_failure_proves_nothing(self):
        def boom(request):
            raise httpx.ConnectTimeout("lent")

        assert (await lookup_repo(REPO, client(boom))).state == Lookup.UNKNOWN

    @pytest.mark.parametrize("body", [b"pas du json", b"[1, 2]", b"null"])
    async def test_unexpected_body_is_unknown(self, body):
        assert (await lookup_repo(REPO, client(lambda r: httpx.Response(200, content=body)))).state == Lookup.UNKNOWN

    async def test_description_is_bounded(self):
        info = await lookup_repo(REPO, client(lambda r: httpx.Response(200, json={"description": "x" * 5000})))
        assert len(info.description) == 200
