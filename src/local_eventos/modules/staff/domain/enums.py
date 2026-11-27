"""Enumeraciones del personal de Darze (HU15, HU17, R-STF-11/R-STF-12/R-ASG-8).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from enum import StrEnum


class WorkerFunction(StrEnum):
    """Función del trabajador: lista fija del sistema más `OTHER` con descripción."""

    COOK = "COOK"
    WAITER = "WAITER"
    BARTENDER = "BARTENDER"
    ASSISTANT = "ASSISTANT"
    COORDINATOR = "COORDINATOR"
    OTHER = "OTHER"


class WorkerType(StrEnum):
    """Tipo de trabajador: `FIXED` o `EVENTUAL`; opcional, sin interno/externo (R-STF-11)."""

    FIXED = "FIXED"
    EVENTUAL = "EVENTUAL"


class WorkerStatus(StrEnum):
    """Estado del trabajador: la baja es lógica, nunca borrado físico (R-STF-2)."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class AssignmentStatus(StrEnum):
    """Estado de la asignación: se anula lógicamente, no se borra ni se reactiva (R-ASG-8)."""

    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class UnavailabilityKind(StrEnum):
    """Motivo de la indisponibilidad: `OTHER` exige descripción (HU16, R-DIS-1)."""

    VACATION = "VACATION"
    LEAVE = "LEAVE"
    REST = "REST"
    OTHER = "OTHER"


class UnavailabilityStatus(StrEnum):
    """Estado de la indisponibilidad: se anula lógicamente, nunca se borra ni reactiva (HU16)."""

    ACTIVE = "ACTIVE"
    CANCELLED = "CANCELLED"


class AvailabilityState(StrEnum):
    """Disponibilidad de un trabajador en una ventana, por precedencia UNAVAILABLE > BUSY > FREE.

    HU16: `UNAVAILABLE` (indisponibilidad registrada) prevalece sobre `BUSY` (asignación).
    """

    FREE = "FREE"
    BUSY = "BUSY"
    UNAVAILABLE = "UNAVAILABLE"
