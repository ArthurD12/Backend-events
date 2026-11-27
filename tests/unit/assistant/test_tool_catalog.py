"""Herramientas del asistente con fakes de los `public_api`: permisos, parámetros y formato."""

import json
from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import uuid4

import pytest

from local_eventos.modules.assistant.application.tool_catalog import Lookups, build_tools, soles
from local_eventos.modules.assistant.application.tools import ToolRegistry
from local_eventos.modules.commercial.public_api import (
    ClientSummary,
    ContractStatus,
    EventAccount,
    EventDetail,
    EventFindResult,
    EventReportFilters,
    EventReportItem,
    EventStatus,
    EventSummary,
    EventType,
    QuoteFilters,
    QuotePage,
    QuoteStatus,
    QuoteSummary,
)
from local_eventos.modules.identity.domain.permissions import Role, permissions_of
from local_eventos.modules.inventory.public_api import (
    Category,
    EventRequirement,
    ProductInfo,
    ProductKind,
    RequirementLine,
    StockItem,
    Unit,
)
from local_eventos.modules.ledger.public_api import MonthlyCash
from local_eventos.modules.ledger.public_api import MovementCategory as Cat
from local_eventos.modules.purchasing.public_api import PurchaseReportItem, PurchaseStatus

EVENT_ID, CLIENT_ID, CONTRACT_ID, COORD_ID = uuid4(), uuid4(), uuid4(), uuid4()
SUMMARY = EventSummary(
    EVENT_ID, "EV-2026-0001", CONTRACT_ID, "José Ramírez", EventType.WEDDING,
    date(2026, 12, 19), time(20), time(3), "Los Jardines", 120, COORD_ID, EventStatus.CONFIRMED,
)  # fmt: skip
ITEM = EventReportItem(
    EVENT_ID, "EV-2026-0001", date(2026, 12, 19), "José Ramírez", EventType.WEDDING, 120,
    EventStatus.CONFIRMED, CONTRACT_ID, 1_000_000, 400_000, 600_000, True,
)  # fmt: skip
PAID_UP = EventReportItem(
    uuid4(), "EV-2026-0002", date(2026, 12, 20), "Ana", EventType.BIRTHDAY, 50,
    EventStatus.CONFIRMED, uuid4(), 100_000, 100_000, 0, False,
)  # fmt: skip
PRODUCT = ProductInfo(uuid4(), "INS-001", "Arroz", Unit.KG, ProductKind.CONSUMABLE, True)
STOCK = StockItem(PRODUCT, Category.SUPPLIES, Decimal(10), Decimal(4), 500, 2_000, True,
                  date(2026, 12, 1), True)  # fmt: skip


QUOTE = QuoteSummary(
    uuid4(), "COT-2026-0007", CLIENT_ID, "José Ramírez", EventType.WEDDING, date(2026, 12, 19),
    120, 1_250_000, QuoteStatus.EXPIRED, date(2026, 11, 20),
)  # fmt: skip


class Calls:
    def __init__(self) -> None:
        self.names: list[str] = []
        self.found: dict[str, Any] = {}


