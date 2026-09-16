from pathlib import Path

import pytest

from socinpro.portal.browser_adapter import BrowserSettings, PlaywrightSocinproSession, PortalAdapterError
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
