# Recuperação sintética e imagens versionadas

## Executar no PC pessoal

Pré-requisitos: Python 3 e Docker Engine/Desktop iniciado com Compose 2.24+.
Na raiz do clone:

```sh
python3 scripts/validate_docker.py
```

O ensaio cria somente dados fictícios. Não carrega o `.env` local, não monta
pastas do PC e não publica portas. Cada execução recebe um nome aleatório.

1. Constrói e testa a imagem, inicia Streamlit/PostgreSQL e testa persistência.
2. Cria um registro SQL, arquivo binário e arquivo de auditoria sintéticos.
3. Para a aplicação para impedir escritas durante o snapshot coordenado.
4. Usa o utilitário existente `scripts/backup_postgres.py` para gerar e validar
   um dump no formato custom do PostgreSQL; arquiva todo o `/data` sintético.
5. Cria uma segunda stack, com outro banco e outro volume da aplicação.
6. Confirma que o destino está vazio, restaura o dump e o arquivo compactado.
7. Confere o registro SQL, hashes SHA-256 de todos os arquivos e saúde HTTP/SQL.
8. Verifica a recusa de uma segunda restauração sobre arquivos já existentes.
9. Remove as duas stacks, seus volumes e backups temporários.

O ensaio não apaga dados da stack original para simular perda: recupera em volumes
novos e independentes, que não têm acesso aos arquivos originais. O extrator usa
o filtro `data` do Python 3.14 dentro da imagem e só recebe arquivos produzidos
pelo próprio ensaio. Não é uma interface de restauração para arquivos arbitrários.

Interrupções normais acionam a limpeza em `finally`. Encerramento forçado do
processo ou indisponibilidade do Docker podem deixar recursos `muv-check-*`;
identifique a execução antes de removê-los. Não use limpeza global de volumes.

Esse teste comprova o mecanismo de recuperação com dados sintéticos. Para produção,
ainda é necessário definir agendamento, destino externo, retenção, criptografia,
alertas e recuperação das configurações/credenciais externas. O dump não cobre
roles de cluster ou tablespaces. A aplicação precisa permanecer sem escritores
durante o backup coordenado dos arquivos e banco. Não existe migração financeira
ou persistência financeira nova nesta alteração.

## Publicação no GitHub Container Registry

O workflow de validação exporta a imagem da aplicação somente após aprovação do
ensaio inteiro e verifica se o arquivo exportado pode ser carregado pelo Docker.
Em `main`, transfere esse arquivo ao job de publicação por um artifact com retenção
de um dia. Os arquivos de dados e backups temporários não entram nesse artifact.

O job `Publish validated image` depende dos testes Python e Docker. Ele carrega
e publica a imagem já testada, sem reconstrução, usando `GITHUB_TOKEN` com
`packages: write` apenas nesse job. Não requer PAT ou senha adicionada aos secrets.
As regras da organização ainda podem impedir a criação/publicação de packages;
o primeiro push efetivo verifica essa permissão. A visibilidade do package não
é alterada pelo workflow.

O job só executa em pushes ou execução manual da `main`; pull requests e branches
`ci/**` não publicam. A configuração deve ser integrada à `main` antes da primeira
publicação. Cada execução usa uma tag com SHA completo, ID e tentativa do workflow:

```text
ghcr.io/musicas-do-brasil/muv-royalties-ops:sha-<commit>-run-<execucao>-<tentativa>
```

As tags identificam a execução; a referência imutável é o digest `@sha256:...`,
registrado no resumo do job. Use essa referência em `MUV_APP_IMAGE` no ambiente
externo da Hostinger. O workflow não atualiza a VPS. Para voltar à versão anterior,
use o digest anterior, desde que os dados e o schema continuem compatíveis.

A imagem publicada pelo runner Ubuntu é `linux/amd64`. O ensaio local em Mac
Apple Silicon valida `linux/arm64`; publicar também arm64 exigirá um job nativo
equivalente antes de montar uma imagem multi-arquitetura.

Para testar localmente a exportação sem publicar:

```sh
python3 scripts/validate_docker.py --export-image /tmp/muv-validated-image.tar
```

O comando também cria `/tmp/muv-validated-image.tar.id`. Esses arquivos contêm
código proprietário e dependências; mantenha-os privados e remova-os quando não
forem mais necessários. Eles não são backups de documentos ou do banco.
