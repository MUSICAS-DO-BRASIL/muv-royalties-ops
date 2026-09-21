# MUV Royalties Ops

Projeto interno para apoiar a operação de royalties da MUV, com automações de leitura, preparação, validação e conciliação de informações operacionais.

## Objetivo

Organizar processos de recebimentos e preparação mensal, preservando a operação atual baseada em arquivos e planilhas enquanto as regras passam a ser reproduzíveis em código. O foco é aumentar rastreabilidade, consistência, validação e capacidade de reconciliação.

## Escopo operacional

- Fluxos de HM e MDB, incluindo preparação mensal e suporte à criação de competências.
- Processamento de extratos e conciliação para os bancos BTG e Safra.
- Automações específicas por fonte pagadora, sociedade ou canal de recebimento.
- Estruturas de staging, validação e normalização que preparam a evolução gradual para o modelo canônico MUV.

## Arquitetura

```text
Fontes e arquivos externos
        ↓
Leitura e staging
        ↓
Validação e normalização
        ↓
Regras de negócio e reconciliação
        ↓
Planilhas operacionais e futura integração com PostgreSQL
```

Planilhas continuam sendo uma interface operacional e de consumo. Dados de origem, transformações e resultados devem permanecer rastreáveis, e regras críticas não devem depender somente de fórmulas.

## Execução local

Cada automação possui dependências e instruções próprias em seu diretório. Em geral, é necessário criar um ambiente Python local, instalar os requisitos do fluxo desejado e fornecer os arquivos operacionais fora do repositório.

Nunca inclua documentos de produção, credenciais ou dados financeiros reais em comandos, configurações ou commits.

## Testes

Os testes automatizados estão próximos aos respectivos fluxos. Antes de alterações, execute a compilação Python e os testes relevantes ao módulo modificado.

### Validação Docker e GitHub Actions

Com Python 3 e Docker Engine/Desktop iniciado, use Docker Compose 2.24 ou mais
recente e execute na raiz do clone:

```sh
python3 scripts/validate_docker.py
```

O comando constrói a imagem de testes e a imagem da aplicação, executa a suíte
sintética no container sem rede e inicia uma stack temporária com PostgreSQL.
Verifica saúde HTTP/SQL, configuração sintética BTG e persistência dos arquivos
e do banco após recriar os containers. Não lê o `.env` local, não publica portas,
não acessa portais corporativos e não exige documentos ou credenciais reais.
Depois pausa a aplicação sintética, usa `backup_postgres.py` para gerar um dump,
arquiva `/data` e restaura ambos em uma segunda stack com volumes novos. Compara
o registro SQL, hashes de todos os arquivos e a saúde da aplicação restaurada;
também verifica que uma restauração recusa um destino já preenchido.
Ao terminar, remove somente os containers, volumes e imagens temporários da
própria execução; as imagens-base e o cache de build podem permanecer no Docker.
Os backups sintéticos também são apagados ao final. Não configura backup periódico
ou externo de produção e não substitui Excel COM ou homologação operacional.

O workflow `.github/workflows/validation.yml` executa testes Python e essa mesma
validação Docker em Linux nos pull requests e pushes em `main`/`ci/**`.
Também permite execução manual quando estiver na branch padrão. Os testes usam
permissões de leitura e nenhum segredo corporativo. Em pushes ou execução manual
na `main`, um job separado publica a mesma imagem validada no GitHub Container Registry,
somente se os dois jobs de testes passarem. Pull requests não publicam imagens.
Não há deploy automático na Hostinger. Resultados e referência da imagem ficam
na aba Actions. Veja [recuperação e publicação](docs/RECOVERY_AND_IMAGES.md).

## Entrada, resultados e histórico

| Tipo | Destino e comportamento |
|---|---|
| Upload bancário | Cópia em pasta temporária exclusiva. O nome deve ser apenas um nome de PDF, sem caminho; arquivos existentes não são substituídos. A cópia é removida ao terminar, inclusive em caso de erro. |
| Extrato bancário para download | Gerado em memória; o navegador salva onde o operador escolher. Não cria automaticamente um arquivo permanente no servidor. |
| Conciliação mensal | `MUV_OPERATIONAL_ROOT/AAAA/MMAAAA/ENTIDADE/`. A preparação cria um arquivo novo e preserva o existente; etapas COM exigem Windows. |
| Demonstrativo SOCINPRO | Subpasta `SOCINPRO` da entidade/competência. Repetição equivalente preserva o arquivo; conteúdo divergente bloqueia a publicação. |
| Auditoria SOCINPRO | `technical_root/socinpro_entidade_AAAAMM_<id>/audit.json`, um diretório por publicação. A pasta técnica deve estar fora de toda a raiz operacional. No Docker, use armazenamento persistente, por exemplo `/data/technical`. |

