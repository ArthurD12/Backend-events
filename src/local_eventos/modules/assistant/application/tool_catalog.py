"""Herramientas de consulta del asistente (CA-35.2). Cada una lee SOLO `public_api` de otros
módulos, exige su permiso (RN28) y no cambia nada (RN30).

Los montos salen ya en soles y las fechas en día/mes/año (hora de Lima) para que el modelo los
copie tal cual y no calcule ni convierta (CA-39.2).
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

from local_eventos.modules.assistant.application.tools import Tool, ToolInputError, ToolRegistry
from local_eventos.modules.commercial.public_api import (
    ClientSearchLookup,
    EventAccountLookup,
    EventDetailLookup,
    EventFindLookup,
    EventReportFilters,
    EventReportItem,
    EventReportLookup,
    EventSearchLookup,
    EventStatus,
    EventType,
    QuoteFilters,
    QuoteSearchLookup,
    QuoteStatus,
    UpcomingEventsLookup,
)
from local_eventos.modules.identity.public_api import Permission, UserNamesLookup
from local_eventos.modules.inventory.public_api import (
    EventRequirementLookup,
    StockItem,
    StockReportLookup,
)
from local_eventos.modules.ledger.public_api import CashTotalsLookup, MovementCategory
from local_eventos.modules.purchasing.public_api import PurchaseReportLookup, PurchaseStatus

MAX_ROWS = 15  # respuestas cortas: el modelo recibe a lo sumo estas filas
_OPEN_PURCHASES_WINDOW_DAYS = 730


@dataclass(frozen=True)
class Lookups:
    """Consultas de otros módulos (todas de `public_api`) que usan las herramientas."""

    today: Callable[[], date]  # hoy en Lima
    upcoming_events: UpcomingEventsLookup
    events_report: EventReportLookup
    events_search: EventSearchLookup
    events_find: EventFindLookup
    quotes_search: QuoteSearchLookup
    event_detail: EventDetailLookup
    event_account: EventAccountLookup
    stock_report: StockReportLookup
    event_requirement: EventRequirementLookup
    purchases_report: PurchaseReportLookup
    cash_totals: CashTotalsLookup
    clients_search: ClientSearchLookup
    user_names: UserNamesLookup


def soles(cents: int) -> str:
    return f"S/ {cents / 100:,.2f}"


def day(value: date | None) -> str | None:
    return None if value is None else value.strftime("%d/%m/%Y")


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _text(data: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = data.get(key)
    if value is None or value == "":
        if required:
            raise ToolInputError(f"Falta el parámetro «{key}».")
        return ""
    if not isinstance(value, str):
        raise ToolInputError(f"«{key}» debe ser texto.")
    return value.strip()


def _int(data: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise ToolInputError(f"«{key}» debe ser un entero entre {low} y {high}.")
    return value


def _choice[E: StrEnum](data: dict[str, Any], key: str, kind: type[E]) -> E | None:
    value = _text(data, key, required=False)
    if not value:
        return None
    try:
        return kind(value)
    except ValueError:
        allowed = ", ".join(m.value for m in kind)
        raise ToolInputError(f"«{key}» debe ser uno de: {allowed}.") from None


def _date(data: dict[str, Any], key: str) -> date | None:
    value = _text(data, key, required=False)
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ToolInputError(f"«{key}» debe tener el formato AAAA-MM-DD.") from None


def _date_range(data: dict[str, Any]) -> tuple[date | None, date | None]:
    date_from, date_to = _date(data, "date_from"), _date(data, "date_to")
    if date_from and date_to and date_from > date_to:
        raise ToolInputError("«date_from» no puede ser posterior a «date_to».")
    return date_from, date_to


def build_tools(lookups: Lookups) -> ToolRegistry:
    """Las herramientas del asistente. El orden y los textos son estables (caché del prompt)."""
    return ToolRegistry(
        [
            _upcoming_events(lookups),
            _event_detail(lookups),
            _event_account(lookups),
            _pending_collections(lookups),
            _stock(lookups),
            _stock_alerts(lookups),
            _event_requirement(lookups),
            _open_purchases(lookups),
            _cash_flow(lookups),
            _search_clients(lookups),
            _client_history(lookups),
            _search_events(lookups),
            _search_quotes(lookups),
        ]
    )


def _tool(
    name: str,
    description: str,
    schema: dict[str, Any],
    permission: Permission,
    handler: Callable[[dict[str, Any]], Awaitable[Any]],
) -> Tool:
    return Tool(name, description, schema, permission.value, handler)


# 1. Próximos eventos ------------------------------------------------------------------------
def _upcoming_events(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        days = _int(data, "days", 14, 1, 90)
        items = await lk.upcoming_events(days)
        return {
            "eventos": [
                {
                    "codigo": i.code,
                    "fecha": day(i.event_date),
                    "cliente": i.client_name,
                    "tipo": i.event_type.value,
                    "invitados": i.guests,
                    "estado": i.status.value,
                }
                for i in items[:MAX_ROWS]
            ],
            "total": len(items),
        }

    return _tool(
        "upcoming_events",
        "Próximos eventos (no cancelados ni finalizados) desde hoy hasta N días. "
        "Úsala para '¿qué eventos tengo esta semana?'.",
        _schema({"days": {"type": "integer", "description": "Días hacia adelante (1 a 90)"}}, []),
        Permission.EVENTS_READ,
        run,
    )


# 2. Detalle de un evento --------------------------------------------------------------------
async def _resolve_event(lk: Lookups, code: str) -> Any:
    """El evento por código exacto, o las coincidencias para pedir aclaración."""
    found = await lk.events_search(code, 5)
    exact = [e for e in found if e.code.lower() == code.lower()]
    if len(exact) == 1:
        return exact[0], None
    if len(found) == 1:
        return found[0], None
    if not found:
        return None, {"error": "sin_datos", "detalle": "No hay un evento con ese código."}
    return None, {
        "error": "ambiguo",
        "detalle": "Hay varios eventos que coinciden; pide al usuario que elija uno.",
        "coincidencias": [
            {"codigo": e.code, "cliente": e.client_name, "fecha": day(e.event_date)} for e in found
        ],
    }


def _event_detail(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        event, problem = await _resolve_event(lk, _text(data, "code"))
        if event is None:
            return problem
        detail = await lk.event_detail(event.id)
        if detail is None:
            return {"error": "sin_datos", "detalle": "No hay un evento con ese código."}
        names = await lk.user_names([detail.coordinator_id])
        return {
            "codigo": detail.code,
            "estado": detail.status.value,
            "tipo": detail.event_type.value,
            "fecha": day(detail.event_date),
            "horario": f"{detail.start_time:%H:%M} a {detail.end_time:%H:%M}"
            + (" (del día siguiente)" if detail.ends_next_day else ""),
            "lugar": detail.venue,
            "invitados": detail.guests,
            "responsable": names.get(detail.coordinator_id),
            "cliente": detail.client.name,
            "servicios": [s.description for s in detail.services[:MAX_ROWS]],
        }

    return _tool(
        "event_detail",
        "Detalle de un evento por su código (p. ej. EV-2026-0001): estado, fecha, horario, "
        "lugar, invitados, responsable, cliente y servicios.",
        _schema(
            {"code": {"type": "string", "description": "Código del evento o parte de él"}}, ["code"]
        ),  # fmt: skip
        Permission.EVENTS_READ,
        run,
    )


# 3. Cuenta de un evento ---------------------------------------------------------------------
def _event_account(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        event, problem = await _resolve_event(lk, _text(data, "code"))
        if event is None:
            return problem
        account = await lk.event_account(event.id)
        if account is None:
            return {"error": "sin_datos", "detalle": "El evento no tiene cuenta."}
        return {
            "evento": event.code,
            "contrato": account.contract_code,
            "total": soles(account.total_cents),
            "pagado": soles(account.paid_cents),
            "devuelto": soles(account.refunded_cents),
            "saldo": soles(account.balance_cents),
            "vence": day(account.balance_due_date),
            "vencido": account.overdue,
            "pagos": [
                {
                    "numero": p.number,
                    "monto": soles(p.amount_cents),
                    "fecha": day(p.paid_on),
                    "anulado": p.voided,
                }
                for p in account.payments[-MAX_ROWS:]
            ],
        }

    return _tool(
        "event_account",
        "Cuenta de un evento o su contrato: total, pagado, saldo, vencimiento y últimos pagos.",
        _schema({"code": {"type": "string", "description": "Código del evento"}}, ["code"]),
        Permission.PAYMENTS_RECORD,
        run,
    )


# 4. Cobros pendientes -----------------------------------------------------------------------
def _collection_row(item: EventReportItem) -> dict[str, Any]:
    return {
        "codigo": item.code,
        "cliente": item.client_name,
        "fecha": day(item.event_date),
        "total": soles(item.total_cents),
        "pagado": soles(item.paid_cents),
        "saldo": soles(item.balance_cents),
        "vencido": item.overdue,
    }


def _pending_collections(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        only_overdue = data.get("only_overdue", False)
        if not isinstance(only_overdue, bool):
            raise ToolInputError("«only_overdue» debe ser verdadero o falso.")
        items = await lk.events_report(EventReportFilters())
        pending = [
            i
            for i in items
            if i.balance_cents > 0
            and i.status is not EventStatus.CANCELLED
            and (i.overdue or not only_overdue)
        ]
        pending.sort(key=lambda i: (not i.overdue, i.event_date))
        return {
            "eventos": [_collection_row(i) for i in pending[:MAX_ROWS]],
            "total_eventos": len(pending),
            "saldo_total": soles(sum(i.balance_cents for i in pending)),
        }

    return _tool(
        "pending_collections",
        "Eventos con saldo por cobrar (código, cliente, fecha, total, pagado, saldo, vencido). "
        "Responde '¿qué eventos aún les falta completar pagos?'.",
        _schema({"only_overdue": {"type": "boolean", "description": "Solo saldos vencidos"}}, []),
        Permission.PAYMENTS_RECORD,
        run,
    )


# 5. Stock -----------------------------------------------------------------------------------
def _stock_row(item: StockItem) -> dict[str, Any]:
    return {
        "producto": item.product.name,
        "codigo": item.product.code,
        "unidad": item.product.unit.value,
        "stock": str(item.stock),
        "minimo": str(item.min_stock),
        "bajo_minimo": item.is_low_stock,
        "proximo_vencimiento": day(item.next_expiry),
        "por_vencer": item.expiring_soon,
    }


def _stock(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        text = _text(data, "product").lower()
        items = [i for i in await lk.stock_report() if text in i.product.name.lower()]
        if not items:
            return {"error": "sin_datos", "detalle": "No hay productos con ese nombre."}
        return {"productos": [_stock_row(i) for i in items[:MAX_ROWS]], "total": len(items)}

    return _tool(
        "stock",
        "Stock actual de un producto del almacén buscado por nombre (puede devolver varios).",
        _schema(
            {"product": {"type": "string", "description": "Nombre o parte del nombre"}}, ["product"]
        ),  # fmt: skip
        Permission.INVENTORY_READ,
        run,
    )


def _stock_alerts(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        kind = _text(data, "kind", required=False) or "both"
        if kind not in {"low", "expiring", "both"}:
            raise ToolInputError("«kind» debe ser low, expiring o both.")
        items = await lk.stock_report()
        low = [i for i in items if i.is_low_stock]
        expiring = [i for i in items if i.expiring_soon]
        result: dict[str, Any] = {}
        if kind in {"low", "both"}:
            result["stock_bajo"] = [_stock_row(i) for i in low[:MAX_ROWS]]
            result["total_stock_bajo"] = len(low)
        if kind in {"expiring", "both"}:
            result["por_vencer"] = [_stock_row(i) for i in expiring[:MAX_ROWS]]
            result["total_por_vencer"] = len(expiring)
        return result

    return _tool(
        "stock_alerts",
        "Productos con stock bajo el mínimo y/o por vencer.",
        _schema({"kind": {"type": "string", "enum": ["low", "expiring", "both"]}}, []),
        Permission.INVENTORY_READ,
        run,
    )


# 6. Requerimiento y faltantes ---------------------------------------------------------------
def _event_requirement(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        event, problem = await _resolve_event(lk, _text(data, "code"))
        if event is None:
            return problem
        req = await lk.event_requirement(event.id)
        if req is None:
            return {"error": "sin_datos", "detalle": "El evento no tiene requerimiento."}
        return {
            "evento": req.event_code,
            "calculado": req.calculated,
            "invitados": req.guests,
            "faltantes": [
                {
                    "producto": line.product.name,
                    "unidad": line.product.unit.value,
                    "requerido": str(line.required),
                    "disponible": str(line.available),
                    "falta": str(line.shortage),
                }
                for line in req.lines
                if line.shortage > 0
            ][:MAX_ROWS],
            "lineas_totales": len(req.lines),
            "servicios_sin_receta": req.without_recipe[:MAX_ROWS],
        }

    return _tool(
        "event_requirement",
        "Requerimiento de materiales de un evento y sus faltantes (lo que hay que comprar).",
        _schema({"code": {"type": "string", "description": "Código del evento"}}, ["code"]),
        Permission.INVENTORY_READ,
        run,
    )


# 7. Compras abiertas ------------------------------------------------------------------------
def _open_purchases(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        today = lk.today()
        start = today - timedelta(days=_OPEN_PURCHASES_WINDOW_DAYS)
        rows: list[dict[str, Any]] = []
        for status in (PurchaseStatus.REQUESTED, PurchaseStatus.ORDERED):
            for p in await lk.purchases_report(start, today, status):
                rows.append(
                    {
                        "codigo": p.code,
                        "estado": p.status.value,
                        "creada": day(p.created_on),
                        "proveedor": p.supplier_name,
                        "total": None if p.total_cents is None else soles(p.total_cents),
                    }
                )
        return {"compras": rows[:MAX_ROWS], "total": len(rows)}

    return _tool(
        "open_purchases",
        "Compras abiertas: solicitadas u ordenadas al proveedor y aún no recibidas.",
        _schema({}, []),
        Permission.PURCHASING_MANAGE,
        run,
    )


# 8. Flujo de caja ---------------------------------------------------------------------------
def _cash_flow(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        today = lk.today()
        year = _int(data, "year", today.year, 2020, 2100)
        month = _int(data, "month", today.month, 1, 12)
        first = date(year, month, 1)
        last = (date(year + (month == 12), month % 12 + 1, 1)) - timedelta(days=1)
        months = [
            m for m in await lk.cash_totals(first, last) if (m.year, m.month) == (year, month)
        ]
        if not months:
            return {"mes": f"{month:02d}/{year}", "movimientos": False}
        m = months[0]
        other_income = m.by_category.get(MovementCategory.OTHER_INCOME, 0)
        income = m.client_payments_cents - m.refunds_cents + other_income
        expenses = {
            c.value: v for c, v in m.by_category.items() if c is not MovementCategory.OTHER_INCOME
        }
        total_expenses = sum(expenses.values())
        return {
            "mes": f"{month:02d}/{year}",
            "ingresos": soles(income),
            "egresos": soles(total_expenses),
            "neto": soles(income - total_expenses),
            "devoluciones": soles(m.refunds_cents),
            "egresos_por_categoria": {k: soles(v) for k, v in expenses.items()},
        }

    return _tool(
        "cash_flow",
        "Flujo de caja de un mes: ingresos, egresos y neto. Por defecto, el mes actual.",
        _schema(
            {
                "year": {"type": "integer", "description": "Año (p. ej. 2026)"},
                "month": {"type": "integer", "description": "Mes de 1 a 12"},
            },
            [],
        ),
        Permission.FINANCE_READ,
        run,
    )


# 9. Clientes --------------------------------------------------------------------------------
def _search_clients(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        found = await lk.clients_search(_text(data, "name"), 6)
        if not found:
            return {"error": "sin_datos", "detalle": "No hay clientes con ese nombre."}
        result: dict[str, Any] = {
            "clientes": [
                {
                    "id": str(c.id),
                    "nombre": c.name,
                    "documento": f"{c.document_type} {c.document_number}",
                    "telefono": c.phone,
                    "activo": c.active,
                }
                for c in found
            ]
        }
        if len(found) > 1:
            result["aviso"] = "Hay varios clientes; pide aclaración antes de seguir."
        return result

    return _tool(
        "search_clients",
        "Busca clientes por nombre, documento o teléfono. Devuelve su id para client_history.",
        _schema(
            {"name": {"type": "string", "description": "Nombre o parte del nombre"}}, ["name"]
        ),  # fmt: skip
        Permission.CLIENTS_MANAGE,
        run,
    )


def _client_history(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        try:
            client_id = UUID(_text(data, "client_id"))
        except ValueError:
            raise ToolInputError("«client_id» no es un id válido; usa search_clients.") from None
        items = await lk.events_report(EventReportFilters(client_id=client_id))
        if not items:
            return {"error": "sin_datos", "detalle": "El cliente no tiene eventos."}
        return {
            "eventos": [_collection_row(i) | {"estado": i.status.value} for i in items[-MAX_ROWS:]],
            "total_eventos": len(items),
            "total_contratado": soles(sum(i.total_cents for i in items)),
            "total_pagado": soles(sum(i.paid_cents for i in items)),
            "saldo": soles(sum(i.balance_cents for i in items)),
        }

    return _tool(
        "client_history",
        "Historial resumido de un cliente: sus eventos con total, pagado y saldo.",
        _schema(
            {"client_id": {"type": "string", "description": "Id devuelto por search_clients"}},
            ["client_id"],
        ),  # fmt: skip
        Permission.PAYMENTS_RECORD,
        run,
    )


# 12. Eventos por fecha, cliente, tipo o estado (HU36) -----------------------------------------
_DATE_FROM = {"type": "string", "description": "Desde (inclusive), formato AAAA-MM-DD"}
_DATE_TO = {"type": "string", "description": "Hasta (inclusive), formato AAAA-MM-DD"}


def _search_events(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        date_from, date_to = _date_range(data)
        client = _text(data, "client", required=False)
        event_type = _choice(data, "event_type", EventType)
        status = _choice(data, "status", EventStatus)
        if not (date_from or date_to or client or event_type or status):
            date_from = lk.today()  # sin filtros: lo que viene, no todo el historial
        found = await lk.events_find(
            text=client,
            status=status,
            event_type=event_type,
            date_from=date_from,
            date_to=date_to,
            limit=MAX_ROWS,
        )
        return {
            "eventos": [
                {
                    "codigo": e.code,
                    "fecha": day(e.event_date),
                    "cliente": e.client_name,
                    "tipo": e.event_type.value,
                    "invitados": e.guests,
                    "estado": e.status.value,
                }
                for e in found.items
            ],
            "total": found.total,
        }

    return _tool(
        "search_events",
        "Busca eventos por rango de fechas del evento, cliente (texto), tipo y/o estado; todos "
        "los filtros son opcionales y se combinan. Sin filtros, los eventos desde hoy. Úsala "
        "para '¿qué bodas hay en diciembre?' o '¿qué eventos de Ana están confirmados?'.",
        _schema(
            {
                "date_from": _DATE_FROM,
                "date_to": _DATE_TO,
                "client": {
                    "type": "string",
                    "description": "Nombre o parte del nombre del cliente",
                },
                "event_type": {"type": "string", "enum": [t.value for t in EventType]},
                "status": {"type": "string", "enum": [s.value for s in EventStatus]},
            },
            [],
        ),
        Permission.EVENTS_READ,
        run,
    )


# 13. Cotizaciones por estado, cliente o fecha del evento (HU36) --------------------------------
_QUOTE_STATUS_LABEL = {
    QuoteStatus.DRAFT: "borrador",
    QuoteStatus.SENT: "enviada",
    QuoteStatus.ACCEPTED: "aceptada",
    QuoteStatus.REJECTED: "rechazada",
    QuoteStatus.EXPIRED: "vencida",
}


def _search_quotes(lk: Lookups) -> Tool:
    async def run(data: dict[str, Any]) -> Any:
        date_from, date_to = _date_range(data)
        found = await lk.quotes_search(
            QuoteFilters(
                text=_text(data, "client", required=False),
                status=_choice(data, "status", QuoteStatus),
                event_date_from=date_from,
                event_date_to=date_to,
            ),
            page=1,
            page_size=MAX_ROWS,
        )
        return {
            "cotizaciones": [
                {
                    "codigo": q.code,
                    "cliente": q.client_name,
                    "fecha_evento": day(q.event_date),
                    "total": soles(q.total_cents),
                    "estado": _QUOTE_STATUS_LABEL[q.status],
                    "vigente_hasta": day(q.valid_until),
                }
                for q in found.items
            ],
            "total": found.total,
        }

    return _tool(
        "search_quotes",
        "Busca cotizaciones por estado (DRAFT borrador, SENT enviada, ACCEPTED aceptada, "
        "REJECTED rechazada, EXPIRED vencida), cliente (texto) y rango de fechas del evento; "
        "todos opcionales. 'Pendientes de respuesta' son las SENT; DRAFT y SENT solo cuentan si "
        "siguen vigentes, y las que pasaron su vigencia sin respuesta son EXPIRED.",
        _schema(
            {
                "status": {"type": "string", "enum": [s.value for s in QuoteStatus]},
                "client": {"type": "string", "description": "Nombre del cliente o código"},
                "date_from": _DATE_FROM,
                "date_to": _DATE_TO,
            },
            [],
        ),
        Permission.QUOTES_MANAGE,
        run,
    )
