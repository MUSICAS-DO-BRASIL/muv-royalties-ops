"""Presentation-only formatting shared by Streamlit pages."""
from __future__ import annotations

from decimal import Decimal


STATUS_CLASS = {
    "PASS": "ok", "RECEBIDO": "ok", "CONCILIADO": "ok", "FECHADO": "ok",
    "PENDENTE": "warn", "PROCESSANDO": "warn", "PARCIAL": "warn", "REVISÃO NECESSÁRIA": "warn",
    "ATRASADO": "bad", "CRÍTICO": "bad", "DUPLICIDADE": "bad", "BLOQUEADO": "bad",
    "INATIVA": "neutral",
}


def brl(value: Decimal | None) -> str:
    """Format a monetary amount for Brazilian operators without truncation."""
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def status_class(status: str) -> str:
    return STATUS_CLASS.get(status, "neutral")
