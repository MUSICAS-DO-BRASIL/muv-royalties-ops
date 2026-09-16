"""Optional Linux container entrypoint and read-only PostgreSQL readiness probe.

No financial persistence or schema is implemented here. Existing Windows/UI
entrypoints never import this module automatically.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
from typing import Mapping
from urllib.request import urlopen


class RuntimeHealthError(RuntimeError):
    """Configuration or readiness failed; messages must not expose credentials."""


@dataclass(frozen=True)
class DatabaseConfig:
    host: str
    port: int
    name: str
    user: str
    password: str = field(repr=False)

    @classmethod
    def from_environment(cls, environ: Mapping[str, str] | None = None) -> DatabaseConfig:
        values = os.environ if environ is None else environ
        keys = ('DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD')
        if any(not values.get(key, '').strip() for key in keys):
            raise RuntimeHealthError('Database configuration is incomplete.')
        try:
            port = int(values['DB_PORT'])
        except ValueError:
            raise RuntimeHealthError('Database port is invalid.') from None
        if not 1 <= port <= 65535:
            raise RuntimeHealthError('Database port is invalid.')
        return cls(values['DB_HOST'], port, values['DB_NAME'], values['DB_USER'], values['DB_PASSWORD'])


def check_database(config: DatabaseConfig) -> None:
    """Actually authenticate and run SELECT 1, without creating tables or data."""
    try:
        import psycopg
        with psycopg.connect(host=config.host, port=config.port, dbname=config.name,
                             user=config.user, password=config.password,
                             connect_timeout=5, autocommit=True,
                             options='-c default_transaction_read_only=on -c statement_timeout=5000') as connection:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                if cursor.fetchone() != (1,):
                    raise RuntimeHealthError('Database readiness failed.')
    except Exception:
        raise RuntimeHealthError('Database readiness failed.') from None


def check_application() -> None:
    try:
        with urlopen('http://127.0.0.1:8501/_stcore/health', timeout=5) as response:
            if response.status != 200 or response.read().strip() != b'ok':
                raise RuntimeHealthError('Application readiness failed.')
    except Exception:
        raise RuntimeHealthError('Application readiness failed.') from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('start', 'check-db', 'health'))
    args = parser.parse_args(argv)
    try:
        check_database(DatabaseConfig.from_environment())
        if args.command == 'health':
            check_application()
        elif args.command == 'start':
            app = Path(__file__).with_name('bank_extraction_app_v2.py')
            os.execv(sys.executable, [sys.executable, '-m', 'streamlit', 'run', str(app),
                                     '--server.address=0.0.0.0', '--server.port=8501',
                                     '--server.headless=true', '--server.fileWatcherType=none',
                                     '--browser.gatherUsageStats=false'])
    except RuntimeHealthError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
