# Containerization V1 — local synthetic foundation

Portability V1 was integrated by a normal fast-forward push: remote main moved
from `ee9b616` to `e245d29`. This branch starts at `e245d29`.
Local main and `backup/mac-main-680696f` remain at `680696f`.

## Architecture and inventory

Compose has exactly two services: `app` (Streamlit, port 8501) and `postgres`
(PostgreSQL 18). No public database port, workers, proxy, or cloud resources.
The app port binds only to host loopback. The runtime uses UID/GID 10001, a
read-only root filesystem, writable temporary storage, and a named data volume.

- Selected UI: `recebimentos/process_extrato/bank_extraction_app_v2.py`.
- Additional existing UI: `recebimentos/process_extrato/socinpro_operator_app_v1.py`.
  It is not started as a second Compose service.
- API entrypoint: **none**; Streamlit's health route is not a financial API.
- Portable: financial core/Decimal, BTG/Safra parsers and classifiers, SOCINPRO
  ingestion/reconciliation/catalog mapping, audit, month discovery and configuration.
- Windows only: native Excel validation and operational MDB COM workbook writes.
  Windows entrypoints remain unchanged. No Excel, Wine, GUI or pywin32 in the image.
- PostgreSQL before this branch: no runtime or production schema. This branch adds
  only connection configuration and a read-only `SELECT 1` readiness probe.
  Financial persistence and production schema remain **unimplemented**.

The optional `container_runtime` module checks database connectivity before
replacing itself with Streamlit via exec. Health checks repeat the authenticated
query and verify HTTP 200 / `ok` from Streamlit `/_stcore/health`. A connection,
query or HTTP failure is unhealthy, with a generic error that omits credentials.
PostgreSQL has its own `pg_isready` check. Neither check creates tables or records.

## External configuration

Copy `.env.example` to ignored `.env` and fill `DB_PASSWORD` with a fresh local-only
password. Do not commit `.env`. The example intentionally has no usable password;
Compose rejects missing/empty required values. Do not reuse production credentials.

| Variable | Local stack value / contract |
|---|---|
| DB_HOST | `postgres` (Compose service DNS, not localhost) |
| DB_PORT | `5432`; integer 1–65535 |
| DB_NAME | `muv_synthetic` |
| DB_USER | `muv_synthetic` |
| DB_PASSWORD | External, required, never baked into the image |

DB_HOST/DB_PORT select the application connection target; they do not change
PostgreSQL's internal listening port. The local recipe expects postgres:5432.
The image's bootstrap DB user has elevated privileges: this is a local synthetic
setup, not the production role/permission design. Environment credentials may be
visible to local Docker administrators; avoid printing resolved Compose config.
Changing initialization variables does not change users in an existing DB volume.

Compose maps PostgreSQL storage to `postgres_data:/var/lib/postgresql`, the
PostgreSQL 18 volume layout. The app's `app_data:/data` contains months, templates,
config and technical folders. Paths are supplied through MUV_OPERATIONAL_ROOT,
MUV_TEMPLATE_ROOT and the existing mapping environment variables. No templates,
mappings or financial files are bundled. Empty UI startup needs none of them.
For synthetic parser experiments only, inject synthetic account/mapping values;
missing mappings and account config retain their existing blocking behavior.

## Local startup and verification (requires a running Docker daemon)

From the repository root, after configuring `.env`:

```sh
docker compose config --quiet
docker compose build
docker compose up -d --wait
docker compose ps
docker compose exec app python -m container_runtime check-db
docker compose exec app python -m container_runtime health
docker compose exec app python -c "import bank_extraction_core, btg_statement_parser, process_safra_mp_toyalties, socinpro.real_ingestion, month_preparation, mdb_safra_worksheet_writer"
```

Open http://127.0.0.1:8501 with uploads empty. Use only synthetic fixtures.
The checks must succeed before claiming app-to-database connectivity.
Stop with `docker compose down`; named volumes remain. Do not remove volumes
unless their synthetic contents can be discarded.

Portable tests inside the image (test target adds pytest, default app does not):

```sh
docker build --target test -t muv-royalties-test .
docker run --rm muv-royalties-test
```

Host tests, using an activated project virtual environment:

```sh
python -m pip install -r requirements-dev.txt -r requirements-container.txt
python -m pytest
python -m compileall -q recebimentos
git diff --check
```

## Build and security boundaries

Linux Python and PostgreSQL image references are pinned to multi-architecture
manifest digests obtained from the official registry. Direct project requirements
and psycopg binary 3.3.5 are pinned. Transitive Python dependencies are not fully
locked; the Mac-only constraints file is deliberately not reused as a Linux lock.
A validated Linux dependency lock and scheduled image refresh remain future work.

`.dockerignore` denies all files by default, then permits build manifests and
Python sources under process_extrato, with explicit exclusions for secrets,
profiles, data, caches, virtual environments and operational files. No `COPY . .`,
no Git history, `.env`, JSON mappings, PDF/XLSX or host bind mounts. Review any new
Python source before building; an allowlist cannot detect secrets embedded in code.
Source tests remain in the runtime source tree but pytest is only in the test target.

## Validation observed on macOS

- Final portability acceptance: **151 passed, 0 failed, 1 skipped**; 43 modules compiled.
- Containerization host suite: **169 passed, 0 failed, 1 skipped**; 45 modules compiled.
- Skip: `test_windows_file_attribute_adapter` — `WINDOWS_ONLY: exige Windows`.
- Docker Compose static config: PASS with synthetic external values; missing password
  rejected; database port unexposed; health dependencies and volume target verified.
- Registry manifests inspected; Dockerfile/digests/context/diff reviewed; pip check PASS.
- SENSITIVE_FINDINGS = [] in reviewed worktree/diff/context sources. No real documents,
  mappings, credentials, browser profiles or financial records introduced.
- Docker CLI available; **daemon unavailable**. Build, Compose up, container tests,
  app startup and live PostgreSQL connectivity are all **NOT_RUN**.
- Tests use driver/HTTP doubles to validate errors, SQL, secret redaction, startup
  blocking and exec arguments. These are not evidence of actual DB connectivity.
- Windows design and Linux COM rejection retained; no native Windows COM run.

Static/host acceptance: **PASS**. Overall container runtime acceptance: **REVIEW**
until an actual build and synthetic stack checks pass. This is a committed local
foundation, not a deployment-ready certification.

## Future Hostinger path

First execute build, portable tests and Compose health/connectivity on Linux;
review architecture support and dependency locking. Then define production roles,
secrets handling, volumes/backups and authenticated/TLS access for a staging design.
Do not expose the current local recipe directly to the internet. No production
royalties schema is invented here; persistence requires a separately reviewed scope.
SAFE_TO_PLAN_HOSTINGER_STAGING = false pending runtime evidence.

HOSTINGER_PURCHASED = false
HOSTINGER_DEPLOYMENT_EXECUTED = false
CLOUD_RESOURCES_CREATED = false

Reference contracts: [Compose startup ordering](https://docs.docker.com/compose/how-tos/startup-order/),
[Streamlit Docker health route](https://docs.streamlit.io/deploy/tutorials/docker),
[official PostgreSQL image](https://hub.docker.com/_/postgres),
[Psycopg installation](https://www.psycopg.org/psycopg3/docs/basic/install.html).
