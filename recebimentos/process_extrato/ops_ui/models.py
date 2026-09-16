"""Typed view models. They contain no financial decision logic."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


Entity = Literal["HM", "MDB"]
ProviderMode = Literal["DEMO", "LIVE"]


@dataclass(frozen=True)
class MonthOverview:
    entity: Entity
    competence: str
    state: str
    expected_sources: int
    received_sources: int
    pending_sources: int
    reconciliation_pending: int
    review_pending: int
    critical_exceptions: int


@dataclass(frozen=True)
class SourceStatus:
    source: str
    status: str
    last_execution: str | None
    documents_found: int | None
    document_value: Decimal | None
    pending_count: int
    action: str
    detail: str = ""


@dataclass(frozen=True)
class ReconciliationSummary:
    bank_total: Decimal
    document_total: Decimal
    difference: Decimal
    status: str
    record_count: int
    pending_count: int


@dataclass(frozen=True)
class ReviewItem:
    item_id: str
    source: str
    entity: Entity
    competence: str
    bank_value: Decimal
    document_value: Decimal
    difference: Decimal
    reason: str
    evidence: str
    note: str


@dataclass(frozen=True)
class CloseControl:
    label: str
    status: str
    detail: str


@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    actor: str
    operation: str
    entity: Entity
    competence: str
    source: str
    result: str
    details: str
