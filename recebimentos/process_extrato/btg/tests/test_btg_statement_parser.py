from __future__ import annotations

from decimal import Decimal
from dataclasses import replace
from pathlib import Path
import unittest
from unittest.mock import patch

from btg_bank_adapter import run_btg_month
from btg_statement_parser import StatementBlockedError, _parse_details_from_lines, parse_ptbr_decimal, validate_btg_statement


def fixture_lines(*, account: str = "TEST_BANK_ACCOUNT_001"):
    return [
        (1, 1, "HURST MUSIC SPE I S.A."),
        (1, 2, "Banco: 208 BTG PACTUAL"),
        (1, 3, f"Conta Investimento: {account}"),
        (2, 1, "Movimentação - Conta Investimento"),
        (2, 2, "Data Descrição Débito Crédito Saldo"),
        (2, 3, "01/08/2026 Saldo Inicial 1.000,00"),
        (2, 4, "02/08/2026 CRÉDITO COM NÚMERO 123-ABC 100,25 1.100,25"),
        (2, 5, "02/08/2026 DÉBITO - TAXA 0,25 1.100,00"),
        (3, 1, "03/08/2026 CRÉDITO-PÁGINA 200,00 1.300,00"),
        (3, 2, "3 de 3"),
        (3, 3, "03/08/2026 Saldo Final 1.300,00"),
        (3, 4, "Total de Créditos 300,25"),
        (3, 5, "Total de Débitos 0,25"),
    ]


class BtgStatementParserTests(unittest.TestCase):
    def test_ptbr_decimal_is_exact(self):
        self.assertEqual(parse_ptbr_decimal("1.234.567,89"), Decimal("1234567.89"))

    def test_parses_credit_debit_and_page_break(self):
        details = _parse_details_from_lines(fixture_lines(), "fixture.pdf")
        self.assertEqual(len(details.transactions), 3)
        self.assertEqual([t.direction for t in details.transactions], ["CREDIT", "DEBIT", "CREDIT"])
        self.assertEqual(details.transactions[0].description_raw, "CRÉDITO COM NÚMERO 123-ABC")
        self.assertEqual(details.transactions[-1].source_page, 3)
        self.assertTrue(validate_btg_statement(details).passed)

    def test_wrong_account_is_blocked(self):
        with self.assertRaises(StatementBlockedError):
            _parse_details_from_lines(fixture_lines(account="TEST_BANK_ACCOUNT_002"), "fixture.pdf")

    def test_global_closure_failure_is_reported(self):
        lines = fixture_lines()
        lines[-1] = (3, 5, "Total de Débitos 0,24")
        self.assertFalse(validate_btg_statement(_parse_details_from_lines(lines, "fixture.pdf")).passed)

    def test_per_transaction_balance_delta_failure_is_reported(self):
        details = _parse_details_from_lines(fixture_lines(), "fixture.pdf")
        transactions = list(details.transactions)
        transactions[1] = replace(transactions[1], amount=Decimal("0.24"))
        validation = validate_btg_statement(replace(details, transactions=tuple(transactions)))
        self.assertFalse(validation.passed)
        self.assertTrue(any("Balance delta mismatch" in error for error in validation.errors))

    def test_invalid_pdf_is_rejected(self):
        from btg_statement_parser import StatementError, parse_btg_statement_details
        with self.assertRaises(StatementError):
            parse_btg_statement_details(Path("does-not-exist.pdf"))

    def test_rerun_is_logically_idempotent(self):
        details = _parse_details_from_lines(fixture_lines(), "fixture.pdf")
        self.assertEqual(details.transactions, _parse_details_from_lines(fixture_lines(), "fixture.pdf").transactions)

    def test_adapter_output_is_repeatable(self):
        details = _parse_details_from_lines(fixture_lines(), "fixture.pdf")
        with self.subTest("no actual PDF is needed for adapter contract"):
            with patch("btg_bank_adapter.parse_btg_statement_details", return_value=details):
                from tempfile import TemporaryDirectory
                with TemporaryDirectory() as directory:
                    first = run_btg_month(entity="HM", period="2026-08", input_pdf="unused.pdf", output_root=directory)
                    second = run_btg_month(entity="HM", period="2026-08", input_pdf="unused.pdf", output_root=directory)
                    self.assertEqual(first["operational_credit_xlsx"], second["operational_credit_xlsx"])
                    self.assertTrue(first["operational_credit_xlsx"].is_file())


if __name__ == "__main__":
    unittest.main()
