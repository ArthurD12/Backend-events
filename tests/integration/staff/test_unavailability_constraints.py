"""Constraints y triggers de indisponibilidades contra PostgreSQL real (HU16, T-12).

Cubre los CHECK de `staff_unavailabilities` con SQL directo, la FK a `staff_workers`
con `ON DELETE RESTRICT`, la inmutabilidad de `worker_id`, la prohibición de reactivar
una anulada, el no borrado físico y la presencia de los índices declarados en la
migración. Necesita Docker/PostgreSQL.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine
from testcontainers.community.postgres import PostgresContainer

from local_eventos.shared.infrastructure.db import create_engine

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[3]
_WORKER_ID = UUID("22222222-2222-2222-2222-222222222222")
_OTHER_WORKER_ID = UUID("33333333-3333-3333-3333-333333333333")

_INSERT_WORKER = text(
    """
    INSERT INTO staff_workers (
        id, name, document_type, document_number, phone, worker_function,
        function_description, worker_type, rate_cents, overtime_applies,
        overtime_rate_cents, status
    ) VALUES (
        :id, :name, 'DNI', :document_number, NULL, 'WAITER',
        NULL, NULL, NULL, false, NULL, 'ACTIVE'
    )
    """
)

_INSERT_UNAVAILABILITY = text(
    """
    INSERT INTO staff_unavailabilities (
        id, worker_id, kind, description, start_at, end_at, status
    ) VALUES (
        :id, :worker_id, :kind, :description, :start_at, :end_at, :status
    )
    """
)

_VALID_UNAVAILABILITY: dict[str, Any] = {
    "kind": "VACATION",
    "description": None,
    "start_at": datetime(2026, 12, 19, 18, 0, tzinfo=UTC),
    "end_at": datetime(2026, 12, 19, 23, 0, tzinfo=UTC),
    "status": "ACTIVE",
}


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    async with engine.begin() as connection:
        # TRUNCATE no dispara los triggers de fila append-only; deja todo vacío.
        await connection.execute(
            text(
                "TRUNCATE staff_unavailabilities_audit, staff_unavailabilities, "
                "staff_attendance_audit, staff_attendance, "
                "staff_assignment_audit, staff_assignments, "
                "staff_worker_audit, staff_workers RESTART IDENTITY CASCADE"
            )
        )
    yield engine
    await engine.dispose()


async def _seed_worker(
    engine: AsyncEngine,
    *,
    worker_id: UUID = _WORKER_ID,
    document_number: str = "44125896",
    name: str = "Ana Pérez",
) -> None:
    async with engine.begin() as connection:
        await connection.execute(
            _INSERT_WORKER,
            {
                "id": worker_id,
                "name": name,
                "document_number": document_number,
            },
        )


def _values(**overrides: Any) -> dict[str, Any]:
    return {
        "id": uuid4(),
        "worker_id": _WORKER_ID,
        **_VALID_UNAVAILABILITY,
        **overrides,
    }


async def _insert(engine: AsyncEngine, values: dict[str, Any]) -> None:
    async with engine.begin() as connection:
        await connection.execute(_INSERT_UNAVAILABILITY, values)


async def _count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as connection:
        total = await connection.scalar(text(f"SELECT count(*) FROM {table}"))
    return int(total or 0)


@pytest.mark.parametrize(
    ("overrides", "constraint"),
    [
        pytest.param(
            {"end_at": _VALID_UNAVAILABILITY["start_at"]},
            "ck_staff_unavailabilities_window_valid",
            id="ventana-vacia",
        ),
        pytest.param(
            {"kind": "SICK"},
            "ck_staff_unavailabilities_kind_valid",
            id="tipo-invalido",
        ),
        pytest.param(
            {"kind": "OTHER", "description": None},
            "ck_staff_unavailabilities_description_valid",
            id="otro-sin-descripcion",
        ),
        pytest.param(
            {"kind": "VACATION", "description": "Viaje"},
            "ck_staff_unavailabilities_description_valid",
            id="descripcion-con-otro-tipo",
        ),
        pytest.param(
            {"kind": "OTHER", "description": "   "},
            "ck_staff_unavailabilities_description_valid",
            id="otro-descripcion-en-blanco",
        ),
        pytest.param(
            {"status": "DELETED"},
            "ck_staff_unavailabilities_status_valid",
            id="estado-invalido",
        ),
    ],
)
async def test_los_checks_rechazan_datos_invalidos_con_sql_directo(
    engine: AsyncEngine,
    overrides: dict[str, Any],
    constraint: str,
) -> None:
    await _seed_worker(engine)

    with pytest.raises(IntegrityError, match=constraint):
        await _insert(engine, _values(**overrides))

    assert await _count(engine, "staff_unavailabilities") == 0


async def test_fk_a_staff_workers_rechaza_un_trabajador_inexistente(
    engine: AsyncEngine,
) -> None:
    with pytest.raises(IntegrityError, match="fk_staff_unavailabilities_worker_id"):
        await _insert(engine, _values(worker_id=uuid4()))

    assert await _count(engine, "staff_unavailabilities") == 0


async def test_fk_restrict_impide_borrar_al_trabajador_referenciado(
    engine: AsyncEngine,
) -> None:
    await _seed_worker(engine)
    await _insert(engine, _values())

    with pytest.raises(IntegrityError, match="fk_staff_unavailabilities_worker_id"):
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM staff_workers WHERE id = :id"), {"id": _WORKER_ID}
            )

    assert await _count(engine, "staff_workers") == 1
    assert await _count(engine, "staff_unavailabilities") == 1


async def test_worker_id_es_inmutable(engine: AsyncEngine) -> None:
    await _seed_worker(engine)
    await _seed_worker(
        engine,
        worker_id=_OTHER_WORKER_ID,
        document_number="44125897",
        name="Luis Gómez",
    )
    unavailability_id = uuid4()
    await _insert(engine, _values(id=unavailability_id))

    with pytest.raises(IntegrityError, match="inmutable"):
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE staff_unavailabilities SET worker_id = :other WHERE id = :id"),
                {"other": _OTHER_WORKER_ID, "id": unavailability_id},
            )

    async with engine.connect() as connection:
        stored = await connection.scalar(
            text("SELECT worker_id FROM staff_unavailabilities WHERE id = :id"),
            {"id": unavailability_id},
        )

    assert stored == _WORKER_ID


async def test_una_anulada_no_se_reactiva(engine: AsyncEngine) -> None:
    await _seed_worker(engine)
    unavailability_id = uuid4()
    await _insert(engine, _values(id=unavailability_id, status="CANCELLED"))

    with pytest.raises(IntegrityError, match="no se reactiva"):
        async with engine.begin() as connection:
            await connection.execute(
                text("UPDATE staff_unavailabilities SET status = 'ACTIVE' WHERE id = :id"),
                {"id": unavailability_id},
            )

    async with engine.connect() as connection:
        stored = await connection.scalar(
            text("SELECT status FROM staff_unavailabilities WHERE id = :id"),
            {"id": unavailability_id},
        )

    assert stored == "CANCELLED"


async def test_la_indisponibilidad_no_se_borra_fisicamente(engine: AsyncEngine) -> None:
    await _seed_worker(engine)
    unavailability_id = uuid4()
    await _insert(engine, _values(id=unavailability_id))

    with pytest.raises(IntegrityError, match="no se borra"):
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM staff_unavailabilities WHERE id = :id"),
                {"id": unavailability_id},
            )

    assert await _count(engine, "staff_unavailabilities") == 1


async def test_los_indices_de_la_migracion_estan_presentes(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        workers_start = await connection.scalar(
            text(
                "SELECT indexname FROM pg_indexes"
                " WHERE schemaname = 'public' AND tablename = :table"
                " AND indexname = :index"
            ),
            {"table": "staff_unavailabilities", "index": "ix_staff_unavailabilities_worker_start"},
        )
        start_end = await connection.scalar(
            text(
                "SELECT indexname FROM pg_indexes"
                " WHERE schemaname = 'public' AND tablename = :table"
                " AND indexname = :index"
            ),
            {"table": "staff_unavailabilities", "index": "ix_staff_unavailabilities_start_end"},
        )
        audit = await connection.scalar(
            text(
                "SELECT indexname FROM pg_indexes"
                " WHERE schemaname = 'public' AND tablename = :table"
                " AND indexname = :index"
            ),
            {
                "table": "staff_unavailabilities_audit",
                "index": "ix_staff_unavailabilities_audit_unavailability_occurred",
            },
        )

    assert workers_start == "ix_staff_unavailabilities_worker_start"
    assert start_end == "ix_staff_unavailabilities_start_end"
    assert audit == "ix_staff_unavailabilities_audit_unavailability_occurred"
