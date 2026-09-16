"""Run with: streamlit run recebimentos/process_extrato/streamlit_ops_app.py"""
from __future__ import annotations

from datetime import date
from html import escape

import streamlit as st

from ops_ui.context import ENTITIES, OpsContext, resolve_competence
from ops_ui.presentation import brl, status_class
from ops_ui.providers import LiveProviderUnavailable, provider_from_environment
from ops_ui.services import MonthPreparationAdapter, close_action


def badge(status: str) -> str:
    return f'<span class="status {status_class(status)}">{escape(status)}</span>'


def configure() -> None:
    st.set_page_config(page_title="MUV Royalties Ops", layout="wide", initial_sidebar_state="expanded", menu_items={"Get Help": None, "Report a bug": None, "About": None})
    st.markdown("""<style>
    .block-container {box-sizing:border-box;padding:2.6rem 1.35rem 2rem;width:100%;max-width:1540px}.app-header{box-sizing:border-box;width:100%;display:flex;gap:1.25rem;align-items:center;min-height:42px;border-bottom:1px solid #e5e7eb;padding:.2rem 0 .7rem;margin:0 0 1.05rem}.app-name{font-size:1.23rem;font-weight:700;color:#172033;white-space:nowrap}.header-context{font-size:.83rem;color:#4b5563;line-height:1.35;min-width:220px}.header-state{font-size:.78rem;color:#4b5563;white-space:nowrap;margin-left:auto}
    .status{display:inline-block;padding:.15rem .46rem;border-radius:999px;font-size:.68rem;font-weight:700;letter-spacing:.025em;line-height:1.2;white-space:nowrap}.ok{background:#e7f4ec;color:#23613b}.warn{background:#fff5df;color:#875c0a}.bad{background:#fae9e8;color:#9b302b}.neutral{background:#eef0f3;color:#4b5563}
    .kpi-card,.finance-card{height:100%;box-sizing:border-box;border:1px solid #e5e7eb;border-radius:8px;padding:.58rem .72rem;background:#fff}.kpi-label,.finance-label{font-size:.73rem;color:#6b7280;line-height:1.1;min-height:1.65rem}.kpi-value{font-size:1.35rem;font-weight:700;color:#172033;line-height:1.15}.finance-value{font-size:1.14rem;font-weight:700;color:#172033;line-height:1.25;white-space:nowrap;overflow:visible}
    .section-title{font-size:1.03rem;font-weight:680;color:#172033;margin:1.2rem 0 .45rem}.operator-head,.operator-row{display:grid;grid-template-columns:1.45fr 1.15fr 1.5fr 1.38fr .72fr;gap:.7rem;align-items:center}.operator-head{padding:.2rem .7rem;color:#6b7280;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.025em}.operator-row{border:1px solid #e5e7eb;border-radius:7px;padding:.48rem .7rem;margin:.28rem 0;background:#fff;min-height:45px}.operator-source{font-weight:680;color:#172033}.operator-detail{font-size:.78rem;color:#5d6675;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.operator-number{font-size:.8rem;color:#374151;white-space:nowrap}
    .source-card,.control-row,.audit-row{border:1px solid #e5e7eb;border-radius:7px;padding:.52rem .7rem;margin:.3rem 0;background:#fff}.source-card{display:flex;align-items:center;gap:.65rem;min-height:40px;min-width:0}.source-message{font-size:.8rem;color:#5d6675;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.source-meta{font-size:.75rem;color:#6b7280;white-space:nowrap;flex:0 0 auto}.source-card .status{flex:0 0 auto}.notice-compact{font-size:.82rem;padding:.48rem .65rem;border-radius:7px;background:#f6f8fb;color:#4b5563;border:1px solid #e5e7eb;margin:.65rem 0}
    .review-shell{border:1px solid #dfe4ec;border-radius:9px;padding:.75rem;margin:.45rem 0 .7rem;background:#fff}.review-heading{display:flex;justify-content:space-between;align-items:center;margin-bottom:.55rem}.evidence{border:1px solid #e5e7eb;border-radius:7px;padding:.6rem .7rem;min-height:104px}.evidence-label{font-size:.72rem;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.025em}.evidence-value{font-size:1.15rem;font-weight:700;color:#172033;margin:.18rem 0}.review-difference{font-size:1.1rem;font-weight:700;color:#9b302b;white-space:nowrap}.review-copy{font-size:.82rem;color:#4b5563;line-height:1.4}
    .control-row{display:flex;align-items:center;gap:.65rem;min-height:39px}.control-name{font-weight:650;min-width:190px;color:#172033}.control-detail{font-size:.8rem;color:#5d6675;flex:1}.close-panel{border:1px solid #e8c8c6;border-radius:9px;padding:.8rem .9rem;background:#fffafa;margin-top:.85rem}.close-title{font-size:1rem;font-weight:700;color:#7f2925}.close-copy{font-size:.83rem;color:#6b3c39;margin-top:.15rem}
    .audit-head,.audit-row{display:grid;grid-template-columns:1fr 1.3fr .8fr 1fr .85fr 2.2fr;gap:.65rem;align-items:center}.audit-head{padding:.25rem .7rem;font-size:.7rem;color:#6b7280;font-weight:700;text-transform:uppercase}.audit-row{font-size:.8rem;min-height:39px}.audit-detail{color:#5d6675}
    [data-testid="stSidebar"]{min-width:242px;max-width:242px}[data-testid="stSidebar"] .stRadio label{padding:.17rem 0;font-weight:500;color:#374151}[data-testid="stSidebar"] .stSelectbox label,[data-testid="stSidebar"] .stTextInput label{font-weight:650;color:#1f2937}
    @media(max-width:1100px){.operator-head,.operator-row{grid-template-columns:1.35fr 1fr 1.2fr 1.15fr .6fr;gap:.4rem}.operator-detail{font-size:.72rem}.audit-head,.audit-row{grid-template-columns:.85fr 1.1fr .7fr .9fr .8fr 1.5fr;gap:.4rem}.app-header{gap:.65rem}.header-context{font-size:.75rem}}
    </style>""", unsafe_allow_html=True)


