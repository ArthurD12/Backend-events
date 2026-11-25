"""Caso de uso: listar trabajadores con filtros, búsqueda y paginación (HU15, CA-15.8).

Por defecto devuelve solo activos, igual que el catálogo: los inactivos aparecen
cuando el filtro los incluye (`status=INACTIVE` o `status=ALL`). El texto se busca
por nombre sin tildes ni mayúsculas o por documento normalizado. Python puro: sin
FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRepository,
)
from local_eventos.modules.staff.application.search_text import normalize_name
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100
_ALL_STATUSES = "ALL"


class SearchWorkers:
    """Busca y pagina trabajadores por texto, función y estado."""

    def __init__(self, workers: WorkerRepository) -> None:
        self._workers = workers

    async def execute(
        self,
        text: str = "",
        function: WorkerFunction | None = None,
        status: WorkerStatus | str | None = WorkerStatus.ACTIVE,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
    ) -> WorkerPage:
        """Devuelve una página ordenada por nombre.

        `text` se recorta y compara sin tildes ni mayúsculas. `status` acepta
        `ACTIVE` (por defecto), `INACTIVE` o `ALL`/`None` para incluir ambos.
        `page` se normaliza a 1 o más y `page_size` queda entre 1 y 100
        (`DEFAULT_PAGE_SIZE = 20` si no se indica).
        """
        clean_page = max(page, 1)
        clean_page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        return await self._workers.search(
            text=normalize_name(text),
            function=function,
            status=_resolve_status(status),
            page=clean_page,
            page_size=clean_page_size,
        )


def _resolve_status(status: WorkerStatus | str | None) -> WorkerStatus | None:
    """Traduce `ALL`/`None` a un filtro sin estado; el resto se conserva."""
    if status is None:
        return None
    if isinstance(status, WorkerStatus):
        return status
    if status.strip().upper() == _ALL_STATUSES:
        return None
    return WorkerStatus(status.strip().upper())
