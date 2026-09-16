from pathlib import Path

import pytest

from socinpro.portal.browser_adapter import (
    DEMONSTRATIVO_PATH,
    DEMONSTRATIVO_URL,
    BrowserSettings,
    PlaywrightSocinproSession,
    PortalAdapterError,
    competence_date_range,
)
from socinpro.portal_runtime import HumanInterventionRequired, RuntimeAccount


class FakeLocator:
    first = None

    def __init__(self, text="", count=0):
        self.text = text
        self._count = count
        self.first = self

    def inner_text(self, **_kwargs):
        return self.text

    def wait_for(self, **_kwargs):
        return None

    def count(self):
        return self._count

    def nth(self, _index):
        return self


class FakePage:
    def __init__(self, text="", count=0):
        self.text = text
        self.count = count

    def locator(self, _selector):
        return FakeLocator(self.text, self.count)


class AuthenticatedNavigationPage(FakePage):
    def __init__(self, final_url, text="Demonstrativo SOCINPRO"):
        super().__init__(text)
        self.url = "https://associado.socinpro.org.br/portal-web/pages/protected/home.xhtml"
        self.final_url = final_url
        self.goto_calls = []

    def goto(self, url, **kwargs):
        self.goto_calls.append((url, kwargs))
        self.url = self.final_url


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Financeiro", "PASS"),
        ("senha inválida", "INVALID_CREDENTIAL"),
        ("captcha", "CAPTCHA_REQUIRED"),
        ("código MFA", "MFA_REQUIRED"),
    ],
)
def test_login_outcomes_are_categorised_without_credentials(tmp_path, text, expected):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    if expected == "PASS":
        session._validate_session(FakePage(text))
    elif expected.endswith("REQUIRED"):
        with pytest.raises(HumanInterventionRequired, match=expected):
            session._validate_session(FakePage(text))
    else:
        with pytest.raises(PortalAdapterError, match=expected):
            session._validate_session(FakePage(text))


def test_no_payment_and_unexpected_page_are_distinct(tmp_path):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._page = FakePage("Nenhum demonstrativo")
    session._competence = "2026-08"
    session._search_confirmed = True
    assert tuple(session.download_statements(RuntimeAccount(1, "user", "secret"))) == ()

    session._page = FakePage("layout sem tabela", count=1)
    with pytest.raises(PortalAdapterError, match="UNEXPECTED_PAGE"):
        session.download_statements(RuntimeAccount(1, "user", "secret"))


def test_staging_root_and_secret_safety(tmp_path):
    staging = tmp_path / "caller-staging"
    session = PlaywrightSocinproSession(BrowserSettings(staging))
    target = session._unique_target("original.pdf")
    assert target.parent == staging
    account = RuntimeAccount(7, "synthetic-user", "never-log-this-password")
    assert "never-log-this-password" not in repr(account)
    assert "never-log-this-password" not in str(PortalAdapterError("DOWNLOAD_TIMEOUT"))


def test_download_timeout_is_categorised(tmp_path):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    class BrokenDownloadPage:
        def expect_download(self, **_kwargs):
            raise TimeoutError("synthetic timeout")
    session._first_visible = lambda *_args: object()
    with pytest.raises(PortalAdapterError, match="DOWNLOAD_TIMEOUT"):
        session._download(BrokenDownloadPage(), RuntimeAccount(1, "user", "secret"), "analitico", ["button"])


@pytest.mark.parametrize(("competence", "start", "end"), [("2026-08", "01/08/2026", "31/08/2026"), ("2026-09", "01/09/2026", "30/09/2026"), ("2026-02", "01/02/2026", "28/02/2026"), ("2028-02", "01/02/2028", "29/02/2028"), ("2026-12", "01/12/2026", "31/12/2026")])
def test_exact_competence_month_boundaries(competence, start, end):
    actual_start, actual_end = competence_date_range(competence)
    assert actual_start.strftime("%d/%m/%Y") == start and actual_end.strftime("%d/%m/%Y") == end


def test_download_is_saved_only_to_caller_staging_root(tmp_path):
    class Button:
        def click(self):
            return None
    class Download:
        suggested_filename = "portal-original.pdf"
        def save_as(self, path):
            Path(path).write_bytes(b"%PDF-synthetic")
    class Event:
        value = Download()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    class Page:
        def expect_download(self, **_kwargs): return Event()
    staging = tmp_path / "staging"
    session = PlaywrightSocinproSession(BrowserSettings(staging))
    session._first_visible = lambda *_args: Button()
    path = session._download(Page(), RuntimeAccount(1, "user", "secret"), "analitico", ["button"])
    assert path.parent == staging
    assert path.name == "portal-original.pdf"


