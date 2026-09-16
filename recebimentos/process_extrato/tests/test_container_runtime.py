"""No sockets or real credentials: exercise configuration and readiness contracts."""
from contextlib import contextmanager
from unittest.mock import MagicMock
import sys

import pytest

import container_runtime as runtime


def config_env():
    return dict(DB_HOST='synthetic-db', DB_PORT='5432', DB_NAME='synthetic',
                DB_USER='synthetic', DB_PASSWORD='SYNTHETIC_ONLY')


@pytest.mark.parametrize('key', ['DB_HOST', 'DB_PORT', 'DB_NAME', 'DB_USER', 'DB_PASSWORD'])
def test_config_requires_each_external_value(key):
    env = config_env(); del env[key]
    with pytest.raises(runtime.RuntimeHealthError, match='incomplete'):
        runtime.DatabaseConfig.from_environment(env)


@pytest.mark.parametrize('port', ['0', '65536', 'not-a-port'])
def test_config_rejects_invalid_port(port):
    with pytest.raises(runtime.RuntimeHealthError, match='invalid'):
        runtime.DatabaseConfig.from_environment(dict(config_env(), DB_PORT=port))


def test_config_redacts_password_and_reads_external_host():
    config = runtime.DatabaseConfig.from_environment(config_env())
    assert config.host == 'synthetic-db' and config.port == 5432
    assert 'SYNTHETIC_ONLY' not in repr(config)


@pytest.mark.parametrize('row,passes', [((1,), True), ((0,), False)])
def test_database_probe_requires_real_query_result(monkeypatch, row, passes):
    driver = MagicMock()
    monkeypatch.setitem(sys.modules, 'psycopg', driver)
    cursor = driver.connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = row
    config = runtime.DatabaseConfig.from_environment(config_env())
    if passes:
        runtime.check_database(config)
    else:
        with pytest.raises(runtime.RuntimeHealthError):
            runtime.check_database(config)
    cursor.execute.assert_called_once_with('SELECT 1')
    kwargs = driver.connect.call_args.kwargs
    assert kwargs['host'] == config.host and kwargs['password'] == config.password
    assert kwargs['connect_timeout'] == 5
    assert 'default_transaction_read_only=on' in kwargs['options']
    driver.connect.return_value.__exit__.assert_called_once()


def test_database_failure_does_not_expose_driver_credentials(monkeypatch):
    driver = MagicMock()
    driver.connect.side_effect = RuntimeError('SYNTHETIC_ONLY connection secret')
    monkeypatch.setitem(sys.modules, 'psycopg', driver)
    with pytest.raises(runtime.RuntimeHealthError) as error:
        runtime.check_database(runtime.DatabaseConfig.from_environment(config_env()))
    assert str(error.value) == 'Database readiness failed.'
    assert error.value.__suppress_context__


@pytest.mark.parametrize('status,body,passes', [(200,b'ok',True), (503,b'ok',False), (200,b'not ready',False)])
def test_app_probe_checks_status_and_body(monkeypatch, status, body, passes):
    response = MagicMock(); response.status = status; response.read.return_value = body
    @contextmanager
    def fake_urlopen(url, timeout):
        assert url.endswith('/_stcore/health') and timeout == 5
        yield response
    monkeypatch.setattr(runtime, 'urlopen', fake_urlopen)
    if passes:
        runtime.check_application()
    else:
        with pytest.raises(runtime.RuntimeHealthError):
            runtime.check_application()


def test_start_is_blocked_when_database_fails(monkeypatch, capsys):
    for key, value in config_env().items(): monkeypatch.setenv(key, value)
    def fail(_): raise runtime.RuntimeHealthError('Database readiness failed.')
    monkeypatch.setattr(runtime, 'check_database', fail)
    execute = MagicMock(); monkeypatch.setattr(runtime.os, 'execv', execute)
    assert runtime.main(['start']) == 1
    execute.assert_not_called()
    assert capsys.readouterr().err == 'Database readiness failed.\n'


def test_start_executes_headless_streamlit_after_probe(monkeypatch):
    for key, value in config_env().items(): monkeypatch.setenv(key, value)
    probe = MagicMock(); execute = MagicMock()
    monkeypatch.setattr(runtime, 'check_database', probe)
    monkeypatch.setattr(runtime.os, 'execv', execute)
    assert runtime.main(['start']) == 0
    probe.assert_called_once()
    args = execute.call_args.args[1]
    assert args[:4] == [sys.executable, '-m', 'streamlit', 'run']
    assert '--server.headless=true' in args and '--server.port=8501' in args


def test_health_checks_both_services(monkeypatch):
    for key, value in config_env().items(): monkeypatch.setenv(key, value)
    db = MagicMock(); app = MagicMock()
    monkeypatch.setattr(runtime, 'check_database', db)
    monkeypatch.setattr(runtime, 'check_application', app)
    assert runtime.main(['health']) == 0
    db.assert_called_once(); app.assert_called_once()
