# Portability Fix V1

Base: `origin/main` em `ee9b61695f97cb77b82bbb98d996373937478278`.
Branch: `feat/linux-portability-v1`. Resultado: **PASS** para os quatro defeitos.

## Preservação e escopo

`main` local permanece em `680696f1325df9003d614819e45b205c8913fc7c`,
também preservado em `backup/mac-main-680696f`. A feature nasceu limpa de
origin/main. Não houve reset, rebase, merge, force, incorporação do commit local,
provisionamento, conexão a banco ou deploy Hostinger.

## Mudanças

- MDB usa ExcelComWorkbookBackend por padrão em todas as plataformas. O backend
  sintético exige injeção explícita. BankExtractionService aceita mdb_writer
  para manter os testes de integração sintéticos sem alterar defaults operacionais.
- UnsupportedWorkbookPlatformError bloqueia macOS/Linux antes dos imports COM.
  Em Windows, dispatch, escrita, recálculo e salvamento COM permanecem iguais.
- SOCINPRO resolve PDFs/XLSX por pathlib contra o cwd no momento da chamada,
  preservando referências explicitamente fornecidas. Nenhuma raiz pessoal foi adicionada.
- HM passa self._monthly_root ao bootstrap, respeitando env/default ou argumento.

## Validação

Python 3.14.7, macOS arm64. Ambiente do gate anterior, dependências oficiais;
pip check sem conflitos. Suíte: **151 passed, 0 failed, 1 skipped**.
Skip original: `test_windows_file_attribute_adapter`, `WINDOWS_ONLY: exige Windows`.
Gate adicional anterior, inalterado: **10 passed, 0 failed** (antes 5/5).
py_compile: **43 módulos PASS**. git diff --check: **PASS**.

Regressões incluem: backend padrão não modifica XLSX sem Windows, serviço MDB
não publica nem modifica template, erro antes do import COM em darwin/linux,
PDF/XLSX relativos e absolutos com espaços/Unicode, raiz HM usada pelo bootstrap,
saída sintética HM sob raiz explícita e dispatch/save Windows com doubles COM.
Imports em processos novos cobrem core, bancos, SOCINPRO, preparação e abstrações MDB.
Os testes existentes de escrita sintética agora injetam seu backend explicitamente;
asserções de integridade e bloqueio foram mantidas.

`HM_OUTPUT_CREATED_UNDER_SUPPLIED_ROOT=true` refere-se ao teste sintético de
MonthPreparationService com validador injetado. BankExtractionService usa o
bootstrap HM de descoberta: ele respeita a raiz, mas continua retornando REVIEW
sem criar workbook quando falta template. Nenhum gravador novo foi implementado.

`WINDOWS_PRODUCTION_DESIGN_PRESERVED=true` é revisão de código e teste com doubles;
Excel nativo Windows não foi executado. Linux real/container também não foi executado.

## Pendências fora desta rodada

PostgreSQL runtime não implementado; configuração portátil NOT_IMPLEMENTED.
Próximo mínimo: contrato externo de conexão, driver/repositório, schema/migrations
necessários e testes isolados de integração. Sem credenciais ou provisionamento.

Docker CLI 29.6.2 instalado, daemon indisponível; Dockerfile ausente; build NOT_RUN.
É seguro começar Containerization V1 como trabalho de definição/build/testes Linux,
não como autorização de deploy ou afirmação de prontidão operacional completa.

Auditoria de diff e arquivos de código/config/testes do worktree: SENSITIVE_FINDINGS=[].
Fixtures são sintéticas; nenhum PDF/XLSX real, mapping real, .env, cookie, perfil de
navegador ou credencial adicionado. Ambientes locais/caches não entram no commit.
O histórico antigo não é certificado como sanitizado (limite já documentado na V1.1).

## Commit local preservado (inspeção read-only)

LOCAL_ONLY_COMMIT_SUBJECT = feat: establish royalties operations platform baseline

LOCAL_ONLY_COMMIT_ALREADY_PRESENT_UPSTREAM = false

O commit não é ancestral de origin/main nem tem patch equivalente em git cherry.
Seus 28 caminhos estão presentes no upstream; 19 blobs são idênticos e 9 diferem.
Isso não justifica incorporar a baseline antiga. Nenhum conteúdo financeiro antigo
foi extraído para este relatório. LOCAL_ONLY_COMMIT_FILES:

