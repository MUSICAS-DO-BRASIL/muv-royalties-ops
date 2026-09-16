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

    def inner_html(self):
        return self.text

    def wait_for(self, **_kwargs):
        return None

    def count(self):
        return self._count

    def all_inner_texts(self):
        return [self.text] if self._count else []

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
    session._search_clicked = True
    session._search_confirmed = True
    session._search_diagnostics = {"SEARCH_CONTROL_FOUND": True, "SEARCH_ACTIVATION_ATTEMPTED": True, "SEARCH_ACTIVATION_CONFIRMED": True, "SEARCH_RESULT_REFRESH_CONFIRMED": True}
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
    session._first_visible = lambda _page, selectors: start_field if any("Inicial" in selector or "inicial" in selector for selector in selectors) else end_field
    session._search_snapshot = lambda _page: ((), "", None)
    session._activate_search = lambda _page: setattr(session, "_search_clicked", True)
    session._confirm_search_refresh = lambda *_args: setattr(session, "_search_confirmed", True)

    session.select_competence("2026-08")

    assert (start_field.value, end_field.value) == ("01/08/2026", "31/08/2026")
    assert session._search_confirmed is True


def test_competence_failure_preserves_initialized_navigation_diagnostics(tmp_path):
    page = AuthenticatedNavigationPage(f"https://associado.socinpro.org.br{DEMONSTRATIVO_PATH}")
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._page = page
    session._navigate_to_demonstrativo = lambda _page: session._navigation_diagnostics.update(
        {"PORTAL_STAGE": "DEMONSTRATIVO_PAGE", "DEMONSTRATIVO_PAGE_CONFIRMED": True}
    )
    session._first_visible = lambda *_args: (_ for _ in ()).throw(TimeoutError("synthetic browser timeout"))

    with pytest.raises(PortalAdapterError, match="COMPETENCE_SELECTION_FAILED") as caught:
        session.select_competence("2026-08")

    assert caught.value.diagnostics["PORTAL_STAGE"] == "COMPETENCE_SELECTION"
    assert caught.value.diagnostics["DEMONSTRATIVO_PAGE_CONFIRMED"] is True


class SearchControl:
    def __init__(self, click=None, enabled=True):
        self.first = self
        self._click = click or (lambda: None)
        self._enabled = enabled

    def wait_for(self, **_kwargs):
        return None

    def is_enabled(self):
        return self._enabled

    def click(self, **_kwargs):
        return self._click()

    def locator(self, _selector):
        return self


class BrokenSearchControl(SearchControl):
    def wait_for(self, **_kwargs):
        raise TimeoutError("not visible")


class SearchPage:
    def __init__(self, control):
        self.control = control
        self.rows = []
        self.body = "Nenhum demonstrativo encontrado"
        self.markup = "<tr class='empty'></tr>"

    def get_by_role(self, _role, **_kwargs):
        return BrokenSearchControl()

    def get_by_text(self, _text):
        return BrokenSearchControl() if self.control is None else self.control

    def locator(self, selector):
        if "tbody tr" in selector:
            return FakeLocator(self.rows[0] if self.rows else "", len(self.rows))
        if selector == "body":
            return FakeLocator(self.body)
        if selector == "tbody":
            locator = FakeLocator()
            locator.inner_html = lambda: self.markup
            return locator
        return BrokenSearchControl()

    def wait_for_timeout(self, _milliseconds):
        return None


def test_search_activates_actionable_parent_of_nested_visible_text(tmp_path):
    clicked = []
    page = SearchPage(SearchControl(lambda: clicked.append(True)))
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))

    session._activate_search(page)

    assert clicked == [True]
    assert session._search_clicked is True


def test_search_activates_role_button_control(tmp_path):
    clicked = []

    class ButtonPage(SearchPage):
        def get_by_role(self, _role, **_kwargs):
            return SearchControl(lambda: clicked.append(True))

    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._activate_search(ButtonPage(None))

    assert clicked == [True]
    assert session._search_clicked is True


