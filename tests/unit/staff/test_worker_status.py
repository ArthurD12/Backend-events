"""Pruebas de los casos de uso de baja y reactivación de trabajadores (HU15).

Usan un repositorio fake y un `Clock` fijo: sin base de datos ni reloj real.
Cubren CA-15.9, CA-15.10 y CA-15.24, incluida la idempotencia sin auditoría.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from local_eventos.modules.staff.application.errors import WorkerNotFoundError
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRef,
)
from local_eventos.modules.staff.application.use_cases.change_worker_status import (
    ActivateWorker,
    DeactivateWorker,
)
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, DocumentType
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
    """Repositorio en memoria que respeta el contrato de `WorkerRepository`."""

    def __init__(self) -> None:
        self.workers: dict[UUID, Worker] = {}
        self.audits: list[WorkerAudit] = []

    async def save(self, worker: Worker, audit: WorkerAudit) -> None:
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


def _repository_with_worker(
    *, status: WorkerStatus = WorkerStatus.ACTIVE
) -> FakeWorkerRepository:
    repository = FakeWorkerRepository()
    worker = Worker.register(
        worker_id=WORKER_ID,
        name="Ana Torres",
        document_type=DocumentType.DNI,
        document_number="44125896",
    )
    if status is WorkerStatus.INACTIVE:
        worker.deactivate()
    repository.workers[WORKER_ID] = worker
    return repository


async def test_ca15_9_desactiva_con_motivo_y_auditoria() -> None:
    repository = _repository_with_worker()
    deactivate = DeactivateWorker(repository, FixedClock(NOW))

    worker = await deactivate.execute(WORKER_ID, "Fin de temporada", ACTOR_ID)

    assert worker.status is WorkerStatus.INACTIVE
    assert repository.workers[WORKER_ID] is worker
    assert len(repository.audits) == 1
    audit = repository.audits[0]
    assert audit.action is AuditAction.DEACTIVATED
    assert audit.worker_id == WORKER_ID
    assert audit.reason == "Fin de temporada"
    assert audit.changed_by == ACTOR_ID
    assert audit.changed_at == NOW


async def test_ca15_9_motivo_es_opcional_y_vacio_queda_none() -> None:
    repository = _repository_with_worker()
    deactivate = DeactivateWorker(repository, FixedClock(NOW))

    await deactivate.execute(WORKER_ID, "   ", ACTOR_ID)

    assert repository.audits[0].reason is None


async def test_motivo_omitido_queda_none() -> None:
    repository = _repository_with_worker()
    deactivate = DeactivateWorker(repository, FixedClock(NOW))

    await deactivate.execute(WORKER_ID, None, ACTOR_ID)

    assert repository.audits[0].reason is None


async def test_ca15_10_reactiva() -> None:
    repository = _repository_with_worker(status=WorkerStatus.INACTIVE)
    activate = ActivateWorker(repository, FixedClock(NOW))

    worker = await activate.execute(WORKER_ID, "Vuelve al plantel", ACTOR_ID)

    assert worker.status is WorkerStatus.ACTIVE
    assert len(repository.audits) == 1
    audit = repository.audits[0]
    assert audit.action is AuditAction.ACTIVATED
    assert audit.reason == "Vuelve al plantel"
    assert audit.changed_by == ACTOR_ID
    assert audit.changed_at == NOW


async def test_actor_y_fecha_correctos() -> None:
    repository = _repository_with_worker()
    deactivate = DeactivateWorker(repository, FixedClock(NOW))

    await deactivate.execute(WORKER_ID, None, ACTOR_ID)

    audit = repository.audits[0]
    assert audit.changed_by == ACTOR_ID
    assert audit.changed_at == NOW


async def test_repetir_la_baja_no_crea_otra_auditoria() -> None:
    repository = _repository_with_worker()
    deactivate = DeactivateWorker(repository, FixedClock(NOW))

    await deactivate.execute(WORKER_ID, "Primera baja", ACTOR_ID)
    worker = await deactivate.execute(WORKER_ID, "Repetida", ACTOR_ID)

    assert worker.status is WorkerStatus.INACTIVE
    assert len(repository.audits) == 1
    assert repository.audits[0].reason == "Primera baja"


async def test_repetir_la_reactivacion_no_crea_otra_auditoria() -> None:
    repository = _repository_with_worker(status=WorkerStatus.INACTIVE)
    activate = ActivateWorker(repository, FixedClock(NOW))

    await activate.execute(WORKER_ID, "Primera", ACTOR_ID)
    worker = await activate.execute(WORKER_ID, "Repetida", ACTOR_ID)

    assert worker.status is WorkerStatus.ACTIVE
    assert len(repository.audits) == 1


async def test_no_encontrado() -> None:
    repository = FakeWorkerRepository()
    deactivate = DeactivateWorker(repository, FixedClock(NOW))
    activate = ActivateWorker(repository, FixedClock(NOW))

    with pytest.raises(WorkerNotFoundError):
        await deactivate.execute(WORKER_ID, None, ACTOR_ID)
    with pytest.raises(WorkerNotFoundError):
        await activate.execute(WORKER_ID, None, ACTOR_ID)

    assert repository.audits == []
