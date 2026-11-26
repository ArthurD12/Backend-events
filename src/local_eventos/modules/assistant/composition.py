"""Ensamblaje de dependencias del módulo assistant."""

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.assistant.application.ports.language_model import LanguageModel
from local_eventos.modules.assistant.application.ports.query_log import Clock, QueryLog
from local_eventos.modules.assistant.application.tool_catalog import Lookups, build_tools
from local_eventos.modules.assistant.application.tools import ToolRegistry
from local_eventos.modules.assistant.infrastructure.anthropic_language_model import (
    AnthropicLanguageModel,
)
from local_eventos.modules.assistant.infrastructure.clock import SystemClock
from local_eventos.modules.assistant.infrastructure.query_log import SqlAlchemyQueryLog
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
from local_eventos.shared.infrastructure.config import AssistantSettings


def language_model() -> LanguageModel | None:
    """El proveedor real si hay `ANTHROPIC_API_KEY`; sin clave, `None` (asistente no disponible)."""
    key = AssistantSettings().anthropic_api_key.strip()
    return AnthropicLanguageModel.from_api_key(key) if key else None


def query_log(session: AsyncSession) -> QueryLog:
    return SqlAlchemyQueryLog(session)


def clock() -> Clock:
    return SystemClock()


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
