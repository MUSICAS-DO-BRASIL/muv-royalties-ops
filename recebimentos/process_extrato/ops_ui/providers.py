"""Safe data-provider contract for the operator UI.

Demo data is deliberately synthetic. A LIVE provider must be explicitly
implemented and configured; it never falls back silently to demo data.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
import os

from .models import AuditEvent, CloseControl, MonthOverview, ReconciliationSummary, ReviewItem, SourceStatus


class LiveProviderUnavailable(RuntimeError):
    pass


class OpsDataProvider(ABC):
    mode: str

    @abstractmethod
    def get_month_overview(self, entity: str, competence: str) -> MonthOverview: ...
    @abstractmethod
    def get_source_statuses(self, entity: str, competence: str) -> list[SourceStatus]: ...
    @abstractmethod
    def get_reconciliation_summary(self, entity: str, competence: str) -> ReconciliationSummary: ...
    @abstractmethod
    def get_review_items(self, entity: str, competence: str) -> list[ReviewItem]: ...
    @abstractmethod
    def get_close_controls(self, entity: str, competence: str) -> list[CloseControl]: ...
    @abstractmethod
    def get_audit_events(self, entity: str, competence: str) -> list[AuditEvent]: ...


class DemoOpsDataProvider(OpsDataProvider):
    mode = "DEMO"

    def get_month_overview(self, entity: str, competence: str) -> MonthOverview:
        return MonthOverview(entity, competence, "REVISÃO NECESSÁRIA", 4, 2, 2, 1, 2, 1)

    def get_source_statuses(self, entity: str, competence: str) -> list[SourceStatus]:
        return [
            SourceStatus("Banco", "RECEBIDO", "Dados demonstrativos", 3, Decimal("12500.00"), 0, "Ver evidências"),
            SourceStatus("SOCINPRO", "REVISÃO NECESSÁRIA", "Não executado nesta interface", 2, Decimal("11800.00"), 1, "Abrir revisão", "Execução de portal permanece desabilitada."),
            SourceStatus("Documentação de apoio", "PENDENTE", None, 0, None, 1, "Processar", "Ação simulada em DEMO."),
            SourceStatus("Catálogo", "INATIVA", None, None, None, 0, "Ver evidências"),
        ]

    def get_reconciliation_summary(self, entity: str, competence: str) -> ReconciliationSummary:
        return ReconciliationSummary(Decimal("12500.00"), Decimal("11800.00"), Decimal("700.00"), "PARCIAL", 3, 1)

    def get_review_items(self, entity: str, competence: str) -> list[ReviewItem]:
        return [ReviewItem("demo-001", "SOCINPRO", entity, competence, Decimal("12500.00"), Decimal("11800.00"), Decimal("700.00"), "Diferença documental requer confirmação humana", "Comprovante demonstrativo disponível", "Nenhuma decisão foi persistida.")]

    def get_close_controls(self, entity: str, competence: str) -> list[CloseControl]:
        return [
            CloseControl("Recebimentos completos", "PENDENTE", "2 fontes ainda não concluídas."),
            CloseControl("Conciliação", "PARCIAL", "Há diferença entre banco e documentos."),
            CloseControl("Pendências", "PENDENTE", "1 pendência operacional."),
            CloseControl("Revisão humana", "PENDENTE", "2 itens aguardam decisão."),
            CloseControl("Diferenças", "CRÍTICO", "Diferença financeira não é corrigida automaticamente."),
            CloseControl("Publicação", "BLOQUEADO", "Disponível somente após aprovação do backend."),
        ]

    def get_audit_events(self, entity: str, competence: str) -> list[AuditEvent]:
        return [AuditEvent("Dados demonstrativos", "Operador DEMO", "Consulta de competência", entity, competence, "—", "PASS", "Dados sintéticos; nenhuma credencial ou payload de portal exibido."), AuditEvent("Dados demonstrativos", "Sistema", "Verificação de fechamento", entity, competence, "—", "BLOQUEADO", "Pré-requisitos não atendidos.")]


def provider_from_environment() -> OpsDataProvider:
    mode = os.getenv("MUV_OPS_MODE", "DEMO").strip().upper()
    if mode in {"", "DEMO"}:
        return DemoOpsDataProvider()
    if mode == "LIVE":
        raise LiveProviderUnavailable("Modo LIVE solicitado, mas nenhum provider LIVE homologado está configurado. A operação foi bloqueada com segurança.")
    raise LiveProviderUnavailable("MUV_OPS_MODE inválido. Use DEMO ou configure um provider LIVE homologado.")
