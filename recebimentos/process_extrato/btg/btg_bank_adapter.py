"""File-oriented adapter around the reusable BTG parser core."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict
from datetime import date
from decimal import Decimal
from pathlib import Path
import json

from openpyxl import Workbook

from btg_statement_parser import (
    ENTITY, StatementDetails, ValidationResult, build_btg_royalty_extract,
    parse_btg_statement_details, validate_btg_statement,
)


def _decimal_default(value: object) -> str:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, date):
        return value.isoformat()
    raise TypeError(f"Not JSON serializable: {type(value).__name__}")


def write_operational_credit_xlsx(transactions, output_path: str | Path) -> Path:
    """Write the deliberately simple, credit-only operational workbook."""
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Extrato"
    sheet.append(["Data", "Descrição", "Crédito"])
    for transaction in transactions:
        sheet.append([transaction.transaction_date, transaction.description_raw, transaction.amount])
    sheet.column_dimensions["A"].width = 14
    sheet.column_dimensions["B"].width = 70
    sheet.column_dimensions["C"].width = 18
    for cell in sheet["A"][1:]:
        cell.number_format = "DD/MM/YYYY"
    for cell in sheet["C"][1:]:
        cell.number_format = "#,##0.00"
    workbook.save(destination)
    return destination


def diagnostic_credit_totals(transactions) -> list[dict[str, object]]:
    totals: dict[str, tuple[int, Decimal]] = {}
    for transaction in build_btg_royalty_extract(transactions):
        count, total = totals.get(transaction.description_raw, (0, Decimal("0.00")))
        totals[transaction.description_raw] = (count + 1, total + transaction.amount)
    return [
        {"description": description, "transaction_count": count, "credit_total": total}
        for description, (count, total) in sorted(totals.items())
    ]


def run_btg_month(*, entity: str, period: str, input_pdf: str | Path, output_root: str | Path) -> dict[str, object]:
    """Validate one HM statement and write segregated technical/operational outputs.

    It never reads or writes official reconciliation workbooks.  The caller owns
    ``output_root`` (typically a staging/test location).
    """
    if entity != ENTITY:
        raise ValueError("This adapter is restricted to entity HM")
    if not __import__("re").fullmatch(r"\d{4}-\d{2}", period):
        raise ValueError("period must be YYYY-MM")
    details: StatementDetails = parse_btg_statement_details(input_pdf)
    validation: ValidationResult = validate_btg_statement(details)
    if not validation.passed:
        raise ValueError("BTG statement validation failed: " + "; ".join(validation.errors))

    root = Path(output_root)
    operational_path = root / "operational" / f"extrato_royalties_{period[5:7]}_{period[:4]}.xlsx"
    technical_path = root / "technical" / f"btg_statement_{period}.json"
    credit_transactions = build_btg_royalty_extract(details.transactions)
    write_operational_credit_xlsx(credit_transactions, operational_path)
    technical_path.parent.mkdir(parents=True, exist_ok=True)
    technical_payload = {
        "period": period,
        "identity": asdict(details.identity),
        "validation": asdict(validation),
        "transactions": [asdict(transaction) for transaction in details.transactions],
        "diagnostic_credit_totals": diagnostic_credit_totals(details.transactions),
    }
    technical_path.write_text(json.dumps(technical_payload, default=_decimal_default, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"details": details, "validation": validation, "operational_credit_xlsx": operational_path, "technical_output": technical_path}