- `.gitignore`
- `README.md`
- `recebimentos/conciliacao/DIGITAL_obras/utilizados/FUSION/automacao_fusion/config_empresas.example.json`
- `recebimentos/process_extrato/bank_extraction_app_v2.py`
- `recebimentos/process_extrato/bank_extraction_context.py`
- `recebimentos/process_extrato/bank_extraction_core.py`
- `recebimentos/process_extrato/bank_extraction_month_context.py`
- `recebimentos/process_extrato/bank_extraction_status.py`
- `recebimentos/process_extrato/bank_extraction_ui.py`
- `recebimentos/process_extrato/btg/README_BTG_HM_ADAPTER_V1.md`
- `recebimentos/process_extrato/btg/README_HM_MONTH_BOOTSTRAP_V1.md`
- `recebimentos/process_extrato/btg/btg_bank_adapter.py`
- `recebimentos/process_extrato/btg/btg_statement_parser.py`
- `recebimentos/process_extrato/btg/hm_month_bootstrap.py`
- `recebimentos/process_extrato/btg/hm_structural_migration.py`
- `recebimentos/process_extrato/btg/tests/test_btg_statement_parser.py`
- `recebimentos/process_extrato/btg/tests/test_hm_month_bootstrap.py`
- `recebimentos/process_extrato/btg/tests/test_hm_structural_migration.py`
- `recebimentos/process_extrato/cloud_aware_workbook_publisher.py`
- `recebimentos/process_extrato/cloud_native_workbook_publisher.py`
- `recebimentos/process_extrato/mdb/safra_royalties_classifier.py`
- `recebimentos/process_extrato/mdb/test_safra_royalties_classifier.py`
- `recebimentos/process_extrato/month_preparation.py`
- `recebimentos/process_extrato/tests/test_bank_extraction_core.py`
- `recebimentos/process_extrato/tests/test_bank_extraction_month_context_integration.py`
- `recebimentos/process_extrato/tests/test_cloud_aware_workbook_publisher.py`
- `recebimentos/process_extrato/tests/test_cloud_native_workbook_publisher.py`
- `recebimentos/process_extrato/tests/test_month_preparation.py`

## Checkpoint de validação

```json
{
  "PORTABILITY_FIX_V1_STATUS": "PASS",
  "BACKUP_BRANCH_CREATED": true,
  "BACKUP_BRANCH_HEAD": "680696f1325df9003d614819e45b205c8913fc7c",
  "PORTABILITY_BRANCH_CREATED": true,
  "PORTABILITY_BRANCH_BASE": "ee9b61695f97cb77b82bbb98d996373937478278",
  "BRANCH_BASE": "ee9b61695f97cb77b82bbb98d996373937478278",
  "CURRENT_BRANCH": "feat/linux-portability-v1",
  "WORKTREE_CLEAN_AFTER_PREPARATION": true,
  "SAFE_TO_CONTINUE_PORTABILITY_FIX": true,
  "MDB_OPERATIONAL_OPENPYXL_FALLBACK": false,
  "OPERATIONAL_OPENPYXL_FALLBACK": false,
  "NON_WINDOWS_MDB_OPERATIONAL_WRITE": "EXPLICITLY_BLOCKED",
  "SYNTHETIC_OPENPYXL_BACKEND": "SUPPORTED",
  "COM_PLATFORM_CHECK_EXPLICIT": true,
  "COM_UNAVAILABLE_FAILS_CLOSED": true,
  "COM_IMPORT_ISOLATED": true,
  "SOCINPRO_ABSOLUTE_PDF_PATH": "PASS",
  "SOCINPRO_RELATIVE_PDF_PATH": "PASS",
  "SOCINPRO_ABSOLUTE_XLSX_PATH": "PASS",
  "SOCINPRO_RELATIVE_XLSX_PATH": "PASS",
  "HM_EXPLICIT_MONTHLY_ROOT_RESPECTED": true,
  "HM_OUTPUT_CREATED_UNDER_SUPPLIED_ROOT": true,
  "NO_WINDOWS_PATH_REQUIRED": true,
  "NON_WINDOWS_IMPORT_GATE": "PASS",
  "PORTABILITY_GATE_TESTS_PASSED": 10,
  "PORTABILITY_GATE_TESTS_FAILED": 0,
  "GLOBAL_TEST_SUITE": "PASS",
  "TESTS_PASSED": 151,
  "TESTS_FAILED": 0,
  "TESTS_SKIPPED": 1,
  "SKIP_REASON": "WINDOWS_ONLY: exige Windows",
  "PY_COMPILE": "PASS",
  "GIT_DIFF_CHECK": "PASS",
  "WINDOWS_PRODUCTION_DESIGN_PRESERVED": true,
  "POSTGRES_RUNTIME_IMPLEMENTED": false,
  "POSTGRES_PORTABLE_CONFIG": "NOT_IMPLEMENTED",
  "DOCKER_AVAILABLE": true,
  "DOCKER_DAEMON_AVAILABLE": false,
  "DOCKERFILE_FOUND": false,
  "DOCKER_BUILD": "NOT_RUN",
  "SENSITIVE_FINDINGS": [],
  "SAFE_TO_START_CONTAINERIZATION_V1": true,
  "HOSTINGER_DEPLOYMENT_EXECUTED": false,
  "LOCAL_ONLY_COMMIT_SUBJECT": "feat: establish royalties operations platform baseline",
  "LOCAL_ONLY_COMMIT_ALREADY_PRESENT_UPSTREAM": false
}
```

Hash do commit e resultado do push são registrados no checkpoint externo ao commit.
