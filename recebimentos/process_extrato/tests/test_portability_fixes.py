"""Synthetic regressions for the four portability defects; never run real COM."""
import builtins
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
from unittest.mock import MagicMock

import pytest
from openpyxl import Workbook

from bank_extraction_core import BankExtractionService
from mdb_safra_worksheet_writer import (
    ExcelComWorkbookBackend, MdbSafraWorksheetWriter, MdbWorkbookLayout,
    UnsupportedWorkbookPlatformError,
)
from mdb.test_mdb_safra_worksheet_writer import _book, _rows
from socinpro.real_ingestion import parse_payment_pdf, parse_payment_workbook
from socinpro.test_real_ingestion import payment_pdf


@pytest.mark.parametrize('platform', ['darwin', 'linux'])
def test_default_mdb_writer_blocks_without_modifying_file(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(sys, 'platform', platform)
    path = tmp_path / 'synthetic.xlsx'
    _book(path)
    before = path.read_bytes()
    writer = MdbSafraWorksheetWriter()
    assert isinstance(writer.backend, ExcelComWorkbookBackend)
    with pytest.raises(UnsupportedWorkbookPlatformError, match='requires Windows'):
        writer.write(path, _rows())
    assert path.read_bytes() == before


@pytest.mark.parametrize('platform', ['darwin', 'linux'])
def test_com_platform_error_precedes_imports(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(sys, 'platform', platform)
    original = builtins.__import__
    def guarded(name, *args, **kwargs):
        assert name.split('.')[0] not in {'pythoncom', 'win32com'}
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', guarded)
    with pytest.raises(UnsupportedWorkbookPlatformError, match='requires Windows'):
        ExcelComWorkbookBackend().write_safra_rows(tmp_path / 'absent.xlsx', (), MdbWorkbookLayout('Safra'))
    assert not (tmp_path / 'absent.xlsx').exists()


@pytest.mark.parametrize('relative', [False, True])
@pytest.mark.parametrize('kind', ['pdf', 'xlsx'])
def test_socinpro_input_paths(tmp_path, monkeypatch, relative, kind):
    monkeypatch.chdir(tmp_path)
    folder = tmp_path / 'pasta sintética com espaços 漢字'
    folder.mkdir()
    source = folder / ('synthetic.' + kind)
    if kind == 'pdf':
        payment_pdf(source)
    else:
        book = Workbook(); sheet = book.active; sheet.title = 'pagamentos'
        sheet.append(['cod_socinpro', 'titular', 'data_pagamento', 'valor_pagamento'])
        sheet.append(['123456', 'TITULAR SINTETICO', date(2026, 9, 25), '-100,50'])
        book.save(source); book.close()
    before = source.read_bytes()
    path = source.relative_to(tmp_path) if relative else source
    parsed = parse_payment_pdf(path) if kind == 'pdf' else parse_payment_workbook(path)[0]
    assert parsed.receipt_value == Decimal('100.50')
    assert parsed.source_reference.startswith(source.as_uri())
    assert source.read_bytes() == before


def test_hm_bootstrap_uses_supplied_root(tmp_path, monkeypatch):
    import bank_extraction_core
    import btg_statement_parser
    from btg.tests.test_btg_statement_parser import fixture_lines
    details = btg_statement_parser._parse_details_from_lines(fixture_lines(), 'synthetic.pdf')
    monkeypatch.setattr(btg_statement_parser, 'parse_btg_statement_details', lambda _: details)
    original_loader = bank_extraction_core._load_module
    contexts = []
    def load(name, path):
        module = original_loader(name, path)
        original_prepare = module.prepare_hm_month
        def capture(**kwargs):
            result = original_prepare(**kwargs)
            contexts.append(result)
            return result
        module.prepare_hm_month = capture
        return module
    monkeypatch.setattr(bank_extraction_core, '_load_module', load)
    root = tmp_path / 'meses explícitos'
    status, _ = BankExtractionService(monthly_root=root).prepare_month(
        entity='HM', period='2026-08', source_bytes=b'synthetic', source_name='synthetic.pdf')
    assert status == 'REVIEW'  # Existing bootstrap intentionally does not create workbooks.
    assert contexts[0].monthly_folder == root / '2026' / '082026' / 'HM'
    assert not root.exists()


def test_hm_synthetic_output_under_supplied_root(tmp_path):
    from tests.test_month_preparation import create_clean_template, fixture_result
    from month_preparation import MonthPreparationService
    templates = tmp_path / 'templates'
    create_clean_template(templates, 'HM')
    root = tmp_path / 'meses explícitos'
    service = MonthPreparationService(monthly_root=root, templates_root=templates,
                                      native_excel_validator=lambda _: (True, False, ()))
    result = service.prepare_month('HM', '2026-09', fixture_result('HM', '2026-09'))
    assert result.status == 'PREPARED'
    assert result.workbook_path.is_file()
    assert result.workbook_path.is_relative_to(root)


def test_windows_com_design_uses_native_save(tmp_path, monkeypatch):
    # COM doubles verify dispatch/save routing, not native Excel compatibility.
    monkeypatch.setattr(sys, 'platform', 'win32')
    pythoncom = MagicMock(); win32com = MagicMock(); client = win32com.client
    monkeypatch.setitem(sys.modules, 'pythoncom', pythoncom)
    monkeypatch.setitem(sys.modules, 'win32com', win32com)
    monkeypatch.setitem(sys.modules, 'win32com.client', client)
    writer = MdbSafraWorksheetWriter()
    assert isinstance(writer.backend, ExcelComWorkbookBackend)
    writer.backend.write_safra_rows(tmp_path / 'synthetic.xlsx', _rows(), MdbWorkbookLayout('Safra'))
    client.DispatchEx.assert_called_once_with('Excel.Application')
    book = client.DispatchEx.return_value.Workbooks.Open.return_value
    book.Save.assert_called_once()
    book.Close.assert_called_once_with(False)
    pythoncom.CoInitialize.assert_called_once()
    pythoncom.CoUninitialize.assert_called_once()