def _lookups(calls: Calls) -> Lookups:
    async def upcoming(days: int = 14) -> list[EventReportItem]:
        calls.names.append(f"upcoming:{days}")
        return [ITEM]

    async def report(filters: EventReportFilters) -> list[EventReportItem]:
        calls.names.append("report")
        return [ITEM, PAID_UP] if filters.client_id is None else [ITEM]

    async def search(text: str, limit: int = 10) -> list[EventSummary]:
        return [SUMMARY] if text.lower() in SUMMARY.code.lower() else []

    async def detail(event_id: Any) -> EventDetail:
        return EventDetail(
            EVENT_ID, "EV-2026-0001", EventStatus.CONFIRMED, EventType.WEDDING, date(2026, 12, 19),
            time(20), time(3), True, "Los Jardines", 120, COORD_ID, CONTRACT_ID,
            ClientSummary(CLIENT_ID, "José Ramírez", "DNI", "40000001", "987", None, True), (),
        )  # fmt: skip

    async def account(event_id: Any) -> EventAccount:
        return EventAccount(CONTRACT_ID, "CT-1", ContractStatus.SIGNED, 1_000_000, 400_000, 0,
                            600_000, date(2026, 12, 12), True, [])  # fmt: skip

    async def stock(*args: Any, **kwargs: Any) -> list[StockItem]:
        return [STOCK]

    async def requirement(event_id: Any) -> EventRequirement:
        line = RequirementLine(
            PRODUCT, Decimal(20), Decimal(0), Decimal(0), Decimal(4), Decimal(16)
        )
        return EventRequirement(EVENT_ID, "EV-2026-0001", EventStatus.CONFIRMED, True, 120,
                                [line], ["Brindis"])  # fmt: skip

    async def purchases(
        date_from: date, date_to: date, status: PurchaseStatus | None = None
    ) -> list[PurchaseReportItem]:
        assert status is not None
        return [PurchaseReportItem(uuid4(), "COM-1", date(2026, 11, 1), "Makro", status, None,
                                   None, None)]  # fmt: skip

    async def cash(date_from: date, date_to: date) -> list[MonthlyCash]:
        return [
            MonthlyCash(
                2026, 11, 800_000, 50_000, {Cat.SUPPLIES: 200_000, Cat.OTHER_INCOME: 10_000}
            )
        ]

    async def clients(text: str, limit: int = 10) -> list[ClientSummary]:
        one = ClientSummary(CLIENT_ID, "José Ramírez", "DNI", "40000001", "987", None, True)
        two = ClientSummary(uuid4(), "José Ramírez", "DNI", "40000002", "988", None, True)
        return [one, two] if text == "José" else []

    async def find(**kwargs: Any) -> EventFindResult:
        calls.found["events"] = kwargs
        return EventFindResult([SUMMARY], 1)

    async def quotes(filters: QuoteFilters, *, page: int = 1, page_size: int = 20) -> QuotePage:
        calls.found["quotes"] = filters
        return QuotePage([QUOTE], 1, page, page_size)

    async def names(ids: Any) -> dict[Any, str]:
        return {COORD_ID: "María Pérez"}

    return Lookups(
        today=lambda: date(2026, 11, 26), upcoming_events=upcoming, events_report=report,
        events_search=search, events_find=find, quotes_search=quotes, event_detail=detail,
        event_account=account, stock_report=stock,
        event_requirement=requirement, purchases_report=purchases, cash_totals=cash,
        clients_search=clients, user_names=names,
    )  # fmt: skip


CALLS = Calls()


@pytest.fixture
def tools() -> ToolRegistry:
    CALLS.found.clear()
    return build_tools(_lookups(CALLS))


ADMIN = frozenset(p.value for p in permissions_of(Role.ADMIN))
PURCHASER = frozenset(p.value for p in permissions_of(Role.PURCHASING_MANAGER))


async def run(tools: ToolRegistry, name: str, data: dict[str, Any], perms: frozenset[str] = ADMIN):
    outcome = await tools.execute(name, data, perms)
    return json.loads(outcome.content), outcome.is_error


def test_specs_are_strict_and_stable(tools: ToolRegistry) -> None:
    specs = tools.specs()
    assert len(specs) == 13 and len({s.name for s in specs}) == 13
    for spec in specs:
        assert spec.input_schema["additionalProperties"] is False
        assert spec.input_schema["type"] == "object"


def test_soles_format() -> None:
    assert soles(123_456) == "S/ 1,234.56"


async def test_upcoming_events(tools: ToolRegistry) -> None:
    data, err = await run(tools, "upcoming_events", {"days": 7})
    assert not err and data["eventos"][0]["codigo"] == "EV-2026-0001"
    assert data["eventos"][0]["fecha"] == "19/12/2026" and "saldo" not in json.dumps(data)


