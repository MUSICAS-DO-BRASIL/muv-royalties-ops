# MUV Royalties Ops — Streamlit Operator UI V1

## Propósito

Interface interna para operadores consultarem e conduzirem a competência mensal de HM e MDB. A V1 apresenta contexto, recebimentos, conciliação, revisão humana, controles de fechamento e auditoria sem transferir regras financeiras para componentes Streamlit.

## Arquitetura

`recebimentos/process_extrato/streamlit_ops_app.py` contém a composição visual. O pacote `ops_ui` separa contexto, view models, contrato de dados e adaptadores. A competência padrão usa `month_preparation.default_competence`; a preparação usa `MonthPreparationAdapter`, que delega a descoberta a `MonthPreparationService` e não recria workbook, validações ou regras HM/MDB.

O contrato `OpsDataProvider` define os dados necessários para as seis páginas. `DemoOpsDataProvider` contém somente valores sintéticos identificados na interface. Um provider LIVE futuro deve implementar o contrato usando serviços e repositórios existentes, mantendo dados de origem, auditoria e reconciliação no backend.

## Executar em DEMO

Na raiz do worktree, com as dependências instaladas:

```powershell
python -m streamlit run recebimentos/process_extrato/streamlit_ops_app.py --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

DEMO é o padrão. O badge `DEMO` identifica os dados sintéticos e nenhuma ação executa portais, lê credenciais ou persiste decisão humana.

## Contrato LIVE e segurança

`MUV_OPS_MODE=LIVE` não usa dados demonstrativos. Como ainda não há provider LIVE homologado, a aplicação mostra erro operacional e para — comportamento fail-closed. A futura implementação precisa conectar o provider a serviços auditados e expor somente detalhes seguros.

SOCINPRO permanece desabilitado: `SOCINPRO_REAL_EXECUTION_ENABLED=false`. Esta V1 não chama automação de navegador, não acessa portal e não lê credenciais. O adaptador de preparação também é somente de descoberta até receber um resultado bancário validado pelo backend; assim preserva criação exclusiva e não sobrescreve workbook.

Fechamento/publicação fica bloqueado até a existência de serviço de fechamento auditado. Diferenças financeiras permanecem visíveis; o banco é apresentado como a verdade primária de caixa e a interface não corrige valores.

## Páginas

- **Visão Geral:** indicadores da competência e fontes operacionais.
- **Recebimentos:** situação por fonte e descoberta segura da preparação mensal.
- **Conciliação:** totais bancário/documental, diferença, registros e pendências.
- **Revisão:** itens, evidência e ações desabilitadas sem persistência auditada.
- **Fechamento:** pré-requisitos e controle fail-closed.
- **Auditoria:** filtros de tipo, fonte e status com detalhes seguros.

## Próximos passos de integração

1. Implementar `OpsDataProvider` LIVE contra os serviços PostgreSQL/auditoria existentes, sem misturar dados sintéticos.
2. Fornecer adaptador que receba apenas resultado bancário previamente validado para habilitar `prepare_month` com o serviço existente.
3. Conectar revisão e fechamento somente às operações auditadas e idempotentes do backend.
4. Quando houver API dedicada, manter `ops_ui` como camada de apresentação e trocar o provider; isso permite futura migração de frontend sem replicar regras de negócio.
