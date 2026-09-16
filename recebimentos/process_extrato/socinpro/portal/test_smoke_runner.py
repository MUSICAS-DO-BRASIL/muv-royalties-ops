import argparse
from types import SimpleNamespace

from socinpro.portal import smoke_runner


def test_smoke_runner_uses_first_runtime_account_and_only_caller_staging(monkeypatch, tmp_path):
    account = SimpleNamespace(index=1, masked_identifier="id#synthetic")
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=(account,)))
    created = []

    class Session:
        browser_started = True

        def __init__(self, settings):
            created.append(settings)

        def authenticate(self, _account):
            return None

        def select_competence(self, _competence):
            return None

        def download_statements(self, _account):
            return ()

        def close(self):
            return None

    monkeypatch.setattr(smoke_runner, "PlaywrightSocinproSession", Session)
    result = smoke_runner.run_smoke(
        argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, start_at=1, max_accounts=None, stop_after_first_download=False, staging_root=tmp_path, browser_executable=None)
    )
    assert result["SOCINPRO_REAL_SMOKE_STATUS"] == "NO_PAYMENT"
    assert result["PLANNED_ACCOUNT_START"] == 1
    assert result["ACCOUNT_RESULTS"][0]["masked_identifier"] == "id#synthetic"
    assert created[0].staging_dir == tmp_path.resolve()
    assert created[0].headed is True


def test_range_stops_at_first_download_and_no_payment_continues(monkeypatch, tmp_path):
    accounts = tuple(SimpleNamespace(index=index, masked_identifier=f"id#{index}") for index in range(1, 13))
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=accounts))
    calls = []
    class Session:
        browser_started = True
        def __init__(self, settings): self.settings = settings
        def authenticate(self, account): calls.append(account.index)
        def select_competence(self, _competence): pass
        def download_statements(self, account):
            if account.index != 4: return ()
            path = self.settings.staging_dir / "download.pdf"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"x"); return (path,)
        def close(self): pass
    monkeypatch.setattr(smoke_runner, "PlaywrightSocinproSession", Session)
    args = argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, start_at=2, max_accounts=10, stop_after_first_download=True, staging_root=tmp_path, browser_executable=None)
    result = smoke_runner.run_smoke(args)
    assert (result["PLANNED_ACCOUNT_START"], result["PLANNED_ACCOUNT_END"], result["PLANNED_ACCOUNT_COUNT"]) == (2, 11, 10)
    assert calls == [2, 3, 4] and result["STOPPED_AFTER_FIRST_DOWNLOAD"] is True


def test_start_beyond_accounts_fails_before_browser(monkeypatch, tmp_path):
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=(SimpleNamespace(index=1, masked_identifier="id#1"),)))
    args = argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, start_at=2, max_accounts=1, stop_after_first_download=False, staging_root=tmp_path, browser_executable=None)
    assert smoke_runner.run_smoke(args)["SOCINPRO_REAL_SMOKE_STATUS"] == "SMOKE_START_AT_OUT_OF_RANGE"


def test_smoke_runner_returns_only_sanitized_navigation_diagnostics(monkeypatch, tmp_path):
    account = SimpleNamespace(index=1, masked_identifier="id#synthetic")
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=(account,)))

    class Session:
        def __init__(self, _settings): pass
        def authenticate(self, _account): pass
        def select_competence(self, _competence):
            raise smoke_runner.PortalAdapterError("POST_LOGIN_NAVIGATION_FAILED", {"PORTAL_STAGE": "POST_LOGIN_NAVIGATION", "LAYOUT_FAILURE_REASON": "TARGET_PAGE_NOT_CONFIRMED"})
        def close(self): pass

    monkeypatch.setattr(smoke_runner, "PlaywrightSocinproSession", Session)
    args = argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, start_at=1, max_accounts=None, stop_after_first_download=False, staging_root=tmp_path, browser_executable=None)
    result = smoke_runner.run_smoke(args)

    account_result = result["ACCOUNT_RESULTS"][0]
    assert account_result["status"] == "PORTAL_LAYOUT_REVIEW"
    assert account_result["navigation_diagnostics"] == {"PORTAL_STAGE": "POST_LOGIN_NAVIGATION", "LAYOUT_FAILURE_REASON": "TARGET_PAGE_NOT_CONFIRMED"}