async def test_invalid_days_is_input_error(tools: ToolRegistry) -> None:
    data, err = await run(tools, "upcoming_events", {"days": 500})
    assert err and data["error"] == "parametros_invalidos"


async def test_event_detail_and_ambiguity(tools: ToolRegistry) -> None:
    data, _ = await run(tools, "event_detail", {"code": "EV-2026-0001"})
    assert data["responsable"] == "María Pérez" and data["cliente"] == "José Ramírez"
    assert data["horario"].endswith("(del día siguiente)")
    missing, _ = await run(tools, "event_detail", {"code": "EV-9999"})
    assert missing["error"] == "sin_datos"


async def test_event_account_in_soles(tools: ToolRegistry) -> None:
    data, _ = await run(tools, "event_account", {"code": "EV-2026-0001"})
    assert (data["total"], data["pagado"], data["saldo"]) == (
        "S/ 10,000.00",
        "S/ 4,000.00",
        "S/ 6,000.00",
    )
    assert data["vencido"] is True and data["vence"] == "12/12/2026"


async def test_pending_collections_skip_paid_events(tools: ToolRegistry) -> None:
    data, _ = await run(tools, "pending_collections", {})
    assert [e["codigo"] for e in data["eventos"]] == ["EV-2026-0001"]
    assert data["saldo_total"] == "S/ 6,000.00"


async def test_stock_and_alerts(tools: ToolRegistry) -> None:
    data, _ = await run(tools, "stock", {"product": "arroz"})
    assert data["productos"][0]["stock"] == "4"
    none, _ = await run(tools, "stock", {"product": "queso"})
    assert none["error"] == "sin_datos"
    alerts, _ = await run(tools, "stock_alerts", {"kind": "low"})
    assert alerts["total_stock_bajo"] == 1 and "por_vencer" not in alerts


async def test_event_requirement_lists_only_shortages(tools: ToolRegistry) -> None:
    data, _ = await run(tools, "event_requirement", {"code": "EV-2026-0001"})
    assert data["faltantes"][0]["falta"] == "16" and data["servicios_sin_receta"] == ["Brindis"]


async def test_open_purchases(tools: ToolRegistry) -> None:
    data, _ = await run(tools, "open_purchases", {})
    assert data["total"] == 2 and {c["estado"] for c in data["compras"]} == {"REQUESTED", "ORDERED"}


async def test_cash_flow_month(tools: ToolRegistry) -> None:
    data, _ = await run(tools, "cash_flow", {"year": 2026, "month": 11})
    assert (data["ingresos"], data["egresos"], data["neto"]) == (
        "S/ 7,600.00", "S/ 2,000.00", "S/ 5,600.00",
    )  # fmt: skip


async def test_clients_ambiguity_and_history(tools: ToolRegistry) -> None:
    found, _ = await run(tools, "search_clients", {"name": "José"})
    assert len(found["clientes"]) == 2 and "aclaración" in found["aviso"]
    history, _ = await run(tools, "client_history", {"client_id": str(CLIENT_ID)})
    assert history["total_contratado"] == "S/ 10,000.00" and history["saldo"] == "S/ 6,000.00"
    bad, err = await run(tools, "client_history", {"client_id": "no-es-uuid"})
    assert err and bad["error"] == "parametros_invalidos"


@pytest.mark.parametrize(
    ("tool", "data"),
    [
        ("event_account", {"code": "EV"}), ("pending_collections", {}),
        ("cash_flow", {}), ("search_clients", {"name": "x"}),
        ("client_history", {"client_id": str(uuid4())}),
    ],
)  # fmt: skip
async def test_purchasing_manager_lacks_permission(
    tools: ToolRegistry, tool: str, data: dict[str, Any]
) -> None:
    result, err = await run(tools, tool, data, PURCHASER)
    assert err and result == {"error": "sin_permiso"}


