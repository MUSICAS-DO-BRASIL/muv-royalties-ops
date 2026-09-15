"""Synthetic, PDF-free checks for the canonical Safra text parser."""
from decimal import Decimal
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from process_safra_mp_toyalties import Cabecalho, extrair_lancamentos, main, parse_cabecalho


HEADER = """Extrato de Movimentação EMPRESA TESTE ALFA
CNPJ: 000
AG: 000 | CONTA: 000-000
Período de 01/08/2026 a 31/08/2026"""


def _rows(text: str):
    return extrair_lancamentos([HEADER + "\nLANÇAMENTOS REALIZADOS\n" + text], parse_cabecalho([HEADER]))


def test_parse_header_is_complete_and_deterministic():
    first = parse_cabecalho(["irrelevante", HEADER])
    second = parse_cabecalho(["irrelevante", HEADER])
    assert first == second
    assert (first.nome, first.agencia, first.conta, first.periodo_ini, first.periodo_fim) == (
        "EMPRESA TESTE ALFA", "000", "000-000", "01/08/2026", "31/08/2026")


def test_parse_header_keeps_missing_and_invalid_fields_empty():
    parsed = parse_cabecalho(["conteúdo irrelevante", "Período inválido"])
    assert parsed == Cabecalho()


def test_multiline_credits_are_exact_and_deterministic():
    rows = _rows("""DATA LANÇAMENTO
01/08 CRÉDITO TESTE ALFA 1.234,56
continuação acentuada
DOC-ALFA
02/08 CRÉDITO TESTE BETA 789,01
segunda linha BETA
DOC-BETA
03/08 CRÉDITO TESTE GAMA
terceira linha
mais detalhes
DOC-GAMA
345,67
linha inválida sem data""")
    assert [row.data for row in rows] == ["01/08/2026", "02/08/2026", "03/08/2026"]
    assert [row.valor_str for row in rows] == ["1.234,56", "789,01", "345,67"]
    assert sum((Decimal(row.valor_str.replace('.', '').replace(',', '.')) for row in rows), Decimal()) == Decimal("2369.24")
    assert rows[0].complemento == "continuação acentuada ALFA"
    assert rows[1].complemento == "segunda linha BETA BETA"
    assert rows[2].complemento == "terceira linha mais detalhes linha inválida sem data"
    assert rows == _rows("""01/08 CRÉDITO TESTE ALFA 1.234,56
continuação acentuada
DOC-ALFA
02/08 CRÉDITO TESTE BETA 789,01
segunda linha BETA
DOC-BETA
03/08 CRÉDITO TESTE GAMA
terceira linha
mais detalhes
DOC-GAMA
345,67
linha inválida sem data""")


def test_empty_and_malformed_input_produce_no_records():
    header = Cabecalho(periodo_ini="01/08/2026", periodo_fim="31/08/2026")
    assert extrair_lancamentos([], header) == []
    assert extrair_lancamentos(["LANÇAMENTOS REALIZADOS\ntexto solto\n99/99 sem valor"], header) == []


def test_manual_main_accepts_explicit_temporary_directories(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    output_dir = tmp_path / "output"
    input_dir.mkdir()
    output_dir.mkdir()
    monkeypatch.setenv("MUV_SAFRA_INPUT_DIR", str(input_dir))
    monkeypatch.setenv("MUV_SAFRA_OUTPUT_DIR", str(output_dir))

    main()


def test_manual_main_blocks_missing_input_dir_env(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.delenv("MUV_SAFRA_INPUT_DIR", raising=False)
    monkeypatch.setenv("MUV_SAFRA_OUTPUT_DIR", str(output_dir))

    with pytest.raises(SystemExit):
        main()


def test_manual_main_blocks_missing_output_dir_env(monkeypatch, tmp_path):
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    monkeypatch.setenv("MUV_SAFRA_INPUT_DIR", str(input_dir))
    monkeypatch.delenv("MUV_SAFRA_OUTPUT_DIR", raising=False)

    with pytest.raises(SystemExit):
        main()


def test_manual_main_blocks_invalid_input_and_output_paths(monkeypatch, tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setenv("MUV_SAFRA_INPUT_DIR", str(tmp_path / "missing-input"))
    monkeypatch.setenv("MUV_SAFRA_OUTPUT_DIR", str(output_dir))
    with pytest.raises(SystemExit):
        main()

    input_dir = tmp_path / "input"
    input_dir.mkdir()
    output_file = tmp_path / "not-a-directory"
    output_file.write_text("synthetic", encoding="utf-8")
    monkeypatch.setenv("MUV_SAFRA_INPUT_DIR", str(input_dir))
    monkeypatch.setenv("MUV_SAFRA_OUTPUT_DIR", str(output_file))
    with pytest.raises(SystemExit):
        main()
