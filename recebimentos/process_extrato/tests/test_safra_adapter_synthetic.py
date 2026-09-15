from decimal import Decimal
import json
import sys
from pathlib import Path

import pdfplumber
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from bank_extraction_core import SafraAdapter, SafraExtractionResult


_VALID_STATEMENT_TEXT = """Extrato de Movimentação EMPRESA TESTE ALFA
CNPJ: 000
AG: 000 | CONTA: 000-000
Período de 01/08/2026 a 31/08/2026
LANÇAMENTOS REALIZADOS
01/08 TED RECEBIDA BCO 000 PAGADOR TESTE ALFA 0001 1.234,56
descrição multiline sintética
02/08 TED RECEBIDA BCO 000 PAGADOR TESTE BETA 0002 789,01
03/08 TED RECEBIDA BCO 000 PAGADOR TESTE GAMA 0003 345,67"""


class _Page:
    def __init__(self, text=_VALID_STATEMENT_TEXT):
        self.text = text

    def extract_text(self, **_kwargs):
        return self.text


class _Pdf:
    def __init__(self, page=None):
        self.pages = [page or _Page()]

    def __enter__(self): return self
    def __exit__(self, *_args): return False


def _prepare_valid_safra_source(monkeypatch, tmp_path, *, pdf_bytes=b"synthetic-safra-input", page=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "extrato_sintetico.pdf"
    source.write_bytes(pdf_bytes)
    source_map = tmp_path / "source-map.json"
    source_map.write_text(json.dumps({"aliases": [
        {"bank_payor_alias": "PAGADOR TESTE ALFA", "canonical_royalty_source": "FONTE_TESTE_A"},
        {"bank_payor_alias": "PAGADOR TESTE BETA", "canonical_royalty_source": "FONTE_TESTE_B"},
        {"bank_payor_alias": "PAGADOR TESTE GAMA", "canonical_royalty_source": "FONTE_TESTE_C"}]}, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setenv("MUV_SAFRA_SOURCE_MAP", str(source_map))
    monkeypatch.setattr(pdfplumber, "open", lambda _path: _Pdf(page))
    return source


def test_safra_adapter_happy_path_uses_real_parser(monkeypatch, tmp_path):
    source = _prepare_valid_safra_source(monkeypatch, tmp_path)
    result = SafraAdapter().extract(source, "2026-08")
    assert (result.entity, result.bank_source, result.period) == ("MDB", "SAFRA", "2026-08")
    assert result.period_validation_status == "PASS"
    assert result.technical_transaction_count == result.credit_count == 3
    assert result.total_credits == Decimal("2369.24")
    assert len(result.operational_credits) == 3
    assert [item.payor_source for item in result.operational_credits] == ["FONTE_TESTE_A", "FONTE_TESTE_B", "FONTE_TESTE_C"]


def test_safra_adapter_blocks_period_mismatch(monkeypatch, tmp_path):
    source = _prepare_valid_safra_source(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        SafraAdapter().extract(source, "2026-09")


def test_safra_adapter_blocks_missing_period(monkeypatch, tmp_path):
    source = _prepare_valid_safra_source(monkeypatch, tmp_path)

    class MissingPeriodPage(_Page):
        def extract_text(self, **kwargs):
            return super().extract_text(**kwargs).replace("Período de 01/08/2026 a 31/08/2026\n", "")

    monkeypatch.setattr(pdfplumber, "open", lambda _path: _Pdf(MissingPeriodPage()))
    with pytest.raises(ValueError, match="Cabeçalho Safra incompleto"):
        SafraAdapter().extract(source, "2026-08")


def test_safra_adapter_source_hash_and_output_are_deterministic(monkeypatch, tmp_path):
    source = _prepare_valid_safra_source(monkeypatch, tmp_path)

    result_run_1 = SafraAdapter().extract(source, "2026-08")
    result_run_2 = SafraAdapter().extract(source, "2026-08")

    assert result_run_1.source_sha256 == result_run_2.source_sha256
    assert result_run_1 == result_run_2
    assert result_run_1.operational_credits == result_run_2.operational_credits
    assert result_run_1.safra_rows == result_run_2.safra_rows


def test_safra_adapter_preserves_rich_rows_without_changing_operational_credits(monkeypatch, tmp_path):
    source = _prepare_valid_safra_source(monkeypatch, tmp_path)

    result = SafraAdapter().extract(source, "2026-08")

    assert isinstance(result, SafraExtractionResult)
    assert len(result.safra_rows) == len(result.operational_credits) == 3
    first_row, first_credit = result.safra_rows[0], result.operational_credits[0]
    assert first_row.lancamento == first_credit.description
    assert first_row.complemento == "descrição multiline sintética"
    assert first_row.documento == "0001"
    assert first_row.valor_str == "1.234,56"
    assert first_row.credit == Decimal("1234.56")
    assert [(row.transaction_date, row.lancamento, row.credit, row.payor_source, row.status) for row in result.safra_rows] == [
        (credit.transaction_date, credit.description, credit.credit, credit.payor_source, credit.status)
        for credit in result.operational_credits
    ]
    assert [(row.lancamento, row.complemento) for row in result.safra_rows] == [
        ("TED RECEBIDA BCO 000 PAGADOR TESTE ALFA", "descrição multiline sintética"),
        ("TED RECEBIDA BCO 000 PAGADOR TESTE BETA", None),
        ("TED RECEBIDA BCO 000 PAGADOR TESTE GAMA", None),
    ]


def test_safra_adapter_source_hash_changes_with_different_input(monkeypatch, tmp_path):
    source_a = _prepare_valid_safra_source(monkeypatch, tmp_path / "input-a")
    result_a = SafraAdapter().extract(source_a, "2026-08")

    changed_text = _VALID_STATEMENT_TEXT.replace("descrição multiline sintética", "descrição multiline sintética alternativa")
    source_b = _prepare_valid_safra_source(
        monkeypatch,
        tmp_path / "input-b",
        pdf_bytes=b"synthetic-safra-input-with-a-different-description",
        page=_Page(changed_text),
    )
    result_b = SafraAdapter().extract(source_b, "2026-08")

    assert result_a.source_sha256 != result_b.source_sha256


def test_safra_adapter_does_not_require_manual_directory_configuration(monkeypatch, tmp_path):
    monkeypatch.delenv("MUV_SAFRA_INPUT_DIR", raising=False)
    monkeypatch.delenv("MUV_SAFRA_OUTPUT_DIR", raising=False)
    source = _prepare_valid_safra_source(monkeypatch, tmp_path)

    result = SafraAdapter().extract(source, "2026-08")

    assert result.status == "PASS"


def test_safra_adapter_blocks_missing_account(monkeypatch, tmp_path):
    source = tmp_path / "extrato_sintetico.pdf"
    source.write_bytes(b"synthetic-safra-input")
    source_map = tmp_path / "source-map.json"
    source_map.write_text(json.dumps({"aliases": []}), encoding="utf-8")
    monkeypatch.setenv("MUV_SAFRA_SOURCE_MAP", str(source_map))
    class MissingAccountPage:
        def extract_text(self, **_kwargs):
            return "Período de 01/08/2026 a 31/08/2026\nLANÇAMENTOS REALIZADOS\n01/08 TEXTO 1,00"
    class MissingAccountPdf:
        pages = [MissingAccountPage()]
        def __enter__(self): return self
        def __exit__(self, *_args): return False
    monkeypatch.setattr(pdfplumber, "open", lambda _path: MissingAccountPdf())
    with pytest.raises(ValueError, match="Cabeçalho Safra incompleto"):
        SafraAdapter().extract(source, "2026-08")
