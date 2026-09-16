"""Run with: streamlit run recebimentos/process_extrato/streamlit_ops_app.py"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import streamlit as st

from ops_ui.context import ENTITIES, OpsContext, resolve_competence
from ops_ui.providers import LiveProviderUnavailable, provider_from_environment
from ops_ui.services import MonthPreparationAdapter, close_action


STATUS_CLASS = {"RECEBIDO": "ok", "CONCILIADO": "ok", "FECHADO": "ok", "PENDENTE": "warn", "PROCESSANDO": "warn", "PARCIAL": "warn", "REVISÃO NECESSÁRIA": "warn", "ATRASADO": "bad", "CRÍTICO": "bad", "DUPLICIDADE": "bad", "BLOQUEADO": "bad", "INATIVA": "neutral"}


def money(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def badge(status: str) -> str:
    css = STATUS_CLASS.get(status, "neutral")
    return f'<span class="status {css}">{status}</span>'


def configure() -> None:
    st.set_page_config(page_title="MUV Royalties Ops", layout="wide", initial_sidebar_state="expanded")
    st.markdown("""<style>
    .block-container {padding-top: 1.15rem; padding-bottom: 2rem; max-width: 1480px;}
    [data-testid="stMetric"] {border: 1px solid #e5e7eb; border-radius: 8px; padding: .55rem .75rem; background:#fff;}
    .status {display:inline-block;padding:.14rem .45rem;border-radius:999px;font-size:.72rem;font-weight:650;letter-spacing:.02em;}
    .ok{background:#dcfce7;color:#166534}.warn{background:#fef3c7;color:#92400e}.bad{background:#fee2e2;color:#991b1b}.neutral{background:#e5e7eb;color:#374151}
    .ops-card {border:1px solid #e5e7eb;border-radius:8px;padding:.75rem .85rem;margin:.35rem 0;background:#fff;}
    .muted{color:#6b7280;font-size:.85rem;}
    </style>""", unsafe_allow_html=True)


def sidebar() -> tuple[OpsContext, str]:
    with st.sidebar:
        st.caption("MUV ROYALTIES OPS")
        entity_name = st.selectbox("Entidade", list(ENTITIES.values()))
        entity = next(code for code, name in ENTITIES.items() if name == entity_name)
        suggested = resolve_competence(None, date.today())
        competence = st.text_input("Competência", value=st.session_state.get("ops_competence", suggested), help="Formato YYYY-MM. O padrão é M-1.")
        try:
            competence = resolve_competence(competence)
            st.session_state["ops_competence"] = competence
        except ValueError as error:
            st.error(str(error))
            competence = suggested
        page = st.radio("Navegação", ["Visão Geral", "Recebimentos", "Conciliação", "Revisão", "Fechamento", "Auditoria"])
    return OpsContext(entity, competence), page


def header(context: OpsContext, state: str, mode: str) -> None:
    left, middle, right, demo = st.columns([2.5, 2, 2, .7])
    left.markdown("### MUV Royalties Ops")
    middle.markdown(f"**Entidade**  \\n+{context.entity_name}")
    right.markdown(f"**Competência**  \\n+{context.period_label}")
    demo.markdown(badge(mode if mode == "DEMO" else state), unsafe_allow_html=True)
    st.caption(f"Estado do mês: {state}")


def overview(provider, context):
    item = provider.get_month_overview(context.entity, context.competence)
    cols = st.columns(6)
    for col, label, value in zip(cols, ["Fontes esperadas", "Recebidas", "Pendentes", "Conciliação", "Revisão", "Exceções críticas"], [item.expected_sources, item.received_sources, item.pending_sources, item.reconciliation_pending, item.review_pending, item.critical_exceptions]):
        col.metric(label, value)
    st.subheader("Fontes e situação operacional")
    for source in provider.get_source_statuses(context.entity, context.competence):
        st.markdown(f'<div class="ops-card"><b>{source.source}</b> &nbsp; {badge(source.status)}<br><span class="muted">{source.detail or "Sem pendências adicionais."}</span></div>', unsafe_allow_html=True)


def receipts(provider, context):
    st.subheader("Operação de recebimentos")
    st.caption("As ações desta V1 são informativas ou simuladas. Nenhum portal é executado.")
    for source in provider.get_source_statuses(context.entity, context.competence):
        columns = st.columns([2, 1.2, 1.2, 1.2, .8, 1])
        columns[0].write(source.source)
        columns[1].markdown(badge(source.status), unsafe_allow_html=True)
        columns[2].write(source.last_execution or "—")
        columns[3].write(f"{source.documents_found if source.documents_found is not None else '—'} docs · {money(source.document_value)}")
        columns[4].write(f"{source.pending_count} pend.")
        columns[5].button(source.action, key=f"source-{source.source}", disabled=True)
    st.info("SOCINPRO: a futura ação “Executar SOCINPRO” está intencionalmente desabilitada nesta interface. Progresso, contas e downloads dependerão de um adaptador seguro.")
    prep = MonthPreparationAdapter().inspect(context.entity, context.competence)
    st.subheader("Preparação do mês")
    st.markdown(f"{badge(prep.status)}  {prep.detail}", unsafe_allow_html=True)
    st.caption(f"Pasta: {prep.month_folder}")
    st.button("Preparar mês", disabled=not prep.can_prepare, help="Disponível somente após o backend fornecer resultado bancário validado.")


def reconciliation(provider, context):
    data = provider.get_reconciliation_summary(context.entity, context.competence)
    st.subheader("Conciliação")
    a, b, c, d, e = st.columns(5)
    a.metric("Banco", money(data.bank_total)); b.metric("Fonte documental", money(data.document_total)); c.metric("Diferença", money(data.difference)); d.markdown(badge(data.status), unsafe_allow_html=True); e.metric("Pendências", data.pending_count)
    st.warning("O banco é a verdade primária de caixa. Diferenças documentais permanecem visíveis e não são corrigidas automaticamente.")
    st.caption(f"Quantidade de registros: {data.record_count}. Evidências serão exibidas quando o serviço de backend estiver conectado.")


def review(provider, context):
    st.subheader("Revisão humana")
    for item in provider.get_review_items(context.entity, context.competence):
        st.markdown(f'<div class="ops-card"><b>{item.source}</b><br><span class="muted">Banco {money(item.bank_value)} · Documento {money(item.document_value)} · Diferença {money(item.difference)}<br>{item.reason}<br>Evidência: {item.evidence}<br>Observação: {item.note}</span></div>', unsafe_allow_html=True)
        a, b, c = st.columns(3)
        a.button("Aprovar", key=f"approve-{item.item_id}", disabled=True); b.button("Rejeitar", key=f"reject-{item.item_id}", disabled=True); c.button("Manter pendente", key=f"pending-{item.item_id}", disabled=True)
    st.info("Decisões não são persistidas nesta V1. Ações serão habilitadas somente por serviço auditado.")


def closing(provider, context):
    st.subheader("Fechamento")
    for control in provider.get_close_controls(context.entity, context.competence):
        st.markdown(f'<div class="ops-card"><b>{control.label}</b> &nbsp; {badge(control.status)}<br><span class="muted">{control.detail}</span></div>', unsafe_allow_html=True)
    action = close_action()
    st.button("Fechar e publicar competência", disabled=not action.allowed)
    st.error(action.detail)


def audit(provider, context):
    st.subheader("Auditoria")
    f1, f2, f3 = st.columns(3)
    event_type = f1.selectbox("Tipo de evento", ["Todos", "Consulta de competência", "Verificação de fechamento"])
    source = f2.selectbox("Fonte", ["Todas", "SOCINPRO", "Banco"])
    result = f3.selectbox("Status", ["Todos", "PASS", "BLOQUEADO"])
    for event in provider.get_audit_events(context.entity, context.competence):
        if event_type != "Todos" and event.operation != event_type: continue
        if source != "Todas" and event.source != source: continue
        if result != "Todos" and event.result != result: continue
        st.markdown(f'<div class="ops-card"><b>{event.operation}</b> &nbsp; {badge(event.result)}<br><span class="muted">{event.timestamp} · {event.actor} · {event.entity} · {event.competence} · {event.source}<br>{event.details}</span></div>', unsafe_allow_html=True)


def main() -> None:
    configure()
    context, page = sidebar()
    try:
        provider = provider_from_environment()
    except LiveProviderUnavailable as error:
        st.error(str(error))
        st.stop()
    overview_data = provider.get_month_overview(context.entity, context.competence)
    header(context, overview_data.state, provider.mode)
    {"Visão Geral": overview, "Recebimentos": receipts, "Conciliação": reconciliation, "Revisão": review, "Fechamento": closing, "Auditoria": audit}[page](provider, context)


if __name__ == "__main__":
    main()