def test_search_click_is_not_recorded_when_action_cannot_be_activated(tmp_path):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))

    with pytest.raises(PortalAdapterError, match="SEARCH_ACTION_FAILED"):
        session._activate_search(SearchPage(None))

    assert session._search_clicked is False


def test_search_refresh_requires_post_click_result_mutation(tmp_path):
    page = SearchPage(SearchControl())
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    before = session._search_snapshot(page)
    page.markup = "<tr><td>25/08/2026</td></tr>"

    session._confirm_search_refresh(page, before)

    assert session._search_confirmed is True


def test_pre_search_empty_state_cannot_authorize_no_payment(tmp_path):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._page = FakePage("Nenhum demonstrativo")
    session._competence = "2026-08"

    with pytest.raises(PortalAdapterError, match="SEARCH_NOT_EXECUTED"):
        session.download_statements(RuntimeAccount(1, "user", "secret"))


def test_refreshed_empty_search_allows_no_payment(tmp_path):
    page = SearchPage(SearchControl())
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    before = session._search_snapshot(page)
    session._activate_search(page)
    page.markup = "<tr class='empty refreshed'></tr>"
    session._confirm_search_refresh(page, before)
    session._page = page
    session._competence = "2026-08"

    assert tuple(session.download_statements(RuntimeAccount(1, "user", "secret"))) == ()


def test_select_competence_activates_search_and_confirms_payment_refresh(tmp_path):
    page = SearchPage(None)
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._page = page
    session._navigate_to_demonstrativo = lambda _page: None

    class Field:
        def __init__(self): self.value = ""
        def fill(self, value): self.value = value
        def press(self, _key): return None
        def input_value(self): return self.value

    start, end = Field(), Field()
    session._first_visible = lambda _page, selectors: start if any("Inicial" in selector or "inicial" in selector for selector in selectors) else end
    def refresh_payment():
        page.rows = ["25/08/2026 demonstrativo"]
        page.body = "Resultado atualizado"
        page.markup = "<tr><td>25/08/2026</td></tr>"

    page.control = SearchControl(refresh_payment)

    session.select_competence("2026-08")

    assert (start.value, end.value) == ("01/08/2026", "31/08/2026")
    assert session._search_clicked is True
    assert session._search_confirmed is True
    session._download = lambda *_args: tmp_path / "synthetic.pdf"
    assert len(tuple(session.download_statements(RuntimeAccount(1, "user", "secret")))) == 2


def test_date_control_missing_reports_specific_sanitized_reason(tmp_path):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._competence_diagnostics = session._new_competence_diagnostics("01/08/2026", "31/08/2026")
    session._first_visible = lambda *_args: (_ for _ in ()).throw(PortalAdapterError("UNEXPECTED_PAGE"))

    with pytest.raises(PortalAdapterError, match="COMPETENCE_SELECTION_FAILED") as caught:
        session._date_control(object(), "START_DATE", ["input[name*='dtInicial' i]"])

    assert caught.value.diagnostics["COMPETENCE_FAILURE_REASON"] == "START_DATE_CONTROL_NOT_FOUND"
    assert caught.value.diagnostics["START_DATE_CONTROL_FOUND"] is False


def test_date_readback_mismatch_blocks_search(tmp_path):
    session = PlaywrightSocinproSession(BrowserSettings(tmp_path))
    session._competence_diagnostics = session._new_competence_diagnostics("01/08/2026", "31/08/2026")

    class Field:
        def __init__(self, value): self.value = value
        def input_value(self): return self.value

    with pytest.raises(PortalAdapterError, match="COMPETENCE_SELECTION_FAILED") as caught:
        session._validate_competence_dates(Field("02/08/2026"), Field("31/08/2026"))

    assert caught.value.diagnostics["COMPETENCE_FAILURE_REASON"] == "START_DATE_MISMATCH"
    assert caught.value.diagnostics["START_DATE_MATCH"] is False
    assert session._search_clicked is False
