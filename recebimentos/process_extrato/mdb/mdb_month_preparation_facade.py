"""Isolated create-only MDB month facade with an explicit template dependency."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from bank_extraction_core import SafraExtractionResult
from cloud_aware_workbook_publisher import create_workbook_only
from mdb_safra_worksheet_writer import MdbSafraWorksheetWriter


@dataclass(frozen=True)
class MdbMonthPreparationResult:
    status: str
    workbook_path: Path | None
    errors: tuple[str, ...] = ()


class MdbMonthPreparationFacade:
    def __init__(self, *, template_path: str | Path, monthly_root: str | Path, writer: MdbSafraWorksheetWriter | None = None) -> None:
        self.template_path = Path(template_path)
        self.monthly_root = Path(monthly_root)
        self.writer = writer or MdbSafraWorksheetWriter()

    def prepare(self, result: SafraExtractionResult, competence: str) -> MdbMonthPreparationResult:
        if result.entity != "MDB" or result.bank_source != "SAFRA" or result.period != competence:
            return MdbMonthPreparationResult("BLOCKED", None, ("Resultado Safra inválido para MDB.",))
        if not self.template_path.is_file():
            return MdbMonthPreparationResult("BLOCKED", None, ("Template MDB não encontrado.",))
        year, month = competence.split("-")
        destination = self.monthly_root / year / f"{month}{year}" / "MDB" / f"Conciliação - Músicas do Brasil_{year}{month}.xlsx"
        if destination.exists():
            return MdbMonthPreparationResult("ALREADY_EXISTS", destination)
        try:
            with TemporaryDirectory(prefix="muv-mdb-") as temporary:
                staged = Path(temporary) / destination.name
                shutil.copy2(self.template_path, staged)
                self.writer.write(staged, result.safra_rows)
                publication = create_workbook_only(staged, destination)
                if publication.status != "PASS":
                    return MdbMonthPreparationResult("BLOCKED", None, (publication.status,))
            return MdbMonthPreparationResult("PREPARED", destination)
        except Exception as exc:
            return MdbMonthPreparationResult("BLOCKED", None, (str(exc),))
