"""UI-only entity context.  The selected entity is the sole input."""
from __future__ import annotations

from dataclasses import dataclass

from bank_extraction_core import ENTITY_BANK


@dataclass(frozen=True)
class EntityContext:
    entity: str
    bank: str
    bank_label: str
    upload_label: str
    period: str


def resolve_entity_context(selected_entity: str, period: str) -> EntityContext:
    if selected_entity not in ENTITY_BANK:
        raise ValueError("Contexto de entidade inválido.")
    bank = ENTITY_BANK[selected_entity]
    labels = {
        "HM": ("BTG Pactual", "Extrato BTG"),
        "MDB": ("Safra", "Extrato Safra"),
    }
    bank_label, upload_label = labels[selected_entity]
    return EntityContext(selected_entity, bank, bank_label, upload_label, period)


def validate_processing_context(context: EntityContext) -> None:
    """Fail closed if a caller ever supplies a bank inconsistent with its entity."""
    expected = resolve_entity_context(context.entity, context.period)
    if context != expected:
        raise ValueError("Contexto entidade/banco inconsistente. Processamento bloqueado.")
