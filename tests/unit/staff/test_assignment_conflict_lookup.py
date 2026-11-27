"""Pruebas del adaptador `AssignmentConflictLookup` (HU16, T-08). Sin base de datos.

Verifican que la lectura es **una sola** consulta `WHERE id IN (...)` sobre
`staff_assignments`, que proyecta únicamente `id`, `worker_function` y
`function_description`, que los ids ausentes se mapean a `None` y que no se usa
`AssignmentView` ni se leen datos de pago (plan §7.1, §3.1).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.staff.application.ports.assignment_conflict_lookup import (
    AssignmentFunction,
)
from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.infrastructure import assignment_conflict_lookup as module


class _Result:
    """Resultado mínimo con la única operación que usa el adaptador: `all()`."""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)


class _SpySession:
    """Sesión falsa que guarda las sentencias y devuelve filas prefijadas."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.statements: list[Any] = []

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        return _Result(self.rows)


def _lookup(session: _SpySession) -> module.SqlAlchemyAssignmentConflictLookup:
    return module.SqlAlchemyAssignmentConflictLookup(cast(AsyncSession, session))


async def test_by_ids_una_consulta_y_solo_columnas_permitidas() -> None:
    first, second, missing = uuid4(), uuid4(), uuid4()
    session = _SpySession(
        [
            SimpleNamespace(id=first, worker_function="WAITER", function_description=None),
            SimpleNamespace(id=second, worker_function="OTHER", function_description="Sonido"),
        ]
    )

    result = await _lookup(session).by_ids([first, second, missing])

    assert result[first] == AssignmentFunction(WorkerFunction.WAITER, None)
    assert result[second] == AssignmentFunction(WorkerFunction.OTHER, "Sonido")
    assert result[missing] is None
    assert len(session.statements) == 1

    statement = session.statements[0]
    assert set(statement.selected_columns.keys()) == {
        "id",
        "worker_function",
        "function_description",
    }
    sql = str(statement)
    assert "staff_assignments" in sql
    assert "WHERE" in sql and " IN " in sql
    # Sin predicados temporales ni de estado: el solape lo decide HU17.
    assert "start_at" not in sql
    assert "end_at" not in sql
    assert "status" not in sql
    # Sin pago ni la vista económica de HU17.
    assert "pay_cents" not in sql
    assert "currency" not in sql
    assert not hasattr(module, "AssignmentView")
    assert not hasattr(module, "AssignmentOverlap")


async def test_by_ids_sin_ids_no_consulta() -> None:
    session = _SpySession([])

    assert await _lookup(session).by_ids([]) == {}
    assert session.statements == []


async def test_by_ids_deduplica_ids_en_una_consulta() -> None:
    worker = uuid4()
    session = _SpySession(
        [SimpleNamespace(id=worker, worker_function="COOK", function_description=None)]
    )

    result = await _lookup(session).by_ids([worker, worker])

    assert result == {worker: AssignmentFunction(WorkerFunction.COOK, None)}
    assert len(session.statements) == 1
