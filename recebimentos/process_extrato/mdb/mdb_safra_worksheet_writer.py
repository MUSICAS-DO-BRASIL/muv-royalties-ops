"""Typed, fail-closed writer for the MDB Safra A:G worksheet contract."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import unicodedata

from openpyxl import load_workbook

from bank_extraction_core import SafraWorksheetRow


EXPECTED_HEADERS = ("data", "lancamento", "complemento", "documento", "valor_str", "valor", "fonte pagadora")


@dataclass(frozen=True)
class MdbWorkbookLayout:
    safra_sheet_name: str


def _fold(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character for character in text if not unicodedata.combining(character)).strip().casefold()


class MdbSafraWorksheetWriter:
    """Write validated Safra rich rows without touching MDB mappings or other sheets."""

    def write(self, path: str | Path, rows: tuple[SafraWorksheetRow, ...], *, layout: MdbWorkbookLayout = MdbWorkbookLayout("Safra")) -> None:
        workbook = load_workbook(path, data_only=False, keep_links=True)
        try:
            if layout.safra_sheet_name not in workbook.sheetnames:
                raise ValueError("Aba Safra não encontrada.")
            sheet = workbook[layout.safra_sheet_name]
            headers = tuple(_fold(sheet.cell(1, column).value) for column in range(1, 8))
            if headers != EXPECTED_HEADERS:
                raise ValueError("Layout Safra MDB inválido: headers A:G não correspondem ao contrato.")
            if any(sheet.cell(row, column).value is not None for row in range(2, sheet.max_row + 1) for column in range(1, 8)):
                raise ValueError("Aba Safra MDB já contém dados; escrita não é idempotente.")
            if any(row.status != "PASS" for row in rows):
                raise ValueError("Linha Safra em revisão não pode ser publicada.")
            for row_number, row in enumerate(rows, start=2):
                sheet.cell(row_number, 1, row.transaction_date)
                sheet.cell(row_number, 2, row.lancamento)
                sheet.cell(row_number, 3, row.complemento)
                sheet.cell(row_number, 4, row.documento)
                sheet.cell(row_number, 5, row.valor_str)
                sheet.cell(row_number, 6, row.credit)
                sheet.cell(row_number, 7, row.payor_source)
            workbook.save(path)
        finally:
            workbook.close()
