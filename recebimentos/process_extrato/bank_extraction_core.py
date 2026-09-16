"""Domain services for the operator-facing bank-extraction application.

This module owns validation, normalization and idempotent staging output.  It
never writes a reconciliation workbook or an association/source workbook.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Callable, Literal
import importlib.util
import json
import os
import re
import sys

if TYPE_CHECKING:
    from mdb_safra_worksheet_writer import MdbSafraWorksheetWriter

ROOT = Path(os.environ.get("MUV_OPERATIONAL_ROOT") or Path(__file__).resolve().parents[2]).expanduser()
PROCESS_ROOT = Path(__file__).resolve().parent
BTG_DIR = PROCESS_ROOT / "btg"
MDB_DIR = PROCESS_ROOT / "mdb"
ENTITY_BANK: dict[str, str] = {"MDB": "SAFRA", "HM": "BTG"}


@dataclass(frozen=True)
class OperationalCredit:
    transaction_date: date
    description: str
    credit: Decimal
    payor_source: str
    status: Literal["PASS", "REVIEW"]


@dataclass(frozen=True)
class SafraWorksheetRow:
    """Lossless Safra row projection reserved for the MDB worksheet writer."""
    transaction_date: date
    lancamento: str
    complemento: str | None
    documento: str | None
    valor_str: str
    credit: Decimal
    payor_source: str
    status: Literal["PASS", "REVIEW"]


@dataclass(frozen=True)
class BankExtractionResult:
    entity: str
    bank_source: str
    period: str
    source_file_name: str
    account_validation_status: str
    period_validation_status: str
    financial_validation_status: str | None
    technical_transaction_count: int | None
    credit_count: int | None
    debit_count: int | None
    initial_balance: Decimal | None
    total_credits: Decimal | None
    total_debits: Decimal | None
    final_balance: Decimal | None
    operational_credits: tuple[OperationalCredit, ...]
    unknown_source_count: int
    warnings: tuple[str, ...]
    errors: tuple[str, ...]
    source_sha256: str

    @property
    def status(self) -> str:
        if self.errors:
            return "BLOCKED"
        if self.unknown_source_count or self.warnings:
            return "REVIEW"
        return "PASS"


@dataclass(frozen=True)
class SafraExtractionResult(BankExtractionResult):
    """Safra-specific result extension without changing the shared bank contract."""
    safra_rows: tuple[SafraWorksheetRow, ...] = ()


def _load_module(name: str, path: Path):
    module_dir = str(path.parent)
    if module_dir not in sys.path:
        sys.path.insert(0, module_dir)
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load domain module: {path.name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _validate_period(period: str) -> None:
    if not re.fullmatch(r"\d{4}-\d{2}", period):
        raise ValueError("Competência deve usar o formato YYYY-MM.")
    datetime.strptime(period + "-01", "%Y-%m-%d")


def _hash(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


class BTGAdapter:
    """Thin adapter over the approved HM BTG parser and its exact validation."""
    entity = "HM"
    bank_source = "BTG"

    def extract(self, source: Path, period: str) -> BankExtractionResult:
        parser = _load_module("bank_app_btg_parser", BTG_DIR / "btg_statement_parser.py")
        details = parser.parse_btg_statement_details(source)
        validation = parser.validate_btg_statement(details)
        if not validation.passed:
            raise ValueError("Fechamento BTG inválido: " + "; ".join(validation.errors))
        mapping_payload = json.loads(Path(os.environ.get("MUV_BTG_SOURCE_MAP") or BTG_DIR / "btg_source_mapping.v1.json").expanduser().read_text(encoding="utf-8"))
        mapping = {item["description_raw"]: item["canonical_royalty_source"] for item in mapping_payload["aliases"]}
        credits = tuple(
            OperationalCredit(t.transaction_date, t.description_raw, t.amount,
                              mapping.get(t.description_raw, "REVIEW / UNKNOWN"),
                              "PASS" if t.description_raw in mapping else "REVIEW")
            for t in parser.build_btg_royalty_extract(details.transactions)
        )
        return BankExtractionResult(
            self.entity, self.bank_source, period, source.name, "PASS", "PASS", "PASS",
            validation.transaction_count, validation.credit_transaction_count, validation.debit_transaction_count,
            validation.initial_balance, validation.total_credits, validation.total_debits, validation.final_balance,
            credits, sum(item.status == "REVIEW" for item in credits),
            (("Há créditos BTG sem De_Para aprovado; eles permanecem em revisão.",) if any(item.status == "REVIEW" for item in credits) else ()), (), _hash(source),
        )


class SafraAdapter:
    """Facade over the proven multiline Safra parser and deterministic classifier."""
    entity = "MDB"
    bank_source = "SAFRA"

    def extract(self, source: Path, period: str) -> BankExtractionResult:
        parser = _load_module("bank_app_safra_parser", MDB_DIR / "process_safra_mp_toyalties.py")
        classifier = _load_module("bank_app_safra_classifier", MDB_DIR / "safra_royalties_classifier.py")
        import pdfplumber
        with pdfplumber.open(source) as pdf:
            pages = [page.extract_text(x_tolerance=2, y_tolerance=2) or "" for page in pdf.pages]
        header = parser.parse_cabecalho(pages)
        if not header.conta or not header.periodo_ini or not header.periodo_fim:
            raise ValueError("Cabeçalho Safra incompleto: conta ou período não identificado.")
        statement_period = datetime.strptime(header.periodo_ini, "%d/%m/%Y").strftime("%Y-%m")
        if statement_period != period:
            raise ValueError(f"Competência informada ({period}) diverge do extrato Safra ({statement_period}).")
        source_map = classifier.load_source_map()
        rows = parser.extrair_lancamentos(pages, header)
        operational: list[OperationalCredit] = []
        safra_rows: list[SafraWorksheetRow] = []
        for row in rows:
            amount = Decimal(row.valor_str.replace(".", "").replace(",", ".")).quantize(Decimal("0.01"))
            classification = classifier.classify_transaction(row.lancamento, row.complemento, amount, source_map=source_map)
            if classification.category not in {"ROYALTY_RECEIPT", "REVIEW_UNKNOWN_CREDIT"}:
                continue
            source_name = classification.canonical_source or "REVIEW / UNKNOWN"
            status = "PASS" if classification.canonical_source else "REVIEW"
            transaction_date = datetime.strptime(row.data, "%d/%m/%Y").date()
            operational.append(OperationalCredit(transaction_date, row.lancamento, amount, source_name, status))
            safra_rows.append(SafraWorksheetRow(
                transaction_date, row.lancamento, row.complemento, row.documento,
                row.valor_str, amount, source_name, status,
            ))
        unknown = sum(x.status == "REVIEW" for x in operational)
        return SafraExtractionResult(
            self.entity, self.bank_source, period, source.name, "PASS", "PASS", None,
            len(rows), len(operational), None, None, sum((x.credit for x in operational), Decimal("0.00")), None, None,
            tuple(operational), unknown,
            ((f"{unknown} crédito(s) sem Fonte Pagadora confirmada.",) if unknown else ()), (), _hash(source),
            tuple(safra_rows),
        )


class BankExtractionService:
    def __init__(
        self,
        *,
        mdb_template_path: str | Path | None = None,
        monthly_root: str | Path | None = None,
        mdb_safra_sheet_name: str = "Safra",
        mdb_writer: MdbSafraWorksheetWriter | None = None,
    ) -> None:
        self._adapters = {"HM": BTGAdapter(), "MDB": SafraAdapter()}
        self._mdb_template_path = Path(mdb_template_path) if mdb_template_path is not None else None
        self._monthly_root = Path(monthly_root) if monthly_root is not None else ROOT
        self._mdb_safra_sheet_name = mdb_safra_sheet_name
        self._mdb_writer = mdb_writer

    def process(self, *, entity: str, period: str, source_path: str | Path) -> BankExtractionResult:
        if entity not in ENTITY_BANK:
            raise ValueError("Entidade inválida.")
        _validate_period(period)
        source = Path(source_path)
        if source.suffix.lower() != ".pdf" or not source.is_file():
            raise ValueError("Envie um arquivo PDF de extrato bancário válido.")
        return self._adapters[entity].extract(source, period)

    def month_folder(self, entity: str, period: str) -> Path:
        year, month = period.split("-")
        return self._monthly_root / year / f"{month}{year}" / entity

    def month_status(self, entity: str, period: str) -> tuple[bool, Path | None]:
        folder = self.month_folder(entity, period)
        names = {"HM": "Conciliação - Hurst Music", "MDB": "Conciliação - Músicas do Brasil"}
        canonical = folder / f"{names[entity]}_{period[:4]}{period[5:]}.xlsx"
        if canonical.is_file():
            return True, canonical
        # MDB's approved historical files used MMYYYY.  Keep that discovery
        # compatibility while making YYYYMM the canonical name for new months.
        if entity == "MDB":
            legacy = folder / f"{names[entity]}_{period[5:]}{period[:4]}.xlsx"
            if legacy.is_file():
                return True, legacy
        return False, None

    def operational_xlsx_bytes(self, result: BankExtractionResult) -> bytes:
        """Build the deliberate three-column bank artifact in memory for download."""
        from openpyxl import Workbook
        from io import BytesIO
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Extrato"
        sheet.append(["Data", "Descrição", "Crédito"])
        for item in result.operational_credits:
            sheet.append([item.transaction_date, item.description, item.credit])
        sheet.column_dimensions["A"].width = 14
        sheet.column_dimensions["B"].width = 70
        sheet.column_dimensions["C"].width = 18
        for cell in sheet["A"][1:]: cell.number_format = "DD/MM/YYYY"
        for cell in sheet["C"][1:]: cell.number_format = "#,##0.00"
        stream = BytesIO(); workbook.save(stream)
        return stream.getvalue()

    def prepare_month(self, *, entity: str, period: str, source_bytes: bytes, source_name: str) -> tuple[str, str]:
        """Delegate only to the month bootstrap; never create/publish in the UI."""
        exists, path = self.month_status(entity, period)
        if exists:
            return "ALREADY_EXISTS", str(path)
        if entity == "HM":
            bootstrap = _load_module("bank_app_hm_bootstrap", BTG_DIR / "hm_month_bootstrap.py")
            with TemporaryDirectory(prefix="muv-hm-bootstrap-") as temp:
                statement = Path(temp) / source_name
                statement.write_bytes(source_bytes)
                context = bootstrap.prepare_hm_month(period=period, btg_statement=statement, monthly_root=self._monthly_root)
            return context.validation_status, "; ".join(context.review_reasons)
        if entity != "MDB":
            return "BLOCKED", "Entidade inválida para preparação mensal."
        if self._mdb_template_path is None:
            return "REVIEW", "Template MDB não configurado; nenhum workbook foi criado."
        if not self._mdb_template_path.is_file():
            return "BLOCKED", "Template MDB não encontrado; nenhum workbook foi criado."
        facade_module = _load_module("bank_app_mdb_month_facade", MDB_DIR / "mdb_month_preparation_facade.py")
        facade = facade_module.MdbMonthPreparationFacade(
            template_path=self._mdb_template_path,
            monthly_root=self._monthly_root,
            layout=facade_module.MdbWorkbookLayout(safra_sheet_name=self._mdb_safra_sheet_name),
            writer=self._mdb_writer,
        )
        try:
            with TemporaryDirectory(prefix="muv-mdb-bootstrap-") as temp:
                statement = Path(temp) / source_name
                statement.write_bytes(source_bytes)
                result = self.process(entity="MDB", period=period, source_path=statement)
                outcome = facade.prepare(result, period)
        except ValueError as exc:
            return "BLOCKED", str(exc)
        return outcome.status, "; ".join(outcome.errors) if outcome.errors else str(outcome.workbook_path or "")