def sidebar() -> tuple[OpsContext, str]:
    with st.sidebar:
        st.caption("MUV ROYALTIES OPS")
        st.markdown("##### Contexto operacional")
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
        st.markdown("##### Navegação")
        page = st.radio("Seção", ["Visão Geral", "Recebimentos", "Conciliação", "Revisão", "Fechamento", "Auditoria"], label_visibility="collapsed")
    return OpsContext(entity, competence), page


def header(context: OpsContext, state: str, mode: str) -> None:
    st.markdown(f'<div class="app-header"><div class="app-name">MUV Royalties Ops</div>{badge(mode)}<div class="header-context">{escape(context.entity_name)}<br>{escape(context.period_label)}</div><div class="header-state">Estado do mês&nbsp; {badge(state)}</div></div>', unsafe_allow_html=True)


def kpi(label: str, value: int) -> str:
    return f'<div class="kpi-card"><div class="kpi-label">{escape(label)}</div><div class="kpi-value">{value}</div></div>'


def overview(provider, context):
    item = provider.get_month_overview(context.entity, context.competence)
    cols = st.columns(6, gap="small")
    for col, label, value in zip(cols, ["Fontes esperadas", "Recebidas", "Pendentes", "Conciliação", "Revisão", "Exceções críticas"], [item.expected_sources, item.received_sources, item.pending_sources, item.reconciliation_pending, item.review_pending, item.critical_exceptions]):
        col.markdown(kpi(label, value), unsafe_allow_html=True)
    st.markdown('<div class="section-title">Fontes e situação operacional</div>', unsafe_allow_html=True)
    for source in provider.get_source_statuses(context.entity, context.competence):
        message = source.detail or "Sem pendências adicionais."
        meta = f"{source.pending_count} pendência(s)" if source.pending_count else "Sem pendências"
        st.markdown(f'<div class="source-card"><b>{escape(source.source)}</b>{badge(source.status)}<span class="source-message">{escape(message)}</span><span class="source-meta">{meta}</span></div>', unsafe_allow_html=True)


