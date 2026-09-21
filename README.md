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

\`\`\`text
Fontes e arquivos externos
        ↓
Leitura e staging
        ↓
Validação e normalização
        ↓
Regras de negócio e reconciliação
        ↓
Planilhas operacionais e futura integração com PostgreSQL
\`\`\`

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
permissões de leitura e nenhum segredo corporativo. Após integração na `main`,
um job separado publica a mesma imagem validada no GitHub Container Registry,
somente se os dois jobs de testes passarem. Pull requests não publicam imagens.
Não há deploy automático na Hostinger. Resultados e referência da imagem ficam
na aba Actions. Veja [recuperação e publicação](docs/RECOVERY_AND_IMAGES.md).

## Segurança

Projeto interno e proprietário. O repositório não contém dados financeiros ou documentos operacionais de produção.

O controle de versão deve conter apenas código, documentação sanitizada, configurações de exemplo e fixtures sintéticas explicitamente aprovadas. Workbooks oficiais, extratos, documentos, logs operacionais, credenciais, sessões e dados de produção permanecem fora do Git.

## Estado atual

- Extração bancária HM V2: aprovada.
- Template canônico HM V1: aprovado.
- Suporte à criação mensal HM: disponível.
- Preparação genérica de mês: implementada.
- Testes relevantes: aprovados no marco de referência.
- Arquivos oficiais: preservados fora do controle de versão.

## Roadmap

1. Consolidar automações e validações por fonte.
2. Ampliar staging, proveniência, idempotência e reconciliação.
3. Executar Excel e PostgreSQL em paralelo quando houver base validada.
4. Evoluir para uma plataforma de dados centralizada de forma gradual e auditável.

## Ambiente de desenvolvimento e home office

### Requisitos e instalação

Git, acesso autorizado ao repositório e Python 3.14 (validado com 3.14.7 em
macOS arm64). Outros sistemas/versões precisam da própria validação.
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
mappings de produção. O parser PDF Safra `process_safra_mp_toyalties.py` também
está ausente: o classificador Safra é importável/testável, mas a extração PDF
Safra completa permanece pendente. A extração BTG completa requer mapping externo.

A preparação oficial exige validação Excel COM em Windows; no Mac retorna
`WINDOWS_EXCEL_REQUIRED`, sem criar substituto. Diagnóstico de atributos Windows
é isolado. Sincronização local e publicação OneDrive/SharePoint dependem do
ambiente corporativo; o transporte Graph precisa de implementação/autorização.
Não há integração Credential Manager nem automação de navegador versionada neste
clone. Credenciais, sessões corporativas e documentos operacionais ficam fora do Git.

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
README, fixtures ou arquivos versionados. Arquivos `.env` não são carregados
automaticamente. Configuração ausente/vazia/inválida bloqueia o parsing com
mensagem genérica; importar o core e abrir a UI vazia não exige conta configurada.
A identidade validada continua presente nos resultados técnicos locais, como
antes; esses resultados são operacionais e não devem entrar no Git.

A comparação exige a conta inteira, além da empresa e banco esperados.
Os testes usam somente `TEST_BANK_ACCOUNT_001` e variantes sintéticas.

`SAFRA_PARSER_STATUS = MISSING_FROM_CLEAN_REPOSITORY` e
`SAFRA_RECOVERY_REQUIRED_ON_WINDOWS = true`: recuperar e auditar no ambiente
Windows corporativo antes de habilitar esse fluxo. Nenhum parser foi recriado.

A sanitização V1.1 cobre o checkout atual. Commits anteriores ainda contêm o
identificador removido; o histórico não foi reescrito.
Consulte [a auditoria V1.1](docs/HOME_OFFICE_READINESS_V1_1.md) e
[o relatório histórico V1](docs/HOME_OFFICE_READINESS_V1.md).