As rotinas não movem nem apagam os documentos originais do operador. Os uploads
bancários não são um arquivo histórico permanente: mantenha os originais em seu
local operacional autorizado. Auditorias mensais antigas em JSON são preservadas;
novas publicações não as substituem. Consumidores externos do histórico devem
considerar os novos subdiretórios, além dos arquivos legados existentes.

Se o demonstrativo for salvo e a gravação da auditoria falhar, a publicação informa
`AUDITORIA_SOCINPRO_FALHOU:DEMONSTRATIVO_PRESERVADO`. Corrija a pasta técnica e
repita a publicação; o demonstrativo equivalente é preservado. Isso não cria uma
transação única entre workbook e auditoria. A interface bancária continua exibindo
erros de processamento ao operador; um histórico persistente de todas as falhas
bancárias ainda não está implementado.

## Segurança

Projeto interno e proprietário. O repositório não contém dados financeiros ou documentos operacionais de produção.

O controle de versão deve conter apenas código, documentação sanitizada, configurações de exemplo e fixtures sintéticas explicitamente aprovadas. Workbooks oficiais, extratos, documentos, logs operacionais, credenciais, sessões e dados de produção permanecem fora do Git.

## Estado atual

Marco verificado em **21/09/2026**, no commit `35faa7b`:

