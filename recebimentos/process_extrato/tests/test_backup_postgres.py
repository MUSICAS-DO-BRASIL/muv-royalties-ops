"""Backup failures must not erase valid archives or expose subprocess output."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
import pytest

spec = importlib.util.spec_from_file_location('muv_backup', Path(__file__).resolve().parents[3] / 'scripts/backup_postgres.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def invoke(tmp_path, **kwargs):
    return module.backup(compose_file=tmp_path/'compose.yaml', env_file=tmp_path/'external.env',
                         project='synthetic', destination=tmp_path/'backups', **kwargs)


def fake_runner(monkeypatch, *, dump_code=0, validation_code=0, upload_code=0):
    def run(args, **kwargs):
        if 'pg_dump' in args[-1]:
            kwargs['stdout'].write(b'PGDMP-synthetic')
            return SimpleNamespace(returncode=dump_code)
        return SimpleNamespace(returncode=validation_code if 'pg_restore' in args else upload_code)
    monkeypatch.setattr(module.subprocess, 'run', run)


def test_backup_is_private_and_prunes_only_old_owned_archives(tmp_path, monkeypatch):
    folder=tmp_path/'backups';folder.mkdir()
    old=folder/'muv-postgres-20200101T000000000000Z.dump';old.write_bytes(b'old');os.utime(old,(1,1))
    unrelated=folder/'unrelated.dump';unrelated.write_bytes(b'keep');os.utime(unrelated,(1,1))
    symlink=folder/'muv-postgres-20200102T000000000000Z.dump'
    try:
        symlink.symlink_to(unrelated)
    except OSError as exc:
        if os.name == 'nt' and exc.winerror == 1314:
            pytest.skip('symlinks unavailable on this Windows host: missing privilege (WinError 1314)')
        raise
    fake_runner(monkeypatch)
    target=invoke(tmp_path,retention_days=1)
    assert target.read_bytes()==b'PGDMP-synthetic' and target.stat().st_mode & 0o777 == 0o600
    assert not old.exists() and unrelated.exists() and symlink.is_symlink()
    assert not list(folder.glob('.muv-backup-*'))


@pytest.mark.parametrize('failure', ['dump','validation','upload'])
def test_failure_preserves_old_backups(tmp_path, monkeypatch, failure):
    folder=tmp_path/'backups';folder.mkdir()
    old=folder/'muv-postgres-20200101T000000000000Z.dump';old.write_bytes(b'old');os.utime(old,(1,1))
    fake_runner(monkeypatch,dump_code=int(failure=='dump'),validation_code=int(failure=='validation'),upload_code=int(failure=='upload'))
    with pytest.raises(module.BackupError):
        invoke(tmp_path,upload_executable='/synthetic-uploader' if failure=='upload' else None)
    assert old.read_bytes()==b'old'
    assert not list(folder.glob('.muv-backup-*'))


def test_cli_failure_redacts_subprocess_exception(tmp_path, monkeypatch, capsys):
    def fail(**kwargs): raise OSError('SYNTHETIC_PASSWORD')
    monkeypatch.setattr(module,'backup',fail)
    assert module.main(['--compose-file','c','--env-file','e','--project','synthetic','--destination',str(tmp_path)])==1
    assert 'SYNTHETIC_PASSWORD' not in capsys.readouterr().err


@pytest.mark.parametrize('options',[{'retention_days':0},{'upload_executable':'relative-script'}])
def test_invalid_retention_or_upload_is_blocked(tmp_path, options):
    with pytest.raises(module.BackupError):invoke(tmp_path,**options)
    assert not (tmp_path/'backups').exists()
