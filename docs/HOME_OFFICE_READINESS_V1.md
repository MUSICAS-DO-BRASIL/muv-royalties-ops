# Portabilidade e home office V1 — validação macOS

> Relatório histórico do checkpoint V1. A remoção do identificador no checkout
> foi tratada posteriormente na [V1.1](HOME_OFFICE_READINESS_V1_1.md); as ressalvas
> abaixo descrevem o estado anterior. O parser Safra segue ausente.

## Resultado

**REVIEW**. Um clone novo permite instalar dependências, executar a suíte
multiplataforma, importar os módulos disponíveis e iniciar a UI sem dados
operacionais. A aprovação integral permanece pendente: falta o parser PDF Safra
e há identificador bancário fixo no baseline. Não houve alteração da validação
financeira BTG nem criação de substituto para Excel.

Ambiente: macOS 26.6.2, arm64, Python 3.14.7, Git 2.50.1 (Apple Git-155).
Clone HTTPS do repositório oficial na branch inicial `main`, HEAD
`680696f1325df9003d614819e45b205c8913fc7c`, igual ao baseline informado.
As alterações foram feitas apenas em `chore/home-office-readiness-v1`.

## Inventário e classificação

| Componentes versionados | Plataforma | Docker |
| --- | --- | --- |
| Extração bancária: modelos, contexto, status, staging | CROSS_PLATFORM | DOCKER_READY para desenvolvimento sintético |
| Parser/adapter BTG e validação Decimal | CROSS_PLATFORM | DOCKER_READY; mapping externo para fluxo integrado |
| Classificador Safra | CROSS_PLATFORM | DOCKER_READY; mapping externo |
| Parser PDF Safra referenciado, ausente | UNKNOWN | NEEDS_WORK |
| Domínio de preparação mensal e inspeção openpyxl | CROSS_PLATFORM | DOCKER_READY para domínio/inspeção |
| Recalcular/reabrir com Excel COM | WINDOWS_ONLY | WINDOWS_HOST_REQUIRED |
| Atributos de arquivos via API Windows | WINDOWS_ONLY, com guarda de plataforma | WINDOWS_HOST_REQUIRED para esse diagnóstico |
| Publicador local e política de publicação Graph | CROSS_PLATFORM | NEEDS_WORK para operação corporativa |
| OneDrive/SharePoint sync e transporte Graph autorizado | CORPORATE_ENVIRONMENT_ONLY | NEEDS_WORK |
| UI Streamlit V2 vazia | CROSS_PLATFORM | DOCKER_READY para smoke test |
| Exemplo de configuração FUSION | CROSS_PLATFORM como JSON; automação não versionada | NEEDS_WORK |
| Credential Manager e browser com perfil corporativo | UNKNOWN: não há implementação no clone | Sem componente disponível para avaliar |

`DOCKER_READY` é avaliação de arquitetura, não execução Linux comprovada.
O transporte Graph é um protocolo injetável; `graph_auth_available()` permanece
falso. Instalar MSAL sozinho não o implementa nem autoriza acesso.

## Dependências e ambiente

- Antes: nenhum manifesto reproduzível; status inicial FAIL.
- Depois: `requirements.txt`, `requirements-dev.txt` e dependências opcionais em
  `requirements-windows.txt`. Pytest não integra runtime.
- Dependências diretas validadas: openpyxl 3.1.5, pdfplumber 0.11.10,
  Streamlit 1.63.0, pytest 9.1.1.
- `constraints-macos-py314.txt` registra versões transitivas do ambiente validado.
  Não é lock multiplataforma; Windows/Linux ainda precisam de execução própria.
- `.venv` criada no clone e ignorada por `.gitignore`; nenhuma instalação global.
- Instalação concluída sem erros; `pip check`: sem requisitos quebrados.
- Imports históricos de scripts resolvidos pela configuração pytest/PYTHONPATH,
  sem converter o projeto em pacote para esta validação.

## Arquivos externos e imports

`MUV_OPERATIONAL_ROOT` configura os meses; `MUV_TEMPLATE_ROOT` configura os
templates HM/MDB. `MUV_BTG_SOURCE_MAP` e `MUV_SAFRA_SOURCE_MAP` configuram os
mappings. Defaults anteriores preservados. Definir variáveis antes do processo.

O bootstrap HM anterior já recebe raiz e candidatos de template por argumento;
a criação de staging continua deliberadamente não implementada nesse bootstrap.
A preparação genérica mantém a exigência de Excel nativo e publicação create-only.

Imports em processos Python novos: PASS para bank extraction, BTG parser/adapter,
classificador Safra, month preparation, HM bootstrap, publicadores e app V2.
**CORE_IMPORT_STATUS = REVIEW** no escopo completo solicitado: o classificador
Safra passa, mas `mdb/process_safra_mp_toyalties.py` não existe no Git. Importar
a fachada não demonstra disponibilidade do parser carregado dinamicamente.
Nenhum ImportError foi convertido em skip.

## Testes e UI

- `python -m pytest -q`: **65 passed, 1 skipped**, mais 1 subteste aprovado.
- O único skip é o teste de atributos nativos Windows, marcado `windows_only`.
- Nenhum teste COM foi executado ou removido. O guard de plataforma é testado;
  doubles de validador nos testes de domínio não são validação de Excel real.
- Testes antes dependentes de workbook HM passam a usar workbook sintético
  temporário; nenhum teste consulta a raiz corporativa.
- Os casos de classificação Safra usam mapping temporário exclusivo do teste,
  não pretendem homologar o mapping de produção ausente.
