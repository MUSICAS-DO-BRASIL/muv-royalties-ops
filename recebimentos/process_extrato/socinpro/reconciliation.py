"""Exact, non-mutating reconciliation of receipt-level payment evidence."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class Reconciliation:
    matched_count: int
    matched_total: Decimal
    unmatched_bank_count: int
    unmatched_bank_total: Decimal
    unmatched_document_count: int
    unmatched_document_total: Decimal
    difference: Decimal


def reconcile_by_amount(document_values: Iterable[Decimal], bank_values: Iterable[Decimal]) -> Reconciliation:
    """One-to-one amount matching; duplicates are consumed, never double counted."""
    documents = list(document_values); banks = list(bank_values); used = [False] * len(banks)
    matched = []
    unmatched_documents = []
    for document in documents:
        index = next((i for i, bank in enumerate(banks) if not used[i] and bank == document), None)
        if index is None:
            unmatched_documents.append(document)
        else:
            used[index] = True; matched.append(document)
    unmatched_banks = [bank for index, bank in enumerate(banks) if not used[index]]
    total = lambda values: sum(values, Decimal("0.00"))
    return Reconciliation(len(matched), total(matched), len(unmatched_banks), total(unmatched_banks), len(unmatched_documents), total(unmatched_documents), total(documents) - total(banks))
