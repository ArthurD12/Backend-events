"""Pruebas de los casos de uso de alta y listado de indisponibilidad (HU16, T-05).

Cubre CA-16.1 (alta guardada y auditada con usuario y fecha-hora), CA-16.2
(trabajador inexistente/inactivo y validaciones de horario, tipo y descripción) y
el listado de solo lectura con filtros. Sin base de datos: fakes en memoria.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from uuid import UUID

import pytest

from local_eventos.modules.staff.application.errors import (
    WorkerInactiveError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.worker_repository import WorkerRef
from local_eventos.modules.staff.application.use_cases.list_unavailability import (
    ListUnavailability,
)
from local_eventos.modules.staff.application.use_cases.register_unavailability import (
    RegisterUnavailability,
)
from local_eventos.modules.staff.domain.enums import (
    UnavailabilityKind,
    UnavailabilityStatus,
    WorkerFunction,
    WorkerStatus,
)
from local_eventos.modules.staff.domain.errors import (
    AvailabilityRangeTooLargeError,
    AvailabilityWindowInvalidError,
    StaffValidationError,
    UnavailabilityKindRequiredError,
    UnavailabilityScheduleInvalidError,
)
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.unavailability_audit import (
    UnavailabilityAction,
    UnavailabilityAudit,
)

WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
ACTOR_ID = UUID("99999999-9999-9999-9999-999999999999")
NOW = datetime(2026, 11, 27, 15, 45, tzinfo=UTC)
DATE = date(2026, 12, 1)


class FakeClock:
    """Reloj fijo para que la auditoría sea determinista."""

    def now(self) -> datetime:
        return NOW


class FakeWorkerLookup:
    """Devuelve las referencias mínimas sembradas o `None`."""

    def __init__(self, workers: dict[UUID, WorkerRef]) -> None:
        self.workers = workers

    async def get(self, worker_id: UUID) -> WorkerRef | None:
        return self.workers.get(worker_id)


class FakeUnavailabilityRepository:
    """Repositorio en memoria con la semántica del puerto."""

    def __init__(self) -> None:
        self.unavailabilities: dict[UUID, Unavailability] = {}
        self.audits: list[UnavailabilityAudit] = []
        self.saves = 0

    async def save(
        self, unavailability: Unavailability, audit: UnavailabilityAudit
    ) -> None:
        self.saves += 1
        self.unavailabilities[unavailability.id] = unavailability
        self.audits.append(audit)

    async def get(self, unavailability_id: UUID) -> Unavailability | None:
        return self.unavailabilities.get(unavailability_id)

    async def get_for_update(self, unavailability_id: UUID) -> Unavailability | None:
        return self.unavailabilities.get(unavailability_id)

    async def list_active_overlapping(
        self,
        start_at: datetime,
        end_at: datetime,
        worker_ids: list[UUID],
    ) -> list[Unavailability]:
        return [
            item
            for item in self.unavailabilities.values()
            if item.worker_id in worker_ids
            and item.status is UnavailabilityStatus.ACTIVE
            and item.start_at < end_at
            and item.end_at > start_at
        ]

    def _matching(
        self,
        worker_id: UUID | None,
        start_at: datetime | None,
        end_at: datetime | None,
    ) -> list[Unavailability]:
        items = [
            item
            for item in self.unavailabilities.values()
            if worker_id is None or item.worker_id == worker_id
        ]
        if start_at is not None and end_at is not None:
            items = [
                item for item in items if item.start_at < end_at and item.end_at > start_at
            ]
        return sorted(items, key=lambda item: item.start_at)

    async def list_by_worker(
        self,
        worker_id: UUID,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Unavailability]:
        return self._matching(worker_id, start_at, end_at)

    async def list(
        self,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
    ) -> list[Unavailability]:
        return self._matching(None, start_at, end_at)


def _worker_ref(
    worker_id: UUID = WORKER_ID, status: WorkerStatus = WorkerStatus.ACTIVE
) -> WorkerRef:
    return WorkerRef(
        id=worker_id,
        name="Ana Torres",
        function=WorkerFunction.WAITER,
        function_description=None,
        status=status,
    )


def _register_use_case(
    *,
    worker: WorkerRef | None = None,
    has_worker: bool = True,
) -> tuple[RegisterUnavailability, FakeUnavailabilityRepository]:
    repository = FakeUnavailabilityRepository()
    if not has_worker:
        workers = FakeWorkerLookup({})
    else:
        workers = FakeWorkerLookup({WORKER_ID: worker if worker is not None else _worker_ref()})
    use_case = RegisterUnavailability(
        workers=workers, unavailabilities=repository, clock=FakeClock()
    )
    return use_case, repository


async def _execute(
    use_case: RegisterUnavailability,
    **overrides: object,
) -> Unavailability:
    data: dict[str, object] = {
        "worker_id": WORKER_ID,
        "date": DATE,
        "start_time": time(18, 0),
        "end_time": time(23, 0),
        "kind": UnavailabilityKind.VACATION,
        "description": None,
        "actor_id": ACTOR_ID,
    }
    data.update(overrides)
    return await use_case.execute(**data)  # type: ignore[arg-type]


# --- CA-16.1: alta guardada y auditada -------------------------------------


async def test_ca16_1_alta_auditada() -> None:
    use_case, repository = _register_use_case()

    unavailability = await _execute(use_case)

    assert unavailability.id in repository.unavailabilities
    assert unavailability.worker_id == WORKER_ID
    assert unavailability.kind is UnavailabilityKind.VACATION
    assert unavailability.status is UnavailabilityStatus.ACTIVE
    assert unavailability.start_at == datetime(2026, 12, 1, 23, 0, tzinfo=UTC)
    assert unavailability.end_at == datetime(2026, 12, 2, 4, 0, tzinfo=UTC)

    assert repository.saves == 1
    (audit,) = repository.audits
    assert audit.action is UnavailabilityAction.CREATED
    assert audit.unavailability_id == unavailability.id
    assert audit.actor_id == ACTOR_ID
    assert audit.occurred_at == NOW
    assert audit.reason is None
    assert audit.previous_values is None
    assert audit.new_values is None


async def test_ca16_14_cruce_medianoche() -> None:
    use_case, _ = _register_use_case()

    unavailability = await _execute(
        use_case, start_time=time(22, 0), end_time=time(2, 0)
    )

    assert unavailability.start_at == datetime(2026, 12, 2, 3, 0, tzinfo=UTC)
    assert unavailability.end_at == datetime(2026, 12, 2, 7, 0, tzinfo=UTC)


# --- CA-16.2: trabajador y validaciones ------------------------------------


async def test_ca16_2_trabajador_inexistente() -> None:
    use_case, repository = _register_use_case(has_worker=False)

    with pytest.raises(WorkerNotFoundError) as exc_info:
        await _execute(use_case)

    assert exc_info.value.code == "staff.not_found"
    assert repository.saves == 0


async def test_ca16_2_trabajador_inactivo() -> None:
    use_case, repository = _register_use_case(
        worker=_worker_ref(status=WorkerStatus.INACTIVE)
    )

    with pytest.raises(WorkerInactiveError) as exc_info:
        await _execute(use_case)

    assert exc_info.value.code == "staff.worker_inactive"
    assert repository.saves == 0


async def test_ca16_2_horario_invalido() -> None:
    use_case, repository = _register_use_case()

    with pytest.raises(UnavailabilityScheduleInvalidError) as exc_info:
        await _execute(use_case, start_time=time(10, 0), end_time=time(10, 0))

    assert exc_info.value.code == "staff.unavailability_schedule_invalid"
    assert repository.saves == 0


async def test_ca16_2_tipo_obligatorio() -> None:
    use_case, repository = _register_use_case()

    with pytest.raises(UnavailabilityKindRequiredError) as exc_info:
        await _execute(use_case, kind=None)

    assert exc_info.value.code == "staff.unavailability_kind_required"
    assert repository.saves == 0


async def test_ca16_2_descripcion_obligatoria_para_otro() -> None:
    use_case, repository = _register_use_case()

    with pytest.raises(StaffValidationError) as exc_info:
        await _execute(use_case, kind=UnavailabilityKind.OTHER, description=None)

    assert exc_info.value.code == "staff.unavailability_description_required"
    assert repository.saves == 0


async def test_ca16_2_descripcion_prohibida_fuera_de_otro() -> None:
    use_case, repository = _register_use_case()

    with pytest.raises(StaffValidationError) as exc_info:
        await _execute(use_case, description="Detalle que no corresponde")

    assert exc_info.value.code == "staff.unavailability_description_not_allowed"
    assert repository.saves == 0


async def test_otro_con_descripcion_se_guarda() -> None:
    use_case, repository = _register_use_case()

    unavailability = await _execute(
        use_case, kind=UnavailabilityKind.OTHER, description="  Trámite personal  "
    )

    assert unavailability.kind is UnavailabilityKind.OTHER
    assert unavailability.description == "Trámite personal"
    assert repository.saves == 1


# --- Listado de solo lectura ------------------------------------------------


def _seed(*items: Unavailability) -> FakeUnavailabilityRepository:
    repository = FakeUnavailabilityRepository()
    for item in items:
        repository.unavailabilities[item.id] = item
    return repository


def _item(
    *,
    worker_id: UUID,
    start_at: datetime,
    end_at: datetime,
    kind: UnavailabilityKind = UnavailabilityKind.REST,
) -> Unavailability:
    return Unavailability.register(
        worker_id=worker_id, kind=kind, start_at=start_at, end_at=end_at
    )


async def test_listado_incluye_canceladas_y_filtra_por_trabajador() -> None:
    active = _item(
        worker_id=WORKER_ID,
        start_at=datetime(2026, 12, 1, 14, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, 22, 0, tzinfo=UTC),
    )
    cancelled = _item(
        worker_id=WORKER_ID,
        start_at=datetime(2026, 12, 3, 14, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 3, 22, 0, tzinfo=UTC),
    )
    cancelled.cancel()
    other = _item(
        worker_id=OTHER_WORKER_ID,
        start_at=datetime(2026, 12, 1, 14, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, 22, 0, tzinfo=UTC),
    )
    repository = _seed(active, cancelled, other)
    use_case = ListUnavailability(unavailabilities=repository)

    result = await use_case.execute(worker_id=WORKER_ID)

    assert result == [active, cancelled]
    assert any(
        item.status is UnavailabilityStatus.CANCELLED for item in result
    )
    assert repository.saves == 0
    assert repository.audits == []


async def test_listado_sin_trabajador_filtra_por_ventana() -> None:
    inside = _item(
        worker_id=WORKER_ID,
        start_at=datetime(2026, 12, 1, 14, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 1, 22, 0, tzinfo=UTC),
    )
    outside = _item(
        worker_id=OTHER_WORKER_ID,
        start_at=datetime(2026, 12, 10, 14, 0, tzinfo=UTC),
        end_at=datetime(2026, 12, 10, 22, 0, tzinfo=UTC),
    )
    repository = _seed(inside, outside)
    use_case = ListUnavailability(unavailabilities=repository)

    result = await use_case.execute(from_date=DATE, to_date=DATE)

    assert result == [inside]


async def test_listado_rango_demasiado_amplio() -> None:
    use_case = ListUnavailability(unavailabilities=FakeUnavailabilityRepository())

    with pytest.raises(AvailabilityRangeTooLargeError) as exc_info:
        await use_case.execute(
            from_date=date(2026, 12, 1), to_date=date(2027, 1, 1)
        )

    assert exc_info.value.code == "staff.availability_range_too_large"


async def test_listado_una_sola_fecha_es_invalida() -> None:
    use_case = ListUnavailability(unavailabilities=FakeUnavailabilityRepository())

    with pytest.raises(AvailabilityWindowInvalidError) as exc_info:
        await use_case.execute(from_date=DATE)

    assert exc_info.value.code == "staff.availability_window_invalid"
