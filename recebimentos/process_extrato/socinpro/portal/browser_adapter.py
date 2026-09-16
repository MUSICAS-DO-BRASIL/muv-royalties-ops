"""Playwright adapter for the SOCINPRO portal.

The adapter has no credential, cookie, profile, or default-download path in
source.  Each account receives a fresh browser context and downloads only to
the caller-provided staging directory. CAPTCHA and MFA always stop for a human.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import calendar
import hashlib
import logging
from pathlib import Path
import re
import time
from typing import Iterable
from urllib.parse import urlparse

from ..portal_runtime import HumanInterventionRequired, RuntimeAccount, SocinproPortalRuntimeError

LOGGER = logging.getLogger(__name__)
LOGIN_URL = "https://associado.socinpro.org.br/portal-web/pages/public/access/login.xhtml"
DEMONSTRATIVO_PATH = "/portal-web/pages/protected/financeiro/demonstrativo-socinpro.xhtml"
DEMONSTRATIVO_URL = f"https://associado.socinpro.org.br{DEMONSTRATIVO_PATH}"
SEARCH_CONTROL_TIMEOUT_MS = 2_500
SEARCH_REFRESH_TIMEOUT_MS = 10_000
SEARCH_POLL_MS = 200


class PortalAdapterError(SocinproPortalRuntimeError):
    """Categorised portal error; its text deliberately omits secret values."""

    def __init__(self, category: str, diagnostics: dict[str, object] | None = None):
        super().__init__(category)
        self.category = category
        self.diagnostics = dict(diagnostics or {})


@dataclass(frozen=True)
class BrowserSettings:
    staging_dir: Path
    headed: bool = True
    timeout_ms: int = 45_000
    download_timeout_ms: int = 120_000
    executable_path: str | None = None
    run_id: str = ""


class PlaywrightSocinproSession:
    """Fresh-context-per-account session, reusable by both HM and MDB."""

    def __init__(self, settings: BrowserSettings):
        self.settings = settings
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._competence: str | None = None
        self._search_confirmed = False
        self._search_clicked = False
        self._search_ajax_observed = False
        self._search_request_handler = None
        self._navigation_diagnostics: dict[str, object] = {}
        self._competence_diagnostics: dict[str, object] = {}
        self._search_diagnostics: dict[str, object] = {}
        self._timing_diagnostics: dict[str, float] = {}
        self._download_diagnostics: dict[str, int] = {}
        self._download_manifest: list[dict[str, object]] = []
        self.browser_started = False

    def authenticate(self, account: RuntimeAccount) -> None:
        page = self._start_page()
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=self.settings.timeout_ms)
            self._first_visible(page, ["input[placeholder*='Usu']", "input[id*='usuario' i]", "input[name*='usuario' i]", "input[type='text']"]).fill(account.identifier)
            self._first_visible(page, ["input[type='password']", "input[placeholder*='senha' i]", "input[id*='senha' i]", "input[name*='senha' i]"]).fill(account.password)
            page.get_by_role("button", name=re.compile("Entrar", re.I)).first.click()
            self._validate_session(page)
            LOGGER.info("SOCINPRO login account_index=%s identifier=%s status=LOGIN_SUCCESS", account.index, account.masked_identifier)
        except HumanInterventionRequired:
            raise
        except Exception as exc:
            raise self._categorise_login_failure(page, exc) from None

    def select_competence(self, competence: str) -> None:
        if not re.fullmatch(r"\d{4}-\d{2}", competence):
            raise PortalAdapterError("COMPETENCE_INVALID")
        page = self._require_page()
        self._navigation_diagnostics = self._new_navigation_diagnostics(page)
        start, end = competence_date_range(competence)
        self._competence_diagnostics = self._new_competence_diagnostics(start.strftime("%d/%m/%Y"), end.strftime("%d/%m/%Y"))
        self._search_diagnostics = {"DATE_MUTATION_COMPLETE": False, "DATE_READBACK_COMPLETE": False, "DATE_CONTROLS_SETTLED": False, "SEARCH_CONTROL_RESOLVED": False, "SEARCH_CONTROL_FOUND": False, "SEARCH_ACTIONABLE_CONTROL_RESOLVED": False, "SEARCH_RESOLVED_TAG": None, "SEARCH_RESOLVED_TYPE": None, "SEARCH_ACTIVATION_ATTEMPTED": False, "SEARCH_REQUEST_OBSERVED": False, "SEARCH_RESULT_CONTAINER_CHANGED": False, "SEARCH_ACTIVATION_CONFIRMED": False, "SEARCH_RESULT_REFRESH_CONFIRMED": False, "SEARCH_PROOF_METHOD": None, "PRE_SEARCH_ROW_COUNT": 0, "PRE_SEARCH_EMPTY_MARKER_PRESENT": False, "PRE_SEARCH_RESULT_FINGERPRINT": None, "REFRESHED_RESULT_EMPTY": False}
        self._timing_diagnostics = {key: 0.0 for key in ("DEMONSTRATIVO_CONFIRM_SECONDS", "START_DATE_LOCATOR_SECONDS", "START_DATE_SET_SECONDS", "START_DATE_READBACK_SECONDS", "END_DATE_LOCATOR_SECONDS", "END_DATE_SET_SECONDS", "END_DATE_READBACK_SECONDS", "DATE_VALIDATION_SECONDS", "SEARCH_CONTROL_LOCATOR_SECONDS", "SEARCH_ACTIVATION_SECONDS", "SEARCH_REFRESH_SECONDS", "COMPETENCE_TOTAL_SECONDS")}
        competence_started = time.perf_counter()
        try:
            self._navigate_to_demonstrativo(page)
        except PortalAdapterError:
            # Navigation is a separate, pre-date-selection state. Do not
            # collapse a portal layout failure into a competence failure.
            raise
        try:
            start_field = self._date_control(page, "START_DATE", ["input[aria-label*='data inicial' i], input[placeholder*='data inicial' i], input[name*='dtInicial' i], input[id*='dtInicial' i], input[name*='dataInicial' i], input[id*='dataInicial' i]"])
            end_field = self._date_control(page, "END_DATE", ["input[aria-label*='data final' i], input[placeholder*='data final' i], input[name*='dtFinal' i], input[id*='dtFinal' i], input[name*='dataFinal' i], input[id*='dataFinal' i]"])
            self._set_competence_date(end_field, "END_DATE", end.strftime("%d/%m/%Y"))
            self._settle_date_control(end_field, "END_DATE")
            self._set_competence_date(start_field, "START_DATE", start.strftime("%d/%m/%Y"))
            self._settle_date_control(start_field, "START_DATE")
            self._dismiss_date_overlays(start_field, end_field)
            self._validate_competence_dates(start_field, end_field)
            before = self._search_snapshot(page)
            self._record_pre_search_state(before)
            self._activate_search(page)
            self._confirm_search_refresh(page, before)
            self._competence = competence
            self._search_confirmed = True
            self._timing_diagnostics["COMPETENCE_TOTAL_SECONDS"] = round(time.perf_counter() - competence_started, 6)
        except PortalAdapterError as exc:
            if exc.category.startswith("SEARCH_") or exc.category == "COMPETENCE_SELECTION_FAILED":
                raise
            raise PortalAdapterError(
                "COMPETENCE_SELECTION_FAILED",
                self._failure_diagnostics("COMPETENCE_SELECTION", "COMPETENCE_SELECTION_FAILED"),
            ) from None
        except Exception as exc:
            raise PortalAdapterError(
                "COMPETENCE_SELECTION_FAILED",
                self._failure_diagnostics("COMPETENCE_SELECTION", "COMPETENCE_SELECTION_FAILED"),
            ) from None

    @property
    def navigation_diagnostics(self) -> dict[str, object]:
        return {**self._navigation_diagnostics, **self._competence_diagnostics, **self._search_diagnostics, **self._download_diagnostics, **self._timing_diagnostics}

    @property
    def download_manifest(self) -> tuple[dict[str, object], ...]:
        """Safe, per-payment provenance for the caller-owned staging run."""
        return tuple(self._download_manifest)

    def download_statements(self, account: RuntimeAccount) -> Iterable[Path]:
        required_search = ("SEARCH_CONTROL_FOUND", "SEARCH_ACTIONABLE_CONTROL_RESOLVED", "SEARCH_ACTIVATION_ATTEMPTED", "SEARCH_ACTIVATION_CONFIRMED", "SEARCH_RESULT_REFRESH_CONFIRMED")
        if not self._competence or not self._search_clicked or not self._search_confirmed or not all(self._search_diagnostics.get(key) is True for key in required_search):
            raise PortalAdapterError("SEARCH_NOT_EXECUTED", self.navigation_diagnostics)
        page = self._require_page()
        self._download_diagnostics = {"PAYMENT_ROWS_DISCOVERED": 0, "PAYMENT_ROWS_PROCESSED": 0, "DOWNLOAD_ACTIONS_DISCOVERED": 0, "DOWNLOAD_ACTIONS_COMPLETED": 0}
        self._download_manifest = []
        rows = page.locator("tbody tr:visible")
        try:
            count = rows.count()
        except Exception as exc:
            raise PortalAdapterError("DOCUMENT_DISCOVERY_FAILED") from exc
        body = page.locator("body").inner_text().casefold()
        if count == 0 or any(text in body for text in ("nenhum demonstrativo", "sem demonstrativo", "não existem")):
            return ()
        files: list[Path] = []
        for row in range(count):
            row_text = rows.nth(row).inner_text()
            payment_date = re.search(r"\d{2}/\d{2}/\d{4}", row_text)
            if payment_date is None:
                continue
            self._download_diagnostics["PAYMENT_ROWS_DISCOVERED"] += 1
            row_key = hashlib.sha256(re.sub(r"\s+", " ", row_text).strip().casefold().encode("utf-8")).hexdigest()
            for label, selectors in (("analitico", [f"#frm\\:tabela\\:{row}\\:j_idt66", f"tbody tr:visible >> nth={row} >> button[title*='anal' i]"]), ("sintetico", [f"#frm\\:tabela\\:{row}\\:j_idt67", f"tbody tr:visible >> nth={row} >> button[title*='sint' i]"])):
                self._download_diagnostics["DOWNLOAD_ACTIONS_DISCOVERED"] += 1
                downloaded = self._download(page, account, label, selectors)
                files.append(downloaded)
                self._download_diagnostics["DOWNLOAD_ACTIONS_COMPLETED"] += 1
                self._download_manifest.append({"run_id": self.settings.run_id, "account_index": account.index, "payment_row_ordinal": row + 1, "payment_row_key": row_key, "payment_date": payment_date.group(0), "document_role": label, "download_action": label, "file_sha256": hashlib.sha256(downloaded.read_bytes()).hexdigest()})
            self._download_diagnostics["PAYMENT_ROWS_PROCESSED"] += 1
        if self._download_diagnostics["PAYMENT_ROWS_DISCOVERED"] != self._download_diagnostics["PAYMENT_ROWS_PROCESSED"] or self._download_diagnostics["DOWNLOAD_ACTIONS_DISCOVERED"] != self._download_diagnostics["DOWNLOAD_ACTIONS_COMPLETED"]:
            raise PortalAdapterError("DOCUMENT_PROCESSING_INCOMPLETE", self.navigation_diagnostics)
        if not files:
            raise PortalAdapterError("UNEXPECTED_PAGE")
        return tuple(files)

    def inventory_payment_rows(self, account: RuntimeAccount) -> tuple[dict[str, object], ...]:
        """Enumerate payment rows and available document actions without clicks.

        A row is accepted only when both required document actions are visible;
        otherwise the account fails closed rather than presenting a partial
        inventory as complete.
        """
        self._require_confirmed_search()
        page = self._require_page()
        self._download_diagnostics = {"PAYMENT_ROWS_DISCOVERED": 0, "PAYMENT_ROWS_PROCESSED": 0, "DOWNLOAD_ACTIONS_DISCOVERED": 0, "DOWNLOAD_ACTIONS_COMPLETED": 0, "ANALITICO_ACTIONS_DISCOVERED": 0, "SINTETICO_ACTIONS_DISCOVERED": 0, "DOCUMENT_DOWNLOAD_COUNT": 0}
        self._download_manifest = []
        rows = page.locator("tbody tr:visible")
        try:
            count = rows.count(); body = page.locator("body").inner_text().casefold()
        except Exception as exc:
            raise PortalAdapterError("DOCUMENT_DISCOVERY_FAILED") from exc
        if count == 0 or any(text in body for text in ("nenhum demonstrativo", "sem demonstrativo", "não existem")):
            return ()
        for row in range(count):
            row_text = rows.nth(row).inner_text(); payment_date = re.search(r"\d{2}/\d{2}/\d{4}", row_text)
            if payment_date is None:
                continue
            self._download_diagnostics["PAYMENT_ROWS_DISCOVERED"] += 1
            available = {label: self._action_visible(page, selectors) for label, selectors in (("analitico", [f"#frm\\:tabela\\:{row}\\:j_idt66", f"tbody tr:visible >> nth={row} >> button[title*='anal' i]"]), ("sintetico", [f"#frm\\:tabela\\:{row}\\:j_idt67", f"tbody tr:visible >> nth={row} >> button[title*='sint' i]"]))}
            for label, found in available.items():
                if found:
                    self._download_diagnostics[f"{label.upper()}_ACTIONS_DISCOVERED"] += 1
                    self._download_diagnostics["DOWNLOAD_ACTIONS_DISCOVERED"] += 1
            if not all(available.values()):
                raise PortalAdapterError("DOCUMENT_ACTION_INVENTORY_INCOMPLETE", self.navigation_diagnostics)
            row_key = hashlib.sha256(re.sub(r"\s+", " ", row_text).strip().casefold().encode("utf-8")).hexdigest()
            self._download_manifest.append({"run_id": self.settings.run_id, "account_index": account.index, "payment_row_ordinal": row + 1, "payment_row_key": row_key, "payment_date": payment_date.group(0), "analitico_action_available": True, "sintetico_action_available": True})
            self._download_diagnostics["PAYMENT_ROWS_PROCESSED"] += 1
        if self._download_diagnostics["PAYMENT_ROWS_DISCOVERED"] != self._download_diagnostics["PAYMENT_ROWS_PROCESSED"]:
            raise PortalAdapterError("DOCUMENT_PROCESSING_INCOMPLETE", self.navigation_diagnostics)
        return self.download_manifest

    def close(self) -> None:
        for item in (self._context, self._browser, self._playwright):
            try:
                if item is not None:
                    item.close() if item is self._context or item is self._browser else item.stop()
            except Exception:
                pass
        self._context = self._browser = self._playwright = self._page = None

    def _start_page(self):
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PortalAdapterError("PLAYWRIGHT_NOT_INSTALLED") from exc
        self.settings.staging_dir.mkdir(parents=True, exist_ok=True)
        self._playwright = sync_playwright().start()
        options = {"headless": not self.settings.headed}
        if self.settings.executable_path:
            options["executable_path"] = self.settings.executable_path
        self._browser = self._playwright.chromium.launch(**options)
        self.browser_started = True
        self._context = self._browser.new_context(accept_downloads=True, viewport=None)
        self._context.set_default_timeout(self.settings.timeout_ms)
        self._page = self._context.new_page()
        return self._page

    def _require_page(self):
        if self._page is None:
            raise PortalAdapterError("SESSION_NOT_AUTHENTICATED")
        return self._page

    def _require_confirmed_search(self) -> None:
        required = ("SEARCH_CONTROL_FOUND", "SEARCH_ACTIONABLE_CONTROL_RESOLVED", "SEARCH_ACTIVATION_ATTEMPTED", "SEARCH_ACTIVATION_CONFIRMED", "SEARCH_RESULT_REFRESH_CONFIRMED")
        if not self._competence or not self._search_clicked or not self._search_confirmed or not all(self._search_diagnostics.get(key) is True for key in required):
            raise PortalAdapterError("SEARCH_NOT_EXECUTED", self.navigation_diagnostics)

    def _action_visible(self, page, selectors: list[str]) -> bool:
        try:
            self._first_visible(page, selectors)
            return True
        except PortalAdapterError:
            return False

    def _validate_session(self, page) -> None:
        text = page.locator("body").inner_text(timeout=10_000).casefold()
        if "captcha" in text:
            raise HumanInterventionRequired("CAPTCHA_REQUIRED", "Complete the CAPTCHA in the opened portal window, then continue.")
        if "código" in text and any(token in text for token in ("mfa", "verificação", "autenticação")):
            raise HumanInterventionRequired("MFA_REQUIRED", "Complete the MFA challenge in the opened portal window, then continue.")
        if any(token in text for token in ("senha inválida", "credenciais inválidas", "usuário inválido")):
            raise PortalAdapterError("INVALID_CREDENTIAL")
        self._first_visible(page, ["text=/Financeiro/i"])

    def _categorise_login_failure(self, page, _exc: Exception) -> PortalAdapterError:
        try:
            text = page.locator("body").inner_text(timeout=2_000).casefold()
        except Exception:
            return PortalAdapterError("PORTAL_UNAVAILABLE")
        if "captcha" in text:
            raise HumanInterventionRequired("CAPTCHA_REQUIRED", "Complete the CAPTCHA in the opened portal window, then continue.")
        if "tempo" in text or "indispon" in text:
            return PortalAdapterError("PORTAL_UNAVAILABLE")
        return PortalAdapterError("UNEXPECTED_PAGE")

    def _first_visible(self, page, selectors: list[str]):
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                locator.wait_for(state="visible", timeout=self.settings.timeout_ms)
                return locator
            except Exception:
                continue
        raise PortalAdapterError("UNEXPECTED_PAGE")

    def _click_text(self, page, labels: list[str]) -> None:
        for label in labels:
            for candidate in (page.get_by_role("link", name=re.compile(label, re.I)), page.get_by_role("button", name=re.compile(label, re.I)), page.get_by_text(re.compile(label, re.I))):
                try:
                    candidate.first.click(timeout=self.settings.timeout_ms)
                    return
                except Exception:
                    continue
        raise PortalAdapterError("UNEXPECTED_PAGE")

    def _navigate_to_demonstrativo(self, page) -> None:
        """Open the authenticated Demonstrativo endpoint and confirm its page identity.

        The legacy menu helper matched the broad word ``Socinpro`` rather than
        the actual ``Distribuição SOCINPRO`` entry.  Its generated JSF markup
        makes that intermediate menu unstable.  The protected route is stable,
        requires the already-authenticated context, and avoids generated IDs.
        """
        diagnostics = self._navigation_diagnostics or self._new_navigation_diagnostics(page)
        diagnostics["PORTAL_STAGE"] = "POST_LOGIN_NAVIGATION"
        self._navigation_diagnostics = diagnostics
        try:
            page.goto(DEMONSTRATIVO_URL, wait_until="domcontentloaded", timeout=self.settings.timeout_ms)
            self._verify_demonstrativo_page(page, diagnostics)
        except Exception as exc:
            if isinstance(exc, PortalAdapterError) and exc.category == "POST_LOGIN_NAVIGATION_FAILED":
                raise
            diagnostics["CURRENT_URL_CLASS"] = self._url_class(page)
            diagnostics["LAYOUT_FAILURE_REASON"] = self._navigation_failure_reason(exc)
            self._navigation_diagnostics = diagnostics
            raise PortalAdapterError("POST_LOGIN_NAVIGATION_FAILED", diagnostics) from None

    def _verify_demonstrativo_page(self, page, diagnostics: dict[str, object]) -> None:
        current_path = urlparse(page.url).path
        if current_path != DEMONSTRATIVO_PATH:
            raise PortalAdapterError("UNEXPECTED_PAGE")
        try:
            body = page.locator("body").inner_text(timeout=self.settings.timeout_ms).casefold()
        except Exception as exc:
            raise PortalAdapterError("UNEXPECTED_PAGE") from exc
        if "demonstrativo" not in body:
            raise PortalAdapterError("UNEXPECTED_PAGE")
        diagnostics["DEMONSTRATIVO_PAGE_CONFIRMED"] = True
        diagnostics["CURRENT_URL_CLASS"] = "DEMONSTRATIVO_PAGE"
        self._navigation_diagnostics = diagnostics

    @staticmethod
    def _new_navigation_diagnostics(page) -> dict[str, object]:
        return {
            "PORTAL_STAGE": "POST_LOGIN_NAVIGATION",
            "NAV_FINANCEIRO_FOUND": False,
            "NAV_FINANCEIRO_ACTIVATED": False,
            "NAV_SOCINPRO_FOUND": False,
            "NAV_SOCINPRO_ACTIVATED": False,
            "NAV_DEMONSTRATIVO_FOUND": False,
            "NAV_DEMONSTRATIVO_ACTIVATED": False,
            "DEMONSTRATIVO_PAGE_CONFIRMED": False,
            "CURRENT_URL_CLASS": PlaywrightSocinproSession._url_class(page),
            "LAYOUT_FAILURE_REASON": None,
        }

    @staticmethod
    def _url_class(page) -> str:
        path = urlparse(str(getattr(page, "url", ""))).path.casefold()
        if path == DEMONSTRATIVO_PATH:
            return "DEMONSTRATIVO_PAGE"
        if "/pages/protected/financeiro/" in path:
            return "FINANCEIRO_AREA"
        if "/pages/protected/" in path:
            return "AUTHENTICATED_HOME" if path.rstrip("/").endswith("/home.xhtml") else "UNKNOWN_AUTHENTICATED_PAGE"
        return "OTHER"

    @staticmethod
    def _navigation_failure_reason(exc: Exception) -> str:
        if isinstance(exc, PortalAdapterError) and exc.category == "UNEXPECTED_PAGE":
            return "TARGET_PAGE_NOT_CONFIRMED"
        return "TARGET_ROUTE_UNAVAILABLE"

    def _failure_diagnostics(self, stage: str, reason: str) -> dict[str, object]:
        diagnostics = dict(self._navigation_diagnostics)
        diagnostics["PORTAL_STAGE"] = stage
        diagnostics["LAYOUT_FAILURE_REASON"] = reason
        self._navigation_diagnostics = diagnostics
        return diagnostics

    def _set_date(self, field, value: str) -> tuple[str, str]:
        """Replace a PrimeFaces date value through normal keyboard interaction.

        ``fill`` can bypass the per-keystroke behavior expected by a JSF date
        widget.  Typing after a Windows select-all produces ordinary input
        events; Tab produces the normal change/blur path.  Return both
        readbacks so a component reversion is distinguishable from a failed
        replacement.
        """
        field.focus()
        field.press("Control+A")
        field.press("Backspace")
        field.type(value)
        immediately_after_mutation = field.input_value().strip()
        field.press("Tab")
        after_blur = field.input_value().strip()
        return immediately_after_mutation, after_blur

    def _date_control(self, page, prefix: str, selectors: list[str]):
        started = time.perf_counter()
        diagnostics = self._competence_diagnostics
        try:
            field = self._first_visible(page, selectors)
            diagnostics[f"{prefix}_CONTROL_FOUND"] = True
            try:
                actionable = field.is_editable()
            except Exception:
                actionable = True
            diagnostics[f"{prefix}_CONTROL_ACTIONABLE"] = bool(actionable)
            if not actionable:
                raise self._competence_failure(f"{prefix}_NOT_ACTIONABLE")
            return field
        except PortalAdapterError as exc:
            if exc.category == "COMPETENCE_SELECTION_FAILED":
                raise
            raise self._competence_failure(f"{prefix}_CONTROL_NOT_FOUND") from None
        finally:
            self._timing_diagnostics[f"{prefix}_LOCATOR_SECONDS"] = round(time.perf_counter() - started, 6)

    def _set_competence_date(self, field, prefix: str, expected: str) -> None:
        started = time.perf_counter()
        self._competence_diagnostics[f"{prefix}_SET_ATTEMPTED"] = True
        try:
            immediately_after_mutation, after_blur = self._set_date(field, expected)
            self._competence_diagnostics[f"{prefix}_VALUE_AFTER_MUTATION"] = immediately_after_mutation
            self._competence_diagnostics[f"{prefix}_VALUE_AFTER_BLUR"] = after_blur
            if immediately_after_mutation != expected:
                raise self._competence_failure(f"{prefix}_MUTATION_MISMATCH")
            if after_blur != expected:
                reason = f"{prefix}_REVERTED_AFTER_BLUR" if immediately_after_mutation == expected else f"{prefix}_BLUR_MISMATCH"
                raise self._competence_failure(reason)
        except PortalAdapterError:
            raise
        except Exception:
            raise self._competence_failure(f"{prefix}_SET_FAILED") from None
        finally:
            self._timing_diagnostics[f"{prefix}_SET_SECONDS"] = round(time.perf_counter() - started, 6)

    def _validate_competence_dates(self, start_field, end_field) -> None:
        started = time.perf_counter()
        diagnostics = self._competence_diagnostics
        try:
            readback_started = time.perf_counter()
            actual_start = start_field.input_value().strip()
            self._timing_diagnostics["START_DATE_READBACK_SECONDS"] = round(time.perf_counter() - readback_started, 6)
            diagnostics["START_DATE_READBACK_AVAILABLE"] = True
            diagnostics["ACTUAL_START_DATE"] = actual_start
        except Exception:
            raise self._competence_failure("START_DATE_READBACK_FAILED") from None
        try:
            readback_started = time.perf_counter()
            actual_end = end_field.input_value().strip()
            self._timing_diagnostics["END_DATE_READBACK_SECONDS"] = round(time.perf_counter() - readback_started, 6)
            diagnostics["END_DATE_READBACK_AVAILABLE"] = True
            diagnostics["ACTUAL_END_DATE"] = actual_end
        except Exception:
            raise self._competence_failure("END_DATE_READBACK_FAILED") from None
        diagnostics["START_DATE_MATCH"] = actual_start == diagnostics["EXPECTED_START_DATE"]
        diagnostics["END_DATE_MATCH"] = actual_end == diagnostics["EXPECTED_END_DATE"]
        diagnostics["DATE_RANGE_VALIDATION"] = diagnostics["START_DATE_MATCH"] and diagnostics["END_DATE_MATCH"]
        if not diagnostics["START_DATE_MATCH"]:
            raise self._competence_failure("START_DATE_MISMATCH")
        if not diagnostics["END_DATE_MATCH"]:
            raise self._competence_failure("END_DATE_MISMATCH")
        diagnostics["COMPETENCE_STAGE"] = "COMPETENCE_SELECTION_PASS"
        self._search_diagnostics["DATE_READBACK_COMPLETE"] = True
        self._search_diagnostics["DATE_CONTROLS_SETTLED"] = diagnostics["DATE_RANGE_VALIDATION"]
        self._timing_diagnostics["DATE_VALIDATION_SECONDS"] = round(time.perf_counter() - started, 6)

    def _competence_failure(self, reason: str) -> PortalAdapterError:
        self._competence_diagnostics["COMPETENCE_STAGE"] = "COMPETENCE_SELECTION_FAILED"
        self._competence_diagnostics["COMPETENCE_FAILURE_REASON"] = reason
        return PortalAdapterError("COMPETENCE_SELECTION_FAILED", self.navigation_diagnostics)

    @staticmethod
    def _new_competence_diagnostics(start: str, end: str) -> dict[str, object]:
        return {"COMPETENCE_STAGE": "COMPETENCE_SELECTION", "START_DATE_CONTROL_FOUND": False, "END_DATE_CONTROL_FOUND": False, "START_DATE_CONTROL_ACTIONABLE": False, "END_DATE_CONTROL_ACTIONABLE": False, "EXPECTED_START_DATE": start, "EXPECTED_END_DATE": end, "START_DATE_SET_ATTEMPTED": False, "END_DATE_SET_ATTEMPTED": False, "START_DATE_VALUE_AFTER_MUTATION": None, "END_DATE_VALUE_AFTER_MUTATION": None, "START_DATE_VALUE_AFTER_BLUR": None, "END_DATE_VALUE_AFTER_BLUR": None, "START_DATE_READBACK_AVAILABLE": False, "END_DATE_READBACK_AVAILABLE": False, "START_DATE_MATCH": False, "END_DATE_MATCH": False, "DATE_RANGE_VALIDATION": False, "COMPETENCE_FAILURE_REASON": None}

    def _settle_date_control(self, field, prefix: str) -> None:
        """Commit a date widget without using Enter or implicit form submission."""
        try:
            field.press("Escape")
            actual = field.input_value().strip()
        except Exception:
            raise self._competence_failure(f"{prefix}_SETTLE_READBACK_FAILED") from None
        if actual != self._competence_diagnostics[f"EXPECTED_{prefix}"]:
            raise self._competence_failure(f"{prefix}_SETTLE_MISMATCH")
        self._search_diagnostics["DATE_MUTATION_COMPLETE"] = True

    @staticmethod
    def _dismiss_date_overlays(start_field, end_field) -> None:
        """Dismiss PrimeFaces overlays normally; final value readback is authoritative."""
        start_field.press("Escape")
        end_field.press("Escape")

    def _activate_search(self, page) -> None:
        """Click the visible actionable Pesquisar control, never its text node."""
        started = time.perf_counter()
        text = re.compile(r"^\s*Pesquisar\s*$", re.I)
        candidates = [
            page.locator("button:has-text('Pesquisar'), input[type='submit'][value*='Pesquisar' i], input[type='button'][value*='Pesquisar' i], a:has-text('Pesquisar'), [role='button']:has-text('Pesquisar')"),
            page.get_by_role("button", name=text),
            page.get_by_role("link", name=text),
            page.locator("input[type='submit'][value*='Pesquisar' i], input[type='button'][value*='Pesquisar' i]"),
            page.locator("button[title*='Pesquisar' i], [role='button'][aria-label*='Pesquisar' i]"),
            page.get_by_text(text).locator("xpath=ancestor-or-self::*[self::button or self::a or @role='button' or @onclick][1]"),
            page.locator("button:has-text('Pesquisar'), a:has-text('Pesquisar')"),
        ]
        self._start_search_request_observer(page)
        for candidate in candidates:
            try:
                control = candidate.first
                control.wait_for(state="visible", timeout=SEARCH_CONTROL_TIMEOUT_MS)
                self._search_diagnostics["SEARCH_CONTROL_FOUND"] = True
                self._search_diagnostics["SEARCH_CONTROL_RESOLVED"] = True
                self._search_diagnostics["SEARCH_ACTIONABLE_CONTROL_RESOLVED"] = True
                self._record_search_control_metadata(control)
                self._timing_diagnostics["SEARCH_CONTROL_LOCATOR_SECONDS"] = round(time.perf_counter() - started, 6)
                if not control.is_enabled():
                    continue
                self._search_diagnostics["SEARCH_ACTIVATION_ATTEMPTED"] = True
                control.click(timeout=SEARCH_CONTROL_TIMEOUT_MS)
                self._search_clicked = True
                self._timing_diagnostics["SEARCH_ACTIVATION_SECONDS"] = round(time.perf_counter() - started, 6)
                return
            except Exception:
                continue
        self._stop_search_request_observer(page)
        self._timing_diagnostics["SEARCH_CONTROL_LOCATOR_SECONDS"] = round(time.perf_counter() - started, 6)
        self._timing_diagnostics["SEARCH_ACTIVATION_SECONDS"] = round(time.perf_counter() - started, 6)
        raise PortalAdapterError("SEARCH_ACTION_FAILED", self._failure_diagnostics("SEARCH", "SEARCH_ACTION_FAILED"))

    def _search_snapshot(self, page) -> tuple[int, bool, str]:
        rows = tuple(page.locator("tbody tr:visible").all_inner_texts())
        container = page.locator("tbody")
        try:
            markup = container.inner_html()
        except Exception:
            markup = ""
        try:
            container_text = container.inner_text().casefold()
        except Exception:
            container_text = ""
        empty_marker = any(text in (container_text + " " + markup.casefold()) for text in ("nenhum demonstrativo", "sem demonstrativo", "não existem"))
        fingerprint_source = "\n".join((*rows, markup or ""))
        fingerprint = hashlib.sha256(fingerprint_source.encode("utf-8")).hexdigest()[:16]
        return len(rows), empty_marker, fingerprint

    def _record_pre_search_state(self, snapshot: tuple[int, bool, str]) -> None:
        row_count, empty_marker, fingerprint = snapshot
        self._search_diagnostics.setdefault("SEARCH_CONTROL_FOUND", False)
        self._search_diagnostics.setdefault("SEARCH_ACTIVATION_ATTEMPTED", False)
        self._search_diagnostics.setdefault("SEARCH_ACTIVATION_CONFIRMED", False)
        self._search_diagnostics.setdefault("SEARCH_RESULT_REFRESH_CONFIRMED", False)
        self._search_diagnostics.setdefault("SEARCH_PROOF_METHOD", None)
        self._search_diagnostics.setdefault("REFRESHED_RESULT_EMPTY", False)
        self._search_diagnostics["PRE_SEARCH_ROW_COUNT"] = row_count
        self._search_diagnostics["PRE_SEARCH_EMPTY_MARKER_PRESENT"] = empty_marker
        self._search_diagnostics["PRE_SEARCH_RESULT_FINGERPRINT"] = fingerprint

    def _confirm_search_refresh(self, page, before: tuple[int, bool, str]) -> None:
        started = time.perf_counter()
        deadline = time.monotonic() + min(self.settings.timeout_ms, SEARCH_REFRESH_TIMEOUT_MS) / 1000
        try:
            while time.monotonic() < deadline:
                current = self._search_snapshot(page)
                if current != before:
                    self._confirm_search_proof(current, "RESULT_CONTAINER_MUTATION")
                    return
                page.wait_for_timeout(SEARCH_POLL_MS)
            if self._search_ajax_observed:
                self._confirm_search_proof(before, "AJAX_REQUEST")
                return
        finally:
            self._stop_search_request_observer(page)
            self._timing_diagnostics["SEARCH_REFRESH_SECONDS"] = round(time.perf_counter() - started, 6)
        raise PortalAdapterError("SEARCH_REFRESH_NOT_CONFIRMED", self._failure_diagnostics("SEARCH", "SEARCH_REFRESH_NOT_CONFIRMED"))

    def _confirm_search_proof(self, snapshot: tuple[int, bool, str], method: str) -> None:
        row_count, empty_marker, _fingerprint = snapshot
        self._search_confirmed = True
        self._search_diagnostics["SEARCH_ACTIVATION_CONFIRMED"] = True
        self._search_diagnostics["SEARCH_RESULT_REFRESH_CONFIRMED"] = True
        self._search_diagnostics["SEARCH_PROOF_METHOD"] = method
        self._search_diagnostics["SEARCH_REQUEST_OBSERVED"] = method == "AJAX_REQUEST"
        self._search_diagnostics["SEARCH_RESULT_CONTAINER_CHANGED"] = method == "RESULT_CONTAINER_MUTATION"
        self._search_diagnostics["REFRESHED_RESULT_EMPTY"] = row_count == 0 and empty_marker

    def _start_search_request_observer(self, page) -> None:
        self._search_ajax_observed = False

        def request_observed(request) -> None:
            if str(getattr(request, "method", "")).upper() == "POST":
                self._search_ajax_observed = True

        try:
            page.on("request", request_observed)
        except Exception:
            self._search_request_handler = None
        else:
            self._search_request_handler = request_observed

    def _record_search_control_metadata(self, control) -> None:
        """Record only safe control identity fields, never DOM content."""
        try:
            metadata = control.evaluate("element => ({tag: element.tagName, type: element.getAttribute('type')})")
            self._search_diagnostics["SEARCH_RESOLVED_TAG"] = str(metadata.get("tag", "")).casefold() or None
            self._search_diagnostics["SEARCH_RESOLVED_TYPE"] = metadata.get("type")
        except Exception:
            pass

    def _stop_search_request_observer(self, page) -> None:
        if self._search_request_handler is None:
            return
        try:
            page.remove_listener("request", self._search_request_handler)
        except Exception:
            pass
        self._search_request_handler = None

    def _download(self, page, account: RuntimeAccount, label: str, selectors: list[str]) -> Path:
        button = self._first_visible(page, selectors)
        try:
            self.settings.staging_dir.mkdir(parents=True, exist_ok=True)
            with page.expect_download(timeout=self.settings.download_timeout_ms) as event:
                button.click()
            download = event.value
            suggested = Path(download.suggested_filename or f"socinpro_{account.index}_{label}.pdf").name
            target = self._unique_target(suggested)
            download.save_as(target)
            if target.suffix.casefold() != ".pdf" or target.stat().st_size < 5 or target.read_bytes()[:5] != b"%PDF-":
                target.unlink(missing_ok=True)
                raise PortalAdapterError("DOWNLOAD_INVALID")
            return target
        except PortalAdapterError:
            raise
        except Exception as exc:
            raise PortalAdapterError("DOWNLOAD_TIMEOUT") from exc

    def _unique_target(self, filename: str) -> Path:
        target = self.settings.staging_dir / filename
        number = 1
        while target.exists():
            target = self.settings.staging_dir / f"{Path(filename).stem} ({number}){Path(filename).suffix}"
            number += 1
        return target


def competence_date_range(competence: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}-\d{2}", competence):
        raise PortalAdapterError("COMPETENCE_INVALID")
    year, month = map(int, competence.split("-"))
    if not 1 <= month <= 12:
        raise PortalAdapterError("COMPETENCE_INVALID")
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
