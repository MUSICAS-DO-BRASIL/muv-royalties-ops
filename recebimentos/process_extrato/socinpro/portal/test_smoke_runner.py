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
        argparse.Namespace(entity="HM", competence="2026-08", account_limit=1, staging_root=tmp_path, browser_executable=None)
    )
    assert result["SOCINPRO_REAL_SMOKE_STATUS"] == "NO_PAYMENT"
    assert result["ACCOUNT_INDEX"] == 1
    assert result["IDENTIFIER_MASKED"] == "id#synthetic"
    assert created[0].staging_dir == tmp_path.resolve()
    assert created[0].headed is True
