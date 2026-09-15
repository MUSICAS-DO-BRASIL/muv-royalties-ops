"""V2 presentation components for the Bank Extraction operator screen.

The module deliberately owns layout and presentation only.  Domain state is
resolved by the entrypoint and supplied as immutable contexts/results.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st

from bank_extraction_context import EntityContext
from bank_extraction_core import BankExtractionResult, OperationalCredit
from bank_extraction_month_context import MonthContext
from month_preparation import MonthPreparationResult
from bank_extraction_status import bank_closure_status, source_mapping_status


APP_CSS = """
<style>
#MainMenu,footer,[data-testid="stHeader"],[data-testid="stToolbar"]{visibility:hidden;height:0}
[data-testid="stAppViewContainer"]{background:#f4f6f8;color:#14291f}
.block-container{max-width:1440px;padding:2rem 2.6rem 3rem}
[data-testid="stSidebar"]{background:#0d201a;border-right:1px solid #18352b}
[data-testid="stSidebar"] *{color:#e9f1ec!important}
.ops-brand{font-size:1.55rem;font-weight:760;letter-spacing:-.04em;margin:0}.ops-kicker{color:#98b8a8!important;font-size:.72rem;letter-spacing:.13em;text-transform:uppercase;margin:.1rem 0 2.2rem}.ops-nav-active{background:#18382c;border:1px solid #285041;border-radius:8px;padding:.66rem .72rem;font-weight:700;font-size:.9rem}.ops-nav-muted{color:#aec2b7!important;padding:.7rem .72rem;font-size:.88rem}.ops-context-label{color:#8fac9d!important;font-size:.67rem;letter-spacing:.11em;text-transform:uppercase;margin:1.9rem 0 .55rem}.ops-context-value{font-size:.86rem;line-height:1.65}.ops-footer{position:fixed;bottom:1.4rem;color:#8fac9d!important;font-size:.72rem}
.v2-header{display:flex;justify-content:space-between;align-items:flex-start;gap:1.4rem;margin:0 0 1.55rem}.v2-title{font-size:2rem;letter-spacing:-.045em;font-weight:760;color:#102a20;margin:0}.v2-subtitle{color:#64756d;font-size:.96rem;margin:.38rem 0 0}.v2-badges{display:flex;gap:.42rem;flex-wrap:wrap;justify-content:flex-end;padding-top:.16rem}.v2-badge{border:1px solid #d5dfda;background:#fff;color:#254437;border-radius:999px;padding:.32rem .58rem;font-size:.69rem;font-weight:760;letter-spacing:.05em}.v2-badge.pass{background:#e6f4eb;border-color:#bce2c8;color:#176238}.v2-badge.review{background:#fff4d9;border-color:#ecd39a;color:#805b0b}.v2-badge.blocked{background:#fbe8e8;border-color:#edc0c0;color:#9a2e2e}.v2-badge.waiting{background:#eef2f0;color:#596b62}
.v2-section{margin-top:1.45rem}.v2-section-title{font-size:.72rem;font-weight:780;letter-spacing:.11em;text-transform:uppercase;color:#687a71;margin:0 0 .55rem}.context-strip{display:grid;grid-template-columns:1.25fr 1.15fr .9fr;gap:.75rem;background:#fff;border:1px solid #dce5e0;border-radius:12px;padding:.8rem;box-shadow:0 3px 12px rgba(23,48,37,.04)}.bank-display{height:38px;border:1px solid #d9e2dc;border-radius:7px;padding:0 .7rem;display:flex;align-items:center;background:#f8faf9;color:#365447;font-size:.87rem;font-weight:650}.context-strip [data-testid="stSelectbox"],.context-strip [data-testid="stDateInput"]{margin:0}.context-strip label{display:none}
.v2-stepper{display:grid;grid-template-columns:repeat(4,1fr);background:#fff;border:1px solid #dce5e0;border-radius:12px;overflow:hidden}.v2-step{padding:.76rem .9rem;border-right:1px solid #e5ebe7;min-height:68px}.v2-step:last-child{border-right:0}.v2-step-number{color:#82928a;font-size:.68rem;font-weight:800;letter-spacing:.1em}.v2-step-name{font-size:.86rem;font-weight:720;color:#294438;margin:.18rem 0}.v2-step-state{font-size:.68rem;color:#7c8c83}.v2-step.current{box-shadow:inset 0 3px #177a52}.v2-step.current .v2-step-name{color:#17633e}.v2-step.done .v2-step-number{color:#177a52}.v2-step.review{box-shadow:inset 0 3px #c58d16}.v2-step.blocked{box-shadow:inset 0 3px #b84b4b}
.upload-panel,.month-panel,.empty-panel{background:#fff;border:1px solid #dce5e0;border-radius:12px;padding:1.2rem;box-shadow:0 3px 12px rgba(23,48,37,.035)}.upload-heading{font-size:1.05rem;font-weight:740;color:#1e392d;margin:0}.upload-detail{color:#718179;font-size:.83rem;margin:.24rem 0 .85rem}.file-summary{background:#f0f7f3;border:1px solid #cfe5d7;border-radius:8px;padding:.7rem .8rem;color:#25553b;font-size:.84rem;margin-bottom:.7rem}.primary-action{margin-top:.65rem}
.metric-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:.65rem}.metric{background:#fff;border:1px solid #dce5e0;border-radius:10px;padding:.85rem .95rem;min-height:78px}.metric-label{color:#708178;font-size:.67rem;font-weight:780;letter-spacing:.08em;text-transform:uppercase}.metric-value{color:#18372a;font-size:1.3rem;font-weight:760;letter-spacing:-.025em;margin-top:.35rem}.status-panel{margin:.75rem 0;background:#eef7f1;border:1px solid #cae7d3;border-radius:9px;padding:.72rem .85rem;color:#28563c;font-size:.85rem}.status-panel.review{background:#fff6e4;border-color:#eed5a2;color:#7b5a0e}.status-panel.blocked{background:#fff0f0;border-color:#efcaca;color:#8d3232}
.table-toolbar{display:flex;justify-content:space-between;align-items:center;gap:.8rem;margin-bottom:.45rem}.month-file{color:#62746a;font-size:.82rem;margin:.2rem 0 .7rem}.month-ready{font-size:1rem;font-weight:730;color:#17633e;margin:.25rem 0}.month-blocked{font-size:.88rem;color:#826218;margin:.25rem 0}.technical-details [data-testid="stExpander"]{background:#fff;border:1px solid #dce5e0;border-radius:9px}.empty-title{font-weight:730;color:#284337}.empty-copy{font-size:.85rem;color:#718179;margin:.18rem 0 0}
@media(max-width:960px){.block-container{padding:1.2rem}.v2-header{display:block}.v2-badges{justify-content:flex-start;margin-top:.85rem}.context-strip,.metric-grid{grid-template-columns:repeat(2,1fr)}.v2-stepper{grid-template-columns:repeat(2,1fr)}.v2-step:nth-child(2){border-right:0}.v2-step:nth-child(-n+2){border-bottom:1px solid #e5ebe7}}
</style>
"""


def brl(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def period_label(period: str, *, short: bool = False) -> str:
    months = ("Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro")
    year, month = period.split("-")
    name = months[int(month) - 1]
    return f"{name[:3].upper()} {year}" if short else f"{name} de {year}"


def badge(value: str) -> str:
    """Render either a neutral context badge or a semantic status badge."""
    css = {"PASS": "pass", "REVIEW": "review", "BLOCKED": "blocked"}.get(value, "waiting")
    return f'<span class="v2-badge {css}">{value}</span>'


def page_shell() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)


def sidebar(context: EntityContext) -> None:
    with st.sidebar:
        st.markdown('<p class="ops-brand">MUV</p><p class="ops-kicker">Royalties Finance Ops</p>', unsafe_allow_html=True)
        st.markdown('<div class="ops-nav-active">Extração Bancária</div><div class="ops-nav-muted">Histórico</div>', unsafe_allow_html=True)
        st.markdown('<p class="ops-context-label">Contexto atual</p>', unsafe_allow_html=True)
        st.markdown(f'<div class="ops-context-value">{context.entity}<br>{context.bank}<br>{context.period[5:]}/{context.period[:4]}</div>', unsafe_allow_html=True)
        st.markdown('<p class="ops-footer">Ambiente operacional</p>', unsafe_allow_html=True)


def header(context: EntityContext, result: BankExtractionResult | None) -> None:
    status = result.status if result else "AGUARDANDO"
    badges = "".join((badge(context.entity), badge(context.bank), badge(period_label(context.period, short=True)), badge(status)))
    st.markdown(f'<div class="v2-header"><div><h1 class="v2-title">Extração Bancária</h1><p class="v2-subtitle">Valide o extrato bancário e prepare os recebimentos da competência.</p></div><div class="v2-badges">{badges}</div></div>', unsafe_allow_html=True)


def context_strip(context: EntityContext, period_date: date) -> tuple[str, date]:
    st.markdown('<div class="context-strip">', unsafe_allow_html=True)
    entity_col, period_col, bank_col = st.columns((1.25, 1.15, .9))
    with entity_col:
        entity = st.selectbox("Entidade", ("MDB", "HM"), index=("MDB", "HM").index(context.entity), key="selected_entity", format_func=lambda value: "HM — Hurst Music" if value == "HM" else "MDB — Músicas do Brasil")
    with period_col:
        selected_period = st.date_input("Competência", value=period_date, format="DD/MM/YYYY", key="selected_period")
    with bank_col:
        st.markdown(f'<div class="bank-display">{context.bank_label} 🔒</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    return entity, selected_period


def stepper(result: BankExtractionResult | None) -> None:
    if result is None:
        states = (("01", "Extrato", "CURRENT", "Aguardando arquivo"), ("02", "Validação", "WAITING", ""), ("03", "Revisão", "WAITING", ""), ("04", "Conciliação", "WAITING", ""))
    else:
        review_state = "DONE" if result.status == "PASS" else "REVIEW" if result.status == "REVIEW" else "BLOCKED"
        states = (("01", "Extrato", "DONE", "Importado"), ("02", "Validação", "DONE" if not result.errors else "BLOCKED", "Concluída" if not result.errors else "Bloqueada"), ("03", "Revisão", review_state, result.status), ("04", "Conciliação", "CURRENT" if result.status == "PASS" else "WAITING", "Pronta" if result.status == "PASS" else "Aguardando"))
    items = []
    for number, title, state, detail in states:
        css = {"DONE": "done", "CURRENT": "current", "REVIEW": "review", "BLOCKED": "blocked", "WAITING": "waiting"}[state]
        items.append(f'<div class="v2-step {css}"><div class="v2-step-number">{number}</div><div class="v2-step-name">{title}</div><div class="v2-step-state">{detail}</div></div>')
    st.markdown('<div class="v2-stepper">' + "".join(items) + '</div>', unsafe_allow_html=True)


def upload_panel(context: EntityContext):
    st.markdown('<div class="v2-section"><p class="v2-section-title">Extrato bancário</p></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="upload-panel"><p class="upload-heading">Importar extrato {context.bank}</p><p class="upload-detail">PDF esperado: {context.upload_label}. O arquivo é processado temporariamente.</p>', unsafe_allow_html=True)
    uploaded = st.file_uploader("Selecione o extrato", type=("pdf",), label_visibility="collapsed", key="statement_upload")
    if uploaded:
        st.markdown(f'<div class="file-summary">{uploaded.name} · PDF · {uploaded.size / 1024:.1f} KB · pronto para validar</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    return uploaded


def metric(label: str, value: str) -> str:
    return f'<div class="metric"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>'


def status_panel(result: BankExtractionResult) -> None:
    mapping = source_mapping_status(result)
    closure = bank_closure_status(result)
    if result.status == "PASS":
        text, css = f"Extrato validado. Fechamento bancário {closure}; Fonte Pagadora {mapping}.", ""
    elif result.status == "REVIEW":
        text, css = f"{result.unknown_source_count} crédito(s) precisam de revisão de Fonte Pagadora. Fechamento bancário {closure}.", "review"
    else:
        text, css = "Processamento bloqueado. Revise o contexto e o extrato informado.", "blocked"
    st.markdown(f'<div class="status-panel {css}">{text}</div>', unsafe_allow_html=True)


def transaction_table(credits: tuple[OperationalCredit, ...]) -> None:
    st.markdown('<div class="v2-section"><p class="v2-section-title">Créditos identificados</p></div>', unsafe_allow_html=True)
    left, right = st.columns((1, 1.5))
    with left:
        choice = st.segmented_control("Filtro de status", ("Todos", "PASS", "REVIEW"), default="Todos", label_visibility="collapsed", key="credit_filter")
    with right:
        search = st.text_input("Buscar crédito", placeholder="Buscar descrição ou Fonte Pagadora", label_visibility="collapsed", key="credit_search").strip().casefold()
    rows = [item for item in credits if (choice == "Todos" or item.status == choice) and (not search or search in item.description.casefold() or search in item.payor_source.casefold())]
    st.dataframe([{"Data": item.transaction_date, "Descrição": item.description, "Fonte Pagadora": item.payor_source, "Crédito": item.credit, "Status": item.status} for item in rows], hide_index=True, width="stretch", column_config={"Data": st.column_config.DateColumn(format="DD/MM/YYYY"), "Crédito": st.column_config.NumberColumn(format="R$ %.2f"), "Status": st.column_config.TextColumn(width="small")})


def month_panel(month_context: MonthContext, result: BankExtractionResult | None = None,
                preparation: MonthPreparationResult | None = None) -> bool:
    st.markdown('<div class="v2-section"><p class="v2-section-title">Conciliação do mês</p></div>', unsafe_allow_html=True)
    if month_context.is_prepared:
        filename = month_context.workbook_path.name if month_context.workbook_path else "Workbook mensal"
        st.markdown(f'<div class="month-panel"><div class="month-ready">✓ Preparada</div><div class="month-file">{filename}</div></div>', unsafe_allow_html=True)
        st.button(month_context.action_label, disabled=True, key="month_action")
        return False
    else:
        if result is None:
            st.markdown('<div class="month-panel"><div class="month-blocked">Ainda não preparada</div><div class="month-file">Envie e valide o extrato para preparar a conciliação.</div></div>', unsafe_allow_html=True)
            st.button("Preparar conciliação", disabled=True, key="month_action")
            return False
        st.markdown('<div class="month-panel"><div class="month-blocked">Ainda não preparada</div>'
                    f'<div class="month-file">{result.entity} · {period_label(result.period)} · {result.credit_count or 0} recebimentos · {brl(result.total_credits)}</div></div>', unsafe_allow_html=True)
        allowed = preparation is not None and preparation.status == "REVIEW"
        return st.button("Preparar conciliação", type="primary", disabled=not allowed, key="month_action")


def empty_state() -> None:
    st.markdown('<div class="v2-section"><p class="v2-section-title">Resultado</p><div class="empty-panel"><div class="empty-title">Aguardando extrato</div><div class="empty-copy">Importe um PDF para validar os créditos da competência.</div></div></div>', unsafe_allow_html=True)


def processed_view(result: BankExtractionResult, service, month_context: MonthContext) -> None:
    st.markdown('<div class="v2-section"><p class="v2-section-title">Resumo do processamento</p></div>', unsafe_allow_html=True)
    metrics = (metric("Movimentações", str(result.technical_transaction_count or 0)), metric("Créditos", str(result.credit_count or 0)), metric("Total recebido", brl(result.total_credits)), metric("Pendências", str(result.unknown_source_count)), metric("Fechamento", bank_closure_status(result)))
    st.markdown('<div class="metric-grid">' + "".join(metrics) + '</div>', unsafe_allow_html=True)
    status_panel(result)
    transaction_table(result.operational_credits)
    with st.expander("Detalhes da validação bancária", expanded=False):
        st.json({"Saldo inicial": str(result.initial_balance) if result.initial_balance is not None else None, "Créditos": str(result.total_credits) if result.total_credits is not None else None, "Débitos": str(result.total_debits) if result.total_debits is not None else None, "Saldo final": str(result.final_balance) if result.final_balance is not None else None, "Contagem técnica": result.technical_transaction_count, "Fechamento bancário": bank_closure_status(result), "Fonte Pagadora": source_mapping_status(result), "Status geral": result.status})
    st.download_button("Baixar XLSX bancário", data=service.operational_xlsx_bytes(result), file_name=f"extrato_royalties_{result.period[5:]}_{result.period[:4]}.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="secondary")
