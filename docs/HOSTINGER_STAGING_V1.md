# Hostinger Staging Readiness V1

This is preparation only. CTO approval is recorded; no purchase, provisioning,
connection to Hostinger, cloud resources, certificates or deployment occurred.
Planning envelope: one Linux VPS, 4 vCPU / 16 GB RAM / 200 GB NVMe. These numbers
are not runtime assumptions; capacity and target CPU architecture need validation.

## Deployment contract

`deploy/compose.staging.yaml` is standalone; local `compose.yaml` stays unchanged.
It starts exactly app + PostgreSQL, with restart `unless-stopped`, real health
checks and persistent named volumes. App uses a previously validated immutable
image reference in MUV_APP_IMAGE. PostgreSQL retains the pinned image digest.
Keep the Compose project name stable across updates to retain the same volumes.

App is UID 10001, root filesystem read-only, tmpfs for temporary files, all Linux
capabilities dropped and no-new-privileges enabled. No privileged mode or Docker
socket mount. PostgreSQL uses the official initialization/user model and persistent
storage; it has no published port. Its network is internal. App also has a frontend
network, but publishes its HTTP port only on host loopback for the host proxy.

Copy `deploy/staging.env.example` outside Git. Supply it with `--env-file`, using
owner-only permissions and a restricted service administrator. Do not print resolved
Compose config; use `config --quiet`. Do not commit actual values or bake them into
images. Environment secrets can be read by Docker administrators: restrict membership
in the docker group and access to external configuration.

| Configuration | Contract |
|---|---|
| APP_ENV | staging, descriptive deployment environment |
| APP_PORT | Host loopback HTTP port; container remains 8501 |
| MUV_APP_IMAGE | Validated digest or immutable commit-tagged image |
| DB_HOST / DB_PORT | Compose DNS postgres / 5432 for this topology |
| DB_NAME / DB_USER / DB_PASSWORD | External, mandatory; no password default |
| MUV_CONFIG_DIR | Existing absolute host directory of approved config/mappings; read-only mount /data/config |
| MUV_CREDENTIALS_DIR | Existing absolute host directory; read-only mount /run/muv-credentials |
| MUV_OPERATIONAL_ROOT | Default /data/months; overrides must stay on persistent storage |
| MUV_TEMPLATE_ROOT | Default /data/templates; overrides must stay on persistent storage |
| BACKUP_RETENTION_DAYS | Host backup utility default 14; explicit CLI option preferred in scheduler |
| BACKUP_UPLOAD_EXECUTABLE | Optional trusted absolute executable, no provider selected |

Config and credential bind mounts refuse nonexistent source directories. Host
permissions must allow UID 10001 to read files without making them world-readable.
The directories may remain empty for the synthetic UI/database smoke test.
Template/config changes are external operations, not image rebuilds.

## Secrets and SOCINPRO boundary

Database credentials live only in external protected environment/configuration.
The current app has no intrinsic application authentication secret. For staging,
restrict access at the reverse proxy (credentials/hash supplied separately) until
application authentication is designed. HTTPS without access control is insufficient
for controlled financial data.

HM credential path: /run/muv-credentials/credenciais_hurst.xlsx.
MDB credential path: /run/muv-credentials/credenciais_mdb.xlsx.
These resolve through their existing entity-specific MUV_SOCINPRO_*_CREDENTIALS_PATH
variables. Never place these files in the repository or image. Mount only the
entity runtime sources; LOGINS.xlsx is GLOBAL_MASTER_REFERENCE and is not required
by portal preflight or container startup. Secrets are not generated in these assets.
Mapping files are external, separate from credentials, mounted read-only.

Portable parsing/reconciliation, UI, audit and configuration run in Linux. Excel
COM remains a transitional Windows-only backend; Linux rejects COM-required writes
explicitly without silently switching to openpyxl. No Excel or Wine in the design.

Browser automation is still independently validated: choose Linux browser container
only after real browser validation, or an external Windows-assisted worker when
CAPTCHA/MFA/session constraints require it. No worker, browser profile or credential
is added here. CAPTCHA/MFA remains human-led, and no current app startup invokes it.

## Persistence and backup

| Lifetime | Contents / location |
|---|---|
| Ephemeral | Container writable layers, /tmp, caches and regenerable staging |
| Persistent | PostgreSQL postgres_data volume; app_data /data, operational artifacts, required audit/state |
| External / backup | Protected DB archives and independently retained important application artifacts |

Do not put durable audit output in /tmp. Pass /data/technical to existing audit APIs.
The database probe is SELECT 1 only: production financial persistence/schema and
migrations do not exist. No automatic destructive migration is introduced.

`scripts/backup_postgres.py` produces a timestamped UTC `.dump` in PostgreSQL's
compressed custom format. It uses the running PostgreSQL service/client version,
writes a private temporary file, validates its archive directory with pg_restore,
then publishes it atomically as mode 0600. Failures exit nonzero with sanitized
messages. Retention deletes only old matching archives after successful validation
(and successful upload if configured); failed runs retain older backups.
Use a dedicated protected backup directory, one scheduler job, and failure monitoring.

Example future daily host schedule at 03:00 (host timezone; not installed here):

```cron
0 3 * * * cd /opt/muv && /usr/bin/python3 scripts/backup_postgres.py --compose-file deploy/compose.staging.yaml --env-file /etc/muv/staging.env --project muv-staging --destination /srv/muv-backups --retention-days 14
```

Paths above are deployment conventions, not personal paths. Cron does not import
BACKUP_RETENTION_DAYS/UPLOAD from Compose's env file; pass CLI options or configure
the scheduler environment explicitly. A local successful dump is not proof of an
off-server backup. Define and test a trusted upload adapter later: it receives the
completed dump path as its sole argument, takes provider credentials externally,
returns nonzero on failure and must not log secrets. No shell evaluation is used.