async def test_purchasing_manager_can_read_stock_and_purchases(tools: ToolRegistry) -> None:
    for tool, data in (
        ("stock_alerts", {}),
        ("open_purchases", {}),
        ("event_requirement", {"code": "EV-2026-0001"}),
    ):
        _, err = await run(tools, tool, data, PURCHASER)
        assert not err


async def test_events_manager_cannot_read_cash_but_can_read_collections(
    tools: ToolRegistry,
) -> None:
    manager = frozenset(p.value for p in permissions_of(Role.EVENTS_MANAGER))
    _, denied = await run(tools, "cash_flow", {}, manager)
    _, allowed = await run(tools, "pending_collections", {}, manager)
    assert denied and not allowed


async def test_search_events_passes_filters_and_formats(tools: ToolRegistry) -> None:
    data, err = await run(
        tools,
        "search_events",
        {
            "date_from": "2026-12-01",
            "client": "José",
            "event_type": "WEDDING",
            "status": "CONFIRMED",
        },
    )
    assert not err and data["total"] == 1
    assert data["eventos"][0] == {
        "codigo": "EV-2026-0001", "fecha": "19/12/2026", "cliente": "José Ramírez",
        "tipo": "WEDDING", "invitados": 120, "estado": "CONFIRMED",
    }  # fmt: skip
    sent = CALLS.found["events"]
    assert sent["text"] == "José" and sent["event_type"] is EventType.WEDDING
    assert sent["status"] is EventStatus.CONFIRMED and sent["date_from"] == date(2026, 12, 1)


async def test_search_events_without_filters_starts_today(tools: ToolRegistry) -> None:
    await run(tools, "search_events", {})
    assert CALLS.found["events"]["date_from"] == date(2026, 11, 26)


@pytest.mark.parametrize(
    "bad",
    [
        {"date_from": "19/12/2026"},
        {"date_from": "2026-12-20", "date_to": "2026-12-01"},
        {"event_type": "PARTY"},
        {"status": "LOST"},
    ],
)
async def test_search_events_rejects_bad_params(tools: ToolRegistry, bad: dict[str, Any]) -> None:
    data, err = await run(tools, "search_events", bad)
    assert err and data["error"] == "parametros_invalidos"


async def test_search_events_needs_events_read(tools: ToolRegistry) -> None:
    data, err = await run(tools, "search_events", {}, frozenset({"inventory:read"}))
    assert err and data["error"] == "sin_permiso"
    assert (await run(tools, "search_events", {}, PURCHASER))[1] is False


async def test_search_quotes_formats_and_maps_status(tools: ToolRegistry) -> None:
    data, err = await run(
        tools,
        "search_quotes",
        {"status": "EXPIRED", "client": "José", "date_from": "2026-12-01", "date_to": "2026-12-31"},
    )
    assert not err and data["total"] == 1
    assert data["cotizaciones"][0] == {
        "codigo": "COT-2026-0007", "cliente": "José Ramírez", "fecha_evento": "19/12/2026",
        "total": "S/ 12,500.00", "estado": "vencida", "vigente_hasta": "20/11/2026",
    }  # fmt: skip
    sent = CALLS.found["quotes"]
    assert sent.status is QuoteStatus.EXPIRED and sent.text == "José"
    assert sent.event_date_from == date(2026, 12, 1) and sent.event_date_to == date(2026, 12, 31)


async def test_search_quotes_needs_quotes_manage(tools: ToolRegistry) -> None:
    data, err = await run(tools, "search_quotes", {}, PURCHASER)
    assert err and data["error"] == "sin_permiso"
    manager = frozenset(p.value for p in permissions_of(Role.EVENTS_MANAGER))
    assert (await run(tools, "search_quotes", {}, manager))[1] is False


async def test_search_quotes_rejects_unknown_status(tools: ToolRegistry) -> None:
    data, err = await run(tools, "search_quotes", {"status": "LOST"})
    assert err and data["error"] == "parametros_invalidos"
