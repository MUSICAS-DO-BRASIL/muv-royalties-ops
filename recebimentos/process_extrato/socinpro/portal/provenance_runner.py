"""Inventory SOCINPRO payment provenance without downloading documents.

This operator-run module writes only caller-owned staging evidence.  It never
serializes a password and never touches an operational workbook or catalogue.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Iterable

from ..portal_runtime import RuntimeAccount, preflight_runtime_credentials
from .browser_adapter import BrowserSettings, PlaywrightSocinproSession


def raw_account_identity(login: str) -> str:
    """Keep only the deterministic account-name component, not a canonical name."""
    normalized = str(login).strip().casefold()
    return normalized.rsplit(".", 1)[0] if "." in normalized else normalized


def _atomic_write(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _payment_record(account: RuntimeAccount, row: dict[str, object]) -> dict[str, object]:
    return {
        "account_index": account.index,
        "account_login": account.identifier,
        "raw_account_identity": raw_account_identity(account.identifier),
        "canonical_identity": None,
        "payment_row_ordinal": row.get("payment_row_ordinal"),
        "payment_date": row.get("payment_date"),
        "payment_amount": row.get("portal_displayed_amount"),
        "portal_row_key": row.get("payment_row_key"),
        "portal_identifier": None,
        "analitico_action_available": bool(row.get("analitico_action_available")),
        "sintetico_action_available": bool(row.get("sintetico_action_available")),
    }


def run_provenance_inventory(
    *,
    entity: str,
    competence: str,
    account_indexes: Iterable[int],
    staging_root: Path,
    browser_executable: str | None = None,
) -> dict[str, object]:
    """Run a bounded account batch and atomically checkpoint every account."""
    preflight = preflight_runtime_credentials(entity)
    by_index = {account.index: account for account in preflight.accounts}
    indexes = tuple(account_indexes)
    if not indexes or len(indexes) != len(set(indexes)) or any(index not in by_index for index in indexes):
        raise ValueError("PROVENANCE_ACCOUNT_INDEX_INVALID")

    checkpoint_path = staging_root / "provenance_checkpoint.json"
    payload: dict[str, object] = {
        "entity": entity.upper(),
        "competence": competence,
        "document_download_count": 0,
        "accounts": {},
    }
    if checkpoint_path.is_file():
        payload = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    accounts_payload = payload.setdefault("accounts", {})
    if not isinstance(accounts_payload, dict):
        raise ValueError("PROVENANCE_CHECKPOINT_INVALID")

    for index in indexes:
        account = by_index[index]
        session = PlaywrightSocinproSession(
            BrowserSettings(staging_dir=staging_root / "browser", headed=True, executable_path=browser_executable, run_id="provenance-inventory")
        )
        account_payload: dict[str, object] = {
            "account_index": account.index,
            "account_login": account.identifier,
            "raw_account_identity": raw_account_identity(account.identifier),
            "canonical_identity": None,
            "status": "FAILED",
            "payments": [],
        }
        try:
            session.authenticate(account)
            session.select_competence(competence)
            rows = session.inventory_payment_rows(account)
            account_payload["payments"] = [_payment_record(account, row) for row in rows]
            account_payload["status"] = "PASS"
        except Exception as exc:
            account_payload["failure_category"] = getattr(exc, "category", type(exc).__name__)
        finally:
            session.close()
            account_payload["completed_at"] = datetime.now(timezone.utc).isoformat()
            accounts_payload[str(index)] = account_payload
            _atomic_write(checkpoint_path, payload)

    return {
        "checkpoint_path": str(checkpoint_path),
        "accounts_completed": sum(item.get("status") == "PASS" for item in accounts_payload.values()),
        "payment_rows": sum(len(item.get("payments", [])) for item in accounts_payload.values()),
        "document_download_count": 0,
    }
