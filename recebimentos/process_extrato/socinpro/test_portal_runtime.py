import logging
from pathlib import Path

import pytest
from openpyxl import Workbook

from socinpro.portal_runtime import (
    CREDENTIAL_PATH_ENVIRONMENTS,
    SocinproPortalRuntimeError,
    preflight_runtime_credentials,
)


def write_credentials(path: Path, rows: list[tuple[str, str]]) -> Path:
    book = Workbook()
    sheet = book.active
    sheet.title = "credentials"
    sheet.append(["USUARIO", "SENHA"])
    for row in rows:
        sheet.append(row)
    book.save(path)
    book.close()
    return path


def test_global_master_duplicates_do_not_block_hm_runtime_preflight(tmp_path, caplog):
    hm = write_credentials(tmp_path / "hm.xlsx", [("hm-one", "hm-secret-one"), ("hm-two", "hm-secret-two")])
    global_master = write_credentials(tmp_path / "global-master.xlsx", [("other", "one"), ("other", "two")])
    assert global_master.is_file()  # Deliberately unrelated to the HM runtime contract.

    with caplog.at_level(logging.INFO):
        preflight = preflight_runtime_credentials("HM", environment={CREDENTIAL_PATH_ENVIRONMENTS["HM"]: str(hm)})

    assert preflight.account_count == 2
    assert preflight.unique_account_count == 2
    assert preflight.duplicate_runtime_accounts == 0
    assert preflight.download_allowed is True
    assert "hm-secret-one" not in caplog.text
    assert "hm-secret-two" not in caplog.text


def test_duplicate_runtime_account_blocks_before_any_portal_use(tmp_path):
    hm = write_credentials(tmp_path / "hm.xlsx", [("same-user", "first"), ("same-user", "second")])
    with pytest.raises(SocinproPortalRuntimeError, match="DUPLICATE_RUNTIME_ACCOUNT"):
        preflight_runtime_credentials("HM", credential_path=hm)


def test_entity_credential_sources_are_explicit_and_never_fall_back(tmp_path):
    hm = write_credentials(tmp_path / "hm.xlsx", [("hm-user", "hm-password")])
    mdb = write_credentials(tmp_path / "mdb.xlsx", [("mdb-user", "mdb-password")])
    environment = {
        CREDENTIAL_PATH_ENVIRONMENTS["HM"]: str(hm),
        CREDENTIAL_PATH_ENVIRONMENTS["MDB"]: str(mdb),
    }
    assert preflight_runtime_credentials("HM", environment=environment).source_path == hm.resolve()
    assert preflight_runtime_credentials("MDB", environment=environment).source_path == mdb.resolve()
    with pytest.raises(SocinproPortalRuntimeError, match="RUNTIME_CREDENTIAL_PATH_NOT_CONFIGURED"):
        preflight_runtime_credentials("HM", environment={CREDENTIAL_PATH_ENVIRONMENTS["MDB"]: str(mdb)})
