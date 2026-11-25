"""Pruebas de la fábrica pública `worker_lookup` del módulo staff (HU15, CA-15.12).

Verifican la superficie que consumirá HU17: solo lectura, con id, nombre, función,
descripción y estado; sin documento, teléfono, tarifa ni operaciones de escritura.
Usan un repositorio fake en memoria: sin base de datos ni sesión real.
"""

from __future__ import annotations

from dataclasses import fields
from typing import cast
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff import composition, public_api
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRef,
)
from local_eventos.modules.staff.domain.audit import WorkerAudit
from local_eventos.modules.staff.domain.document import Document, DocumentType
from local_eventos.modules.staff.domain.enums import WorkerFunction, WorkerStatus
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker

ACTIVE_ID = UUID("11111111-1111-1111-1111-111111111111")
INACTIVE_ID = UUID("22222222-2222-2222-2222-222222222222")
MISSING_ID = UUID("99999999-9999-9999-9999-999999999999")


class FakeWorkerRepository:
    """Repositorio en memoria con la misma semántica que el puerto."""

    def __init__(self, workers: list[Worker]) -> None:
        self._workers = {worker.id: worker for worker in workers}

    async def save(self, worker: Worker, audit: WorkerAudit) -> None:
        self._workers[worker.id] = worker

    async def get(self, worker_id: UUID) -> Worker | None:
        return self._workers.get(worker_id)

    async def get_for_update(self, worker_id: UUID) -> Worker | None:
        return self._workers.get(worker_id)

    async def get_by_document(self, document: Document) -> Worker | None:
        return next(
            (worker for worker in self._workers.values() if worker.document == document),
            None,
        )

    async def search(
        self,
        *,
        text: str,
        function: WorkerFunction | None,
        status: WorkerStatus | None,
        page: int,
        page_size: int,
    ) -> WorkerPage:
        matches = [
            worker
            for worker in self._workers.values()
            if (function is None or worker.function is function)
            and (status is None or worker.status is status)
        ]
        start = (page - 1) * page_size
        return WorkerPage(
            items=matches[start : start + page_size],
            total=len(matches),
            page=page,
            page_size=page_size,
        )

    async def lookup(self, worker_id: UUID) -> WorkerRef | None:
        worker = self._workers.get(worker_id)
        if worker is None:
            return None
        return WorkerRef(
            id=worker.id,
            name=worker.name,
            function=worker.function,
            function_description=worker.function_description,
            status=worker.status,
        )


def _worker(
    worker_id: UUID,
    *,
    name: str,
    document_number: str,
    function: WorkerFunction | None,
    function_description: str | None = None,
    inactive: bool = False,
) -> Worker:
    worker = Worker.register(
        worker_id=worker_id,
        name=name,
        document_type=DocumentType.DNI,
        document_number=document_number,
        phone="987654321",
        function=function,
        function_description=function_description,
        rate=Money(15000),
    )
    if inactive:
        worker.deactivate()
    return worker


def _lookup(monkeypatch, workers: list[Worker]):  # type: ignore[no-untyped-def]
    """Fábrica pública con la sesión sustituida por el repositorio fake."""
    repository = FakeWorkerRepository(workers)
    monkeypatch.setattr(composition, "worker_repository", lambda session: repository)
    return public_api.worker_lookup(cast(AsyncSession, object()))


async def test_worker_lookup_devuelve_campos_publicos(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    lookup = _lookup(
        monkeypatch,
        [
            _worker(
                ACTIVE_ID,
                name="José Ramírez",
                document_number="44125896",
                function=WorkerFunction.OTHER,
                function_description="Parrillero",
            )
        ],
    )

    ref = await lookup.get(ACTIVE_ID)

    assert ref is not None
    assert ref.id == ACTIVE_ID
    assert ref.name == "José Ramírez"
    assert ref.function is WorkerFunction.OTHER
    assert ref.function_description == "Parrillero"
    assert ref.status is WorkerStatus.ACTIVE


async def test_worker_lookup_consulta_inactivo(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    lookup = _lookup(
        monkeypatch,
        [
            _worker(
                INACTIVE_ID,
                name="Ana Torres",
                document_number="87654321",
                function=WorkerFunction.WAITER,
                inactive=True,
            )
        ],
    )

    ref = await lookup.get(INACTIVE_ID)

    assert ref is not None
    assert ref.status is WorkerStatus.INACTIVE
    assert ref.function is WorkerFunction.WAITER


async def test_worker_lookup_inexistente_devuelve_none(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    lookup = _lookup(monkeypatch, [])

    assert await lookup.get(MISSING_ID) is None


async def test_worker_lookup_no_expone_datos_sensibles_ni_escritura(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    lookup = _lookup(
        monkeypatch,
        [
            _worker(
                ACTIVE_ID,
                name="José Ramírez",
                document_number="44125896",
                function=WorkerFunction.COOK,
            )
        ],
    )

    assert {field.name for field in fields(WorkerRef)} == {
        "id",
        "name",
        "function",
        "function_description",
        "status",
    }
    for forbidden_field in ("document", "document_number", "phone", "rate"):
        assert forbidden_field not in {field.name for field in fields(WorkerRef)}
    for write_operation in ("save", "register", "update", "deactivate", "activate"):
        assert not hasattr(lookup, write_operation)
