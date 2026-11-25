"""Auditoría de asignaciones de Darze (HU17, R-ASG-8/R-ASG-9).

Una fila append-only por `CREATED`, `UPDATED` o `CANCELLED`. La edición y la
anulación guardan actor, fecha-hora (UTC) y motivo obligatorio; la edición guarda
además los valores anteriores y nuevos de función, horario y pago. El actor es un
UUID de `identity`, sin FK ni import cruzado entre módulos.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from local_eventos.modules.staff.domain.enums import WorkerFunction
from local_eventos.modules.staff.domain.errors import (
    AssignmentReasonRequiredError,
    StaffValidationError,
)
from local_eventos.modules.staff.domain.money import CURRENCY

_SNAPSHOT_KEYS = frozenset(
    {"function", "function_description", "start_at", "end_at", "pay_cents", "currency"}
)


class AssignmentAction(StrEnum):
    """Operación auditada sobre una asignación, de solo inserción (R-ASG-9)."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class AssignmentSnapshot:
    """Valores editables de una asignación para la auditoría `UPDATED` (R-ASG-9).

    Inmutable y serializable a JSON. Se construye desde el `dict` que devuelve
    `Assignment.snapshot()` con `from_mapping` y se vuelve a `dict` con `to_dict`.
    Instantes normalizados a UTC; pago en céntimos enteros `>= 0` y moneda `PEN`.
    """

    function: WorkerFunction
    function_description: str | None
    start_at: datetime
    end_at: datetime
    pay_cents: int
    currency: str = CURRENCY

    def __post_init__(self) -> None:
        if not isinstance(self.function, WorkerFunction):
            raise StaffValidationError(
                "staff.audit_invalid", "La función del snapshot no es válida."
            )
        if self.function_description is not None and not isinstance(self.function_description, str):
            raise StaffValidationError(
                "staff.audit_invalid", "La descripción del snapshot debe ser texto."
            )
        object.__setattr__(self, "start_at", _require_aware(self.start_at, "inicio del snapshot"))
        object.__setattr__(self, "end_at", _require_aware(self.end_at, "fin del snapshot"))
        if isinstance(self.pay_cents, bool) or not isinstance(self.pay_cents, int):
            raise StaffValidationError(
                "staff.audit_invalid", "El pago del snapshot debe ser un entero de céntimos."
            )
        if self.pay_cents < 0:
            raise StaffValidationError(
                "staff.audit_invalid", "El pago del snapshot no puede ser negativo."
            )
        if self.currency != CURRENCY:
            raise StaffValidationError(
                "staff.audit_invalid", f"La moneda del snapshot debe ser {CURRENCY}."
            )

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> AssignmentSnapshot:
        """Construye el snapshot desde el `dict` JSON-compatible de `snapshot()`."""
        missing = _SNAPSHOT_KEYS.difference(values)
        if missing:
            raise StaffValidationError(
                "staff.audit_invalid",
                f"Faltan claves en el snapshot: {', '.join(sorted(missing))}.",
            )
        return cls(
            function=_coerce_function(values["function"]),
            function_description=_coerce_optional_text(values["function_description"]),
            start_at=_coerce_datetime(values["start_at"]),
            end_at=_coerce_datetime(values["end_at"]),
            pay_cents=_coerce_pay(values["pay_cents"]),
            currency=_coerce_text(values["currency"]),
        )

    def to_dict(self) -> dict[str, object]:
        """Devuelve un `dict` JSON-compatible con el mismo formato que `snapshot()`."""
        return {
            "function": self.function.value,
            "function_description": self.function_description,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
            "pay_cents": self.pay_cents,
            "currency": self.currency,
        }


