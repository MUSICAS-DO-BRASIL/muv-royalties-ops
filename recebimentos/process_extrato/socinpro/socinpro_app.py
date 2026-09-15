"""Minimal operator UI for a reviewed SOCINPRO extraction adapter."""
from __future__ import annotations
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import streamlit as st
from .socinpro_vertical import BankReference, CatalogRelation, parse_payment_row, process_socinpro

def run() -> None:
    st.set_page_config(page_title="SOCINPRO | MUV", page_icon="M", layout="wide")
    st.title("SOCINPRO")
    st.caption("Envie apenas uma extração já revisada. Relações incertas ficam em pendência.")
    entity = st.selectbox("Entidade", ("HM", "MDB"))
    competence = st.text_input("Competência", date.today().strftime("%Y-%m"))
    source = st.file_uploader("Arquivo SOCINPRO", type=["json"])
    if st.button("Processar", type="primary", disabled=source is None):
        try:
            payload = json.loads(source.getvalue())
            rows = tuple(parse_payment_row({**item, "entity": entity, "competence": competence}) for item in payload["payments"])
            bank = BankReference(entity, competence, "BTG" if entity == "HM" else "SAFRA", Decimal(str(payload["bank_total"])), "reviewed-bank-result")
            relations = {str(item["source_identity"]): CatalogRelation(str(item["catalog"]), str(item["deal"])) for item in payload.get("catalog_relations", [])}
            result = process_socinpro(entity=entity, competence=competence, payments=rows, bank_result=bank, catalog_resolver=lambda p: relations.get(p.source_identity))
            st.subheader("Resultado"); st.write({"status": result.status, "diferença": str(result.difference), "pendências": list(result.pending)})
        except Exception:
            st.error("Não foi possível processar. Confirme entidade, competência, arquivo e relações de catálogo.")