def receipts(provider, context):
    st.markdown('<div class="section-title">Operação de recebimentos</div>', unsafe_allow_html=True)
    st.caption("Ações nesta V1 são informativas ou simuladas. Nenhum portal é executado.")
    head, action_head = st.columns([8.5, 1.2], gap="small")
    head.markdown('<div class="operator-head"><span>Fonte</span><span>Status</span><span>Última execução / situação</span><span>Documentos / valor</span><span>Pendências</span></div>', unsafe_allow_html=True)
    action_head.markdown('<div class="operator-head" style="display:block;text-align:center">Ação</div>', unsafe_allow_html=True)
    for source in provider.get_source_statuses(context.entity, context.competence):
        row, action = st.columns([8.5, 1.2], gap="small")
        row.markdown(f'<div class="operator-row"><span class="operator-source">{escape(source.source)}</span>{badge(source.status)}<span class="operator-detail">{escape(source.last_execution or "—")}</span><span class="operator-number">{source.documents_found if source.documents_found is not None else "—"} docs · {brl(source.document_value)}</span><span class="operator-number">{source.pending_count}</span></div>', unsafe_allow_html=True)
        action.button(source.action, key=f"source-{source.source}", disabled=True, use_container_width=True)
    st.markdown('<div class="notice-compact">SOCINPRO: “Executar SOCINPRO” permanece desabilitado. Progresso, contas e downloads dependerão de adaptador seguro.</div>', unsafe_allow_html=True)
    prep = MonthPreparationAdapter().inspect(context.entity, context.competence)
    st.markdown('<div class="section-title">Preparação do mês</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="control-row"><span>{badge(prep.status)}</span><span class="control-detail">{escape(prep.detail)}</span></div>', unsafe_allow_html=True)
    st.caption(f"Pasta: {prep.month_folder}")
    st.button("Preparar mês", disabled=not prep.can_prepare, help="Disponível somente após o backend fornecer resultado bancário validado.")


def finance_card(label: str, value: str) -> str:
    return f'<div class="finance-card"><div class="finance-label">{escape(label)}</div><div class="finance-value">{escape(value)}</div></div>'


def reconciliation(provider, context):
    data = provider.get_reconciliation_summary(context.entity, context.competence)
    st.markdown('<div class="section-title">Conciliação</div>', unsafe_allow_html=True)
    a, b, c, d, e = st.columns([1.3, 1.55, 1.15, .85, .75], gap="small")
    a.markdown(finance_card("Banco", brl(data.bank_total)), unsafe_allow_html=True)
    b.markdown(finance_card("Fonte documental", brl(data.document_total)), unsafe_allow_html=True)
    c.markdown(finance_card("Diferença", brl(data.difference)), unsafe_allow_html=True)
    d.markdown(finance_card("Status", data.status), unsafe_allow_html=True)
    e.markdown(finance_card("Pendências", str(data.pending_count)), unsafe_allow_html=True)
    st.markdown('<div class="notice-compact">O banco é a verdade primária de caixa. Diferenças documentais permanecem visíveis e não são corrigidas automaticamente.</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="source-card"><b>Detalhe de reconciliação</b>{badge(data.status)}<span class="source-message">{data.record_count} registros considerados; evidências serão exibidas quando o serviço de backend estiver conectado.</span></div>', unsafe_allow_html=True)