def test_navigation_uses_authenticated_demonstrativo_route_and_verifies_page(tmp_path):
    page = AuthenticatedNavigationPage(f"https://associado.socinpro.org.br{DEMONSTRATIVO_PATH}?cid=synthetic")
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))

    session._navigate_to_demonstrativo(page)

    assert page.goto_calls == [(DEMONSTRATIVO_URL, {"wait_until": "domcontentloaded", "timeout": session.settings.timeout_ms})]


@pytest.mark.parametrize(
    ("final_url", "text"),
    [
        ("https://associado.socinpro.org.br/portal-web/pages/public/access/login.xhtml", "Entrar"),
        (f"https://associado.socinpro.org.br{DEMONSTRATIVO_PATH}", "Página financeira"),
    ],
)
def test_navigation_rejects_redirect_or_non_demonstrativo_page(tmp_path, final_url, text):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))

    with pytest.raises(PortalAdapterError, match="POST_LOGIN_NAVIGATION_FAILED"):
        session._navigate_to_demonstrativo(AuthenticatedNavigationPage(final_url, text))


def test_navigation_failure_has_sanitized_post_login_diagnostics(tmp_path):
    credential_value = "credential-value-that-must-not-appear"
    page = AuthenticatedNavigationPage("https://associado.socinpro.org.br/portal-web/pages/public/access/login.xhtml", text=f"raw html {credential_value} cookie token R$ 999")
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))

    with pytest.raises(PortalAdapterError, match="POST_LOGIN_NAVIGATION_FAILED") as caught:
        session._navigate_to_demonstrativo(page)

    diagnostics = caught.value.diagnostics
    assert diagnostics == {
        "PORTAL_STAGE": "POST_LOGIN_NAVIGATION",
        "NAV_FINANCEIRO_FOUND": False,
        "NAV_FINANCEIRO_ACTIVATED": False,
        "NAV_SOCINPRO_FOUND": False,
        "NAV_SOCINPRO_ACTIVATED": False,
        "NAV_DEMONSTRATIVO_FOUND": False,
        "NAV_DEMONSTRATIVO_ACTIVATED": False,
        "DEMONSTRATIVO_PAGE_CONFIRMED": False,
        "CURRENT_URL_CLASS": "OTHER",
        "LAYOUT_FAILURE_REASON": "TARGET_PAGE_NOT_CONFIRMED",
    }
    assert credential_value not in repr(diagnostics)
    assert all(secret not in repr(diagnostics).casefold() for secret in ("cookie", "token", "raw html", "r$ 999"))


def test_navigation_failure_is_not_misclassified_as_competence_failure(tmp_path):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._page = object()
    session._navigate_to_demonstrativo = lambda _page: (_ for _ in ()).throw(
        PortalAdapterError("POST_LOGIN_NAVIGATION_FAILED", {"PORTAL_STAGE": "POST_LOGIN_NAVIGATION"})
    )

    with pytest.raises(PortalAdapterError, match="POST_LOGIN_NAVIGATION_FAILED") as caught:
        session.select_competence("2026-08")

    assert caught.value.category == "POST_LOGIN_NAVIGATION_FAILED"


def test_successful_navigation_continues_to_competence_selection(tmp_path):
    class Page:
        def locator(self, _selector):
            class Rows:
                def all_inner_texts(self): return []
            return Rows()

    class Field:
        def __init__(self): self.value = ""
        def fill(self, value): self.value = value
        def press(self, _key): return None
        def input_value(self): return self.value

    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._page = Page()
    start_field, end_field = Field(), Field()
    session._navigate_to_demonstrativo = lambda _page: None
    session._first_visible = lambda _page, selectors: start_field if "dtInicial" in selectors[0] else end_field
    session._click_text = lambda _page, labels: labels == ["Pesquisar"]
    session._confirm_search_refresh = lambda *_args: None

    session.select_competence("2026-08")

    assert (start_field.value, end_field.value) == ("01/08/2026", "31/08/2026")
    assert session._search_confirmed is True
