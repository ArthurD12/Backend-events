"""Pruebas de la baja de trabajador con ocupación de asignaciones (HU17, T-11).

Cubren CA-17.25/R-ASG-16: se liberan las asignaciones de eventos cancelados, una
asignación futura vigente bloquea la baja sin escribir auditoría, las pasadas no
bloquean y la reactivación no consulta la ocupación. Todo con fakes en memoria.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from uuid import UUID

import pytest

from local_eventos.modules.staff.application.assignment_occupancy import (
    AssignmentOccupancy,
)
from local_eventos.modules.staff.application.errors import (
    WorkerHasFutureAssignmentsError,
)
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRef,
)
from local_eventos.modules.staff.application.use_cases.change_worker_status import (
    ActivateWorker,
    DeactivateWorker,
)
from local_eventos.modules.staff.domain.audit import WorkerAudit
from local_eventos.modules.staff.domain.document import Document, WorkerDocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.worker import Worker

ACTOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NOW = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
WORKER_ID = UUID("11111111-1111-1111-1111-111111111111")


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeWorkerRepository:
    """Repositorio en memoria; registra las escrituras para comprobar la auditoría."""

    def __init__(self, *, status: WorkerStatus = WorkerStatus.ACTIVE) -> None:
        worker = Worker.register(
            worker_id=WORKER_ID,
            name="Ana Torres",
            document_type=WorkerDocumentType.DNI,
            document_number="44125896",
        )
        if status is WorkerStatus.INACTIVE:
            worker.deactivate()
        self.workers: dict[UUID, Worker] = {WORKER_ID: worker}
        self.audits: list[WorkerAudit] = []
        self.save_calls = 0

    async def save(self, worker: Worker, audit: WorkerAudit) -> None:
        self.save_calls += 1
        self.workers[worker.id] = worker
        self.audits.append(audit)

    async def get(self, worker_id: UUID) -> Worker | None:
        return self.workers.get(worker_id)

    async def get_for_update(self, worker_id: UUID) -> Worker | None:
        return self.workers.get(worker_id)

    async def get_by_document(self, document: Document) -> Worker | None:
        raise NotImplementedError

    async def search(
        self,
        *,
        text: str,
        function: WorkerFunction | None,
        status: WorkerStatus | None,
        page: int,
        page_size: int,
    ) -> WorkerPage:
        raise NotImplementedError

    async def lookup(self, worker_id: UUID) -> WorkerRef | None:
        raise NotImplementedError


class RecordingOccupancy:
    """Ocupación fake que registra el orden de las llamadas."""

    def __init__(self, *, has_future: bool = False) -> None:
        self._has_future = has_future
        self.calls: list[str] = []

    async def release_cancelled(self, worker_id: UUID) -> int:
        self.calls.append("release_cancelled")
        return 0

    async def has_future(self, worker_id: UUID, moment: datetime) -> bool:
        self.calls.append("has_future")
        return self._has_future


def _occupancy(occupancy: RecordingOccupancy) -> AssignmentOccupancy:
    return cast(AssignmentOccupancy, occupancy)


async def test_ca17_25_bloquea_futuras() -> None:
    repository = FakeWorkerRepository()
    occupancy = RecordingOccupancy(has_future=True)
    deactivate = DeactivateWorker(repository, FixedClock(NOW), _occupancy(occupancy))

    with pytest.raises(WorkerHasFutureAssignmentsError):
        await deactivate.execute(WORKER_ID, "Fin de temporada", ACTOR_ID)

    assert repository.workers[WORKER_ID].status is WorkerStatus.ACTIVE
    assert repository.save_calls == 0
    assert repository.audits == []


async def test_sin_asignaciones_futuras_desactiva_y_audita() -> None:
    repository = FakeWorkerRepository()
    occupancy = RecordingOccupancy(has_future=False)
    deactivate = DeactivateWorker(repository, FixedClock(NOW), _occupancy(occupancy))

    worker = await deactivate.execute(WORKER_ID, "Fin de temporada", ACTOR_ID)

    assert worker.status is WorkerStatus.INACTIVE
    assert repository.save_calls == 1
    assert len(repository.audits) == 1
    assert repository.audits[0].reason == "Fin de temporada"


async def test_libera_cancelados_antes_de_consultar_futuras() -> None:
    repository = FakeWorkerRepository()
    occupancy = RecordingOccupancy(has_future=False)
    deactivate = DeactivateWorker(repository, FixedClock(NOW), _occupancy(occupancy))

    await deactivate.execute(WORKER_ID, None, ACTOR_ID)

    assert occupancy.calls == ["release_cancelled", "has_future"]


async def test_reactivar_no_consulta_ocupacion() -> None:
    repository = FakeWorkerRepository(status=WorkerStatus.INACTIVE)
    activate = ActivateWorker(repository, FixedClock(NOW))

    worker = await activate.execute(WORKER_ID, "Vuelve al plantel", ACTOR_ID)

    assert worker.status is WorkerStatus.ACTIVE
    assert repository.save_calls == 1
    assert len(repository.audits) == 1
