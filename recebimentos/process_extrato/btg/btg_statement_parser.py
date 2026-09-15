"""Parsing and financial validation for BTG investment-account statements.

This module is deliberately independent of the legacy numbered scripts.  It
preserves the raw bank description and source locator while deriving the
direction and amount from the exact Decimal balance variation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
import unicodedata
from typing import Iterable

import pdfplumber

from bank_account_config import BankAccountConfig, BankAccountConfigurationError


ENTITY = "HM"
BANK_SOURCE = "BTG"
BANK_CODE = "208"
COMPANY = "HURST MUSIC SPE I S.A."
ZERO = Decimal("0.00")

DATE_RE = re.compile(r"\b\d{2}/\d{2}/\d{4}\b")
MONEY_RE = re.compile(r"(?:\d{1,3}(?:\.\d{3})*|\d+),\d{2}")


class StatementError(ValueError):
    """A PDF cannot be safely treated as a BTG HM statement."""


class StatementBlockedError(StatementError):
    """The account identity is inconsistent with the HM BTG contract."""


@dataclass(frozen=True)
class AccountIdentity:
    company: str
    bank_code: str
    account_ref: str


@dataclass(frozen=True)
class NormalizedTransaction:
    entity: str
    bank_source: str
    account_ref: str
    transaction_date: date
    description_raw: str
    direction: str
    amount: Decimal
    balance_after: Decimal
    source_file: str
    source_page: int
    source_line: int
    operational_credit_candidate: bool


@dataclass(frozen=True)
class StatementDetails:
    identity: AccountIdentity
    initial_balance: Decimal
    total_credits_reported: Decimal
    total_debits_reported: Decimal
    final_balance: Decimal
    transactions: tuple[NormalizedTransaction, ...]


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    initial_balance: Decimal
    total_credits: Decimal
    total_debits: Decimal
    final_balance: Decimal
    transaction_count: int
    credit_transaction_count: int
    debit_transaction_count: int
    errors: tuple[str, ...]


def parse_ptbr_decimal(value: str) -> Decimal:
    """Parse a Brazilian monetary value exactly; rejects malformed input."""
    normalized = value.strip().replace(".", "").replace(",", ".")
    try:
        result = Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"Invalid pt-BR monetary value: {value!r}") from exc
    return result.quantize(Decimal("0.01"))


def _fold(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value.upper())
        if not unicodedata.combining(char)
    )


def _pdf_lines(pdf_path: Path) -> list[tuple[int, int, str]]:
    try:
        with pdfplumber.open(pdf_path) as pdf:
            lines: list[tuple[int, int, str]] = []
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                for line_number, raw in enumerate(text.splitlines(), start=1):
                    line = re.sub(r"\s+", " ", raw).strip()
                    if line:
                        lines.append((page_number, line_number, line))
    except Exception as exc:
        raise StatementError("Unable to read the supplied PDF") from exc
    if not lines:
        raise StatementError("PDF has no extractable text")
    return lines


def _extract_identity(lines: Iterable[tuple[int, int, str]]) -> AccountIdentity:
    try:
        config = BankAccountConfig.from_environment()
    except BankAccountConfigurationError:
        raise StatementBlockedError("BTG account configuration missing or invalid: set MUV_BANK_ACCOUNT_ID") from None
    text = "\n".join(line for _, _, line in lines)
    folded = _fold(text)
    company_ok = "HURST MUSIC SPE I S.A" in folded
    bank_ok = bool(re.search(r"BANCO:\s*208\s*BTG\s*PACTUAL", folded))
    accounts = re.findall(r"CONTA INVESTIMENTO:[ \t]*([^\s]+)", text, flags=re.IGNORECASE)
    account_ok = bool(accounts) and all(account == config.account_id for account in accounts)
    if not (company_ok and bank_ok and account_ok):
        missing = [
            name for name, found in (("company", company_ok), ("bank", bank_ok), ("account", account_ok))
            if not found
        ]
        raise StatementBlockedError("BTG HM identity validation failed: " + ", ".join(missing))
    return AccountIdentity(company=COMPANY, bank_code=BANK_CODE, account_ref=config.account_id)


def _is_non_transaction(line: str) -> bool:
    folded = _fold(line)
    return any(marker in folded for marker in (
        "SALDO INICIAL", "SALDO FINAL", "TOTAL DE CREDITOS", "TOTAL DE DEBITOS",
        "MOVIMENTACAO - CONTA", "DATA DESCRICAO DEBITO CREDITO SALDO",
    )) or bool(re.fullmatch(r"\d+ DE \d+", folded))


def _parse_details_from_lines(lines: list[tuple[int, int, str]], source_file: str) -> StatementDetails:
    identity = _extract_identity(lines)
    initial_balance: Decimal | None = None
    final_balance: Decimal | None = None
    reported_credits: Decimal | None = None
    reported_debits: Decimal | None = None
    candidates: list[tuple[date, str, Decimal, int, int]] = []

    for page, source_line, line in lines:
        folded = _fold(line)
        amounts = MONEY_RE.findall(line)
        if "SALDO INICIAL" in folded:
            if amounts:
                initial_balance = parse_ptbr_decimal(amounts[-1])
            continue
        if "SALDO FINAL" in folded:
            if amounts:
                final_balance = parse_ptbr_decimal(amounts[-1])
            continue
        if "TOTAL DE CREDITOS" in folded:
            if amounts:
                reported_credits = parse_ptbr_decimal(amounts[-1])
            continue
        if "TOTAL DE DEBITOS" in folded:
            if amounts:
                reported_debits = parse_ptbr_decimal(amounts[-1])
            continue
        if _is_non_transaction(line):
            continue
        match = DATE_RE.search(line)
        if not match or not amounts:
            continue
        transaction_date = datetime.strptime(match.group(), "%d/%m/%Y").date()
        balance = parse_ptbr_decimal(amounts[-1])
        # The rightmost amount is the printed balance and preceding monetary
        # tokens are debit/credit columns, not part of the bank description.
        description_segment = line[match.end():line.rfind(amounts[-1])]
        description = MONEY_RE.sub("", description_segment)
        description = re.sub(r"\s+", " ", description).strip(" -")
        if not description:
            raise StatementError(f"Empty transaction description at page {page}, line {source_line}")
        candidates.append((transaction_date, description, balance, page, source_line))

    if None in (initial_balance, final_balance, reported_credits, reported_debits):
        raise StatementError("Statement is missing an initial/final balance or reported totals")

    previous_balance = initial_balance
    transactions: list[NormalizedTransaction] = []
    for transaction_date, description, balance, page, source_line in candidates:
        delta = balance - previous_balance
        if delta == ZERO:
            raise StatementError(f"Zero balance variation at page {page}, line {source_line}")
        direction = "CREDIT" if delta > ZERO else "DEBIT"
        transactions.append(NormalizedTransaction(
            entity=ENTITY, bank_source=BANK_SOURCE, account_ref=identity.account_ref,
            transaction_date=transaction_date, description_raw=description,
            direction=direction, amount=abs(delta), balance_after=balance,
            source_file=source_file, source_page=page, source_line=source_line,
            operational_credit_candidate=(direction == "CREDIT"),
        ))
        previous_balance = balance
    return StatementDetails(identity, initial_balance, reported_credits, reported_debits, final_balance, tuple(transactions))


def parse_btg_statement_details(pdf_path: str | Path) -> StatementDetails:
    path = Path(pdf_path)
    if not path.is_file():
        raise StatementError("PDF path does not exist or is not a file")
    return _parse_details_from_lines(_pdf_lines(path), path.name)


def parse_btg_statement(pdf_path: str | Path) -> tuple[NormalizedTransaction, ...]:
    """Return normalized financial movements only (no headers, totals or balances)."""
    return parse_btg_statement_details(pdf_path).transactions


def validate_btg_statement(details: StatementDetails) -> ValidationResult:
    errors: list[str] = []
    previous_balance = details.initial_balance
    credits = ZERO
    debits = ZERO
    for transaction in details.transactions:
        delta = transaction.balance_after - previous_balance
        signed_amount = transaction.amount if transaction.direction == "CREDIT" else -transaction.amount
        if signed_amount != delta:
            errors.append(f"Balance delta mismatch at page {transaction.source_page}, line {transaction.source_line}")
        if transaction.direction == "CREDIT":
            credits += transaction.amount
        elif transaction.direction == "DEBIT":
            debits += transaction.amount
        else:
            errors.append(f"Invalid direction at page {transaction.source_page}, line {transaction.source_line}")
        previous_balance = transaction.balance_after
    if credits != details.total_credits_reported:
        errors.append("Calculated credits differ from statement total")
    if debits != details.total_debits_reported:
        errors.append("Calculated debits differ from statement total")
    if previous_balance != details.final_balance:
        errors.append("Last transaction balance differs from final balance")
    if details.initial_balance + credits - debits != details.final_balance:
        errors.append("Global balance equation does not close")
    return ValidationResult(not errors, details.initial_balance, credits, debits, details.final_balance,
                            len(details.transactions), sum(t.direction == "CREDIT" for t in details.transactions),
                            sum(t.direction == "DEBIT" for t in details.transactions), tuple(errors))


def build_btg_royalty_extract(transactions: Iterable[NormalizedTransaction]) -> tuple[NormalizedTransaction, ...]:
    """Return the operational credit view without classifying a source/deal."""
    return tuple(transaction for transaction in transactions if transaction.operational_credit_candidate)
