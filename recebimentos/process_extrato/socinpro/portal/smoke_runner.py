"""Operator-run, one-account real smoke for the SOCINPRO portal adapter.

Run locally after configuring ``MUV_SOCINPRO_HM_CREDENTIALS_PATH``. This
runner never receives credentials on the command line and never touches a
monthly workbook, parser, catalogue, mapping, or publication path.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import tempfile
import time
from uuid import uuid4

from ..portal_runtime import HumanInterventionRequired, SocinproPortalRuntimeError, preflight_runtime_credentials
from .browser_adapter import BrowserSettings, PlaywrightSocinproSession, PortalAdapterError


_DIAGNOSTIC_KEYS = {
    "PORTAL_STAGE", "NAV_FINANCEIRO_FOUND", "NAV_FINANCEIRO_ACTIVATED",
    "NAV_SOCINPRO_FOUND", "NAV_SOCINPRO_ACTIVATED", "NAV_DEMONSTRATIVO_FOUND",
    "NAV_DEMONSTRATIVO_ACTIVATED", "DEMONSTRATIVO_PAGE_CONFIRMED",
    "CURRENT_URL_CLASS", "LAYOUT_FAILURE_REASON",
    "COMPETENCE_STAGE", "START_DATE_CONTROL_FOUND", "END_DATE_CONTROL_FOUND",
    "START_DATE_CONTROL_ACTIONABLE", "END_DATE_CONTROL_ACTIONABLE", "EXPECTED_START_DATE",
    "EXPECTED_END_DATE", "START_DATE_SET_ATTEMPTED", "END_DATE_SET_ATTEMPTED",
    "START_DATE_READBACK_AVAILABLE", "END_DATE_READBACK_AVAILABLE", "START_DATE_MATCH",
    "END_DATE_MATCH", "DATE_RANGE_VALIDATION", "DATE_MUTATION_COMPLETE", "DATE_READBACK_COMPLETE", "DATE_CONTROLS_SETTLED", "COMPETENCE_FAILURE_REASON", "ACTUAL_START_DATE", "ACTUAL_END_DATE",
    "SEARCH_CONTROL_FOUND", "SEARCH_ACTIONABLE_CONTROL_RESOLVED", "SEARCH_RESOLVED_TAG", "SEARCH_RESOLVED_TYPE", "SEARCH_ACTIVATION_ATTEMPTED", "SEARCH_REQUEST_OBSERVED", "SEARCH_RESULT_CONTAINER_CHANGED", "SEARCH_ACTIVATION_CONFIRMED", "SEARCH_RESULT_REFRESH_CONFIRMED", "SEARCH_PROOF_METHOD", "PRE_SEARCH_ROW_COUNT", "PRE_SEARCH_EMPTY_MARKER_PRESENT", "PRE_SEARCH_RESULT_FINGERPRINT", "REFRESHED_RESULT_EMPTY",
    "DEMONSTRATIVO_CONFIRM_SECONDS", "START_DATE_LOCATOR_SECONDS", "START_DATE_SET_SECONDS", "START_DATE_READBACK_SECONDS", "END_DATE_LOCATOR_SECONDS", "END_DATE_SET_SECONDS", "END_DATE_READBACK_SECONDS", "DATE_VALIDATION_SECONDS", "SEARCH_CONTROL_LOCATOR_SECONDS", "SEARCH_ACTIVATION_SECONDS", "SEARCH_REFRESH_SECONDS", "COMPETENCE_TOTAL_SECONDS",
    "PAYMENT_ROWS_DISCOVERED", "PAYMENT_ROWS_PROCESSED", "DOWNLOAD_ACTIONS_DISCOVERED", "DOWNLOAD_ACTIONS_COMPLETED",
}


def _safe_navigation_diagnostics(session, fallback_stage: str | None = None, error_diagnostics: dict[str, object] | None = None) -> dict[str, object]:
    """Return only the fixed, non-content-bearing navigation diagnostic schema."""
    source = error_diagnostics if isinstance(error_diagnostics, dict) else getattr(session, "navigation_diagnostics", {})
    if not isinstance(source, dict):
        source = {}
    diagnostics = {key: value for key, value in source.items() if key in _DIAGNOSTIC_KEYS and isinstance(value, (str, bool, int, float, type(None)))}
    if diagnostics or fallback_stage is None:
        return diagnostics
    return {
        "PORTAL_STAGE": fallback_stage,
        "NAV_FINANCEIRO_FOUND": False,
        "NAV_FINANCEIRO_ACTIVATED": False,
        "NAV_SOCINPRO_FOUND": False,
        "NAV_SOCINPRO_ACTIVATED": False,
        "NAV_DEMONSTRATIVO_FOUND": False,
        "NAV_DEMONSTRATIVO_ACTIVATED": False,
        "DEMONSTRATIVO_PAGE_CONFIRMED": False,
        "CURRENT_URL_CLASS": "UNKNOWN_AUTHENTICATED_PAGE",
        "LAYOUT_FAILURE_REASON": None,
    }


def _known_failure_status(category: str) -> tuple[str, str]:
    if category in {"UNEXPECTED_PAGE", "POST_LOGIN_NAVIGATION_FAILED"}:
        return "PORTAL_LAYOUT_REVIEW", "POST_LOGIN_NAVIGATION"
    if category == "COMPETENCE_SELECTION_FAILED":
        return category, "COMPETENCE_SELECTION"
    if category.startswith("SEARCH_"):
        return category, "SEARCH"
    if category == "DOCUMENT_DISCOVERY_FAILED":
        return category, "DOCUMENT_DISCOVERY"
    if category.startswith("DOWNLOAD_"):
        return category, "DOWNLOAD"
    return "FAILED", "UNEXPECTED"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operator-executed SOCINPRO portal smoke.")
    parser.add_argument("--entity", choices=("HM",), default="HM")
    parser.add_argument("--competence", default="2026-08")
    parser.add_argument("--account-limit", type=int, default=1)
    parser.add_argument("--start-at", type=int, default=1)
    parser.add_argument("--max-accounts", type=int, default=None)
    parser.add_argument("--account-index", action="append", type=int, default=[])
    parser.add_argument("--stop-after-first-download", action="store_true")
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--staging-root", type=Path, default=None)
    parser.add_argument("--browser-executable", default=os.environ.get("MUV_SOCINPRO_BROWSER_EXECUTABLE"))
    return parser


def _planned_accounts(accounts, args):
    if args.start_at < 1:
        raise SocinproPortalRuntimeError("SMOKE_START_AT_INVALID")
    requested = tuple(getattr(args, "account_index", ()))
    if requested:
        by_index = {account.index: account for account in accounts}
        if len(set(requested)) != len(requested) or any(index not in by_index for index in requested):
            raise SocinproPortalRuntimeError("SMOKE_ACCOUNT_INDEX_INVALID")
        return tuple(by_index[index] for index in requested)
    max_accounts = args.max_accounts if args.max_accounts is not None else args.account_limit
    if max_accounts < 1:
        raise SocinproPortalRuntimeError("SMOKE_MAX_ACCOUNTS_INVALID")
    if args.start_at > len(accounts):
        raise SocinproPortalRuntimeError("SMOKE_START_AT_OUT_OF_RANGE")
    return tuple(accounts[args.start_at - 1 : args.start_at - 1 + max_accounts])


def run_smoke(args: argparse.Namespace) -> dict[str, object]:
    run_id = f"hm-socinpro-smoke-{uuid4().hex[:12]}"
    staging = (args.staging_root or Path(tempfile.gettempdir()) / "muv-socinpro-smoke" / run_id).resolve()
    result: dict[str, object] = {
        "SOCINPRO_REAL_SMOKE_STATUS": "FAIL",
        "RUN_ID": run_id,
        "ENTITY": args.entity,
        "TARGET_COMPETENCE": args.competence,
        "STAGING_PATH": str(staging),
        "PLANNED_ACCOUNT_START": None,
        "PLANNED_ACCOUNT_END": None,
        "PLANNED_ACCOUNT_COUNT": 0,
        "ACCOUNTS_ATTEMPTED": 0,
        "ACCOUNTS_COMPLETED": 0,
        "ACCOUNTS_NO_PAYMENT": 0,
        "ACCOUNTS_WAITING_HUMAN": 0,
        "ACCOUNTS_FAILED": 0,
        "FIRST_PAYMENT_ACCOUNT_INDEX": None,
        "RAW_DOWNLOAD_COUNT": 0,
        "UNIQUE_DOWNLOAD_COUNT": 0,
        "STOPPED_AFTER_FIRST_DOWNLOAD": False,
        "ACCOUNT_RESULTS": [],
        "DOWNLOAD_MANIFEST": [],
        "TOTAL_ACCOUNT_SECONDS": 0.0,
        "PASSWORDS_EXPOSED": False,
        "OFFICIAL_FILES_CHANGED": False,
        "OFFICIAL_PUBLICATION_EXECUTED": False,
        "INVENTORY_ONLY": bool(getattr(args, "inventory_only", False)),
        "DOCUMENT_DOWNLOAD_COUNT": 0,
        "PORTAL_PAYMENT_ROWS_DISCOVERED": 0,
        "ANALITICO_ACTIONS_DISCOVERED": 0,
        "SINTETICO_ACTIONS_DISCOVERED": 0,
    }
    started = time.perf_counter()
    try:
        preflight = preflight_runtime_credentials(args.entity)
        planned = _planned_accounts(preflight.accounts, args)
        result["PLANNED_ACCOUNT_START"], result["PLANNED_ACCOUNT_END"], result["PLANNED_ACCOUNT_COUNT"] = planned[0].index, planned[-1].index, len(planned)
        all_files: set[str] = set()
        for account in planned:
            account_result = {"account_index": account.index, "masked_identifier": account.masked_identifier, "status": "FAILED", "login_seconds": 0.0, "navigation_seconds": 0.0, "download_seconds": 0.0, "download_count": 0, "download_manifest": [], "captcha_detected": False, "mfa_detected": False, "navigation_diagnostics": {}, "failure_stage": None, "failure_reason": None, "exception_class_safe": None, "session_cleanup": "NOT_RUN"}
            session = PlaywrightSocinproSession(BrowserSettings(staging_dir=staging, headed=True, executable_path=args.browser_executable, run_id=run_id))
            result["ACCOUNTS_ATTEMPTED"] += 1
            try:
                point = time.perf_counter(); session.authenticate(account); account_result["login_seconds"] = round(time.perf_counter() - point, 3)
                point = time.perf_counter(); session.select_competence(args.competence); account_result["navigation_seconds"] = round(time.perf_counter() - point, 3)
                inventory_only = bool(getattr(args, "inventory_only", False))
                point = time.perf_counter(); files = () if inventory_only else tuple(session.download_statements(account));
                if inventory_only: session.inventory_payment_rows(account)
                account_result["download_seconds"] = round(time.perf_counter() - point, 3)
                account_result["download_count"] = len(files)
                account_result["download_manifest"] = list(getattr(session, "download_manifest", ()))
                result["DOWNLOAD_MANIFEST"].extend(account_result["download_manifest"])
                diagnostics = getattr(session, "navigation_diagnostics", {})
                for key in ("PAYMENT_ROWS_DISCOVERED", "ANALITICO_ACTIONS_DISCOVERED", "SINTETICO_ACTIONS_DISCOVERED"):
                    result["PORTAL_PAYMENT_ROWS_DISCOVERED" if key == "PAYMENT_ROWS_DISCOVERED" else key] += int(diagnostics.get(key, 0))
                if files:
                    valid = [item for item in files if item.is_file() and item.stat().st_size > 0 and item.suffix.casefold() not in {".crdownload", ".part"} and staging in item.resolve().parents]
                    if len(valid) != len(files): raise PortalAdapterError("DOWNLOAD_INVALID")
                    account_result["status"] = "PASS"; result["FIRST_PAYMENT_ACCOUNT_INDEX"] = account.index; result["RAW_DOWNLOAD_COUNT"] += len(valid); all_files.update(str(item.resolve()) for item in valid)
                    if args.stop_after_first_download: result["STOPPED_AFTER_FIRST_DOWNLOAD"] = True
                else:
                    account_result["status"] = "NO_PAYMENT"; result["ACCOUNTS_NO_PAYMENT"] += 1
                account_result["navigation_diagnostics"] = _safe_navigation_diagnostics(session)
            except HumanInterventionRequired as exc:
                account_result["status"] = "WAITING_HUMAN"; account_result["captcha_detected"] = exc.category == "CAPTCHA_REQUIRED"; account_result["mfa_detected"] = exc.category == "MFA_REQUIRED"; result["ACCOUNTS_WAITING_HUMAN"] += 1
            except PortalAdapterError as exc:
                status, stage = _known_failure_status(exc.category)
                account_result["status"] = status
                account_result["failure_stage"] = stage
                account_result["failure_reason"] = exc.category
                account_result["navigation_diagnostics"] = _safe_navigation_diagnostics(session, stage if stage == "POST_LOGIN_NAVIGATION" else None, exc.diagnostics)
                result["ACCOUNTS_FAILED"] += 1
            except Exception as exc:
                stage = "POST_LOGIN_NAVIGATION"
                account_result["status"] = "FAILED"
                account_result["failure_stage"] = stage
                account_result["failure_reason"] = "UNEXPECTED_EXCEPTION"
                account_result["exception_class_safe"] = type(exc).__name__
                account_result["navigation_diagnostics"] = _safe_navigation_diagnostics(session, stage)
                result["ACCOUNTS_FAILED"] += 1
            finally:
                try: session.close(); account_result["session_cleanup"] = "PASS"
                except Exception: account_result["session_cleanup"] = "FAIL"
            result["ACCOUNT_RESULTS"].append(account_result)
            if result["STOPPED_AFTER_FIRST_DOWNLOAD"] or account_result["status"] in {"WAITING_HUMAN", "FAILED", "PORTAL_LAYOUT_REVIEW"}:
                break
        result["ACCOUNTS_COMPLETED"] = result["ACCOUNTS_ATTEMPTED"] - result["ACCOUNTS_WAITING_HUMAN"] - result["ACCOUNTS_FAILED"]
        result["UNIQUE_DOWNLOAD_COUNT"] = len(all_files)
        if result["ACCOUNTS_ATTEMPTED"] < result["PLANNED_ACCOUNT_COUNT"] and not (result["STOPPED_AFTER_FIRST_DOWNLOAD"] or result["ACCOUNTS_WAITING_HUMAN"] or result["ACCOUNTS_FAILED"]):
            result["SOCINPRO_REAL_SMOKE_STATUS"] = "REVIEW"
            return result
        no_payment_status = "NO_PAYMENT" if result["PLANNED_ACCOUNT_COUNT"] == 1 else "NO_PAYMENT_RANGE"
        result["SOCINPRO_REAL_SMOKE_STATUS"] = ("PASS" if not result["ACCOUNTS_FAILED"] and not result["ACCOUNTS_WAITING_HUMAN"] else "REVIEW") if bool(getattr(args, "inventory_only", False)) else ("PASS" if result["RAW_DOWNLOAD_COUNT"] else ("WAITING_HUMAN" if result["ACCOUNTS_WAITING_HUMAN"] else (no_payment_status if not result["ACCOUNTS_FAILED"] else "REVIEW")))
    except SocinproPortalRuntimeError as exc:
        result["SOCINPRO_REAL_SMOKE_STATUS"] = str(exc)
    finally:
        result["TOTAL_ACCOUNT_SECONDS"] = round(time.perf_counter() - started, 3)
    return result


def main() -> int:
    result = run_smoke(build_parser().parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["SOCINPRO_REAL_SMOKE_STATUS"] in {"PASS", "NO_PAYMENT", "WAITING_HUMAN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
