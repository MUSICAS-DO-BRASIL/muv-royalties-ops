"""Thin V2 Streamlit entrypoint; domain behaviour remains in the backend modules."""
from __future__ import annotations

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import streamlit as st

from bank_extraction_context import resolve_entity_context, validate_processing_context
from bank_extraction_core import BankExtractionService
from bank_extraction_month_context import resolve_month_context
from bank_extraction_ui import context_strip, empty_state, header, month_panel, page_shell, processed_view, sidebar, stepper, upload_panel
from month_preparation import MonthPreparationService, default_competence


st.set_page_config(page_title="Extração Bancária | MUV", page_icon="M", layout="wide", initial_sidebar_state="expanded")


def current_context():
    selected_entity = st.session_state.get("selected_entity", "MDB")
    selected_period = st.session_state.get("selected_period", date.fromisoformat(default_competence(date.today()) + "-01"))
    return resolve_entity_context(selected_entity, selected_period.strftime("%Y-%m")), selected_period


def run() -> None:
    service = BankExtractionService()
    preparation_service = MonthPreparationService()
    st.session_state.setdefault("result", None)
    context, period_date = current_context()
    # This is the single month discovery for the entire rerun.
    month_context = resolve_month_context(service, context.entity, context.period)
    result = st.session_state.result
    visible_result = result if result and result.entity == context.entity and result.period == context.period else None

    page_shell()
    sidebar(context)
    header(context, visible_result)
    entity, selected_period = context_strip(context, period_date)
    if entity != context.entity or selected_period != period_date:
        st.rerun()

    stepper(visible_result)
    uploaded = upload_panel(context)
    if visible_result is None:
        if st.button("Processar extrato", type="primary", disabled=uploaded is None, key="process_statement"):
            try:
                with st.spinner("Validando extrato bancário..."):
                    validate_processing_context(context)
                    with TemporaryDirectory(prefix="muv-bank-") as temporary:
                        source = Path(temporary) / uploaded.name
                        source.write_bytes(uploaded.getvalue())
                        st.session_state.result = service.process(entity=context.entity, period=context.period, source_path=source)
                st.rerun()
            except Exception:
                st.session_state.result = None
                st.error("Não foi possível processar o extrato. Confirme a entidade, competência e arquivo enviados.")
        empty_state()
    else:
        processed_view(visible_result, service, month_context)
        preparation = preparation_service.discover(context.entity, context.period, visible_result)
        if month_panel(month_context, visible_result, preparation):
            prepared = preparation_service.prepare_month(context.entity, context.period, visible_result)
            if prepared.status == "PREPARED":
                st.success("Conciliação preparada com sucesso.")
                st.rerun()
            else:
                st.error("Não foi possível preparar a conciliação.")
                with st.expander("Ver detalhes", expanded=False):
                    st.write("\n".join(prepared.errors or prepared.warnings) or "A preparação requer uma validação adicional.")


if __name__ == "__main__":
    run()
