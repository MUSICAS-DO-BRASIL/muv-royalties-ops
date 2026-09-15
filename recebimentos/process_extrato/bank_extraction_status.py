"""Presentation semantics for independent bank and source-mapping statuses."""
from __future__ import annotations

from bank_extraction_core import BankExtractionResult


def bank_closure_status(result: BankExtractionResult) -> str:
    """Financial closure never inherits a source-mapping review state."""
    if result.financial_validation_status == "PASS":
        return "PASS"
    if result.financial_validation_status:
        return "FAIL"
    return "N/A"


def source_mapping_status(result: BankExtractionResult) -> str:
    return "REVIEW" if result.unknown_source_count else "PASS"