EXTERNAL_BACKUP_TARGET = UNCONFIGURED_BY_DESIGN. Hostinger storage, S3-compatible
storage or another organization-approved target are options, not selected providers.
Decide retention, encryption, access and restore retrieval before real staging.
App artifacts/audit need a separate consistent filesystem backup/export procedure;
this script backs up one database, not app volumes, cluster roles or tablespaces.
Daily logical backup is V1 coverage, not point-in-time recovery/high availability.

## Restore procedure

Only restore a trusted verified archive. First restore to a NEW disposable database
on an isolated test stack, never directly over the live database. Example using
external `RESTORE_DB`, set to a new approved test name, and `BACKUP_FILE`:

```sh
docker compose --env-file /etc/muv/staging.env -f deploy/compose.staging.yaml -p muv-staging exec -T postgres sh -c 'exec createdb -U "$POSTGRES_USER" "$1"' restore "$RESTORE_DB"
docker compose --env-file /etc/muv/staging.env -f deploy/compose.staging.yaml -p muv-staging exec -T postgres sh -c 'exec pg_restore -U "$POSTGRES_USER" -d "$1" --exit-on-error --single-transaction --no-owner --no-privileges' restore "$RESTORE_DB" < "$BACKUP_FILE"
```

Check schema/counts/known synthetic markers, application connectivity and archive
integrity; record result and duration. Production role/ownership restoration needs
an explicit plan. No --clean, DROP, TRUNCATE or DELETE is part of this procedure.
Switching a live app to a restored database requires a separate approved recovery.

## HTTPS and firewall design

Select one host-level Caddy reverse proxy: simple certificate renewal and WebSocket
proxying without adding a proxy fleet. It will proxy an externally configured domain
to 127.0.0.1:APP_PORT. Its service configuration and authentication secret/hash live
outside Git. No actual hostname, IP, certificate or running proxy is configured now.
Future validation must include Streamlit WebSocket/session/upload behavior.

Public application access: HTTPS 443 only. Port 80 may be allowed strictly for ACME
validation and HTTPS redirection if that issuance method is selected. Otherwise use
a compatible 443/DNS challenge and keep 80 closed. Restrict SSH to approved admin
sources and key authentication, with a tested recovery path. Deny public 5432 and
8501. Account for Docker firewall forwarding rules: rely on no PostgreSQL port
publication and loopback-only app binding, and verify exposure from outside the VPS.
No firewall command was run on the Mac.

## Update, rollback and migration safety

From an approved GitHub commit: fetch/checkout the intended release, build/tag or
pull the validated image, record old/new immutable image IDs, back up state, change
external MUV_APP_IMAGE and run:

```sh
docker compose --env-file /etc/muv/staging.env -f deploy/compose.staging.yaml -p muv-staging config --quiet
docker compose --env-file /etc/muv/staging.env -f deploy/compose.staging.yaml -p muv-staging up -d --wait
docker compose --env-file /etc/muv/staging.env -f deploy/compose.staging.yaml -p muv-staging exec -T app python -m container_runtime health
```

Retain the previous image and deployment manifest. Roll back by restoring those
references and rerunning up/health/synthetic smoke without deleting volumes.
Do not use down --volumes on staging. Future schema changes must be versioned,
backed up as appropriate, explicitly reviewed and fail closed; app rollback is
safe only with a compatible schema. Destructive SQL needs explicit approval.

## Future staging checklist and acceptance

After purchase authorization, in order:

1. Provision VPS with approved OS/architecture/capacity.
2. Create restricted administrator.
3. Install approved SSH public keys; restrict access.
4. Update system.
5. Install supported Docker/Compose.
6. Configure and externally verify firewall.
7. Deploy approved repository/image release.
8. Supply external environment, secrets and permissions.
9. Start PostgreSQL; confirm health and persistence.
10. Start app.
11. Verify HTTP health and authenticated DB query.
12. Exercise backup and external transfer.
13. Restore into isolated database and validate contents.
14. Enable/validate HTTPS, access control and WebSockets.
15. Run synthetic smoke including Linux COM blocking.
16. Only then review controlled real-data use.

Required gates: SERVER_BASELINE, DOCKER_RUNTIME, POSTGRES_HEALTH, APP_HEALTH,
HTTPS, BACKUP, RESTORE_TEST, SYNTHETIC_SMOKE, SECURITY = PASS.
Only then may SAFE_FOR_CONTROLLED_REAL_STAGING=true. It is false today.

## Scope and evidence

Readiness means deployment assets and procedures, not an existing server. Local
synthetic runtime/backup/restore and host/container regression results are recorded
in the session checkpoint. Linux validation here is arm64; validate the future VPS
architecture separately. Provider selection and real credentials remain external.

HOSTINGER_APPROVED_BY_CTO = true
HOSTINGER_PURCHASED = false
HOSTINGER_PROVISIONED = false
HOSTINGER_DEPLOYMENT_EXECUTED = false
CLOUD_RESOURCES_CREATED = false

References: [Compose networking](https://docs.docker.com/compose/how-tos/networking/),
[Caddy HTTPS](https://caddyserver.com/docs/automatic-https),
[pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html).

Validation in this readiness round: 179 host tests and 179 Linux tests passed,
with one existing Windows-only skip in each suite; 49 Python files compiled.
Both Compose contracts validated. Local stack restart/persistence/health/imports
and explicit Linux COM rejection passed. A separate local staging stack produced
a compressed backup and restored its synthetic marker into a fresh database.
All temporary stacks/volumes were shut down; no actual provider target was used.
