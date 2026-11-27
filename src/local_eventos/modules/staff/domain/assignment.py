"""Agregado `Assignment` de Darze (HU17, R-ASG-1..R-ASG-9).

Una asignación fija un trabajador a un evento con función, ventana UTC y pago
acordado. El evento se referencia por UUID, sin conocer `commercial` (R-ASG-13).
`worker_id` y `event_id` se fijan al crear y no se pueden cambiar (R-ASG-1): para
corregirlos se anula la asignación y se crea otra. No hay borrado físico ni
reactivación; la anulación es lógica y libera la ocupación del trabajador.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from local_eventos.modules.staff.domain.enums import AssignmentStatus, WorkerFunction
from local_eventos.modules.staff.domain.errors import (
    AssignmentFunctionRequiredError,
    AssignmentPayInvalidError,
    AssignmentScheduleInvalidError,
    StaffValidationError,
)
from local_eventos.modules.staff.domain.money import Money
from local_eventos.modules.staff.domain.worker import _clean_function_description

_IMMUTABLE_KEYS = frozenset({"event_id", "worker_id"})


@dataclass
class Assignment:
    """Trabajador asignado a un evento con función, horario UTC y pago acordado.

    Se construye con `Assignment.register` (siempre `ACTIVE` y `occupies=True`) y
    solo los campos editables cambian con `update`. `cancel` anula y `release`
    libera la ocupación de un evento cancelado sin cambiar el estado.
    """

    id: UUID
    event_id: UUID
    worker_id: UUID
    function: WorkerFunction
    function_description: str | None
    start_at: datetime
    end_at: datetime
    pay: Money
    status: AssignmentStatus
    occupies: bool

    def __setattr__(self, name: str, value: object) -> None:
        if name in _IMMUTABLE_KEYS and name in self.__dict__:
            raise AttributeError(f"'{name}' es inmutable: anule la asignación y cree una nueva.")
        super().__setattr__(name, value)

    @classmethod
    def register(
        cls,
        *,
        event_id: UUID,
        worker_id: UUID,
        function: WorkerFunction | None,
        start_at: datetime,
        end_at: datetime,
        pay: Money | int,
        function_description: str | None = None,
        assignment_id: UUID | None = None,
    ) -> Assignment:
        """Registra una asignación nueva, activa y ocupando, validando todo antes."""
        new_event_id = _require_uuid(
            event_id, "staff.assignment_event_invalid", "El evento es obligatorio."
        )
        new_worker_id = _require_uuid(
            worker_id, "staff.assignment_worker_invalid", "El trabajador es obligatorio."
        )
        new_function = _require_function(function)
        new_description = _clean_function_description(new_function, function_description)
        new_start_at, new_end_at = _validate_window(start_at, end_at)
        new_pay = _validate_pay(pay)
        return cls(
            id=assignment_id if assignment_id is not None else uuid4(),
            event_id=new_event_id,
            worker_id=new_worker_id,
            function=new_function,
            function_description=new_description,
            start_at=new_start_at,
            end_at=new_end_at,
            pay=new_pay,
            status=AssignmentStatus.ACTIVE,
            occupies=True,
        )

    def update(
        self,
        *,
        function: WorkerFunction | None,
        start_at: datetime,
        end_at: datetime,
        pay: Money | int,
        function_description: str | None = None,
    ) -> bool:
        """Reemplaza solo los campos editables; devuelve si hubo cambio real.

        Valida todo antes de mutar: si algo falla, la asignación conserva sus valores
        anteriores. `event_id` y `worker_id` no forman parte de la edición.
        """
        new_function = _require_function(function)
        new_description = _clean_function_description(new_function, function_description)
        new_start_at, new_end_at = _validate_window(start_at, end_at)
        new_pay = _validate_pay(pay)

        changed = (
            new_function is not self.function
            or new_description != self.function_description
            or new_start_at != self.start_at
            or new_end_at != self.end_at
            or new_pay != self.pay
        )
        if not changed:
            return False

        self.function = new_function
        self.function_description = new_description
        self.start_at = new_start_at
        self.end_at = new_end_at
        self.pay = new_pay
        return True

    def cancel(self) -> bool:
        """Anula la asignación y la libera; idempotente (R-ASG-8)."""
        if self.status is AssignmentStatus.CANCELLED:
            return False
        self.status = AssignmentStatus.CANCELLED
        self.occupies = False
        return True

    def release(self) -> bool:
        """Suelta la ocupación sin cambiar el estado; idempotente (R-ASG-12)."""
        if not self.occupies:
            return False
        self.occupies = False
        return True

    def snapshot(self) -> dict[str, object]:
        """Valores serializables para la auditoría `UPDATED` (T-04).

        La función va por su valor y los instantes en ISO 8601 para que el
        repositorio los guarde como JSONB sin duplicar la serialización.
        """
        return {
            "function": self.function.value,
            "function_description": self.function_description,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "pay_cents": self.pay.cents,
            "currency": self.pay.currency,
        }


def _require_uuid(value: UUID, code: str, message: str) -> UUID:
    if not isinstance(value, UUID):
        raise StaffValidationError(code, message)
    return value


def _require_function(function: WorkerFunction | None) -> WorkerFunction:
    if not isinstance(function, WorkerFunction):
        raise AssignmentFunctionRequiredError()
    return function


def _validate_window(start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
    new_start_at = _require_aware(start_at, "inicio")
    new_end_at = _require_aware(end_at, "fin")
    if new_end_at <= new_start_at:
        raise AssignmentScheduleInvalidError("La hora de fin debe ser posterior a la de inicio.")
    return new_start_at, new_end_at


def _require_aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise AssignmentScheduleInvalidError(
            f"La fecha y hora de {label} deben incluir zona horaria."
        )
    return value.astimezone(UTC)


def _validate_pay(pay: Money | int) -> Money:
    if isinstance(pay, Money):
        return pay
    if isinstance(pay, bool) or not isinstance(pay, int):
        raise AssignmentPayInvalidError()
    try:
        return Money(pay)
    except StaffValidationError as exc:
        raise AssignmentPayInvalidError() from exc
