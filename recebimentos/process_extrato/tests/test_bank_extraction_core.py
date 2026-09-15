from __future__ import annotations
import sys
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from bank_extraction_core import BankExtractionService, ENTITY_BANK
from bank_extraction_context import EntityContext, resolve_entity_context, validate_processing_context
from bank_extraction_status import bank_closure_status, source_mapping_status
from bank_extraction_month_context import resolve_month_context

class BankExtractionContractTests(unittest.TestCase):
    def test_entity_bank_mapping_is_fixed(self):
        self.assertEqual(ENTITY_BANK,{"MDB":"SAFRA","HM":"BTG"})

    def test_hm_resolves_btg(self):
        context=resolve_entity_context("HM","2026-08")
        self.assertEqual((context.entity,context.bank,context.bank_label),("HM","BTG","BTG Pactual"))

    def test_mdb_resolves_safra(self):
        context=resolve_entity_context("MDB","2026-08")
        self.assertEqual((context.entity,context.bank,context.bank_label),("MDB","SAFRA","Safra"))

    def test_entity_switch_hm_mdb_hm(self):
        contexts=[resolve_entity_context(entity,"2026-08") for entity in ("HM","MDB","HM")]
        self.assertEqual([(item.entity,item.bank) for item in contexts],[("HM","BTG"),("MDB","SAFRA"),("HM","BTG")])

    def test_context_badges_follow_entity(self):
        context=resolve_entity_context("HM","2026-08")
        self.assertEqual((context.entity,context.bank,context.period),("HM","BTG","2026-08"))

    def test_processing_blocks_invalid_context(self):
        with self.assertRaises(ValueError):
            validate_processing_context(EntityContext("HM","SAFRA","Safra","Extrato Safra","2026-08"))

    def test_invalid_entity_and_period_are_blocked(self):
        service=BankExtractionService()
        with self.assertRaises(ValueError): service.process(entity="HM",period="08/2026",source_path="missing.pdf")
        with self.assertRaises(ValueError): service.process(entity="INVALID",period="2026-08",source_path="missing.pdf")

    def test_hm_202608_detects_existing_workbook(self):
        exists,path=BankExtractionService().month_status("HM","2026-08")
        self.assertTrue(exists)
        self.assertEqual(path.name,"Conciliação - Hurst Music_202608.xlsx")

    def test_operational_xlsx_is_only_created_on_explicit_download(self):
        self.assertTrue(callable(BankExtractionService().operational_xlsx_bytes))

    def test_existing_month_preparation_is_idempotent(self):
        state, detail=BankExtractionService().prepare_month(entity="HM",period="2026-08",source_bytes=b"not-read",source_name="fixture.pdf")
        self.assertEqual(state,"ALREADY_EXISTS")
        self.assertIn("Conciliação - Hurst Music_202608.xlsx",detail)

    def test_hm_202609_not_prepared_when_absent(self):
        exists, path = BankExtractionService().month_status("HM", "2026-09")
        self.assertFalse(exists)
        self.assertIsNone(path)

    def test_hm_202608_month_context_consistent_everywhere(self):
        context = resolve_month_context(BankExtractionService(), "HM", "2026-08")
        self.assertTrue(context.workbook_already_exists)
        self.assertEqual(context.status, "PREPARED")
        self.assertEqual(context.workbook_path.name, "Conciliação - Hurst Music_202608.xlsx")

    def test_prepared_month_hides_prepare_action(self):
        context = resolve_month_context(BankExtractionService(), "HM", "2026-08")
        self.assertTrue(context.is_prepared)
        self.assertEqual(context.action_label, "Conciliação já preparada")

    def test_not_prepared_month_shows_prepare_action(self):
        context = resolve_month_context(BankExtractionService(), "HM", "2026-09")
        self.assertFalse(context.is_prepared)
        self.assertEqual(context.action_label, "Preparar Conciliação do Mês")

    def _btg_result_with_unknown_sources(self):
        from bank_extraction_core import BankExtractionResult
        from decimal import Decimal
        return BankExtractionResult("HM", "BTG", "2026-08", "fixture.pdf", "PASS", "PASS", "PASS", 3, 2, 1, Decimal("1000.00"), Decimal("300.25"), Decimal("0.25"), Decimal("1300.00"), (), 3, ("unknown",), (), "fixture")

    def test_bank_closure_pass_with_unknown_sources(self):
        self.assertEqual(bank_closure_status(self._btg_result_with_unknown_sources()), "PASS")

    def test_overall_review_with_unknown_sources(self):
        result = self._btg_result_with_unknown_sources()
        self.assertEqual(source_mapping_status(result), "REVIEW")
        self.assertEqual(result.status, "REVIEW")

if __name__=="__main__": unittest.main()
