"""Synthetic recovery rehearsal used only by validate_docker's disposable stack."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import tarfile


# Enumerate bytes, not just filenames; includes nested operational/audit examples.
MANIFEST = """
import hashlib, json
from pathlib import Path
root = Path('/data')
print(json.dumps({str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted(root.rglob('*')) if p.is_file()}, sort_keys=True))
"""

ARCHIVE = """
import sys, tarfile
def only_regular(member):
    if not (member.isfile() or member.isdir()):
        raise RuntimeError('Non-regular entry in synthetic data')
    return member
with tarfile.open(fileobj=sys.stdout.buffer, mode='w|gz') as archive:
    archive.add('/data', arcname='.', filter=only_regular)
"""

RESTORE = """
import sys, tarfile
from pathlib import Path
root = Path('/data')
if any(p.is_file() or p.is_symlink() for p in root.rglob('*')):
    raise RuntimeError('Restore requires an empty synthetic destination')
with tarfile.open(fileobj=sys.stdin.buffer, mode='r|gz') as archive:
    archive.extractall(root, filter='data')
"""


def validate_recovery(*, run, compose, project: str, temporary: Path,
                      root: Path, env_file: Path) -> None:
    """Back up a quiescent synthetic stack and restore into separate fresh volumes."""
    restore_project = project + '-restore'
    restore_override = temporary / 'restore.yaml'
    restore_override.write_text('services:\n  app:\n    image: ' + project + '-app:latest\n')
    # Replace only the known project argument, retaining the no-ports override.
    restore = list(compose)
    restore[restore.index('-p') + 1] = restore_project
    restore += ['-f', str(restore_override)]
    app = compose + ['exec', '-T', 'app']
    run(app + ['python', '-c', "from pathlib import Path; "
               "p=Path('/data/months/synthetic'); p.mkdir(); "
               "(p/'statement.bin').write_bytes(bytes(range(256))); "
               "Path('/data/technical/audit.txt').write_text('synthetic-audit-only')"])
    expected = json.loads(run(app + ['python', '-c', MANIFEST],
                              capture_output=True, text=True).stdout)
    # No application writers while taking the DB and filesystem snapshots.
    run(compose + ['stop', 'app'])
    backup_dir = temporary / 'backups'
    run([sys.executable, str(root / 'scripts/backup_postgres.py'),
         '--compose-file', str(root / 'compose.yaml'), '--env-file', str(env_file),
         '--project', project, '--destination', str(backup_dir)])
    dumps = list(backup_dir.glob('muv-postgres-*.dump'))
    if len(dumps) != 1:
        raise RuntimeError('Expected one synthetic database backup.')
    archive = backup_dir / 'app-data.tar.gz'
    with archive.open('xb') as output:
        archive.chmod(0o600)
        run(compose + ['run', '--rm', '--no-deps', '-T', 'app',
                       'python', '-c', ARCHIVE], stdout=output)
    # Check that the archive itself contains all expected bytes before restoring.
    with tarfile.open(archive, 'r:gz') as saved:
        actual = {}
        for member in saved:
            if member.isfile():
                stream = saved.extractfile(member)
                actual[str(Path(member.name))] = hashlib.sha256(stream.read()).hexdigest()
        if actual != expected:
            raise RuntimeError('Synthetic file backup does not match the source.')
    try:
        run(restore + ['up', '-d', '--wait', '--wait-timeout', '180', 'postgres'])
        # New PostgreSQL volume: restoring cannot overwrite the original database.
        sql = restore + ['exec', '-T', 'postgres', 'psql', '-U', 'muv_synthetic',
                         '-d', 'muv_synthetic', '-v', 'ON_ERROR_STOP=1']
        empty = run(sql + ['-Atc', "SELECT count(*) FROM pg_tables WHERE schemaname='public'"],
                    capture_output=True, text=True)
        if empty.stdout.strip() != '0':
            raise RuntimeError('Synthetic restore database must be empty.')
        with dumps[0].open('rb') as source:
            run(restore + ['exec', '-T', 'postgres', 'pg_restore', '-U', 'muv_synthetic',
                           '-d', 'muv_synthetic', '--exit-on-error', '--single-transaction',
                           '--no-owner', '--no-privileges'], stdin=source)
        with archive.open('rb') as source:
            run(restore + ['run', '--rm', '--no-deps', '-T', 'app',
                           'python', '-c', RESTORE], stdin=source)
        run(restore + ['up', '-d', '--no-build', '--wait', '--wait-timeout', '180'])
        restored_app = restore + ['exec', '-T', 'app']
        run(restored_app + ['python', '-m', 'container_runtime', 'health'])
        restored = json.loads(run(restored_app + ['python', '-c', MANIFEST],
                                  capture_output=True, text=True).stdout)
        row = run(sql + ['-Atc', 'SELECT value FROM synthetic_probe'],
                  capture_output=True, text=True).stdout.strip()
        if restored != expected or row != 'synthetic-only':
            raise RuntimeError('Synthetic recovery verification failed.')
        # The restore must refuse to overwrite an already populated destination.
        with archive.open('rb') as source:
            result = run(restore + ['exec', '-T', 'app', 'python', '-c', RESTORE],
                         stdin=source, check=False, capture_output=True)
        if result.returncode == 0:
            raise RuntimeError('Restore unexpectedly accepted a nonempty destination.')
        print('PASS: PostgreSQL backup/restore, file hashes, restored app health and overwrite refusal.',
              flush=True)
    finally:
        run(restore + ['down', '--volumes', '--remove-orphans'])
