"""Single resolved month state shared by every Bank Extraction UI section."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class MonthContext:
    entity: str
    period: str
    status: str
    workbook_already_exists: bool
    workbook_path: Path | None

    @property
    def is_prepared(self) -> bool:
        return self.status == "PREPARED"

    @property
    def action_label(self) -> str:
        return "Conciliação já preparada" if self.is_prepared else "Preparar Conciliação do Mês"


class MonthStatusReader(Protocol):
    def month_status(self, entity: str, period: str) -> tuple[bool, Path | None]: ...


def resolve_month_context(service: MonthStatusReader, entity: str, period: str) -> MonthContext:
    exists, path = service.month_status(entity, period)
    return MonthContext(entity, period, "PREPARED" if exists else "NOT_PREPARED", exists, path)
