from datetime import date

import pytest

from ops_ui.context import OpsContext, resolve_competence
from ops_ui.presentation import brl, status_class
from ops_ui.providers import DemoOpsDataProvider, LiveProviderUnavailable, provider_from_environment
from ops_ui.services import MonthPreparationAdapter, close_action


def test_default_competence_is_m1():
    assert resolve_competence(None, date(2026, 1, 15)) == "2025-12"
    assert resolve_competence(None, date(2026, 9, 16)) == "2026-08"


def test_historical_competence_override_and_period_label():
    assert resolve_competence("2024-02") == "2024-02"
    assert OpsContext("HM", "2024-02").period_label == "01/02/2024 → 29/02/2024"


def test_entity_context():
    assert OpsContext("MDB", "2026-08").entity_name == "Músicas do Brasil"


def test_demo_provider_is_explicit_and_typed():
    provider = DemoOpsDataProvider()
    overview = provider.get_month_overview("HM", "2026-08")
    assert provider.mode == "DEMO"
    assert overview.entity == "HM"
    assert provider.get_reconciliation_summary("HM", "2026-08").difference > 0


def test_live_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("MUV_OPS_MODE", "LIVE")
    with pytest.raises(LiveProviderUnavailable, match="bloqueada"):
        provider_from_environment()


def test_status_models_and_no_credentials_exposure():
    sources = DemoOpsDataProvider().get_source_statuses("HM", "2026-08")
    assert {source.status for source in sources} >= {"RECEBIDO", "REVISÃO NECESSÁRIA", "PENDENTE"}
    assert "senha" not in " ".join(source.detail.casefold() for source in sources)


def test_month_preparation_adapter_is_discovery_only(tmp_path):
    from month_preparation import MonthPreparationService
    adapter = MonthPreparationAdapter(MonthPreparationService(monthly_root=tmp_path, templates_root=tmp_path / "templates"))
    result = adapter.inspect("HM", "2026-08")
    assert result.can_prepare is False
    assert result.status in {"REVIEW", "BLOCKED"}


def test_close_control_fails_closed():
    action = close_action()
    assert action.allowed is False
    assert "auditado" in action.detail


def test_brl_formatting_is_complete_and_localized():
    from decimal import Decimal

    assert brl(Decimal("12500")) == "R$ 12.500,00"
    assert brl(Decimal("11800")) == "R$ 11.800,00"
    assert brl(Decimal("700")) == "R$ 700,00"
    assert "..." not in brl(Decimal("12500"))


def test_status_badges_have_a_shared_presentation_mapping():
    assert status_class("PASS") == "ok"
    assert status_class("RECEBIDO") == "ok"
    assert status_class("REVISÃO NECESSÁRIA") == "warn"
    assert status_class("BLOQUEADO") == "bad"