@dataclass(frozen=True)
class AssignmentAudit:
    """Operación auditada sobre una asignación, inmutable y de solo inserción.

    `CREATED` no admite motivo ni snapshots. `UPDATED` exige motivo no vacío y los
    dos snapshots. `CANCELLED` exige motivo no vacío y no guarda snapshots.
    `occurred_at` debe ser timezone-aware y se normaliza a UTC.
    """

    assignment_id: UUID
    action: AssignmentAction
    actor_id: UUID
    occurred_at: datetime
    reason: str | None = None
    previous_values: AssignmentSnapshot | None = None
    new_values: AssignmentSnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.assignment_id, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "La asignación auditada debe ser un UUID."
            )
        if not isinstance(self.actor_id, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "El actor de la auditoría debe ser un UUID."
            )
        if not isinstance(self.action, AssignmentAction):
            raise StaffValidationError(
                "staff.audit_invalid", "La acción de auditoría no es válida."
            )
        if not isinstance(self.occurred_at, datetime) or self.occurred_at.tzinfo is None:
            raise StaffValidationError(
                "staff.audit_invalid", "La fecha de la auditoría debe incluir zona horaria."
            )
        object.__setattr__(self, "occurred_at", self.occurred_at.astimezone(UTC))

        reason = _normalize_reason(self.reason)
        object.__setattr__(self, "reason", reason)
        self._validate_previous()
        self._validate_new()

        if self.action is AssignmentAction.CREATED:
            if reason is not None:
                raise StaffValidationError(
                    "staff.audit_reason_not_allowed",
                    "La acción CREATED no admite motivo.",
                )
            if self.previous_values is not None or self.new_values is not None:
                raise StaffValidationError(
                    "staff.audit_invalid",
                    "La acción CREATED no guarda snapshots.",
                )
        elif self.action is AssignmentAction.UPDATED:
            if reason is None:
                raise AssignmentReasonRequiredError("La edición de una asignación requiere motivo.")
            if self.previous_values is None or self.new_values is None:
                raise StaffValidationError(
                    "staff.audit_invalid",
                    "La edición debe guardar los valores anteriores y nuevos.",
                )
        elif self.action is AssignmentAction.CANCELLED:
            if reason is None:
                raise AssignmentReasonRequiredError(
                    "La anulación de una asignación requiere motivo."
                )
            if self.previous_values is not None or self.new_values is not None:
                raise StaffValidationError(
                    "staff.audit_invalid",
                    "La anulación no guarda snapshots.",
                )

    def _validate_previous(self) -> None:
        if self.previous_values is not None and not isinstance(
            self.previous_values, AssignmentSnapshot
        ):
            raise StaffValidationError(
                "staff.audit_invalid", "Los valores anteriores deben ser un snapshot."
            )

    def _validate_new(self) -> None:
        if self.new_values is not None and not isinstance(self.new_values, AssignmentSnapshot):
            raise StaffValidationError(
                "staff.audit_invalid", "Los valores nuevos deben ser un snapshot."
            )

    @classmethod
    def created(
        cls, *, assignment_id: UUID, actor_id: UUID, occurred_at: datetime
    ) -> AssignmentAudit:
        """Auditoría del alta: sin motivo ni snapshots."""
        return cls(
            assignment_id=assignment_id,
            action=AssignmentAction.CREATED,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )

    @classmethod
    def updated(
        cls,
        *,
        assignment_id: UUID,
        actor_id: UUID,
        occurred_at: datetime,
        reason: str,
        previous_values: AssignmentSnapshot,
        new_values: AssignmentSnapshot,
    ) -> AssignmentAudit:
        """Auditoría de la edición: motivo y snapshots anterior/nuevo obligatorios."""
        return cls(
            assignment_id=assignment_id,
            action=AssignmentAction.UPDATED,
            actor_id=actor_id,
            occurred_at=occurred_at,
            reason=reason,
            previous_values=previous_values,
            new_values=new_values,
        )

    @classmethod
    def cancelled(
        cls, *, assignment_id: UUID, actor_id: UUID, occurred_at: datetime, reason: str
    ) -> AssignmentAudit:
        """Auditoría de la anulación lógica: motivo obligatorio, sin snapshots."""
        return cls(
            assignment_id=assignment_id,
            action=AssignmentAction.CANCELLED,
            actor_id=actor_id,
            occurred_at=occurred_at,
            reason=reason,
        )


def _normalize_reason(reason: object) -> str | None:
    if reason is None:
        return None
    if not isinstance(reason, str):
        raise StaffValidationError(
            "staff.audit_invalid", "El motivo de la auditoría debe ser texto."
        )
    stripped = reason.strip()
    return stripped or None


def _require_aware(value: datetime, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise StaffValidationError(
            "staff.audit_invalid", f"La fecha de {label} debe incluir zona horaria."
        )
    return value.astimezone(UTC)


def _coerce_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise StaffValidationError(
                "staff.audit_invalid", "La fecha del snapshot no es ISO 8601 válida."
            ) from exc
    raise StaffValidationError(
        "staff.audit_invalid", "La fecha del snapshot debe ser texto ISO 8601 o datetime."
    )


def _coerce_function(value: object) -> WorkerFunction:
    if isinstance(value, WorkerFunction):
        return value
    if isinstance(value, str):
        try:
            return WorkerFunction(value)
        except ValueError as exc:
            raise StaffValidationError(
                "staff.audit_invalid", "La función del snapshot no es válida."
            ) from exc
    raise StaffValidationError("staff.audit_invalid", "La función del snapshot debe ser texto.")


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise StaffValidationError(
        "staff.audit_invalid", "La descripción del snapshot debe ser texto o nulo."
    )


def _coerce_text(value: object) -> str:
    if isinstance(value, str):
        return value
    raise StaffValidationError("staff.audit_invalid", "La moneda del snapshot debe ser texto.")


def _coerce_pay(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise StaffValidationError(
            "staff.audit_invalid", "El pago del snapshot debe ser un entero de céntimos."
        )
    return value
