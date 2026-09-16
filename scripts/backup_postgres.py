"""Host-side compressed PostgreSQL backup; no provider selected and no secrets logged."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time


class BackupError(RuntimeError):
    pass


def backup(*, compose_file: Path, env_file: Path, project: str, destination: Path,
           retention_days: int = 14, upload_executable: str | None = None) -> Path:
    if retention_days < 1:
        raise BackupError('Retention must be at least one day.')
    if upload_executable and not Path(upload_executable).is_absolute():
        raise BackupError('Upload executable must be an absolute path.')
    destination.mkdir(parents=True, exist_ok=True, mode=0o700)
    compose = ['docker', 'compose', '--env-file', str(env_file.resolve()),
               '-f', str(compose_file.resolve()), '-p', project, 'exec', '-T', 'postgres']
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    target = destination / f'muv-postgres-{stamp}.dump'
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination, prefix='.muv-backup-', delete=False) as output:
            temporary = Path(output.name)
            result = subprocess.run(compose + ['sh', '-c',
                'exec pg_dump --username="$POSTGRES_USER" --dbname="$POSTGRES_DB" --format=custom'],
                stdout=output, stderr=subprocess.DEVNULL, timeout=3600)
            output.flush(); os.fsync(output.fileno())
        if result.returncode or temporary.stat().st_size == 0:
            raise BackupError('PostgreSQL backup failed; existing backups retained.')
        with temporary.open('rb') as source:
            check = subprocess.run(compose + ['pg_restore', '--list'], stdin=source,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if check.returncode:
            raise BackupError('Archive validation failed; existing backups retained.')
        temporary.replace(target)
        if upload_executable:
            result = subprocess.run([upload_executable, str(target.resolve())],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3600)
            if result.returncode:
                raise BackupError('External backup failed; local backups retained.')
        cutoff = time.time() - retention_days * 86400
        for old in destination.iterdir():
            if (re.fullmatch(r'muv-postgres-\d{8}T\d{12}Z\.dump', old.name)
                    and not old.is_symlink() and old.is_file() and old != target
                    and old.stat().st_mtime < cutoff):
                old.unlink()
        return target
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compose-file', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--project', required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--retention-days', type=int, default=int(os.environ.get('BACKUP_RETENTION_DAYS', '14')))
    parser.add_argument('--upload-executable', default=os.environ.get('BACKUP_UPLOAD_EXECUTABLE') or None)
    args = parser.parse_args(argv)
    try:
        path = backup(compose_file=args.compose_file, env_file=args.env_file, project=args.project,
                      destination=args.destination, retention_days=args.retention_days,
                      upload_executable=args.upload_executable)
    except (BackupError, OSError, subprocess.SubprocessError):
        print('Backup failed; inspect service health and external configuration.', file=sys.stderr)
        return 1
    print('Backup complete: ' + path.name)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
