"""Deterministic Safra royalty-source identification, separate from PDF parsing."""
from __future__ import annotations

import json
import os
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable, Mapping, Optional


SOURCE_MAP_PATH = Path(os.environ.get("MUV_SAFRA_SOURCE_MAP") or Path(__file__).with_name("safra_royalties_source_map.v1.json")).expanduser()


def normalize_text(value: object) -> str:
    """Return a stable comparison key (case, accents, punctuation and whitespace normalized)."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode("ascii").upper()
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", text).split())


def load_source_map(path: Path = SOURCE_MAP_PATH) -> dict[str, str]:
    """Load an exact normalized-alias map and reject duplicate normalized keys."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    aliases: dict[str, str] = {}
    for entry in payload["aliases"]:
        alias = normalize_text(entry["bank_payor_alias"])
        if alias in aliases:
            raise ValueError(f"Duplicate normalized bank alias: {alias}")
        aliases[alias] = entry["canonical_royalty_source"]
    return aliases


def extract_bank_payor(lancamento: object, complemento: object = None) -> str:
    """Extract the counterparty field from known Safra incoming-transfer formats.

    This removes only structural bank prefixes and a terminal numeric bank document.
    It deliberately does not search for aliases within arbitrary text.
    """
    def _extract(text: str) -> str:
        for pattern in (
            r"^PIX RECEBIDO\s+",
            r"^TED E RECEBIDA BCO\s+\d+\s+",
            r"^TED RECEBIDA BCO\s+\d+\s+",
        ):
            if re.match(pattern, text):
                return re.sub(r"\s+\d{4,}$", "", re.sub(pattern, "", text)).strip()
        return ""

    # The primary field owns the Safra transfer header.  Continuation text can
    # contain further PDF metadata and must not alter exact payor extraction.
    payor = _extract(normalize_text(lancamento))
    if payor:
        return payor
    return _extract(normalize_text(" ".join(part for part in (str(lancamento or ""), str(complemento or "")) if part)))


def identify_royalty_source(lancamento: object, complemento: object = None, *, source_map: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """Identify a payor only by exact normalized alias equality."""
    payor = extract_bank_payor(lancamento, complemento)
    return (source_map or load_source_map()).get(payor)


def non_royalty_category(lancamento: object, complemento: object, value: Decimal) -> Optional[str]:
    """Classify structural non-royalty bank movements without inspecting payor identity."""
    text = normalize_text(" ".join(part for part in (str(lancamento or ""), str(complemento or "")) if part))
    if "SALDO" in text:
        return "SALDO"
    if "APLIC" in text and ("CDB" in text or "AUTOMATIC" in text):
        return "APLICACAO"
    if "RESGATE" in text:
        return "RESGATE"
    if "TRANSFERENCIA ENTRE CONTAS" in text or "TRANSFERENCIA INTERNA" in text:
        return "TRANSFERENCIA_INTERNA"
    if any(token in text for token in ("TARIFA", "PACOTE", "ENCARGO")):
        return "TARIFA"
    if any(token in text for token in ("IOF", "IMPOSTO", "IRRF", "IR ")):
        return "IMPOSTO"
    if value < 0:
        return "PAGAMENTO"
    return None


@dataclass(frozen=True)
class Classification:
    category: str
    canonical_source: Optional[str] = None
    non_royalty_category: Optional[str] = None


def classify_transaction(lancamento: object, complemento: object, value: Decimal, *, source_map: Optional[Mapping[str, str]] = None) -> Classification:
    """Classify one normalized bank transaction; positive value alone never confirms royalty."""
    non_royalty = non_royalty_category(lancamento, complemento, value)
    if non_royalty:
        return Classification("NON_ROYALTY", non_royalty_category=non_royalty)
    if value > 0:
        source = identify_royalty_source(lancamento, complemento, source_map=source_map)
        if source:
            return Classification("ROYALTY_RECEIPT", canonical_source=source)
        return Classification("REVIEW_UNKNOWN_CREDIT")
    return Classification("NON_ROYALTY", non_royalty_category="OUTRO")