- [PR #1](https://github.com/MUSICAS-DO-BRASIL/muv-royalties-ops/pull/1)
  integrado à `main`: validação Docker, recuperação sintética e publicação de imagens.
- **227 testes aprovados e 1 skip exclusivo de Windows** em cada suíte Python e
  Docker do [workflow de referência](https://github.com/MUSICAS-DO-BRASIL/muv-royalties-ops/actions/runs/35642447257).
- Build, saúde Streamlit/PostgreSQL, persistência após recriar containers e
  recuperação em volumes novos aprovados; arquivos restaurados conferidos por hash.
- Primeira imagem `linux/amd64` publicada no GitHub Container Registry.
- Extração bancária HM V2 e template HM V1 mantêm os marcos anteriores de aprovação;
  preparação oficial de mês e gravações via Excel COM continuam exigindo Windows.
- Parser PDF Safra e adaptador de navegador SOCINPRO presentes no código;
  existência do código e testes sintéticos não comprovam homologação operacional.
- PostgreSQL disponível na infraestrutura, com verificação `SELECT 1`;
  schema e persistência financeira ainda não implementados.
- Deploy na Hostinger e backup periódico externo de produção ainda pendentes.
  Documentos oficiais, mappings e credenciais permanecem fora do Git e da imagem.

### Imagem publicada e uso futuro na Hostinger

A primeira imagem validada pode ser referenciada no arquivo de configuração
externo utilizado por `deploy/compose.staging.yaml`:

```dotenv
MUV_APP_IMAGE=ghcr.io/musicas-do-brasil/muv-royalties-ops@sha256:8d2bb7457cdabd3711729ed06ef9e2ecb3df0c82187b5d45595d78b36607f805
```

Esse digest identifica o marco acima, não uma tag móvel de versão mais recente.
Publicações posteriores aparecem no resumo de cada execução da
[aba Actions](https://github.com/MUSICAS-DO-BRASIL/muv-royalties-ops/actions/workflows/validation.yml).
Use o digest da versão escolhida e confirme a arquitetura da VPS: a publicação
atual é `linux/amd64`; o Docker local no Mac também foi validado em `linux/arm64`.
O servidor precisa de acesso de leitura ao package para baixar uma imagem privada.

Publicar a imagem não implanta a aplicação. Antes de operar na Hostinger, configure
acesso ao registry, variáveis externas, volumes, templates/mappings, HTTPS,
autenticação e backups externos. Consulte o [plano de staging](docs/HOSTINGER_STAGING_V1.md)
e os [limites da recuperação e publicação](docs/RECOVERY_AND_IMAGES.md).

## Roadmap

1. Habilitar proteção da `main` com os checks obrigatórios quando o plano do
   GitHub permitir esse recurso no repositório privado. Em 21/09/2026, as APIs
   de proteção/rulesets retornaram HTTP 403 por limitação de plano; nenhuma regra
   foi ativada e a visibilidade do repositório foi preservada. Até lá, usar PRs e
   conferir `Python synthetic tests` e `Docker tests and recovery` antes de integrar.
2. Definir backup externo, agendamento, retenção e alertas de falha para produção.
3. Implantar staging na Hostinger com acesso protegido e dados fictícios.
4. Preparar e validar Playwright/Chromium em ambiente próprio para SOCINPRO,
   mantendo as etapas de Excel COM no Windows enquanto forem necessárias.
5. Consolidar validações por fonte, proveniência, idempotência e reconciliação;
   implementar persistência financeira no PostgreSQL quando houver base validada.

## Ambiente de desenvolvimento e home office

### Requisitos e instalação

Git, acesso autorizado ao repositório e Python 3.14 (validado com 3.14.7 em
macOS arm64). A suíte também foi validada em Linux arm64 no Docker local e Linux
amd64 no GitHub Actions. Windows/Excel COM e outras versões precisam da própria validação.
Na raiz de um clone novo:

```sh
git clone https://github.com/MUSICAS-DO-BRASIL/muv-royalties-ops.git
cd muv-royalties-ops
git switch -c chore/meu-teste-local
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest
python -m compileall -q recebimentos
git diff --check
```

No PowerShell, use `python -m venv .venv` e `.venv\Scripts\Activate.ps1`.
Não instale pacotes globalmente. `.venv` está ignorado no Git.
`requirements.txt` declara runtime; `requirements-dev.txt` acrescenta pytest.
Os scripts ainda não são um pacote instalável: `pyproject.toml` configura pytest.
Para repetir as versões transitivas validadas no Mac/Python 3.14, instale com:

```sh
python -m pip install -r requirements-dev.txt -c constraints-macos-py314.txt
```

Esse snapshot não é um lock universal para Linux/Windows. Apenas em uma estação
Windows com Excel desktop, instale também `requirements-windows.txt` para COM.
MSAL não é necessário para o core: o transporte Graph autenticado não está
implementado neste clone.

### Dependências fixadas para Linux

`constraints-linux-py314.txt` fixa as versões diretas e transitivas do ambiente
Linux/Python 3.14 de runtime e testes. O Dockerfile aplica esse arquivo nos dois
estágios de instalação, e o job Python do GitHub usa as mesmas restrições:

```sh
python -m pip install -r requirements-dev.txt -r requirements-container.txt -c constraints-linux-py314.txt
python -m pip check
```

Use esse comando em um ambiente virtual Linux. O arquivo é passado com `-c`,
não `-r`: pytest e outras dependências exclusivas de testes não entram na imagem
de runtime só por constarem no snapshot. O Mac mantém seu arquivo de constraints
próprio; Windows/COM e Playwright não estão cobertos pelo snapshot Linux.

Ao atualizar dependências, altere os requisitos diretos quando necessário,
resolva as versões em uma imagem Linux limpa e atualize o snapshot em um PR.
Valide o build, `pip check`, a suíte e o ensaio de recuperação antes de integrar.
Não gere esse arquivo com `pip freeze` do ambiente pessoal macOS ou de um ambiente
com pacotes alheios ao projeto. Versões fixadas reduzem mudanças inesperadas;
esse snapshot não contém hashes de pacotes nem garante imagens idênticas byte a
byte. As imagens-base continuam fixadas por digest no Dockerfile/Compose.

### Testes e aplicação local

`python -m pytest` roda testes com dados sintéticos em diretórios temporários,
incluindo UI via `AppTest`; não requer workbooks oficiais, credenciais ou rede
corporativa. O marcador `windows_only` gera skip explícito fora do Windows.
`corporate_environment` fica sempre desabilitado nesta suíte sintética.
Os doubles do validador Excel e do Graph existem apenas nos testes e não
comprovam validação nativa nem publicação corporativa. Não há teste que abra COM.

```sh
python -m streamlit run recebimentos/process_extrato/bank_extraction_app_v2.py \
  --server.address 127.0.0.1 --server.headless true --browser.gatherUsageStats false
```

Abra a URL local exibida. Para smoke test, deixe o upload vazio; não carregue
extratos ou workbooks reais. Para importar os módulos diretamente no terminal:

```sh
export PYTHONPATH="recebimentos/process_extrato:recebimentos/process_extrato/btg:recebimentos/process_extrato/mdb"
python -c "import bank_extraction_core, btg_statement_parser, safra_royalties_classifier, month_preparation"
```

O `PYTHONPATH` acima usa o separador macOS/Linux; no PowerShell use `;`.
O pytest configura os diretórios automaticamente.

### Arquivos externos e limites

Defina as variáveis **antes de iniciar o Python**, apontando para diretórios
externos ao clone. Exemplos fictícios para macOS/Linux:

```sh
export MUV_OPERATIONAL_ROOT="$HOME/muv-exemplo/meses"
export MUV_TEMPLATE_ROOT="$HOME/muv-exemplo/templates"
export MUV_BTG_SOURCE_MAP="$HOME/muv-exemplo/mappings/btg.json"
export MUV_SAFRA_SOURCE_MAP="$HOME/muv-exemplo/mappings/safra.json"
```

Nenhum desses comandos cria ou baixa dados. Sem configuração, os defaults
históricos continuam sendo `recebimentos/`, `process_extrato/templates/` e os
mappings junto aos módulos BTG/Safra. Não coloque dados reais nesses defaults.
Os serviços de preparação também aceitam raízes por argumento.

- HM: `Conciliação - Hurst Music_TEMPLATE_V1.xlsx` em `MUV_TEMPLATE_ROOT`.
- MDB: `Conciliação - Músicas do Brasil_TEMPLATE_V1.xlsx` na mesma raiz.
- Mapping BTG: JSON com `aliases`, `description_raw` e `canonical_royalty_source`.
- Mapping Safra: JSON com `aliases`, `bank_payor_alias` e `canonical_royalty_source`.
- O bootstrap HM anterior aceita `monthly_root` e `template_candidates`
  explicitamente e não implementa o gravador de staging.

Templates homologados e mappings aprovados **não vêm do GitHub**. Não invente
mappings de produção. O parser PDF Safra está versionado em
`recebimentos/process_extrato/mdb/process_safra_mp_toyalties.py` e é carregado pelo
core bancário. Os testes cobrem cenários sintéticos; o fluxo operacional depende
de arquivos e mappings aprovados. A extração BTG completa também requer mapping externo.

A preparação oficial exige validação Excel COM em Windows; no Mac retorna
`WINDOWS_EXCEL_REQUIRED`, sem criar substituto. Diagnóstico de atributos Windows
é isolado. Sincronização local e publicação OneDrive/SharePoint dependem do
ambiente corporativo; o transporte Graph precisa de implementação/autorização.
Não há integração Credential Manager. A automação de navegador SOCINPRO está
versionada em `recebimentos/process_extrato/socinpro/portal/`, com adaptador
Playwright e executor assistido `smoke_runner.py`. As dependências são opcionais
e estão no `requirements.txt` desse diretório; Playwright e Chromium não fazem
parte da imagem Docker atual. O executor usa navegador com interface gráfica;
CAPTCHA/MFA exigem intervenção humana. Credenciais, sessões corporativas e
documentos operacionais ficam fora do Git. A suíte sintética não acessa o portal real.

### Conta de investimento BTG: configuração obrigatória

O identificador da conta foi removido do código e das fixtures na V1.1.
A camada `btg/bank_account_config.py` lê `MUV_BANK_ACCOUNT_ID` a cada parsing,
sem default operacional. Exemplo **exclusivamente sintético**:

```sh
export MUV_BANK_ACCOUNT_ID="TEST_BANK_ACCOUNT_001"
```

Em operação autorizada, forneça a conta esperada por configuração externa ao
Git. Preserve zeros à esquerda; não use espaços. São aceitos caracteres ASCII
alfanuméricos, `_` e `-`. Não registre o valor em logs, comandos compartilhados,
README, fixtures ou arquivos versionados. O Python não carrega arquivos `.env`
automaticamente. No Docker Compose, os manifests repassam `MUV_BANK_ACCOUNT_ID`
ao container a partir da configuração externa; o `.env.example` local contém
somente um identificador sintético. Configuração ausente/vazia/inválida bloqueia o parsing com
mensagem genérica; importar o core e abrir a UI vazia não exige conta configurada.
A identidade validada continua presente nos resultados técnicos locais, como
antes; esses resultados são operacionais e não devem entrar no Git.

A comparação exige a conta inteira, além da empresa e banco esperados.
Os testes usam somente `TEST_BANK_ACCOUNT_001` e variantes sintéticas.

Os relatórios históricos V1/V1.1 registram o parser Safra como ausente naquele
marco. Esse diagnóstico não descreve o checkout atual, que já contém o parser.
As exigências de validação operacional e de Excel COM continuam aplicáveis.

A sanitização V1.1 cobre o checkout atual. Commits anteriores ainda contêm o
identificador removido; o histórico não foi reescrito.
Consulte [a auditoria V1.1](docs/HOME_OFFICE_READINESS_V1_1.md) e
[o relatório histórico V1](docs/HOME_OFFICE_READINESS_V1.md).