- Integração Streamlit corrigida para o arquivo V2 existente e valores sintéticos.
- AppTest vazio e cenários de contexto preparado: PASS.
- Servidor Streamlit restrito a `127.0.0.1`, raízes temporárias vazias,
  health check HTTP 200: PASS. Processo encerrado depois da verificação.
- `python -m compileall -q recebimentos` e `git diff --check`: PASS.

## Auditoria de caminhos

Busca nos arquivos versionados por `C:\`, `C:/`, caminhos pessoais, Downloads,
OneDrive, Hurst Capital, AppData e `%APPDATA%` (sem dependências da `.venv`).

| Ocorrência no baseline/código | Classificação | Decisão |
| --- | --- | --- |
| `tests/test_month_preparation.py:43`, `C:/temp-root` | TEST_FIXTURE | Apenas composição de Path; sem acesso ao local |
| `tests/test_cloud_native_workbook_publisher.py:29`, `C:/synced/book.xlsx` | TEST_FIXTURE | Recebido pelo FakeGraph, sem acesso ao caminho |
| `btg/README_BTG_HM_ADAPTER_V1.md:60–61`, exemplos `C:\caminho` | DOCUMENTATION | Exemplos fictícios |
| `cloud_aware_workbook_publisher.py:101–104,145`, OneDrive/SharePoint | WINDOWS_ONLY_INTENTIONAL / DOCUMENTATION | Strings para identificar provider, não diretório pessoal |
| `bank_extraction_core.py`, raiz e mapping relativo | DEFAULT_CONFIG | Agora configuráveis por variáveis de ambiente |
| `month_preparation.py`, templates relativos | DEFAULT_CONFIG | Agora configuráveis por variável/argumento |
| `mdb/safra_royalties_classifier.py`, mapping relativo | DEFAULT_CONFIG | Agora configurável por variável/argumento |

Não foram encontrados HARD_CODED_RUNTIME_PATH absolutos pessoais no core.
Não há referências executáveis a Credential Manager, registry ou `os.startfile`.
`ctypes.windll` já está protegido por `os.name`; `win32com` é importado somente
na função Windows, agora com recusa explícita antes do import no Mac.

## Segurança: ressalva obrigatória

Nenhum XLSX/PDF/CSV operacional versionado ou gerado dentro do clone fora da
`.venv`. Não foram baixados ou copiados workbooks, extratos ou documentos oficiais.
Busca por arquivos de credencial, chaves privadas, tokens GitHub/AWS e
atribuições de senha/segredo: sem achados. Esta auditoria cobre o checkout e a
alteração, não certifica todo o histórico ou infraestrutura remota.

**Não é correto declarar SENSITIVE_FINDINGS = [].** O parser BTG contém
identificador bancário fixo em `btg/btg_statement_parser.py:24,125`, também
referenciado por uma fixture em `btg/tests/test_btg_statement_parser.py:13`.
O valor não é repetido neste relatório. O código de identidade financeira foi
preservado. Valores textuais de testes no baseline têm proveniência não
comprovada; nos testes de contexto alterados foram substituídos por valores
sintéticos simples, e documentos bancários nos casos Safra por um número fictício.

- SENSITIVE_FINDINGS: identificador bancário fixo herdado e fixture correspondente.
- REAL_FINANCIAL_DATA: possível identificador bancário real herdado; origem dos
  valores textuais do baseline não atestada. Nenhuma transação real foi carregada.
- OFFICIAL_DOCUMENTS: [].
- CREDENTIALS: [].

Essas ressalvas impedem aprovação integral de sanitização. Mudanças novas não
introduzem dados operacionais, segredos ou valores de configuração pessoais.

## Teste de notebook novo

| Etapa efetivamente executada neste Mac | Resultado |
| --- | --- |
| Clone HTTPS em pasta sem código prévio | PASS |
| Branch de trabalho separada da main | PASS |
| Criar `.venv` e instalar dependências declaradas | PASS |
| Pytest com fixtures sintéticas | PASS: 65 aprovados, 1 skip Windows |
| Imports de módulos disponíveis em processos novos | PASS |
| Disponibilidade do parser PDF Safra completo | REVIEW: arquivo ausente |
| UI vazia: AppTest e servidor HTTP local | PASS |
| Ausência integral de identificadores financeiros no código | REVIEW |

## Docker e cloud: avaliação apenas

WOULD_DOCKER_MATERIALLY_IMPROVE_REPRODUCIBILITY = true.
Um container Linux fixaria a versão Python, as bibliotecas nativas e a base do
sistema operacional para CI/core/UI. O snapshot pip atual fixa pacotes, mas não
a base do sistema. Docker não fornece o parser Safra ausente, mappings,
templates homologados, credenciais nem Excel COM. Nenhum Dockerfile foi criado.

CLOUD_READINESS = REVIEW. Core/domínio/Streamlit são candidatos a Linux container
em AWS, Azure ou GCP, sem preferência de provedor demonstrada por este teste.
Bloqueios concretos: parser Safra ausente; configuração externa de mappings e
templates; validação final dependente de host Windows/Excel; transporte Graph
sem implementação autenticada; dependência de filesystem para meses/publicação;
identificador bancário fixo no código. Ainda faltam testes Linux, armazenamento
persistente e integração de identidade/segredos adequados à execução remota.
Não foi iniciada migração, publicação de site nem execução cloud.

## Limite da aprovação

O desenvolvimento e os testes sintéticos funcionam neste Mac. Pelo critério
integral que exige também sanitização sem achados e todos os parsers presentes,
`SAFE_FOR_HOME_OFFICE_DEVELOPMENT = false` até resolver as ressalvas.
Commit/push e o checkpoint final com hashes são registrados no encerramento da
validação; nenhuma alteração ou merge na main faz parte deste trabalho.
