from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from btg_statement_parser import _parse_details_from_lines
from hm_month_bootstrap import WorkbookInspection, checkpoint, prepare_hm_month
from test_btg_statement_parser import fixture_lines


class HmMonthBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.details = _parse_details_from_lines(fixture_lines(), "fixture.pdf")

    def test_missing_template_is_review_without_writes(self):
        with TemporaryDirectory() as directory, patch("hm_month_bootstrap.parse_btg_statement_details", return_value=self.details):
            context = prepare_hm_month(period="2026-08", btg_statement="ignored.pdf", monthly_root=directory)
            self.assertEqual(context.validation_status, "REVIEW")
            self.assertFalse(context.month_workbook_already_exists)
            self.assertFalse(list(Path(directory).rglob("*.xlsx")))
            self.assertEqual(context, prepare_hm_month(period="2026-08", btg_statement="ignored.pdf", monthly_root=directory))

    def test_existing_workbook_is_not_overwritten(self):
        with TemporaryDirectory() as directory, patch("hm_month_bootstrap.parse_btg_statement_details", return_value=self.details), patch(
            "hm_month_bootstrap.inspect_workbook",
            return_value=WorkbookInspection(Path("existing.xlsx"), "hash", ("BTG",), "BTG", (), False, False, "UNKNOWN_REVIEW", ("fixture",)),
        ):
            folder = Path(directory) / "2026" / "082026" / "HM"
            folder.mkdir(parents=True)
            existing = folder / "existing.xlsx"
            existing.write_bytes(b"not opened because multiple selection is avoided")
            context = prepare_hm_month(period="2026-08", btg_statement="ignored.pdf", monthly_root=directory)
            self.assertTrue(context.month_workbook_already_exists)
            self.assertEqual(context.existing_workbook_path, existing)
            self.assertEqual(existing.read_bytes(), b"not opened because multiple selection is avoided")

    def test_checkpoint_preserves_exact_bank_controls(self):
        with TemporaryDirectory() as directory, patch("hm_month_bootstrap.parse_btg_statement_details", return_value=self.details):
            context = prepare_hm_month(period="2026-08", btg_statement="ignored.pdf", monthly_root=directory)
            result = checkpoint(context)
            self.assertEqual(result["TOTAL_CREDITS"], "300.25")
            self.assertEqual(result["GLOBAL_BALANCE_VALIDATION"], "PASS")


if __name__ == "__main__":
    unittest.main()
