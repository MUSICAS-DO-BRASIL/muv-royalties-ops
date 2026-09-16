import argparse
from types import SimpleNamespace

from socinpro.portal import smoke_runner


def test_smoke_runner_uses_first_runtime_account_and_only_caller_staging(monkeypatch, tmp_path):
    account = SimpleNamespace(index=1, masked_identifier="id#synthetic")
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=(account,)))
    created = []

    class Session:
        browser_started = True
        navigation_diagnostics = {
            "EXPECTED_START_DATE": "01/08/2026", "EXPECTED_END_DATE": "31/08/2026",
            "ACTUAL_START_DATE": "01/08/2026", "ACTUAL_END_DATE": "31/08/2026",
            "DATE_RANGE_VALIDATION": True, "DATE_CONTROLS_SETTLED": True,
            "SEARCH_CONTROL_FOUND": True, "SEARCH_ACTIVATION_ATTEMPTED": True,
            "SEARCH_ACTIVATION_CONFIRMED": True, "SEARCH_RESULT_REFRESH_CONFIRMED": True,
            "SEARCH_PROOF_METHOD": "DOM_MUTATION", "REFRESHED_RESULT_EMPTY": True,
            "COMPETENCE_TOTAL_SECONDS": 1.0, "SEARCH_CONTROL_LOCATOR_SECONDS": 0.1,
            "SEARCH_ACTIVATION_SECONDS": 0.1, "SEARCH_REFRESH_SECONDS": 0.1,
        }

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
    diagnostics = result["ACCOUNT_RESULTS"][0]["navigation_diagnostics"]
    assert diagnostics["SEARCH_PROOF_METHOD"] == "DOM_MUTATION"
    assert diagnostics["DATE_RANGE_VALIDATION"] is True


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


def test_full_range_continues_after_download_when_stop_flag_is_false(monkeypatch, tmp_path):
    accounts = tuple(SimpleNamespace(index=index, masked_identifier=f"id#{index}") for index in range(1, 96))
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=accounts))
    calls = []
    class Session:
        def __init__(self, settings): self.settings = settings
        def authenticate(self, account): calls.append(account.index)
        def select_competence(self, _competence): pass
        def download_statements(self, account):
            if account.index != 1: return ()
            path = self.settings.staging_dir / "download.pdf"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"x"); return (path,)
        def close(self): pass
    monkeypatch.setattr(smoke_runner, "PlaywrightSocinproSession", Session)
    args = argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, start_at=1, max_accounts=95, stop_after_first_download=False, staging_root=tmp_path, browser_executable=None)
    result = smoke_runner.run_smoke(args)
    assert calls == list(range(1, 96))
    assert result["ACCOUNTS_ATTEMPTED"] == 95
    assert result["FIRST_PAYMENT_ACCOUNT_INDEX"] == 1
    assert result["STOPPED_AFTER_FIRST_DOWNLOAD"] is False


def test_smoke_runner_includes_sanitized_search_proof_for_pass(monkeypatch, tmp_path):
    account = SimpleNamespace(index=1, masked_identifier="id#synthetic")
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=(account,)))

    class Session:
        navigation_diagnostics = {"SEARCH_CONTROL_FOUND": True, "SEARCH_ACTIVATION_ATTEMPTED": True, "SEARCH_ACTIVATION_CONFIRMED": True, "SEARCH_RESULT_REFRESH_CONFIRMED": True, "SEARCH_PROOF_METHOD": "DOM_MUTATION", "REFRESHED_RESULT_EMPTY": False}
        def __init__(self, settings): self.settings = settings
        def authenticate(self, _account): pass
        def select_competence(self, _competence): pass
        def download_statements(self, _account):
            path = self.settings.staging_dir / "synthetic.pdf"; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(b"x"); return (path,)
        def close(self): pass

    monkeypatch.setattr(smoke_runner, "PlaywrightSocinproSession", Session)
    args = argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, start_at=1, max_accounts=None, stop_after_first_download=False, staging_root=tmp_path, browser_executable=None)
    result = smoke_runner.run_smoke(args)

    assert result["ACCOUNT_RESULTS"][0]["status"] == "PASS"
    assert result["ACCOUNT_RESULTS"][0]["navigation_diagnostics"]["SEARCH_PROOF_METHOD"] == "DOM_MUTATION"


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


def test_smoke_runner_sanitizes_unexpected_post_login_exception(monkeypatch, tmp_path):
    account = SimpleNamespace(index=1, masked_identifier="id#synthetic")
    monkeypatch.setattr(smoke_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=(account,)))

    class Session:
        navigation_diagnostics = {"PORTAL_STAGE": "POST_LOGIN", "CURRENT_URL_CLASS": "UNKNOWN_AUTHENTICATED_PAGE", "unsafe": "credential-value"}
        def __init__(self, _settings): pass
        def authenticate(self, _account): pass
        def select_competence(self, _competence): raise TimeoutError("cookie token credential-value")
        def close(self): pass

    monkeypatch.setattr(smoke_runner, "PlaywrightSocinproSession", Session)
    args = argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, start_at=1, max_accounts=None, stop_after_first_download=False, staging_root=tmp_path, browser_executable=None)
    result = smoke_runner.run_smoke(args)

    account_result = result["ACCOUNT_RESULTS"][0]
    assert account_result["status"] == "FAILED"
    assert account_result["failure_stage"] == "POST_LOGIN_NAVIGATION"
    assert account_result["failure_reason"] == "UNEXPECTED_EXCEPTION"
    assert account_result["exception_class_safe"] == "TimeoutError"
    assert account_result["navigation_diagnostics"] == {"PORTAL_STAGE": "POST_LOGIN", "CURRENT_URL_CLASS": "UNKNOWN_AUTHENTICATED_PAGE"}
    assert "credential-value" not in repr(account_result)
