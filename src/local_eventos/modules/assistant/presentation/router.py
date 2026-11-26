"""API del asistente de consulta (HU35–HU40). Solo consulta: ninguna ruta cambia datos de negocio.

`ask` y `status` los usa cualquier usuario autenticado; cada herramienta verifica además el
permiso del rol. El historial es solo del administrador (`assistant_log:read`).
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from local_eventos.modules.assistant.application.errors import AssistantProviderError
from local_eventos.modules.assistant.application.ports.query_log import QueryFilter
from local_eventos.modules.assistant.application.use_cases.ask_assistant import (
    AskAssistant,
    Asker,
    HistoryTurn,
)
from local_eventos.modules.assistant.application.use_cases.search_queries import (
    MAX_PAGE_SIZE,
    SearchQueries,
)
from local_eventos.modules.assistant.presentation.dependencies import (
    ClockDep,
    ModelDep,
    QueryLogDep,
    ToolsDep,
    UserNamesDep,
)
from local_eventos.modules.assistant.presentation.errors import problem_for
from local_eventos.modules.assistant.presentation.schemas import (
    AskIn,
    AskOut,
    QueryLogPageOut,
    StatusOut,
    ToolUseOut,
)
from local_eventos.modules.identity.public_api import (
    CurrentUser,
    Permission,
    get_current_user,
    require_permission,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/assistant",
    tags=["asistente"],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

Viewer = Annotated[CurrentUser, Depends(get_current_user)]


@router.post(
    "/ask",
    operation_id="assistant_ask",
    response_model=AskOut,
    responses={
        429: {"model": Problem, "description": "`assistant.rate_limited` (30 por hora, R-IA-2)"},
        502: {"model": Problem, "description": "`assistant.provider_error`"},
        503: {"model": Problem, "description": "`assistant.unavailable` (sin clave del proveedor)"},
    },
)
async def ask(
    body: AskIn,
    user: Viewer,
    model: ModelDep,
    tools: ToolsDep,
    log: QueryLogDep,
    clock: ClockDep,
) -> AskOut | JSONResponse:
    """Responde una pregunta en lenguaje natural usando solo funciones de consulta, con los
    permisos del usuario. La conversación vive en el chat: el frontend envía el historial."""
    asker = Asker(user.id, frozenset(p.value for p in user.permissions))
    history = [HistoryTurn(turn.role, turn.text) for turn in body.history]
    try:
        result = await AskAssistant(model, tools, log, clock)(asker, body.question, history)
    except AssistantProviderError as error:
        # Se responde (no se relanza) para que la auditoría del intento fallido se confirme.
        return problem_for(error)
    return AskOut(answer=result.answer, tools=[ToolUseOut.from_use(t) for t in result.tools])


@router.get("/status", operation_id="assistant_status")
async def status(_: Viewer, model: ModelDep) -> StatusOut:
    """Si el asistente está disponible (hay clave del proveedor); el resto no depende de él."""
    return StatusOut(available=model is not None)


@router.get(
    "/log",
    operation_id="assistant_log_list",
    dependencies=[Depends(require_permission(Permission.ASSISTANT_LOG_READ))],
)
async def list_log(
    log: QueryLogDep,
    names: UserNamesDep,
    user_id: UUID | None = None,
    since: Annotated[datetime | None, Query(description="Desde (con zona horaria)")] = None,
    until: Annotated[datetime | None, Query(description="Hasta (con zona horaria)")] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> QueryLogPageOut:
    """Historial de consultas al asistente, de la más reciente a la más antigua (solo lectura)."""
    found = await SearchQueries(log)(
        QueryFilter(user_id=user_id, since=since, until=until), page=page, page_size=page_size
    )
    return QueryLogPageOut.from_page(found, await names({r.user_id for r in found.items}))
