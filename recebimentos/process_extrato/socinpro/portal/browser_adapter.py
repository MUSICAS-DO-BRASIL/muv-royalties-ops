"""Playwright adapter for the SOCINPRO portal.

The adapter has no credential, cookie, profile, or default-download path in
source.  Each account receives a fresh browser context and downloads only to
the caller-provided staging directory. CAPTCHA and MFA always stop for a human.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import calendar
import logging
from pathlib import Path
import re
import time
from typing import Iterable

from ..portal_runtime import HumanInterventionRequired, RuntimeAccount, SocinproPortalRuntimeError

LOGGER = logging.getLogger(__name__)
LOGIN_URL = "https://associado.socinpro.org.br/portal-web/pages/public/access/login.xhtml"


class PortalAdapterError(SocinproPortalRuntimeError):
    """Categorised portal error; its text deliberately omits secret values."""

    def __init__(self, category: str):
        super().__init__(category)
        self.category = category


@dataclass(frozen=True)
class BrowserSettings:
    staging_dir: Path
    headed: bool = True
    timeout_ms: int = 45_000
    download_timeout_ms: int = 120_000
    executable_path: str | None = None


class PlaywrightSocinproSession:
    """Fresh-context-per-account session, reusable by both HM and MDB."""

    def __init__(self, settings: BrowserSettings):
        self.settings = settings
        self._playwright = None
        self._browser = None
        self._context = None
        self._page = None
        self._competence: str | None = None
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
        year, month = map(int, competence.split("-"))
        if not 1 <= month <= 12:
            raise PortalAdapterError("COMPETENCE_INVALID")
        try:
            self._click_text(page, ["Financeiro"])
            self._click_text(page, ["Socinpro", "SOCINPRO"])
            self._click_text(page, ["Demonstrativo"])
            start, end = date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])
            self._first_visible(page, ["input[id*='dtInicial']", "input[name*='dtInicial']"]).fill(start.strftime("%d/%m/%Y"))
            self._first_visible(page, ["input[id*='dtFinal']", "input[name*='dtFinal']"]).fill(end.strftime("%d/%m/%Y"))
            self._click_text(page, ["Pesquisar"])
            self._competence = competence
        except Exception as exc:
            raise PortalAdapterError("COMPETENCE_SELECTION_FAILED") from exc

    def download_statements(self, account: RuntimeAccount) -> Iterable[Path]:
        if not self._competence:
            raise PortalAdapterError("COMPETENCE_NOT_SELECTED")
        page = self._require_page()
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
            text = rows.nth(row).inner_text().casefold()
            if not re.search(r"\d{2}/\d{2}/\d{4}", text):
                continue
            for label, selectors in (("analitico", [f"#frm\\:tabela\\:{row}\\:j_idt66", f"tbody tr:visible >> nth={row} >> button[title*='anal' i]"]), ("sintetico", [f"#frm\\:tabela\\:{row}\\:j_idt67", f"tbody tr:visible >> nth={row} >> button[title*='sint' i]"])):
                files.append(self._download(page, account, label, selectors))
        if not files:
            raise PortalAdapterError("UNEXPECTED_PAGE")
        return tuple(files)

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
