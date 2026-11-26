"""Ensamblaje de dependencias del módulo assistant."""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.assistant.application.tool_catalog import Lookups, build_tools
from local_eventos.modules.assistant.application.tools import ToolRegistry
from local_eventos.modules.assistant.infrastructure.clock import SystemClock
from local_eventos.modules.commercial.public_api import (
    clients_search,
    event_account,
    event_detail,
    events_report,
    events_search,
    upcoming_events,
)
from local_eventos.modules.identity.public_api import user_names
from local_eventos.modules.inventory.public_api import event_requirement, stock_report
from local_eventos.modules.ledger.public_api import cash_totals
from local_eventos.modules.purchasing.public_api import purchases_report


def tools(session: AsyncSession) -> ToolRegistry:
    """Herramientas de consulta del asistente, dentro de la transacción de la petición."""
    return build_tools(
        Lookups(
            today=SystemClock().today,
            upcoming_events=upcoming_events(session),
            events_report=events_report(session),
            events_search=events_search(session),
            event_detail=event_detail(session),
            event_account=event_account(session),
            stock_report=stock_report(session),
            event_requirement=event_requirement(session),
            purchases_report=purchases_report(session),
            cash_totals=cash_totals(session),
            clients_search=clients_search(session),
            user_names=user_names(session),
        )
    )
