"""Agregado `Unavailability` de Darze (HU16, R-DIS-1..R-DIS-10).

Una indisponibilidad marca que un trabajador no puede trabajar en una ventana
UTC semiabierta `[start_at, end_at)` por vacaciones, permiso, descanso u otro
motivo. No es una asignación ni genera pago, y no bloquea HU17 (Q3): solo se
refleja en la consulta de disponibilidad. `worker_id` se fija al crear y no se
puede cambiar; no hay borrado físico ni reactivación: se anula y se registra
otra (Q4, §2.1).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from local_eventos.modules.staff.domain.enums import (
    UnavailabilityKind,
    UnavailabilityStatus,
)
from local_eventos.modules.staff.domain.errors import (
    UNAVAILABILITY_DESCRIPTION_NOT_ALLOWED,
    UNAVAILABILITY_DESCRIPTION_REQUIRED,
    UNAVAILABILITY_DESCRIPTION_TOO_LONG,
    UNAVAILABILITY_WORKER_INVALID,
    StaffValidationError,
    UnavailabilityKindRequiredError,
    UnavailabilityScheduleInvalidError,
)

_DESCRIPTION_MAX_LENGTH = 120
_IMMUTABLE_KEYS = frozenset({"worker_id"})


@dataclass
class Unavailability:
    """Indisponibilidad de un trabajador en una ventana UTC, con estado lógico.

    Se construye con `Unavailability.register` (siempre `ACTIVE`) y solo los
    campos editables cambian con `update`. `cancel` anula de forma idempotente y
    terminal; no existe `delete` ni reactivación.
    """

    id: UUID
    worker_id: UUID
    kind: UnavailabilityKind
    description: str | None
    start_at: datetime
    end_at: datetime
    status: UnavailabilityStatus

    def __setattr__(self, name: str, value: object) -> None:
        if name in _IMMUTABLE_KEYS and name in self.__dict__:
            raise AttributeError(
                f"'{name}' es inmutable: registre otra indisponibilidad para otro trabajador."
            )
        super().__setattr__(name, value)

    @classmethod
    def register(
        cls,
        *,
        worker_id: UUID,
        kind: UnavailabilityKind | None,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
        unavailability_id: UUID | None = None,
    ) -> Unavailability:
        """Registra una indisponibilidad nueva, activa, validando todo antes."""
        new_worker_id = _require_uuid(
            worker_id, UNAVAILABILITY_WORKER_INVALID, "El trabajador es obligatorio."
        )
        new_kind = _require_kind(kind)
        new_description = _clean_description(new_kind, description)
        new_start_at, new_end_at = _validate_window(start_at, end_at)
        return cls(
            id=unavailability_id if unavailability_id is not None else uuid4(),
            worker_id=new_worker_id,
            kind=new_kind,
            description=new_description,
            start_at=new_start_at,
            end_at=new_end_at,
            status=UnavailabilityStatus.ACTIVE,
        )

    def update(
        self,
        *,
        kind: UnavailabilityKind | None,
        start_at: datetime,
        end_at: datetime,
        description: str | None = None,
    ) -> bool:
        """Reemplaza solo los campos editables; devuelve si hubo cambio real.

        Valida todo antes de mutar: si algo falla, conserva sus valores previos.
        `worker_id` y el estado no forman parte de la edición (no reactiva).
        """
        new_kind = _require_kind(kind)
        new_description = _clean_description(new_kind, description)
        new_start_at, new_end_at = _validate_window(start_at, end_at)

        changed = (
            new_kind is not self.kind
            or new_description != self.description
            or new_start_at != self.start_at
            or new_end_at != self.end_at
        )
        if not changed:
            return False

        self.kind = new_kind
        self.description = new_description
        self.start_at = new_start_at
        self.end_at = new_end_at
        return True

    def cancel(self) -> bool:
        """Anula la indisponibilidad; idempotente y terminal (Q4)."""
        if self.status is UnavailabilityStatus.CANCELLED:
            return False
        self.status = UnavailabilityStatus.CANCELLED
        return True

    def overlaps(self, start_at: datetime, end_at: datetime) -> bool:
        """Indica si la ventana semiabierta dada comparte algún instante con esta."""
        query_start, query_end = _validate_window(start_at, end_at)
        return self.start_at < query_end and self.end_at > query_start

    def snapshot(self) -> dict[str, object]:
        """Valores serializables para la auditoría `UPDATED` (HU16, §2.3)."""
        return {
            "kind": self.kind.value,
            "description": self.description,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
        }


def _require_uuid(value: object, code: str, message: str) -> UUID:
    if not isinstance(value, UUID):
        raise StaffValidationError(code, message)
    return value


def _require_kind(kind: UnavailabilityKind | None) -> UnavailabilityKind:
    if not isinstance(kind, UnavailabilityKind):
        raise UnavailabilityKindRequiredError()
    return kind


def _clean_description(kind: UnavailabilityKind, description: str | None) -> str | None:
    if description is not None and not isinstance(description, str):
        raise StaffValidationError(
            UNAVAILABILITY_DESCRIPTION_REQUIRED,
            "La descripción de la indisponibilidad debe ser texto.",
        )
    cleaned = None if description is None else (" ".join(description.split()) or None)
    if kind is UnavailabilityKind.OTHER:
        if cleaned is None:
            raise StaffValidationError(
                UNAVAILABILITY_DESCRIPTION_REQUIRED,
                "El tipo «otro» exige una descripción.",
            )
        if len(cleaned) > _DESCRIPTION_MAX_LENGTH:
            raise StaffValidationError(
                UNAVAILABILITY_DESCRIPTION_TOO_LONG,
                "La descripción de la indisponibilidad no puede superar "
                f"{_DESCRIPTION_MAX_LENGTH} caracteres.",
            )
        return cleaned
    if cleaned is not None:
        raise StaffValidationError(
            UNAVAILABILITY_DESCRIPTION_NOT_ALLOWED,
            "Solo el tipo «otro» admite descripción.",
        )
    return None


def _validate_window(start_at: datetime, end_at: datetime) -> tuple[datetime, datetime]:
    new_start_at = _require_aware(start_at, "inicio")
    new_end_at = _require_aware(end_at, "fin")
    if new_end_at <= new_start_at:
        raise UnavailabilityScheduleInvalidError()
    return new_start_at, new_end_at


def _require_aware(value: object, label: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise UnavailabilityScheduleInvalidError(
            f"La fecha y hora de {label} deben incluir zona horaria."
        )
    return value.astimezone(UTC)
