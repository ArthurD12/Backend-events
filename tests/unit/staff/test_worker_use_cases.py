"""Pruebas de los casos de uso de alta y edición de trabajadores (HU15).

Usan un repositorio fake y un `Clock` fijo: sin base de datos ni reloj real.
Cubren CA-15.1, CA-15.3, CA-15.4 y CA-15.6.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from local_eventos.modules.staff.application.errors import (
    DuplicateDocumentError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRef,
)
from local_eventos.modules.staff.application.use_cases.register_worker import (
    RegisterWorker,
)
from local_eventos.modules.staff.application.use_cases.update_worker import (
    UpdateWorker,
)
from local_eventos.modules.staff.application.use_cases.worker_data import WorkerData
from local_eventos.modules.staff.domain.audit import AuditAction, WorkerAudit
from local_eventos.modules.staff.domain.document import Document, DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker

ACTOR_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
NOW = datetime(2026, 11, 24, 15, 30, tzinfo=UTC)
WORKER_1_ID = UUID("11111111-1111-1111-1111-111111111111")
WORKER_2_ID = UUID("22222222-2222-2222-2222-222222222222")


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
        for worker in self.workers.values():
            if worker.document == document:
                return worker
        return None

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


def _data(**overrides: object) -> WorkerData:
    values: dict[str, object] = {
        "name": "Ana Torres",
        "document_type": DocumentType.DNI,
        "document_number": "44125896",
    }
    values.update(overrides)
    return WorkerData(**values)  # type: ignore[arg-type]


def _worker(
    *,
    worker_id: UUID,
    name: str = "Ana Torres",
    document_type: DocumentType = DocumentType.DNI,
    document_number: str = "44125896",
) -> Worker:
    return Worker.register(
        worker_id=worker_id,
        name=name,
        document_type=document_type,
        document_number=document_number,
    )


async def test_ca15_1_alta_activa_con_auditoria() -> None:
    repository = FakeWorkerRepository()
    register = RegisterWorker(repository, FixedClock(NOW))

    worker = await register.execute(
        _data(
            phone="987654321",
            function=WorkerFunction.COOK,
            worker_type=WorkerType.FIXED,
            rate=Money(15000),
        ),
        ACTOR_ID,
    )

    assert worker.status is WorkerStatus.ACTIVE
    assert worker.name == "Ana Torres"
    assert worker.document == Document(DocumentType.DNI, "44125896")
    assert repository.workers[worker.id] is worker
    assert len(repository.audits) == 1
    audit = repository.audits[0]
    assert audit.action is AuditAction.CREATED
    assert audit.worker_id == worker.id
    assert audit.changed_by == ACTOR_ID
    assert audit.changed_at == NOW
    assert audit.reason is None


async def test_ca15_3_duplicado_activo_no_se_guarda() -> None:
    repository = FakeWorkerRepository()
    repository.workers[WORKER_1_ID] = _worker(worker_id=WORKER_1_ID)
    register = RegisterWorker(repository, FixedClock(NOW))

    with pytest.raises(DuplicateDocumentError):
        await register.execute(_data(), ACTOR_ID)

    assert len(repository.workers) == 1
    assert repository.audits == []


async def test_ca15_3_duplicado_incluye_inactivos() -> None:
    repository = FakeWorkerRepository()
    inactive = _worker(worker_id=WORKER_1_ID)
    inactive.deactivate()
    repository.workers[WORKER_1_ID] = inactive
    register = RegisterWorker(repository, FixedClock(NOW))

    with pytest.raises(DuplicateDocumentError):
        await register.execute(_data(), ACTOR_ID)

    assert repository.audits == []


async def test_ca15_4_edicion_a_documento_ajeno_conserva_el_anterior() -> None:
    repository = FakeWorkerRepository()
    repository.workers[WORKER_1_ID] = _worker(worker_id=WORKER_1_ID)
    repository.workers[WORKER_2_ID] = _worker(
        worker_id=WORKER_2_ID,
        name="Beto Ruiz",
        document_number="12345678",
    )
    update = UpdateWorker(repository, FixedClock(NOW))

    with pytest.raises(DuplicateDocumentError):
        await update.execute(
            WORKER_2_ID, _data(name="Beto Ruiz", document_number="44125896"), ACTOR_ID
        )

    assert repository.workers[WORKER_2_ID].document == Document(
        DocumentType.DNI, "12345678"
    )
    assert repository.audits == []


async def test_ca15_4_edicion_conserva_su_propio_documento() -> None:
    repository = FakeWorkerRepository()
    repository.workers[WORKER_1_ID] = _worker(worker_id=WORKER_1_ID)
    update = UpdateWorker(repository, FixedClock(NOW))

    updated = await update.execute(
        WORKER_1_ID, _data(name="Ana Torres Vargas"), ACTOR_ID
    )

    assert updated.name == "Ana Torres Vargas"
    assert updated.document == Document(DocumentType.DNI, "44125896")
    assert len(repository.audits) == 1


async def test_ca15_6_edicion_auditada_con_actor_y_fecha() -> None:
    repository = FakeWorkerRepository()
    repository.workers[WORKER_1_ID] = _worker(worker_id=WORKER_1_ID)
    update = UpdateWorker(repository, FixedClock(NOW))

    updated = await update.execute(
        WORKER_1_ID,
        _data(
            phone="999888777",
            function=WorkerFunction.OTHER,
            function_description="Sonidista",
            worker_type=WorkerType.EVENTUAL,
            rate=Money(20000),
            overtime_applies=True,
            overtime_rate=Money(5000),
        ),
        ACTOR_ID,
    )

    assert updated.phone == "999888777"
    assert updated.function is WorkerFunction.OTHER
    assert updated.function_description == "Sonidista"
    assert updated.rate == Money(20000)
    assert updated.overtime_applies is True
    assert updated.overtime_rate == Money(5000)
    assert repository.workers[WORKER_1_ID] is updated
    audit = repository.audits[0]
    assert audit.action is AuditAction.UPDATED
    assert audit.worker_id == WORKER_1_ID
    assert audit.changed_by == ACTOR_ID
    assert audit.changed_at == NOW


async def test_alta_validacion_no_guarda() -> None:
    repository = FakeWorkerRepository()
    register = RegisterWorker(repository, FixedClock(NOW))

    with pytest.raises(StaffValidationError):
        await register.execute(_data(name="   "), ACTOR_ID)

    assert repository.workers == {}
    assert repository.audits == []


async def test_edicion_validacion_no_guarda() -> None:
    repository = FakeWorkerRepository()
    repository.workers[WORKER_1_ID] = _worker(worker_id=WORKER_1_ID)
    update = UpdateWorker(repository, FixedClock(NOW))

    with pytest.raises(StaffValidationError):
        await update.execute(
            WORKER_1_ID,
            _data(function=WorkerFunction.OTHER, function_description=""),
            ACTOR_ID,
        )

    assert repository.workers[WORKER_1_ID].function is None
    assert repository.audits == []


async def test_edicion_no_encontrado() -> None:
    repository = FakeWorkerRepository()
    update = UpdateWorker(repository, FixedClock(NOW))

    with pytest.raises(WorkerNotFoundError):
        await update.execute(WORKER_1_ID, _data(), ACTOR_ID)

    assert repository.audits == []
