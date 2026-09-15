"""Synthetic identity regression checks, including fail-closed configuration."""
import pytest

from bank_account_config import BankAccountConfig, BankAccountConfigurationError
from btg_statement_parser import StatementBlockedError, _parse_details_from_lines
from test_btg_statement_parser import fixture_lines


def test_expected_account_is_preserved_in_identity_and_transactions():
    details = _parse_details_from_lines(fixture_lines(), "synthetic.pdf")
    assert details.identity.account_ref == "TEST_BANK_ACCOUNT_001"
    assert all(row.account_ref == details.identity.account_ref for row in details.transactions)


@pytest.mark.parametrize("account", ["TEST_BANK_ACCOUNT_002", "TEST_BANK_ACCOUNT_001-EXTRA", "TEST_BANK_ACCOUNT_001/EXTRA", "TEST_BANK_ACCOUNT_0010"])
def test_wrong_or_prefix_account_is_blocked(account):
    with pytest.raises(StatementBlockedError) as error:
        _parse_details_from_lines(fixture_lines(account=account), "synthetic.pdf")
    assert account not in str(error.value)
    assert "TEST_BANK_ACCOUNT_001" not in str(error.value)


@pytest.mark.parametrize("value", [None, "", " ", "TEST ACCOUNT", "TEST\nACCOUNT", "TEST.*ACCOUNT"])
def test_missing_or_invalid_configuration_fails_closed(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("MUV_BANK_ACCOUNT_ID", raising=False)
    else:
        monkeypatch.setenv("MUV_BANK_ACCOUNT_ID", value)
    with pytest.raises(StatementBlockedError, match="configuration missing or invalid"):
        _parse_details_from_lines(fixture_lines(), "synthetic.pdf")


def test_configuration_is_read_for_each_parse(monkeypatch):
    monkeypatch.setenv("MUV_BANK_ACCOUNT_ID", "TEST_BANK_ACCOUNT_002")
    details = _parse_details_from_lines(fixture_lines(account="TEST_BANK_ACCOUNT_002"), "synthetic.pdf")
    assert details.identity.account_ref == "TEST_BANK_ACCOUNT_002"
    with pytest.raises(StatementBlockedError):
        _parse_details_from_lines(fixture_lines(), "synthetic.pdf")


def test_config_repr_and_error_do_not_disclose_account():
    assert "TEST_BANK_ACCOUNT_001" not in repr(BankAccountConfig("TEST_BANK_ACCOUNT_001"))
    with pytest.raises(BankAccountConfigurationError) as error:
        BankAccountConfig("TEST PRIVATE VALUE")
    assert "TEST PRIVATE VALUE" not in str(error.value)


@pytest.mark.parametrize("index,replacement", [(0, "OUTRA EMPRESA SINTETICA"), (1, "Banco: 000 BANCO SINTETICO")])
def test_company_and_bank_checks_are_still_required(index, replacement):
    lines = fixture_lines()
    page, line, _ = lines[index]
    lines[index] = (page, line, replacement)
    with pytest.raises(StatementBlockedError):
        _parse_details_from_lines(lines, "synthetic.pdf")


def test_conflicting_account_headers_are_blocked():
    lines = fixture_lines() + [(4, 1, "Conta Investimento: TEST_BANK_ACCOUNT_002")]
    with pytest.raises(StatementBlockedError):
        _parse_details_from_lines(lines, "synthetic.pdf")
