"""Pruebas de los casos de uso de consulta y listado de trabajadores (HU15).

Usan un repositorio fake en memoria: sin base de datos. Cubren CA-15.7 (ficha
activa o inactiva), CA-15.8 (filtros, búsqueda y paginación) y CA-15.12 (lookup
sin datos sensibles).
"""

from __future__ import annotations

from dataclasses import fields
from uuid import UUID

import pytest

from local_eventos.modules.staff.application.errors import WorkerNotFoundError
from local_eventos.modules.staff.application.ports.worker_repository import (
    WorkerPage,
    WorkerRef,
)
from local_eventos.modules.staff.application.search_text import (
    normalize_document,
    normalize_name,
)
from local_eventos.modules.staff.application.use_cases.get_worker import GetWorker
from local_eventos.modules.staff.application.use_cases.get_worker_ref import (
    GetWorkerRef,
)
from local_eventos.modules.staff.application.use_cases.search_workers import (
    SearchWorkers,
)
from local_eventos.modules.staff.domain.audit import WorkerAudit
from local_eventos.modules.staff.domain.document import Document, DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
)
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import Worker

WORKER_1_ID = UUID("11111111-1111-1111-1111-111111111111")
WORKER_2_ID = UUID("22222222-2222-2222-2222-222222222222")
WORKER_3_ID = UUID("33333333-3333-3333-3333-333333333333")


class FakeWorkerRepository:
    """Repositorio en memoria que aplica la misma semántica que el puerto."""

    def __init__(self, workers: list[Worker] | None = None) -> None:
        self.workers = {worker.id: worker for worker in workers or []}

    async def save(self, worker: Worker, audit: WorkerAudit) -> None:
        self.workers[worker.id] = worker

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
        needle_name = normalize_name(text)
        needle_document = normalize_document(text)
        matches = [
            worker
            for worker in self.workers.values()
            if (function is None or worker.function is function)
            and (status is None or worker.status is status)
            and (
                not text
                or needle_name in normalize_name(worker.name)
                or (needle_document and needle_document in worker.document.number)
            )
        ]
        matches.sort(key=lambda worker: normalize_name(worker.name))
        start = (page - 1) * page_size
        return WorkerPage(
            items=matches[start : start + page_size],
            total=len(matches),
            page=page,
            page_size=page_size,
        )

    async def lookup(self, worker_id: UUID) -> WorkerRef | None:
        worker = self.workers.get(worker_id)
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
    *,
    worker_id: UUID,
    name: str,
    document_number: str,
    function: WorkerFunction | None = None,
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


def _repository() -> FakeWorkerRepository:
    return FakeWorkerRepository(
        [
            _worker(
                worker_id=WORKER_1_ID,
                name="José Ramírez",
                document_number="44125896",
                function=WorkerFunction.COOK,
            ),
            _worker(
                worker_id=WORKER_2_ID,
                name="Ana Torres",
                document_number="87654321",
                function=WorkerFunction.WAITER,
                inactive=True,
            ),
            _worker(
                worker_id=WORKER_3_ID,
                name="Luis Quispe",
                document_number="11223344",
                function=WorkerFunction.WAITER,
            ),
        ]
    )


async def test_ca15_7_consulta_ficha_activa() -> None:
    get_worker = GetWorker(_repository())

    worker = await get_worker.execute(WORKER_1_ID)

    assert worker.id == WORKER_1_ID
    assert worker.name == "José Ramírez"
    assert worker.status is WorkerStatus.ACTIVE


async def test_ca15_7_consulta_ficha_inactiva() -> None:
    get_worker = GetWorker(_repository())

    worker = await get_worker.execute(WORKER_2_ID)

    assert worker.status is WorkerStatus.INACTIVE
    assert worker.phone == "987654321"
    assert worker.rate == Money(15000)


async def test_ca15_7_inexistente_lanza_not_found() -> None:
    get_worker = GetWorker(_repository())

    with pytest.raises(WorkerNotFoundError) as excinfo:
        await get_worker.execute(UUID("99999999-9999-9999-9999-999999999999"))

    assert excinfo.value.code == "staff.not_found"


async def test_ca15_8_por_defecto_solo_activos() -> None:
    search = SearchWorkers(_repository())

    page = await search.execute()

    assert {worker.id for worker in page.items} == {WORKER_1_ID, WORKER_3_ID}
    assert page.total == 2
    assert page.page == 1
    assert page.page_size == 20


async def test_ca15_8_filtra_por_estado_inactivo() -> None:
    search = SearchWorkers(_repository())

    page = await search.execute(status=WorkerStatus.INACTIVE)

    assert [worker.id for worker in page.items] == [WORKER_2_ID]


async def test_ca15_8_estado_all_incluye_activos_e_inactivos() -> None:
    search = SearchWorkers(_repository())

    by_all = await search.execute(status="ALL")
    by_none = await search.execute(status=None)

    assert by_all.total == 3
    assert by_none.total == 3


async def test_ca15_8_filtra_por_funcion() -> None:
    search = SearchWorkers(_repository())

    page = await search.execute(function=WorkerFunction.WAITER, status="ALL")

    assert {worker.id for worker in page.items} == {WORKER_2_ID, WORKER_3_ID}


async def test_ca15_8_busca_sin_tildes_ni_mayusculas() -> None:
    search = SearchWorkers(_repository())

    by_name = await search.execute(text="  JOSE   ramirez ")
    by_document = await search.execute(text="44125896")

    assert [worker.id for worker in by_name.items] == [WORKER_1_ID]
    assert [worker.id for worker in by_document.items] == [WORKER_1_ID]


async def test_ca15_8_pagina_y_limita_tamanos() -> None:
    search = SearchWorkers(_repository())

    clamped = await search.execute(status="ALL", page=0, page_size=0)
    capped = await search.execute(status="ALL", page=1, page_size=500)
    second = await search.execute(status="ALL", page=2, page_size=2)

    assert clamped.page == 1
    assert clamped.page_size == 1
    assert capped.page_size == 100
    assert second.page == 2
    assert second.page_size == 2
    assert len(second.items) == 1


async def test_ca15_12_lookup_sin_datos_sensibles() -> None:
    get_ref = GetWorkerRef(_repository())

    ref = await get_ref.execute(WORKER_1_ID)
    missing = await get_ref.execute(UUID("99999999-9999-9999-9999-999999999999"))

    assert ref is not None
    assert ref.name == "José Ramírez"
    assert ref.function is WorkerFunction.COOK
    assert ref.status is WorkerStatus.ACTIVE
    assert {field.name for field in fields(WorkerRef)} == {
        "id",
        "name",
        "function",
        "function_description",
        "status",
    }
    assert missing is None
