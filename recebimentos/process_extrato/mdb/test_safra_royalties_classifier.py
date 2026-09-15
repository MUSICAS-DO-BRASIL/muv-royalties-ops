from decimal import Decimal
import unittest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from safra_royalties_classifier import classify_transaction, extract_bank_payor, identify_royalty_source, load_source_map, normalize_text


class SafraRoyaltiesClassifierTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        aliases = {
            "FUSION MUSIC EDICOES MUSICAIS": "FUSION MUSIC",
            "ABRAMUS DIGITAL SERVICOS I R": "ABRAMUS",
            "SOC INDEP COMPOSITORES AUTORES": "SOCINPRO",
            "SOCINPRO SOC BRAS DE ADM E PRO": "SOCINPRO",
            "UNIAO BRASILEIRA DE COMPOSITOR": "UBC",
            "SONY MUSIC PUBLISHING BRAZIL": "SONY MUSIC PUBLISHING",
            "R3 PRODUCOES ARTISTICAS LTDA": "R3 PRODUCOES",
            "WARNER CHAPPELL MUSIC BRASIL E": "WARNER CHAPPELL",
        }
        path = Path(temporary.name) / "synthetic-map.json"
        path.write_text(json.dumps({"aliases": [
            {"bank_payor_alias": alias, "canonical_royalty_source": source}
            for alias, source in aliases.items()
        ]}), encoding="utf-8")
        self.source_map = load_source_map(path)

    def test_confirmed_aliases_match_exactly_after_normalization(self):
        source_map = self.source_map
        cases = {
            "PIX RECEBIDO FUSION MUSIC EDICOES MUSICAIS 1234": "FUSION MUSIC",
            "TED E RECEBIDA BCO 237 ABRAMUS DIGITAL SERVICOS I. R. 1234": "ABRAMUS",
            "TED E RECEBIDA BCO 237 SOC INDEP COMPOSITORES AUTORES 1234": "SOCINPRO",
            "TED E RECEBIDA BCO 001 SOCINPRO SOC BRAS DE ADM E PRO 1234": "SOCINPRO",
            "TED E RECEBIDA BCO 033 UNIAO BRASILEIRA DE COMPOSITOR 1234": "UBC",
            "TED E RECEBIDA BCO 341 SONY MUSIC PUBLISHING BRAZIL 1234": "SONY MUSIC PUBLISHING",
            "PIX RECEBIDO R3 PRODUCOES ARTISTICAS LTDA 1234": "R3 PRODUCOES",
            "TED E RECEBIDA BCO 745 WARNER CHAPPELL MUSIC BRASIL E 1234": "WARNER CHAPPELL",
        }
        for description, expected in cases.items():
            self.assertEqual(identify_royalty_source(description, source_map=source_map), expected)

    def test_normalization_handles_case_spaces_and_accents(self):
        self.assertEqual(normalize_text("  união   brasileira de compositor "), "UNIAO BRASILEIRA DE COMPOSITOR")
        self.assertEqual(extract_bank_payor("TED E RECEBIDA BCO 033   união brasileira de compositor   1234"), "UNIAO BRASILEIRA DE COMPOSITOR")

    def test_unknown_and_partial_alias_never_match(self):
        source_map = self.source_map
        self.assertIsNone(identify_royalty_source("TED E RECEBIDA BCO 001 SONY MUSIC PUBLISHING 1234", source_map=source_map))
        self.assertIsNone(identify_royalty_source("PIX RECEBIDO FUSION MUSIC EDICOES MUSICAIS EXTRA 1234", source_map=source_map))
        self.assertEqual(classify_transaction("PIX RECEBIDO PAGADOR DESCONHECIDO 1234", None, Decimal("10.00"), source_map=source_map).category, "REVIEW_UNKNOWN_CREDIT")

    def test_non_royalty_does_not_expose_or_classify_payor_as_source(self):
        result = classify_transaction("PIX ENVIADO PAGADOR INTERNO 1234", None, Decimal("-10.00"))
        self.assertEqual(result.category, "NON_ROYALTY")
        self.assertEqual(result.non_royalty_category, "PAGAMENTO")
        self.assertIsNone(result.canonical_source)
