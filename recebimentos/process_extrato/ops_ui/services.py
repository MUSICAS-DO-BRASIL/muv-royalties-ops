"""Adapters that keep Streamlit separate from operational services."""
from __future__ import annotations

from dataclasses import dataclass

from month_preparation import MonthPreparationService


@dataclass(frozen=True)
class PreparationView:
    status: str
    month_folder: str
    workbook: str | None
    detail: str
    can_prepare: bool


class MonthPreparationAdapter:
    def __init__(self, service: MonthPreparationService | None = None) -> None:
        self.service = service or MonthPreparationService()

    def inspect(self, entity: str, competence: str) -> PreparationView:
        result = self.service.discover(entity, competence)
        detail = "Workbook já existe; nenhuma sobrescrita será feita." if result.already_existed else "A preparação requer resultado bancário validado pelo backend."
        return PreparationView(result.status, str(result.month_folder), str(result.workbook_path) if result.workbook_path else None, detail, False)


@dataclass(frozen=True)
class CloseAction:
    allowed: bool
    detail: str


def close_action() -> CloseAction:
    """Fail closed until an audited backend close service is supplied."""
    return CloseAction(False, "Fechamento indisponível: o serviço auditado de fechamento ainda não está conectado.")
