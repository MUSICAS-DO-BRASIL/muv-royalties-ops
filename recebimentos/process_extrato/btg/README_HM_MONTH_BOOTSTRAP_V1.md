# HM Month Bootstrap V1

`prepare_hm_month` creates an in-memory `HMMonthContext` from the validated
BTG adapter and inspects, but never overwrites, the requested monthly folder.
Its default outcome is deliberately conservative: it permits a staging-copy
writer only after a real HM template is confirmed to retain the five bank audit
fields `Data`, `Descrição`, `Débito`, `Crédito` and `Saldo`.

## August 2026 inventory result

No workbook was found in `recebimentos/2026/082026/HM`. The most recent HM
workbook located was a July backup in a technical migration directory. It is
not a safe August template: its BTG sheet has only date, description, credit,
and a source-mapping formula. It lacks debit and balance and feeds legacy
source/de-para formulas.

Classification:

- BTG sheet layout/formulas: `UNKNOWN_REVIEW` for the new bank-audit contract.
- `fontes`, `catalogos`, `de_para_*`: `STRUCTURAL_KEEP` pending a dedicated
  migration design; they are not cleared or edited by this bootstrap.
- July bank rows and catalog values: `MONTHLY_CLEAR` only in a future staging
  migration explicitly approved after formula-impact validation.

Consequently V1 returns `REVIEW`, creates no staging workbook, and sets
`SAFE_TO_CREATE_HM_MONTH_OFFICIAL=false`. This avoids carrying July source
mappings into August or losing BTG debit/balance provenance.