def review(provider, context):
    st.markdown('<div class="section-title">Revisão humana</div>', unsafe_allow_html=True)
    for item in provider.get_review_items(context.entity, context.competence):
        st.markdown(f'<div class="review-shell"><div class="review-heading"><b>{escape(item.source)}</b>{badge("REVISÃO NECESSÁRIA")}</div>', unsafe_allow_html=True)
        bank, document = st.columns(2, gap="small")
        bank.markdown(f'<div class="evidence"><div class="evidence-label">Banco</div><div class="evidence-value">{brl(item.bank_value)}</div><div class="review-copy">Fonte primária de caixa<br>Entidade: {escape(item.entity)} · {escape(item.competence)}</div></div>', unsafe_allow_html=True)
        document.markdown(f'<div class="evidence"><div class="evidence-label">Documento / fonte</div><div class="evidence-value">{brl(item.document_value)}</div><div class="review-copy">Fonte: {escape(item.source)}<br>Evidência: {escape(item.evidence)}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="review-heading" style="margin-top:.65rem"><div><div class="evidence-label">Diferença</div><div class="review-difference">{brl(item.difference)}</div></div><div class="review-copy"><b>Motivo da revisão</b><br>{escape(item.reason)}<br><b>Observação</b><br>{escape(item.note)}</div></div></div>', unsafe_allow_html=True)
        a, b, c, _ = st.columns([1, 1, 1.25, 3.5], gap="small")
        a.button("Aprovar", key=f"approve-{item.item_id}", disabled=True, use_container_width=True)
        b.button("Rejeitar", key=f"reject-{item.item_id}", disabled=True, use_container_width=True)
        c.button("Manter pendente", key=f"pending-{item.item_id}", disabled=True, use_container_width=True)
    st.info("Decisões não são persistidas nesta V1. Ações serão habilitadas somente por serviço auditado.")


def closing(provider, context):
    st.markdown('<div class="section-title">Fechamento</div>', unsafe_allow_html=True)
    controls = provider.get_close_controls(context.entity, context.competence)
    for control in controls:
        st.markdown(f'<div class="control-row"><span class="control-name">{escape(control.label)}</span>{badge(control.status)}<span class="control-detail">{escape(control.detail)}</span></div>', unsafe_allow_html=True)
    action = close_action()
    blocked = sum(control.status not in {"PASS", "CONCILIADO", "FECHADO"} for control in controls)
    st.markdown(f'<div class="close-panel"><div class="close-title">Fechamento bloqueado</div><div class="close-copy">{blocked} controles ainda impedem o fechamento.</div></div>', unsafe_allow_html=True)
    st.button("Fechar competência", disabled=not action.allowed, help=action.detail)
    st.caption(action.detail)


def audit(provider, context):
    st.markdown('<div class="section-title">Auditoria</div>', unsafe_allow_html=True)
    f1, f2, f3 = st.columns(3, gap="small")
    event_type = f1.selectbox("Tipo de evento", ["Todos", "Consulta de competência", "Verificação de fechamento"])
    source = f2.selectbox("Fonte", ["Todas", "SOCINPRO", "Banco"])
    result = f3.selectbox("Status", ["Todos", "PASS", "BLOQUEADO"])
    st.markdown('<div class="audit-head"><span>Horário</span><span>Evento</span><span>Fonte</span><span>Ator</span><span>Resultado</span><span>Detalhe seguro</span></div>', unsafe_allow_html=True)
    for event in provider.get_audit_events(context.entity, context.competence):
        if event_type != "Todos" and event.operation != event_type:
            continue
        if source != "Todas" and event.source != source:
            continue
        if result != "Todos" and event.result != result:
            continue
        st.markdown(f'<div class="audit-row"><span>{escape(event.timestamp)}</span><b>{escape(event.operation)}</b><span>{escape(event.source)}</span><span>{escape(event.actor)}</span>{badge(event.result)}<span class="audit-detail">{escape(event.details)}</span></div>', unsafe_allow_html=True)


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
