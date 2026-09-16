"""Deterministic, source-agnostic relationship resolution for receipt rows.

No database connection is opened here.  Adapters supply only reviewed records,
which keeps precedence explicit and makes missing operational sources fail
closed as PENDING rather than turning text similarity into a relationship.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re
import unicodedata
from typing import Iterable, Literal


ResolutionStatus = Literal["MATCHED", "PENDING", "AMBIGUOUS"]


def normalize_key(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return re.sub(r"\s+", " ", text).strip().casefold()


@dataclass(frozen=True)
class RelationshipKey:
    entity: str
    source: str
    source_code: str
    titular: str

    def normalized(self) -> tuple[str, str, str, str]:
        return (normalize_key(self.entity), normalize_key(self.source), str(self.source_code).strip(), normalize_key(self.titular))


@dataclass(frozen=True)
class Relationship:
    key: RelationshipKey
    canonical_artist: str
    catalog: str
    deal: str
    record_reference: str
    source_name: str

    def semantic_value(self) -> tuple[str, str, str]:
        return (self.canonical_artist.strip(), self.catalog.strip(), self.deal.strip())


@dataclass(frozen=True)
class Resolution:
    key: RelationshipKey
    status: ResolutionStatus
    relationship: Relationship | None = None
    resolution_source: str = ""


PRECEDENCE = ("canonical_db", "mapping_snapshot", "historical_official", "legacy_canonical")


class RelationshipResolver:
    def __init__(self, **sources: Iterable[Relationship]):
        unexpected = set(sources) - set(PRECEDENCE)
        if unexpected:
            raise ValueError("RELATIONSHIP_SOURCE_UNKNOWN")
        self._sources = {name: tuple(sources.get(name, ())) for name in PRECEDENCE}

    def resolve(self, key: RelationshipKey) -> Resolution:
        wanted = key.normalized()
        for source in PRECEDENCE:
            candidates = [item for item in self._sources[source] if item.key.normalized() == wanted]
            values = {item.semantic_value() for item in candidates}
            if not candidates:
                continue
            if len(values) != 1:
                return Resolution(key, "AMBIGUOUS", resolution_source=source)
            return Resolution(key, "MATCHED", candidates[0], source)
        return Resolution(key, "PENDING")


def runtime_mapping_payload(resolutions: Iterable[Resolution]) -> tuple[dict[str, object], str]:
    """Produce the existing SOCINPRO mapping schema and a stable semantic hash."""
    mappings = []
    for result in resolutions:
        if result.status != "MATCHED" or result.relationship is None:
            continue
        item = result.relationship
        mappings.append({"entity": item.key.entity.upper().strip(), "source_code": item.key.source_code.strip(), "titular": item.key.titular.strip(), "catalog": item.catalog.strip(), "deal": item.deal.strip(), "active": True})
    mappings.sort(key=lambda item: (item["entity"], item["source_code"], normalize_key(item["titular"])))
    keys = [(item["entity"], item["source_code"]) for item in mappings]
    if len(keys) != len(set(keys)):
        raise ValueError("RUNTIME_MAPPING_NOT_UNIQUE")
    payload = {"schema_version": 1, "mappings": mappings}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return payload, sha256(encoded).hexdigest()
