"""Historial de accesos: filtros por usuario, fecha y resultado, con paginado (HU03)."""

from datetime import timedelta
from uuid import uuid4

from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogFilter,
)
from local_eventos.modules.identity.application.use_cases.search_access_log import (
    SearchAccessLog,
)
from local_eventos.modules.identity.domain.access_attempt import AccessAttempt, AccessResult

from .fakes import FakeClock, InMemoryAccessLogRepository


async def _log_with_attempts() -> tuple[InMemoryAccessLogRepository, FakeClock]:
    log, clock = InMemoryAccessLogRepository(), FakeClock()
    ana = uuid4()
    for minutes, user_id, result in [
        (0, ana, AccessResult.SUCCESS),
        (10, None, AccessResult.INVALID_CREDENTIALS),
        (20, ana, AccessResult.INVALID_CREDENTIALS),
        (30, ana, AccessResult.SUCCESS),
    ]:
        await log.add(
            AccessAttempt(
                email="ana@darze.pe" if user_id else "x@x.pe",
                user_id=user_id,
                result=result,
                occurred_at=clock.now() + timedelta(minutes=minutes),
            )
        )
    return log, clock


async def test_ca03_3_filtra_por_resultado_y_ordena_del_mas_reciente() -> None:
    log, _ = await _log_with_attempts()

    page = await SearchAccessLog(log)(AccessLogFilter(result=AccessResult.INVALID_CREDENTIALS))

    assert page.total == 2
    assert page.items[0].occurred_at > page.items[1].occurred_at


async def test_ca03_3_filtra_por_usuario_y_rango_de_fechas() -> None:
    log, clock = await _log_with_attempts()
    ana = log.attempts[0].user_id

    page = await SearchAccessLog(log)(
        AccessLogFilter(
            user_id=ana,
            since=clock.now() + timedelta(minutes=15),
            until=clock.now() + timedelta(minutes=30),
        )
    )

    assert page.total == 2


async def test_ca03_3_pagina_y_limita_el_tamano() -> None:
    log, _ = await _log_with_attempts()

    second = await SearchAccessLog(log)(AccessLogFilter(), page=2, page_size=3)
    huge = await SearchAccessLog(log)(AccessLogFilter(), page=0, page_size=10_000)

    assert (len(second.items), second.total, second.page) == (1, 4, 2)
    assert (huge.page, huge.page_size) == (1, 100)
