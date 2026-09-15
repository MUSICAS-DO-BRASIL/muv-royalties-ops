"""Synthetic-filesystem and Streamlit-runtime coverage for the HM month context."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bank_extraction_core import BankExtractionResult, BankExtractionService
from bank_extraction_month_context import resolve_month_context


class MonthContextRealFilesystemTests(unittest.TestCase):
    def test_hm_202608_real_filesystem_selects_canonical_workbook(self):
        context = resolve_month_context(BankExtractionService(), "HM", "2026-08")
        import bank_extraction_core
        expected = bank_extraction_core.ROOT / "2026" / "082026" / "HM" / "Conciliação - Hurst Music_202608.xlsx"
        self.assertTrue(expected.is_file())
        self.assertTrue(context.is_prepared)
        self.assertEqual(context.workbook_path, expected)

    def test_real_streamlit_prepared_context_never_renders_prepare_action(self):
        result = BankExtractionResult(
            "HM", "BTG", "2026-08", "fixture.pdf", "PASS", "PASS", "PASS",
            3, 2, 1, Decimal("1"), Decimal("300.25"), Decimal("1"), Decimal("1"),
            (), 2, ("unknown",), (), "fixture",
        )
        app = AppTest.from_file(ROOT / "bank_extraction_app_v2.py", default_timeout=30)
        app.session_state["selected_entity"] = "HM"
        app.session_state["selected_period"] = date(2026, 8, 1)
        app.session_state["result"] = result
        app.run()
        self.assertFalse(app.exception)
        self.assertTrue(any("Preparada" in message.value for message in app.markdown))
        buttons = {button.label: button.disabled for button in app.button}
        self.assertTrue(buttons["Conciliação já preparada"])
        self.assertNotIn("Preparar Conciliação do Mês", buttons)

    def test_hm_202608_remains_prepared_after_processing(self):
        before = resolve_month_context(BankExtractionService(), "HM", "2026-08")
        result = BankExtractionResult(
            "HM", "BTG", "2026-08", "fixture.pdf", "PASS", "PASS", "PASS",
            3, 2, 1, Decimal("1000.00"), Decimal("300.25"),
            Decimal("0.25"), Decimal("1300.00"), (), 2, ("unknown",), (), "fixture",
        )
        app = AppTest.from_file(ROOT / "bank_extraction_app_v2.py", default_timeout=30)
        app.session_state["selected_entity"] = "HM"
        app.session_state["selected_period"] = date(2026, 8, 1)
        app.session_state["result"] = result
        app.run()
        after = resolve_month_context(BankExtractionService(), "HM", "2026-08")
        self.assertEqual((before.status, after.status), ("PREPARED", "PREPARED"))
        self.assertFalse(app.exception)
        self.assertTrue(any("Preparada" in message.value for message in app.markdown))
        self.assertFalse(any("Nenhum workbook mensal único" in caption.value for caption in app.caption))
