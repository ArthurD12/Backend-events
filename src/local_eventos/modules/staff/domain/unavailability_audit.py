"""Auditoría de indisponibilidades de Darze (HU16, §2.3, Q4).

Una fila append-only por `CREATED`, `UPDATED` o `CANCELLED`. La edición y la
anulación guardan actor, fecha-hora (UTC) y motivo obligatorio (máx. 500); la
edición guarda además los valores anteriores y nuevos de tipo, descripción y
horario. El actor es un UUID de `identity`, sin FK ni import cruzado.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from local_eventos.modules.staff.domain.enums import UnavailabilityKind
from local_eventos.modules.staff.domain.errors import (
    StaffValidationError,
    UnavailabilityReasonRequiredError,
)

_SNAPSHOT_KEYS = frozenset({"kind", "description", "start_at", "end_at"})
_REASON_MAX_LENGTH = 500


class UnavailabilityAction(StrEnum):
    """Operación auditada sobre una indisponibilidad, de solo inserción (Q4)."""

    CREATED = "CREATED"
    UPDATED = "UPDATED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class UnavailabilitySnapshot:
    """Valores editables de una indisponibilidad para la auditoría `UPDATED`.

    Inmutable y serializable a JSON. Se construye desde el `dict` que devuelve
    `Unavailability.snapshot()` con `from_mapping` y se vuelve a `dict` con
    `to_dict`. Instantes normalizados a UTC.
    """

    kind: UnavailabilityKind
    description: str | None
    start_at: datetime
    end_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.kind, UnavailabilityKind):
            raise StaffValidationError(
                "staff.audit_invalid", "El tipo del snapshot no es válido."
            )
        if self.description is not None and not isinstance(self.description, str):
            raise StaffValidationError(
                "staff.audit_invalid", "La descripción del snapshot debe ser texto."
            )
        object.__setattr__(self, "start_at", _require_aware(self.start_at, "inicio del snapshot"))
        object.__setattr__(self, "end_at", _require_aware(self.end_at, "fin del snapshot"))
        if self.end_at <= self.start_at:
            raise StaffValidationError(
                "staff.audit_invalid", "El fin del snapshot debe ser posterior al inicio."
            )

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> UnavailabilitySnapshot:
        """Construye el snapshot desde el `dict` JSON-compatible de `snapshot()`."""
        missing = _SNAPSHOT_KEYS.difference(values)
        if missing:
            raise StaffValidationError(
                "staff.audit_invalid",
                f"Faltan claves en el snapshot: {', '.join(sorted(missing))}.",
            )
        return cls(
            kind=_coerce_kind(values["kind"]),
            description=_coerce_optional_text(values["description"]),
            start_at=_coerce_datetime(values["start_at"]),
            end_at=_coerce_datetime(values["end_at"]),
        )

    def to_dict(self) -> dict[str, object]:
        """Devuelve un `dict` JSON-compatible con el mismo formato que `snapshot()`."""
        return {
            "kind": self.kind.value,
            "description": self.description,
            "start_at": self.start_at.isoformat(),
            "end_at": self.end_at.isoformat(),
        }


@dataclass(frozen=True)
class UnavailabilityAudit:
    """Operación auditada sobre una indisponibilidad, inmutable y de solo inserción.

    `CREATED` no admite motivo ni snapshots. `UPDATED` exige motivo no vacío y los
    dos snapshots. `CANCELLED` exige motivo no vacío y no guarda snapshots.
    `occurred_at` debe ser timezone-aware y se normaliza a UTC.
    """

    unavailability_id: UUID
    action: UnavailabilityAction
    actor_id: UUID
    occurred_at: datetime
    reason: str | None = None
    previous_values: UnavailabilitySnapshot | None = None
    new_values: UnavailabilitySnapshot | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.unavailability_id, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "La indisponibilidad auditada debe ser un UUID."
            )
        if not isinstance(self.actor_id, UUID):
            raise StaffValidationError(
                "staff.audit_invalid", "El actor de la auditoría debe ser un UUID."
            )
        if not isinstance(self.action, UnavailabilityAction):
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

        if self.action is UnavailabilityAction.CREATED:
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
        elif self.action is UnavailabilityAction.UPDATED:
            if reason is None:
                raise UnavailabilityReasonRequiredError()
            if self.previous_values is None or self.new_values is None:
                raise StaffValidationError(
                    "staff.audit_invalid",
                    "La edición debe guardar los valores anteriores y nuevos.",
                )
        elif self.action is UnavailabilityAction.CANCELLED:
            if reason is None:
                raise UnavailabilityReasonRequiredError()
            if self.previous_values is not None or self.new_values is not None:
                raise StaffValidationError(
                    "staff.audit_invalid",
                    "La anulación no guarda snapshots.",
                )

    def _validate_previous(self) -> None:
        if self.previous_values is not None and not isinstance(
            self.previous_values, UnavailabilitySnapshot
        ):
            raise StaffValidationError(
                "staff.audit_invalid", "Los valores anteriores deben ser un snapshot."
            )

    def _validate_new(self) -> None:
        if self.new_values is not None and not isinstance(
            self.new_values, UnavailabilitySnapshot
        ):
            raise StaffValidationError(
                "staff.audit_invalid", "Los valores nuevos deben ser un snapshot."
            )

    @classmethod
    def created(
        cls, *, unavailability_id: UUID, actor_id: UUID, occurred_at: datetime
    ) -> UnavailabilityAudit:
        """Auditoría del alta: sin motivo ni snapshots."""
        return cls(
            unavailability_id=unavailability_id,
            action=UnavailabilityAction.CREATED,
            actor_id=actor_id,
            occurred_at=occurred_at,
        )

    @classmethod
    def updated(
        cls,
        *,
        unavailability_id: UUID,
        actor_id: UUID,
        occurred_at: datetime,
        reason: str,
        previous_values: UnavailabilitySnapshot,
        new_values: UnavailabilitySnapshot,
    ) -> UnavailabilityAudit:
        """Auditoría de la edición: motivo y snapshots anterior/nuevo obligatorios."""
        return cls(
            unavailability_id=unavailability_id,
            action=UnavailabilityAction.UPDATED,
            actor_id=actor_id,
            occurred_at=occurred_at,
            reason=reason,
            previous_values=previous_values,
            new_values=new_values,
        )

    @classmethod
    def cancelled(
        cls, *, unavailability_id: UUID, actor_id: UUID, occurred_at: datetime, reason: str
    ) -> UnavailabilityAudit:
        """Auditoría de la anulación lógica: motivo obligatorio, sin snapshots."""
        return cls(
            unavailability_id=unavailability_id,
            action=UnavailabilityAction.CANCELLED,
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
    if not stripped:
        return None
    if len(stripped) > _REASON_MAX_LENGTH:
        raise StaffValidationError(
            "staff.audit_invalid",
            f"El motivo de la auditoría no puede superar {_REASON_MAX_LENGTH} caracteres.",
        )
    return stripped


def _require_aware(value: object, label: str) -> datetime:
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


def _coerce_kind(value: object) -> UnavailabilityKind:
    if isinstance(value, UnavailabilityKind):
        return value
    if isinstance(value, str):
        try:
            return UnavailabilityKind(value)
        except ValueError as exc:
            raise StaffValidationError(
                "staff.audit_invalid", "El tipo del snapshot no es válido."
            ) from exc
    raise StaffValidationError("staff.audit_invalid", "El tipo del snapshot debe ser texto.")


def _coerce_optional_text(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise StaffValidationError(
        "staff.audit_invalid", "La descripción del snapshot debe ser texto o nulo."
    )
