# Home office V1.1 — sanitização do identificador bancário

## Resultado e escopo

HOME_OFFICE_V1_1_STATUS = PASS para a remoção do hardcode no checkout atual.
Branch: `chore/home-office-readiness-v1`; base da rodada:
`fa59fc15677fcddf81e5fa907ac53de8276ae243`.

A prontidão operacional completa continua em REVIEW por causa do parser Safra.
O escopo desta rodada é configuração de conta e testes, sem alterar regras de
cálculo, reconstruir Safra, acessar dados reais, executar COM ou modificar main.

## Ocorrências originais (valor omitido)

Linhas referentes à base da rodada, antes das alterações:

| FILE | LINE | PURPOSE | RUNTIME_OR_TEST | REQUIRED_FOR_BUSINESS_VALIDATION | SENSITIVE_OR_OPERATIONAL | CAN_BE_EXTERNALIZED |
| --- | --- | --- | --- | --- | --- | --- |
| `recebimentos/process_extrato/btg/btg_statement_parser.py` | 24 | Constante da conta esperada e metadados de saída | RUNTIME | true: identidade e rastreabilidade | true | true: provider central |
| `recebimentos/process_extrato/btg/btg_statement_parser.py` | 125 | Comparar conta do cabeçalho com conta autorizada | RUNTIME | true: rejeitar conta divergente | true | true: comparação com configuração |
| `recebimentos/process_extrato/btg/tests/test_btg_statement_parser.py` | 13 | Default da fixture de extrato | TEST | false para o valor operacional; teste de identidade continua necessário | true: literal herdado | true: substituído por identificador sintético |

Tipo: **INVESTMENT_ACCOUNT**. Não é agência, CPF, CNPJ nem código de banco.
Além dessas três ocorrências literais, a constante alimentava a identidade e
cada transação normalizada. Essas referências agora usam a conta efetivamente
configurada e validada, sem mudar o contrato de metadados de saída.

## Implementação e rigor preservado

- `btg/bank_account_config.py` centraliza a leitura de `MUV_BANK_ACCOUNT_ID`.
- `BankAccountConfig` não tem default operacional; não lê ambiente no import.
- Campo oculto no repr da configuração; mensagens de erro não interpolam a conta.
- Identificador deve ser não vazio e conter apenas letras ASCII, dígitos, `_`, `-`.
  O valor é tratado como texto, sem conversão numérica ou remoção de zeros.
- O parser lê a configuração a cada parsing. Ausência ou conteúdo inválido gera
  `StatementBlockedError` genérico, sem fallback para a conta anterior.
- Comparação da conta inteira, sem aceitar prefixos. Cabeçalhos de conta
  conflitantes também bloqueiam o documento.
- Empresa e banco continuam obrigatórios. Nenhuma conta é inferida do PDF para
  configurar a expectativa: a fonte autorizadora é externa ao documento.
- Cálculos Decimal, variações de saldo, fechamento, créditos/débitos, bootstrap
  HM e preparação mensal foram preservados.
- `account_ref` nos resultados técnicos continua contendo a identidade validada.
  Esses resultados são dados operacionais locais; não são logs nem arquivos Git.

A fixture usa `TEST_BANK_ACCOUNT_001`. O teste de conversão monetária com valor
herdado de origem não comprovada passou a usar uma sequência didática sintética,
preservando separadores de milhar/decimal, tamanho e precisão da asserção.

## Busca ampla no checkout

Inspeção dos arquivos versionados e novos da alteração; excluídos `.git`, `.venv`
e caches. O valor antigo foi lido em memória da base somente para busca exata,
sem imprimi-lo ou copiá-lo para relatórios. Zero ocorrências após a alteração.

