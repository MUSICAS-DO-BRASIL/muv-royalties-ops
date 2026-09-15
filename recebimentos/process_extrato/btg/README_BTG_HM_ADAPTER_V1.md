# BTG HM Bank Adapter V1

Core reutilizável para extratos da conta de investimento HM no BTG (`208`).
Ele não grava em workbooks oficiais de conciliação e não substitui a automação
das associações: produz somente o extrato bancário normalizado e uma visão
operacional de créditos.

## Interfaces

- `parse_btg_statement(pdf_path)`: movimentos normalizados, sem cabeçalhos,
  saldos inicial/final ou totais artificiais.
- `parse_btg_statement_details(pdf_path)`: movimentos e metadados financeiros
  para validação/auditoria.
- `validate_btg_statement(details)`: valida cada variação de saldo e o
  fechamento global, sempre com `Decimal`.
- `build_btg_royalty_extract(transactions)`: créditos operacionais candidatos;
  não realiza mapeamento de fonte, associação ou deal.
- `run_btg_month(entity="HM", period="YYYY-MM", input_pdf=..., output_root=...)`:
  produz `operational/` e `technical/` abaixo do diretório explicitamente
  informado pelo chamador.

O PDF é bloqueado se não identificar simultaneamente a empresa HM, banco 208
BTG Pactual e conta configurada. Os logs/erros não exibem o número da conta.

## Contrato de dados

Cada movimento preserva `description_raw`, arquivo de origem, página e linha.
O valor canônico é `Decimal`, com `direction` (`CREDIT`/`DEBIT`) e
`operational_credit_candidate`. Débitos ficam na saída técnica para auditoria
e validação, mas não entram no XLSX operacional.

O JSON técnico é uma artefato de staging local, contém dados bancários e é
ignorado pelo Git. O PDF real é usado apenas localmente, nunca copiado.

## Legado auditado

| Arquivo | Classificação | Motivo |
| --- | --- | --- |
| `1.0_process_extrato.py` | `DIAGNOSTIC_ONLY` | Imprime texto de páginas e ignora a primeira; possui path absoluto. |
| `2.0_process_extrato.py` | `SUPERSEDED` | Extrator de PDF único com `float`, saldo inferido e path absoluto. |
| `3.0_process_extrato.py` | `SUPERSEDED` | Versão mais recente do fluxo legado, mas mistura XLSXs individuais e consolidado em `s_extrato`. |
| `1.0_xlsx_p_royalties.py` | `SUPERSEDED` | Exige exatamente um XLSX na pasta, incompatível com a saída do script 3; possui paths absolutos. |

Nenhum arquivo legado foi removido ou modificado.

## Execução de teste

```powershell
python -m unittest discover -s tests -v
```

Para criar uma saída de staging, defina um `output_root` novo e explícito:

```python
from btg_bank_adapter import run_btg_month

run_btg_month(
    entity="HM",
    period="2026-08",
    input_pdf=r"C:\caminho\extrato.pdf",
    output_root=r"C:\caminho\staging_btg_2026_08",
)
```
