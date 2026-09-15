#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Processador de Extrato Bancário (Banco Safra - PDF)
- Varre a pasta de entrada por PDFs
- Extrai cabeçalho (Nome, CNPJ, Agência, Conta, Período)
- Extrai seção "LANÇAMENTOS REALIZADOS" reconstruindo registros que vêm em múltiplas linhas
- Normaliza datas (usa o ano do período do extrato)
- Converte valores pt-BR para float
- Salva um XLSX por extrato na pasta de saída

Os diretórios de entrada e saída são fornecidos explicitamente em tempo de execução.
"""

from __future__ import annotations
import re
import os
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pdfplumber
import pandas as pd

# =========================
# REGEX
# =========================
RE_PERIODO = re.compile(r"Período de\s+(\d{2}/\d{2}/\d{4})\s+a\s+(\d{2}/\d{2}/\d{4})", re.I)
RE_AG_CC   = re.compile(r"AG:\s*([\d\.]+)\s*\|\s*CONTA:\s*([\d\.-]+)", re.I)
RE_NOME    = re.compile(r"Extrato de Movimentação\s+(.+)")
RE_CNPJ    = re.compile(r"CNPJ:\s*([\d\.\-\/]+)")
RE_DATA_INICIO_LINHA = re.compile(r"^\s*(\d{2}/\d{2})\s+(.+)$")
RE_VALOR_FINAL = re.compile(r"([-]?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
RE_DOC_E_VALOR = re.compile(r"\s([A-Za-z0-9\-\/]+)\s+([-]?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
RE_NUMERO_DOC  = re.compile(r"^\s*([A-Za-z0-9\-\/]{4,})\s*$")
RE_SO_VALOR    = re.compile(r"^\s*([-]?\d{1,3}(?:\.\d{3})*,\d{2})\s*$")
RE_SECAO_LANC  = re.compile(r"LANÇAMENTOS REALIZADOS", re.I)

BR_TO_FLOAT = lambda s: float(s.replace(".", "").replace(",", "."))

# =========================
# MODELOS
# =========================
@dataclass
class Cabecalho:
    nome: Optional[str] = None
    cnpj: Optional[str] = None
    agencia: Optional[str] = None
    conta: Optional[str] = None
    periodo_ini: Optional[str] = None  # "dd/mm/aaaa"
    periodo_fim: Optional[str] = None  # "dd/mm/aaaa"

@dataclass
class Lancamento:
    data: str                   # "dd/mm/aaaa"
    lancamento: str
    complemento: Optional[str]
    documento: Optional[str]
    valor_str: str              # "1.234,56"
    valor: float                # float PT-BR convertido
    canal: Optional[str]

# =========================
# HELPERS
# =========================
def guess_canal(lancamento_txt: str) -> str:
    s = lancamento_txt.upper()
    if "PIX" in s: return "PIX"
    if "TED" in s: return "TED"
    if "SALDO" in s: return "SALDO"
    if "APLICACAO CDB" in s or "APLICAÇÃO CDB" in s: return "APLICACAO"
    if "RESGATE CDB" in s: return "RESGATE"
    if "TRANSFERENCIA ENTRE CONTAS" in s: return "TRANSFERENCIA_INTERNA"
    return "OUTROS"

def limpar_linha(l: str) -> str:
    l = l.replace("\t", " ")
    l = re.sub(r"\s{2,}", " ", l)
    return l.strip()

def parse_cabecalho(text_pages: List[str]) -> Cabecalho:
    cab = Cabecalho()
    for txt in text_pages:
        if not cab.nome:
            m = RE_NOME.search(txt)
            if m: cab.nome = m.group(1).strip()
        if not cab.cnpj:
            m = RE_CNPJ.search(txt)
            if m: cab.cnpj = m.group(1).strip()
        if not (cab.agencia and cab.conta):
            m = RE_AG_CC.search(txt)
            if m:
                cab.agencia = m.group(1).strip()
                cab.conta   = m.group(2).strip()
        if not (cab.periodo_ini and cab.periodo_fim):
            m = RE_PERIODO.search(txt)
            if m:
                cab.periodo_ini = m.group(1)
                cab.periodo_fim = m.group(2)
        if cab.nome and cab.cnpj and cab.agencia and cab.conta and cab.periodo_ini and cab.periodo_fim:
            break
    return cab

def ano_do_periodo(cab: Cabecalho) -> int:
    if cab.periodo_fim:
        return datetime.strptime(cab.periodo_fim, "%d/%m/%Y").year
    if cab.periodo_ini:
        return datetime.strptime(cab.periodo_ini, "%d/%m/%Y").year
    return datetime.today().year

def extrair_lancamentos(text_pages: List[str], cab: Cabecalho) -> List[Lancamento]:
    registros: List[Lancamento] = []
    dentro_secao = False
    ano = ano_do_periodo(cab)

    cur_data: Optional[str] = None
    cur_lanc: Optional[str] = None
    cur_compl: List[str] = []
    cur_doc: Optional[str] = None
    cur_val: Optional[str] = None

    def preservar_documento(doc: str) -> None:
        """Keep an earlier document in text if the PDF block supplies another one."""
        nonlocal cur_doc
        if cur_doc and cur_doc != doc:
            cur_compl.append(cur_doc)
        cur_doc = doc

    def emitir_registro() -> None:
        """Emit only at an unambiguous record boundary, never at the first value line.

        Safra can place descriptive continuation lines after a date line that already
        contains its amount.  Retaining the open record until the next date preserves
        those lines without crossing a transaction boundary.
        """
        nonlocal cur_data, cur_lanc, cur_compl, cur_doc, cur_val
        if cur_data and cur_lanc and cur_val:
            registros.append(Lancamento(
                data=f"{cur_data}/{ano}",
                lancamento=cur_lanc.strip(),
                complemento=(" ".join(cur_compl).strip() or None),
                documento=(cur_doc.strip() if cur_doc else None),
                valor_str=cur_val,
                valor=BR_TO_FLOAT(cur_val),
                canal=guess_canal(cur_lanc),
            ))
        cur_data = cur_lanc = cur_val = None
        cur_compl = []
        cur_doc = None

    for page_txt in text_pages:
        if not dentro_secao:
            if RE_SECAO_LANC.search(page_txt):
                dentro_secao = True
            else:
                continue

        for raw_line in page_txt.splitlines():
            line = limpar_linha(raw_line)
            if not line:
                continue
            if line.upper().startswith("DATA LANÇAMENTO") or line.upper().startswith("DATA LANCAMENTO"):
                continue
            if line.startswith("Banco Safra S/A") or line.startswith("Página "):
                continue
            if line.startswith("CENTRAL DE SUPORTE") or line.startswith("(11) 3175") or line.startswith("0300 "):
                continue

            mdata = RE_DATA_INICIO_LINHA.match(line)
            if mdata:
                if cur_data and cur_lanc:
                    emitir_registro()

                cur_data = mdata.group(1)
                resto = mdata.group(2)
                cur_compl = []
                cur_doc = None
                cur_val = None
                m_doc_val = RE_DOC_E_VALOR.search(resto)
                if m_doc_val:
                    preservar_documento(m_doc_val.group(1).strip())
                    cur_val = m_doc_val.group(2).strip()
                    cur_lanc = RE_DOC_E_VALOR.sub("", resto).strip()
                else:
                    m_val = RE_VALOR_FINAL.search(resto)
                    if m_val:
                        cur_val = m_val.group(1).strip()
                        cur_lanc = RE_VALOR_FINAL.sub("", resto).strip()
                    else:
                        cur_lanc = resto.strip()
                continue

            if cur_data and cur_lanc:
                if RE_NUMERO_DOC.match(line):
                    preservar_documento(line.strip())
                    continue

                m_doc_val = RE_DOC_E_VALOR.search(line)
                if m_doc_val:
                    preservar_documento(m_doc_val.group(1).strip())
                    cur_val = m_doc_val.group(2).strip()
                    continue

                m_so_valor = RE_SO_VALOR.match(line)
                if m_so_valor:
                    cur_val = m_so_valor.group(1).strip()
                    continue

                cur_compl.append(line)
                continue

            continue

    emitir_registro()
    return registros

# =========================
# PIPELINE
# =========================
def processar_pdf(pdf_path: Path, *, output_dir: Path) -> Optional[Path]:
    """Parse an explicit Safra PDF and write output only to an explicit directory."""
    try:
        with pdfplumber.open(pdf_path) as pdf:
            text_pages = []
            for page in pdf.pages:
                txt = page.extract_text(x_tolerance=2, y_tolerance=2) or ""
                text_pages.append(txt)
    except Exception as e:
        print(f"[ERRO] Falha ao abrir/ler PDF: {pdf_path} -> {e}")
        return None

    cab = parse_cabecalho(text_pages)
    registros = extrair_lancamentos(text_pages, cab)

    if not registros:
        print(f"[AVISO] Nenhum lançamento encontrado no arquivo: {pdf_path.name}")
        return None

    df = pd.DataFrame([asdict(r) for r in registros])

    # === Remover nº do documento do texto (se duplicado) ===
    def _rm_doc(texto, doc):
        if pd.isna(texto) or pd.isna(doc):
            return texto
        pat = rf"(?:^|\s){re.escape(str(doc))}(?=$|\s|[.,;:/-])"
        novo = re.sub(pat, " ", str(texto)).strip()
        return re.sub(r"\s{2,}", " ", novo)

    if "documento" in df.columns:
        df["lancamento"]  = [_rm_doc(l, d) for l, d in zip(df["lancamento"],  df["documento"])]
        if "complemento" in df.columns:
            df["complemento"] = [_rm_doc(c, d) for c, d in zip(df["complemento"], df["documento"])]

    # Metadados do cabeçalho
    df["banco"]          = "Banco Safra"
    df["agencia"]        = cab.agencia
    df["conta"]          = cab.conta
    df["cnpj_conta"]     = cab.cnpj
    df["nome_conta"]     = cab.nome
    df["periodo_inicio"] = cab.periodo_ini
    df["periodo_fim"]    = cab.periodo_fim
    df["fonte_arquivo"]  = pdf_path.name

    # Ordena por data
    df["data_dt"] = pd.to_datetime(df["data"], format="%d/%m/%Y", errors="coerce")
    df = df.sort_values(["data_dt", "lancamento", "valor"]).reset_index(drop=True)
    df = df.drop(columns=["data_dt"])

    # Nome do arquivo de saída
    try:
        yyyymm = datetime.strptime(cab.periodo_ini, "%d/%m/%Y").strftime("%Y%m") if cab.periodo_ini else "YYYYMM"
    except Exception:
        yyyymm = "YYYYMM"
    agencia = (cab.agencia or "AG")
    conta   = (cab.conta or "CONTA")
    output_dir.mkdir(parents=True, exist_ok=True)
    out_xlsx = output_dir / f"royalties_extrato_safra_{agencia}_{conta}_{yyyymm}.xlsx"

    # Salva XLSX (sobrescreve)
    canais_excluir = ["RESGATE", "SALDO", "APLICACAO"]
    try:
        df = df[~df["canal"].isin(canais_excluir)].reset_index(drop=True)
        df = df[df["valor"] > 0].reset_index(drop=True)
        df.to_excel(out_xlsx, index=False)
        print(f"[OK] {pdf_path.name} -> {out_xlsx}")
        return out_xlsx
    except Exception as e:
        print(f"[ERRO] Falha ao salvar XLSX para {pdf_path.name}: {e}")
        return None

def main():
    input_value = os.environ.get("MUV_SAFRA_INPUT_DIR")
    output_value = os.environ.get("MUV_SAFRA_OUTPUT_DIR")
    if not input_value or not output_value:
        raise SystemExit("Defina MUV_SAFRA_INPUT_DIR e MUV_SAFRA_OUTPUT_DIR; nenhuma configuração operacional é assumida.")
    input_dir = Path(input_value).expanduser()
    output_dir = Path(output_value).expanduser()
    if not input_dir.is_dir():
        raise SystemExit("MUV_SAFRA_INPUT_DIR deve apontar para um diretório existente.")
    if output_dir.exists() and not output_dir.is_dir():
        raise SystemExit("MUV_SAFRA_OUTPUT_DIR deve apontar para um diretório ou um novo caminho de saída.")
    pdfs = sorted(input_dir.glob("*.pdf"))
    if not pdfs:
        print(f"[AVISO] Nenhum PDF encontrado em: {input_dir}")
        return

    print(f"[INFO] Encontrados {len(pdfs)} PDF(s) em {input_dir}")
    for pdf in pdfs:
        processar_pdf(pdf, output_dir=output_dir)

if __name__ == "__main__":
    main()
