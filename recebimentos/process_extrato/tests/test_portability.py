"""Portability checks use only synthetic data; never launch Excel COM."""
import os
from pathlib import Path
import subprocess
import sys

import pytest
from streamlit.testing.v1 import AppTest


@pytest.mark.parametrize("module", [
    "bank_extraction_core", "btg_statement_parser", "btg_bank_adapter",
    "safra_royalties_classifier", "month_preparation", "hm_month_bootstrap",
    "process_safra_mp_toyalties", "mdb_safra_worksheet_writer", "mdb_month_preparation_facade",
    "cloud_aware_workbook_publisher", "cloud_native_workbook_publisher",
    "bank_extraction_app_v2", "socinpro.socinpro_vertical", "socinpro.real_ingestion",
])
def test_core_and_app_import_in_fresh_process(module):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (root, root / "btg", root / "mdb"))))
    subprocess.run([sys.executable, "-c", f"import {module}"], env=env, check=True, capture_output=True, timeout=30)


def test_configured_external_roots_in_fresh_process(tmp_path):
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, PYTHONPATH=os.pathsep.join(map(str, (root, root / "mdb"))))
    code = '''
import os
from pathlib import Path
from bank_extraction_core import ROOT
from month_preparation import MonthPreparationService
from safra_royalties_classifier import SOURCE_MAP_PATH
assert ROOT == Path(os.environ["MUV_OPERATIONAL_ROOT"])
assert MonthPreparationService().monthly_root == ROOT
assert MonthPreparationService().templates_root == Path(os.environ["MUV_TEMPLATE_ROOT"])
assert SOURCE_MAP_PATH == Path(os.environ["MUV_SAFRA_SOURCE_MAP"])
'''
    subprocess.run([sys.executable, "-c", code], env=env, check=True, capture_output=True, timeout=30)


def test_native_excel_refuses_non_windows_before_import(monkeypatch, tmp_path):
    import month_preparation
    monkeypatch.setattr(month_preparation.sys, "platform", "darwin")
    result = month_preparation.validate_with_native_excel(tmp_path / "not-opened.xlsx")
    assert result[0:2] == (False, True)
    assert "WINDOWS_EXCEL_REQUIRED" in result[2][0]
    assert "win32com.client" not in sys.modules


@pytest.mark.windows_only
def test_windows_file_attribute_adapter(tmp_path):
    from cloud_aware_workbook_publisher import _win32_attributes
    path = tmp_path / "synthetic.txt"
    path.write_text("synthetic", encoding="utf-8")
    assert isinstance(_win32_attributes(path), int)


def test_empty_streamlit_startup():
    root = Path(__file__).resolve().parents[1]
    app = AppTest.from_file(root / "bank_extraction_app_v2.py", default_timeout=30).run()
    assert not app.exception
    assert app.button(key="process_statement").disabled
    assert not app.session_state["result"]
