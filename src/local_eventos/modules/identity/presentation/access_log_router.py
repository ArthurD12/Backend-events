"""Endpoint del historial de accesos (HU03). Solo para el permiso `access_log:read`.

No hay rutas para modificar ni borrar registros (CA-03.4).
"""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogFilter,
)
from local_eventos.modules.identity.application.use_cases.search_access_log import (
    MAX_PAGE_SIZE,
    SearchAccessLog,
)
from local_eventos.modules.identity.domain.access_attempt import AccessResult
from local_eventos.modules.identity.domain.permissions import Permission
from local_eventos.modules.identity.presentation.dependencies import (
    AccessLog,
    require_permission,
)
from local_eventos.modules.identity.presentation.identity_schemas import AccessLogPageOut
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/access-log",
    tags=["historial de accesos"],
    dependencies=[Depends(require_permission(Permission.ACCESS_LOG_READ))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)


@router.get("", operation_id="access_log_search")
async def search_access_log(
    access_log: AccessLog,
    user_id: UUID | None = None,
    since: Annotated[datetime | None, Query(description="Desde (con zona horaria)")] = None,
    until: Annotated[datetime | None, Query(description="Hasta (con zona horaria)")] = None,
    result: AccessResult | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
) -> AccessLogPageOut:
    """Intentos de inicio de sesión, del más reciente al más antiguo, con filtros y paginado."""
    found = await SearchAccessLog(access_log)(
        AccessLogFilter(user_id=user_id, since=since, until=until, result=result),
        page=page,
        page_size=page_size,
    )
    return AccessLogPageOut.from_page(found)
