"""Pruebas de la superficie pública de asignaciones (HU17, T-21, CA-17.21).

Verifican que `event_assignments(session)(event_id)` delega en
`ListEventAssignmentsForSheet`, devuelve nombre, función, descripción e instantes
UTC, y **no** expone pago, documento, teléfono ni tarifa. También que el router de
asignaciones queda montado en `create_app()`. Usan un repositorio fake en memoria:
sin base de datos.
"""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.main import create_app
from local_eventos.modules.staff import composition, public_api
from local_eventos.modules.staff.application.ports.assignment_repository import (
    AssignmentView,
    EventAssignment,
)
from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction

EVENT_ID = UUID("55555555-5555-5555-5555-555555555555")
OTHER_EVENT_ID = UUID("66666666-6666-6666-6666-666666666666")
WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
ASSIGNMENT_ID = UUID("33333333-3333-3333-3333-333333333333")
OTHER_ASSIGNMENT_ID = UUID("44444444-4444-4444-4444-444444444444")

START_AT = datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
END_AT = datetime(2026, 12, 2, 4, 0, tzinfo=UTC)
LATER_START_AT = datetime(2026, 12, 2, 5, 0, tzinfo=UTC)
LATER_END_AT = datetime(2026, 12, 2, 9, 0, tzinfo=UTC)


class FakeAssignmentRepository:
    """Repositorio en memoria con la semántica de `list_by_event`."""

    def __init__(self, views: list[AssignmentView] | None = None) -> None:
        self.views = views or []
        self.calls: list[UUID] = []

    async def list_by_event(self, event_id: UUID) -> list[AssignmentView]:
        self.calls.append(event_id)
        return [
            view
            for view in self.views
            if view.event_id == event_id and view.status is AssignmentStatus.ACTIVE
        ]


def _view(
    assignment_id: UUID,
    *,
    event_id: UUID,
    worker_id: UUID,
    worker_name: str,
    function: WorkerFunction,
    function_description: str | None,
    start_at: datetime,
    end_at: datetime,
    status: AssignmentStatus = AssignmentStatus.ACTIVE,
) -> AssignmentView:
    return AssignmentView(
        id=assignment_id,
        event_id=event_id,
        worker_id=worker_id,
        worker_name=worker_name,
        function=function,
        function_description=function_description,
        start_at=start_at,
        end_at=end_at,
        pay_cents=20000,
        currency="PEN",
        status=status,
    )


def _lookup(monkeypatch, repository: FakeAssignmentRepository):  # type: ignore[no-untyped-def]
    """Fábrica pública con la sesión sustituida por el repositorio fake."""
    monkeypatch.setattr(composition, "assignment_repository", lambda session: repository)
    return public_api.event_assignments(cast(AsyncSession, object()))


async def test_event_assignments_delega_y_mapea_sin_pago(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    repository = FakeAssignmentRepository(
        [
            _view(
                ASSIGNMENT_ID,
                event_id=EVENT_ID,
                worker_id=WORKER_ID,
                worker_name="José Ramírez",
                function=WorkerFunction.OTHER,
                function_description="Parrillero",
                start_at=START_AT,
                end_at=END_AT,
            ),
            _view(
                OTHER_ASSIGNMENT_ID,
                event_id=EVENT_ID,
                worker_id=OTHER_WORKER_ID,
                worker_name="Ana Torres",
                function=WorkerFunction.WAITER,
                function_description=None,
                start_at=LATER_START_AT,
                end_at=LATER_END_AT,
            ),
            _view(
                UUID("77777777-7777-7777-7777-777777777777"),
                event_id=OTHER_EVENT_ID,
                worker_id=WORKER_ID,
                worker_name="Otro evento",
                function=WorkerFunction.COOK,
                function_description=None,
                start_at=START_AT,
                end_at=END_AT,
            ),
        ]
    )

    lookup = _lookup(monkeypatch, repository)
    result = await lookup(EVENT_ID)

    assert repository.calls == [EVENT_ID]
    assert [item.worker_name for item in result] == ["José Ramírez", "Ana Torres"]
    first = result[0]
    assert first.worker_id == WORKER_ID
    assert first.function is WorkerFunction.OTHER
    assert first.function_description == "Parrillero"
    assert first.starts_at == START_AT
    assert first.ends_at == END_AT


async def test_event_assignments_sin_asignaciones_devuelve_lista_vacia(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    lookup = _lookup(monkeypatch, FakeAssignmentRepository([]))

    assert await lookup(EVENT_ID) == []


def test_event_assignment_no_expone_datos_sensibles_ni_pago() -> None:
    names = {field.name for field in fields(EventAssignment)}

    assert names == {
        "worker_id",
        "worker_name",
        "function",
        "function_description",
        "starts_at",
        "ends_at",
    }
    for forbidden_field in ("pay_cents", "pay", "currency", "document", "phone", "rate"):
        assert forbidden_field not in names


def test_event_assignments_no_expone_escritura(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    lookup = _lookup(monkeypatch, FakeAssignmentRepository([]))

    for write_operation in ("save", "register", "update", "cancel", "release"):
        assert not hasattr(lookup, write_operation)


def test_router_de_asignaciones_montado_en_create_app() -> None:
    app = create_app()

    assert "/v1/staff/assignments" in app.openapi()["paths"]
