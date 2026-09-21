from types import SimpleNamespace

from socinpro.portal import provenance_runner


def test_raw_account_identity_preserves_noncanonical_login_component():
    assert provenance_runner.raw_account_identity("synthetic.operator") == "synthetic"


def test_inventory_checkpoints_account_and_rows_without_password(monkeypatch, tmp_path):
    account = SimpleNamespace(index=1, identifier="synthetic.operator", password="secret")
    monkeypatch.setattr(provenance_runner, "preflight_runtime_credentials", lambda _entity: SimpleNamespace(accounts=(account,)))

    class Session:
        def __init__(self, _settings): pass
        def authenticate(self, _account): pass
        def select_competence(self, _competence): pass
        def inventory_payment_rows(self, _account):
            return ({"payment_row_ordinal": 1, "payment_date": "01/01/2026", "portal_displayed_amount": "123,45", "payment_row_key": "row-key", "analitico_action_available": True, "sintetico_action_available": True},)
        def close(self): pass

    monkeypatch.setattr(provenance_runner, "PlaywrightSocinproSession", Session)
    result = provenance_runner.run_provenance_inventory(entity="HM", competence="2026-01", account_indexes=[1], staging_root=tmp_path)
    stored = (tmp_path / "provenance_checkpoint.json").read_text(encoding="utf-8")
    assert result["payment_rows"] == 1
    assert '"account_login": "synthetic.operator"' in stored
    assert '"raw_account_identity": "synthetic"' in stored
    assert "secret" not in stored
    assert '"document_download_count": 0' in stored
