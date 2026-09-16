"""Resolved UI context, delegated to the existing monthly helper."""
from __future__ import annotations

from calendar import monthrange
from dataclasses import dataclass
from datetime import date

from month_preparation import default_competence


ENTITIES = {"HM": "Hurst Music", "MDB": "Músicas do Brasil"}


@dataclass(frozen=True)
class OpsContext:
    entity: str
    competence: str

    @property
    def entity_name(self) -> str:
        return ENTITIES[self.entity]

    @property
    def period_label(self) -> str:
        year, month = (int(value) for value in self.competence.split("-"))
        return f"01/{month:02d}/{year} → {monthrange(year, month)[1]:02d}/{month:02d}/{year}"


def resolve_competence(value: str | None, reference_date: date | None = None) -> str:
    """Use the canonical M-1 helper unless the operator selected a valid month."""
    if not value:
        return default_competence(reference_date or date.today())
    if len(value) != 7 or value[4] != "-" or not value[:4].isdigit() or not value[5:].isdigit() or not 1 <= int(value[5:]) <= 12:
        raise ValueError("Competência deve estar no formato YYYY-MM.")
    return value
