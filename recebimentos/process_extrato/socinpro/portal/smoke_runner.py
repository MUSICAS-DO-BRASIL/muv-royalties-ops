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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Operator-executed SOCINPRO portal smoke.")
    parser.add_argument("--entity", choices=("HM",), default="HM")
    parser.add_argument("--competence", default="2026-08")
    parser.add_argument("--account-limit", type=int, default=1)
    parser.add_argument("--staging-root", type=Path, default=None)
    parser.add_argument("--browser-executable", default=os.environ.get("MUV_SOCINPRO_BROWSER_EXECUTABLE"))
    return parser


def run_smoke(args: argparse.Namespace) -> dict[str, object]:
    if args.account_limit != 1:
        raise SocinproPortalRuntimeError("SMOKE_ACCOUNT_LIMIT_MUST_BE_ONE")
    run_id = f"hm-socinpro-smoke-{uuid4().hex[:12]}"
    staging = (args.staging_root or Path(tempfile.gettempdir()) / "muv-socinpro-smoke" / run_id).resolve()
    result: dict[str, object] = {
        "SOCINPRO_REAL_SMOKE_STATUS": "FAIL",
        "RUN_ID": run_id,
        "ENTITY": args.entity,
        "TARGET_COMPETENCE": args.competence,
        "ACCOUNT_INDEX": None,
        "IDENTIFIER_MASKED": None,
        "BROWSER_STARTED": False,
        "LOGIN_STATUS": "NOT_RUN",
        "SESSION_VALIDATION": "NOT_RUN",
        "CAPTCHA_DETECTED": False,
        "MFA_DETECTED": False,
        "COMPETENCE_SELECTION": "NOT_RUN",
        "DOCUMENT_DISCOVERY": "NOT_RUN",
        "DOWNLOAD_COUNT": 0,
        "STAGING_PATH": str(staging),
        "SESSION_CLEANUP": "NOT_RUN",
        "BROWSER_START_SECONDS": 0.0,
        "LOGIN_SECONDS": 0.0,
        "NAVIGATION_SECONDS": 0.0,
        "DOWNLOAD_SECONDS": 0.0,
        "TOTAL_ACCOUNT_SECONDS": 0.0,
        "PASSWORDS_EXPOSED": False,
        "OFFICIAL_FILES_CHANGED": False,
        "OFFICIAL_PUBLICATION_EXECUTED": False,
    }
    started = time.perf_counter()
    session = None
    try:
        preflight = preflight_runtime_credentials(args.entity)
        account = preflight.accounts[0]
        result["ACCOUNT_INDEX"], result["IDENTIFIER_MASKED"] = account.index, account.masked_identifier
        session = PlaywrightSocinproSession(BrowserSettings(staging_dir=staging, headed=True, executable_path=args.browser_executable))
        login_started = time.perf_counter()
        session.authenticate(account)
        result["LOGIN_STATUS"] = result["SESSION_VALIDATION"] = "PASS"
        result["LOGIN_SECONDS"] = round(time.perf_counter() - login_started, 3)
        navigation_started = time.perf_counter()
        session.select_competence(args.competence)
        result["COMPETENCE_SELECTION"] = "PASS"
        result["NAVIGATION_SECONDS"] = round(time.perf_counter() - navigation_started, 3)
        download_started = time.perf_counter()
        files = tuple(session.download_statements(account))
        result["DOWNLOAD_SECONDS"] = round(time.perf_counter() - download_started, 3)
        result["DOWNLOAD_COUNT"] = len(files)
        result["DOCUMENT_DISCOVERY"] = "PASS" if files else "NO_PAYMENT"
        result["SOCINPRO_REAL_SMOKE_STATUS"] = "PASS" if files else "NO_PAYMENT"
    except HumanInterventionRequired as exc:
        result["SOCINPRO_REAL_SMOKE_STATUS"] = "WAITING_HUMAN"
        result["LOGIN_STATUS"] = "WAITING_HUMAN"
        result["CAPTCHA_DETECTED"] = exc.category == "CAPTCHA_REQUIRED"
        result["MFA_DETECTED"] = exc.category == "MFA_REQUIRED"
    except PortalAdapterError as exc:
        status = "PORTAL_LAYOUT_REVIEW" if exc.category in {"UNEXPECTED_PAGE", "COMPETENCE_SELECTION_FAILED", "DOCUMENT_DISCOVERY_FAILED"} else exc.category
        result["SOCINPRO_REAL_SMOKE_STATUS"] = status
        result["LOGIN_STATUS"] = status if result["LOGIN_STATUS"] == "NOT_RUN" else result["LOGIN_STATUS"]
    except SocinproPortalRuntimeError as exc:
        result["SOCINPRO_REAL_SMOKE_STATUS"] = str(exc)
    finally:
        if session is not None:
            try:
                session.close()
                result["SESSION_CLEANUP"] = "PASS"
            except Exception:
                result["SESSION_CLEANUP"] = "FAIL"
            result["BROWSER_STARTED"] = bool(getattr(session, "browser_started", False))
        result["TOTAL_ACCOUNT_SECONDS"] = round(time.perf_counter() - started, 3)
    return result


def main() -> int:
    result = run_smoke(build_parser().parse_args())
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["SOCINPRO_REAL_SMOKE_STATUS"] in {"PASS", "NO_PAYMENT", "WAITING_HUMAN"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
