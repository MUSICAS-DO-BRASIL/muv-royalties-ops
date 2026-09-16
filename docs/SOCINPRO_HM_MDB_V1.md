# SOCINPRO HM + MDB V1

## Recovery inventory

The official repository began with no SOCINPRO source module. The legacy
repository was inspected read-only and contains an HM pipeline, an MDB route,
catalog adapter, technical routing, UI, tests and historical closure notes.
Only the behavioural contracts were reused: decimal-first values, semantic
identity independent of document hash, multiple evidence, sidecar audit data,
and fail-closed reconciliation. No legacy source code, hard-coded path,
credential, mapping, production document, or financial output was copied.

## Current source contract

The V1 clean-repository input is a reviewed extracted row, represented by
`SocinproPayment`: entity, competence, payment date, titular, source code,
gross value, source identity and immutable original evidence/reference.
`Decimal` is canonical. Controlled ingestion supports reviewed textual
SOCINPRO payment PDFs and reviewed `pagamentos` workbooks. Portal access
remains outside this repository: where needed, a person downloads the source
and supplies it to the controlled ingestion boundary.

HM and MDB use one core. Their explicit bank adapters are BTG and Safra,
respectively, through an already validated `BankReference`; this module does
not alter bank rules. A deterministic catalogue/deal relation yields `PASS`.
Missing, empty or uncertain catalogue/deal relations yield `REVIEW`, never a
guess. A bank difference likewise remains visible as `REVIEW`. Any `REVIEW`
or `BLOCKED` result is refused by operational publication.

## Publication and audit

When a result is processed, the sole operational artifact is created at
`ROOT/YYYY/MMYYYY/<ENTITY>/SOCINPRO/Demonstrativo_SOCINPRO_YYYYMM.xlsx`.
It contains `Resumo`, `Pagamentos`, and `Pendencias` only when genuine pending
items exist. A non-identical existing workbook raises a conflict, preserving
human work. Audit JSON is external to the operational path and records source
evidence, deterministic payment IDs and reconciliation totals.

## Synthetic acceptance

`test_socinpro_vertical.py` covers both HM/BTG and MDB/Safra from normalized
payment through reconciliation, catalogue association, create-only source
folder, clean demonstrative and reprocessing. It also covers an unknown
relation, duplicate payment, incompatible bank and a divergent existing
demonstrative.

## Controlled real run

The V1.1 parser accepts the proven text-based payment PDF and the historical
`pagamentos` workbook projection, using an explicit entity and competence.
The mapping is runtime-only JSON selected through `MUV_SOCINPRO_MAPPING_PATH`;
the versioned example is synthetic. Missing, malformed or ambiguous mappings
block execution. A controlled real run may now be prepared with a manually
downloaded input, an external approved mapping and the pre-existing validated
bank result for the exact entity and competence. It still never publishes the
official monthly workbook.

## External mapping contract

Set `MUV_SOCINPRO_MAPPING_PATH` to a local JSON file outside Git. Its required
shape is `schema_version: 1` plus `mappings`; each mapping has `entity`,
`source_code`, `titular`, `catalog`, `deal` and boolean `active`. A `(entity,
source_code)` pair is unique. The parser verifies the mapped titular against
the source titular after whitespace/accent normalization. The synthetic schema
example is [socinpro_mapping.example.json](../recebimentos/process_extrato/socinpro/socinpro_mapping.example.json).

Supported source types are intentionally limited to `SOCINPRO_PAYMENT_PDF`
(textual payment demonstrativo) and `SOCINPRO_PAYMENT_WORKBOOK` (legacy
`pagamentos` projection). Portal automation is not required for a controlled
run: a human may download the input and provide it to the parser.

## Historical acceptance

The HM July 2026 historical replay passed against the approved monthly close
in a temporary, read-only workflow. It reproduced the approved documentary,
bank and catalogue totals with no historical publication or catalogue change.
The historical mapping used for that replay remains external runtime
configuration and is never committed. This establishes a golden baseline for
the next unclosed competence; it does not authorize republishing a closed
month. Portal acquisition remains human-in-the-loop when required.

## Portal runtime credential contract

The optional portal runtime is separate from ingestion and uses external,
entity-specific credential paths only: `MUV_SOCINPRO_HM_CREDENTIALS_PATH` for
HM and `MUV_SOCINPRO_MDB_CREDENTIALS_PATH` for MDB. It validates the selected
workbook read-only for a user column, a password column, populated fields and
unique runtime account identifiers before any browser is created. It never
falls back across entities or to a machine-specific path.

`LOGINS.xlsx` is a global master reference and is not a portal runtime
credential dependency. Any downstream catalogue or business use must be
validated at that downstream boundary, after document acquisition; it cannot
block credential preflight or portal download start. Portal browser adapters
remain human-in-the-loop for CAPTCHA and MFA and must not log secrets.
