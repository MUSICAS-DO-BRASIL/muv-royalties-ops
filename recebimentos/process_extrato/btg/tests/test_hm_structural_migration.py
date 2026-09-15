from __future__ import annotations

import unittest
from unittest.mock import patch

from hm_structural_migration import discover_btg_dependencies, formula_regression


class StructuralMigrationAuditTests(unittest.TestCase):
    def test_discovers_credit_and_source_dependencies(self):
        formulas = {
            ("fontes", "C7"): "=SUMIF('BTG'!D:D,B7,'BTG'!C:C)",
            ("other", "A1"): "=1",
        }
        with patch("hm_structural_migration.formula_records", return_value=formulas):
            rows = discover_btg_dependencies("unused.xlsx", "BTG")
        self.assertEqual({row["referenced_btg_column"] for row in rows}, {"C", "D"})

    def test_allows_only_expected_mapping_fallback_change(self):
        before = {("BTG", "D2"): '=XLOOKUP(B2,map,map,"xxxxERROExxxx")', ("fontes", "C7"): "='BTG'!C:C"}
        after = {("BTG", "D2"): '=XLOOKUP(B2,map,map,"REVIEW / UNKNOWN")', ("fontes", "C7"): "='BTG'!C:C"}
        with patch("hm_structural_migration.formula_records", side_effect=[before, after]):
            report = formula_regression("source.xlsx", "staging.xlsx", "BTG")
        self.assertTrue(all(row["pass_fail"] == "PASS" for row in report))


if __name__ == "__main__":
    unittest.main()
