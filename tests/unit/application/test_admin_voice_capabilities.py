"""Chat ADMIN por voz: confirmación hablada, exportación y asientos dictados."""
from collections import deque
from datetime import date

import pytest

from app.infrastructure.admin_capabilities import AdminCapabilityService, _normalize_entry_lines
from app.infrastructure.admin_chat import AdminChatService, AdminCommand, capability_argument_hints


@pytest.mark.parametrize(
    ("transcript", "expected"),
    [
        ("Confirmo.", "confirm"),
        ("¡Confirmo!", "confirm"),
        ("Sí, confirmo.", "confirm"),
        ("Confirmo la operación.", "confirm"),
        ("Cancelo.", "cancel"),
        ("No, cancelo la propuesta.", "cancel"),
        ("Confirmo, pero cambia el monto a 200.", None),
        ("¿Confirmo?", "confirm"),
        ("Sí", None),
    ],
)
def test_spoken_confirmation_tolerates_transcription_punctuation(transcript, expected):
    assert AdminChatService._explicit_action(transcript, None) == expected


def test_report_export_returns_link_to_existing_endpoint_without_writing():
    result = AdminCapabilityService().read("accounting.reports.export", {
        "report": "ledger", "from_date": "2026-11-01", "to_date": "2026-11-30",
        "format": "csv", "account_code": "101",
    })
    assert result["download_url"] == (
        "/api/admin/accounting/reports/ledger?from_date=2026-11-01&to_date=2026-11-30"
        "&format=csv&account_code=101"
    )


@pytest.mark.parametrize(
    "arguments",
    [
        {"report": "journal", "from_date": "2026-11-30", "to_date": "2026-11-01"},
        {"report": "journal", "from_date": "2026-11-01", "to_date": "2026-11-30", "account_code": "101"},
        {"report": "balance", "from_date": "2026-11-01", "to_date": "2026-11-30"},
        {"report": "journal", "from_date": "2026-11-01", "to_date": "2026-11-30", "format": "pdf"},
    ],
)
def test_report_export_rejects_invalid_requests(arguments):
    with pytest.raises(ValueError):
        AdminCapabilityService().read("accounting.reports.export", arguments)


def test_dictated_entry_lines_drop_invented_ids_and_normalize_amounts():
    arguments = {
        "operation_date": "2026-11-09", "concept": "Servicio", "detail": "Cobro", "category_id": 2,
        "lines": [
            {"account_code": "101", "account_id": 101, "account_name": "Cuenta 101",
             "debit": "150", "credit": "0"},
            {"account_code": "70321", "debit": 0, "credit": "150.5"},
        ],
    }
    lines = _normalize_entry_lines(arguments)["lines"]
    assert lines == [
        {"account_code": "101", "debit": "150.00", "credit": "0.00"},
        {"account_code": "70321", "debit": "0.00", "credit": "150.50"},
    ]


class _AccountingCategories:
    """Categorías contables en memoria; el servicio ya no debe consultar la BD de .env."""

    def list_categories(self):
        return [{"id": 2, "code": "SERVICE", "name": "Servicio técnico"}]

    def create_entry(self, *_args, **_kwargs):
        raise AssertionError("La vista previa no debe registrar el asiento.")


class _AccountingCatalog:
    def list_plans(self):
        return [{"id": 1, "code": "PCGE_PE", "status": "ACTIVE", "is_default": True}]

    def get_postable_account(self, *, plan_id, operation_date, account_id=None, account_code=None):
        accounts = {"101": 1001, "70321": 1002}
        if plan_id == 1 and account_code in accounts:
            return {"id": accounts[account_code], "code": account_code, "plan_id": 1}
        return None


def _accounting_service():
    return AdminCapabilityService(
        accounting_repository_factory=_AccountingCategories,
        accounting_catalog_repository_factory=_AccountingCatalog,
    )


def test_dictated_entry_is_previewed_with_valid_schema_and_no_write():
    values, preview = _accounting_service().prepare("accounting.entries.create", {
        "operation_date": "2026-11-09", "concept": "Servicio de reparación",
        "detail": "Cobro en efectivo", "category_id": 2,
        "lines": [{"account_code": "101", "account_id": 101, "debit": "150", "credit": "0"},
                  {"account_code": "70321", "debit": "0", "credit": "150"}],
    }, actor_id=11)
    assert values["operation_date"] == date(2026, 11, 9)
    assert [line["debit"] for line in values["lines"]] == ["150.00", "0.00"]
    assert preview["action"] == "accounting.entries.create"


def test_argument_hints_cover_every_write_and_the_export():
    hints = capability_argument_hints()
    assert "accounting.entries.create:" in hints and "debit*:string" in hints
    assert "accounting.reports.export:" in hints
    assert "tickets.update: {ticket_id*:integer, values*:{" in hints


def test_parser_prefers_json_mode_and_falls_back_to_function_calling():
    calls = []

    class Model:
        def __init__(self):
            self.replies = deque([RuntimeError("tool_use_failed"),
                                  AdminCommand(intent="help")])

        def with_structured_output(self, _schema, **kwargs):
            calls.append(kwargs.get("method", "function_calling"))
            return self

        def invoke(self, _messages):
            reply = self.replies.popleft()
            if isinstance(reply, Exception):
                raise reply
            return reply

    from types import SimpleNamespace
    from app.settings import Settings

    service = AdminChatService.__new__(AdminChatService)
    from decimal import Decimal

    service.settings_factory = lambda: Settings(
        groq_api_key="k", groq_model="m", database_url="postgresql+pg8000://x/y",
        langsmith_api_key=None, langsmith_tracing=False, langsmith_project="tests",
        langsmith_hide_inputs=True, langsmith_hide_outputs=True,
        labor_maintenance_price=Decimal("35.00"), labor_diagnosis_price=Decimal("50.00"),
    )
    model = Model()
    service.model_factory = lambda _settings: model
    command = service._parse_command(SimpleNamespace(history=[]), "hierarchical", "hola")
    assert command.intent == "help"
    assert calls == ["json_mode", "function_calling"]
