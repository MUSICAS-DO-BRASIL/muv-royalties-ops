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
`Decimal` is canonical. Extraction adapters for real SOCINPRO PDF/portal
layouts are intentionally not included: they require reviewed fixtures and
approved external mappings before controlled operation.

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

Not yet authorized. A controlled real SOCINPRO run requires a separately
reviewed portable extraction adapter, externally managed approved mappings,
and the pre-existing validated bank result for the exact entity and competence.
