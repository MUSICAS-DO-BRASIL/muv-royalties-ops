"""Default tests use isolated synthetic data and never the operational roots."""
import sys

import pytest
from openpyxl import Workbook


def pytest_collection_modifyitems(items):
    for item in items:
        if item.get_closest_marker("windows_only") and sys.platform != "win32":
            item.add_marker(pytest.mark.skip(reason="WINDOWS_ONLY: exige Windows"))
        if item.get_closest_marker("corporate_environment"):
            item.add_marker(pytest.mark.skip(reason="CORPORATE_ENVIRONMENT_ONLY: fora da suíte sintética"))


@pytest.fixture(autouse=True)
def isolated_operational_roots(tmp_path, monkeypatch):
    import bank_extraction_core
    import month_preparation

    monkeypatch.setenv("MUV_BANK_ACCOUNT_ID", "TEST_BANK_ACCOUNT_001")
    root = tmp_path / "months"
    templates = tmp_path / "templates"
    monkeypatch.setenv("MUV_OPERATIONAL_ROOT", str(root))
    monkeypatch.setenv("MUV_TEMPLATE_ROOT", str(templates))
    monkeypatch.setenv("MUV_BTG_SOURCE_MAP", str(tmp_path / "missing-btg-map.json"))
    monkeypatch.setenv("MUV_SAFRA_SOURCE_MAP", str(tmp_path / "missing-safra-map.json"))
    monkeypatch.setattr(bank_extraction_core, "ROOT", root)
    monkeypatch.setattr(month_preparation, "ROOT", root)
    monkeypatch.setattr(month_preparation, "TEMPLATE_ROOT", templates)
    # Existing discovery contracts expect one prepared HM month; fixture is generated here.
    target = root / "2026" / "082026" / "HM" / "Conciliação - Hurst Music_202608.xlsx"
    target.parent.mkdir(parents=True)
    workbook = Workbook()
    workbook.active.title = "Banco"
    workbook.active.append(["Data", "Descrição", "Crédito", "Fonte Pagadora"])
    workbook.save(target)
    workbook.close()
