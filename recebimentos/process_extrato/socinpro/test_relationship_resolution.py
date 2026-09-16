from decimal import Decimal
import json

import pytest

from socinpro.reconciliation import reconcile_by_amount
from socinpro.relationship_resolution import Relationship, RelationshipKey, RelationshipResolver, normalize_key, runtime_mapping_payload


def relation(source, artist="Artist", catalog="Cat", deal="Deal"):
    return Relationship(RelationshipKey("HM", "SOCINPRO", "7", "Titular Á"), artist, catalog, deal, "row-1", source)


def test_current_canonical_wins_over_historical_conflict():
    result = RelationshipResolver(canonical_db=(relation("canonical_db", "Current"),), historical_official=(relation("historical_official", "Old"),)).resolve(RelationshipKey("HM", "SOCINPRO", "7", " titular a "))
    assert result.status == "MATCHED" and result.relationship.canonical_artist == "Current" and result.resolution_source == "canonical_db"


def test_exact_historical_and_ambiguous_sources_fail_safe():
    key = RelationshipKey("HM", "SOCINPRO", "7", "Titular A")
    assert RelationshipResolver(historical_official=(relation("historical_official"),)).resolve(key).status == "MATCHED"
    assert RelationshipResolver(historical_official=(relation("historical_official", catalog="A"), relation("historical_official", catalog="B"))).resolve(key).status == "AMBIGUOUS"


def test_normalization_and_deterministic_runtime_mapping():
    assert normalize_key(" TÍTULAR   A ") == "titular a"
    result = RelationshipResolver(mapping_snapshot=(relation("mapping_snapshot"),)).resolve(RelationshipKey("hm", "socinpro", "7", "titular a"))
    first, fingerprint = runtime_mapping_payload((result,))
    second, second_fingerprint = runtime_mapping_payload((result,))
    assert first == second and fingerprint == second_fingerprint
    assert json.loads(json.dumps(first))["mappings"][0]["source_code"] == "7"


def test_runtime_mapping_rejects_duplicate_source_codes():
    first = RelationshipResolver(mapping_snapshot=(relation("mapping_snapshot"),)).resolve(RelationshipKey("HM", "SOCINPRO", "7", "Titular A"))
    second = RelationshipResolver(mapping_snapshot=(Relationship(RelationshipKey("HM", "SOCINPRO", "7", "Other"), "Artist", "C", "D", "2", "mapping_snapshot"),)).resolve(RelationshipKey("HM", "SOCINPRO", "7", "Other"))
    with pytest.raises(ValueError, match="RUNTIME_MAPPING_NOT_UNIQUE"):
        runtime_mapping_payload((first, second))


def test_amount_reconciliation_consumes_duplicate_values_once():
    result = reconcile_by_amount((Decimal("10"), Decimal("10"), Decimal("5")), (Decimal("10"), Decimal("5"), Decimal("7")))
    assert (result.matched_count, result.matched_total, result.unmatched_document_count, result.unmatched_bank_count, result.difference) == (2, Decimal("15"), 1, 1, Decimal("3"))