| Finding/categoria | Localização | Classificação e decisão |
| --- | --- | --- |
| Identificador de investimento original | Três locais acima | SENSITIVE_OR_OPERATIONAL, resolvido no checkout |
| Identificadores `TEST_BANK_ACCOUNT_*` | Fixture, provider tests, conftest e README | TEST_FIXTURE / DOCUMENTATION; claramente sintéticos |
| Código de banco BTG e razão social HM | Parser BTG, fixture e documentação | BUSINESS_VALIDATION: seletores explícitos do domínio, mantidos; não são conta, agência ou transação |
| Nomes de entidades HM/MDB e nomes canônicos de workbooks | Core, preparação, UI e testes | BUSINESS_CONSTANT: contratos de seleção/nomeação; nenhum workbook real acompanha o código |
| Nomes de fontes pagadoras, aliases e códigos de bancos | Testes do classificador Safra | TEST_FIXTURE: mapping temporário construído no teste; não é homologação nem arquivo de mapping operacional |
| Número de documento nos casos Safra | Testes do classificador Safra | TEST_FIXTURE: número fictício uniforme definido na V1 |
| Saldos, totais e créditos em fixtures | Testes BTG/HM/preparação/UI | TEST_FIXTURE: sequência aritmética sintética e valores construídos em memória; nenhum extrato carregado |
| Sequência didática de conversão monetária | `btg/tests/test_btg_statement_parser.py` | TEST_FIXTURE: substituição sintética explícita nesta rodada |
| CNPJ_EXEMPLO e nomes Empresa/Fonte Exemplo | `config_empresas.example.json` | DEFAULT_CONFIG: placeholders textuais, não CNPJs reais |
| CPFs/CNPJs formatados, e-mails e IDs numéricos de 9–14 dígitos | Busca em todo o checkout | Nenhuma ocorrência encontrada |
| Agência bancária, conta operacional adicional | Busca textual de conta/agência/identidade e revisão dos candidatos | Nenhuma ocorrência identificada |
| Datas, versões de dependências, hashes e coordenadas de células | Código, testes, manifests e relatórios | METADATA / TEST_FIXTURE: não classificados automaticamente como dado financeiro |
| Chaves, tokens, senhas atribuídas e arquivos de credenciais | Busca por padrões e extensões | Nenhum achado |
| XLSX/PDF/CSV e documentos operacionais | Lista de arquivos versionados/novos e checkout fora do ambiente | Nenhum arquivo encontrado |

SENSITIVE_FINDINGS = [] no checkout auditado.
REAL_FINANCIAL_DATA = []: sem identificador operacional literal remanescente ou
registros/documentos financeiros reais identificados no checkout.
OFFICIAL_DOCUMENTS = []. CREDENTIALS = [].

**Limite histórico:** os commits anteriores continuam contendo o identificador
removido. Não foi feita reescrita/expurgo de histórico; o PASS acima não certifica
sanitização do histórico Git, forks, caches ou cópias externas. Nenhum valor
operacional novo foi inserido em arquivos, testes, exemplos, logs ou relatórios.

## Evidências de validação

- Pytest: **81 passed, 1 skipped**, mais 1 subteste aprovado.
- Skip explícito: teste de atributos Windows, incompatível com macOS.
- Testes novos: conta esperada passa e chega aos metadados; conta diferente ou
  prefixo falha; ausência/configuração inválida bloqueia; mudanças de configuração
  são respeitadas; repr/erros não expõem o valor; empresa/banco permanecem
  obrigatórios; cabeçalhos conflitantes bloqueiam.
- `py_compile` dos 27 arquivos Python: PASS.
- Imports BTG/core/preparação/app em processo novo sem `MUV_BANK_ACCOUNT_ID`: PASS.
- AppTest Streamlit vazio, sem conta configurada e com raízes temporárias vazias:
  PASS; sem exceção e botão de processamento desabilitado.
- `git diff --check`: PASS.

## Pendência Safra

SAFRA_PARSER_STATUS = MISSING_FROM_CLEAN_REPOSITORY

SAFRA_RECOVERY_REQUIRED_ON_WINDOWS = true

Recuperar e auditar o parser no ambiente Windows corporativo. Nenhum parser novo,
fonte não auditada ou mock de produção foi criado. Nenhum teste foi removido.

## Checkpoint funcional

BANK_IDENTIFIER_HARDCODE_REMOVED = true

BUSINESS_VALIDATION_PRESERVED = true

PRODUCTION_CONFIGURATION_EXTERNALIZED = true

SYNTHETIC_TEST_IDENTIFIERS = true

MAIN_MODIFIED = false

SAFE_TO_CONTINUE_WINDOWS_RECOVERY_TOMORROW = true

Commit/push desta rodada são registrados no checkpoint de encerramento.
