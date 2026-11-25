"""Trabajador de Darze (HU15): cocineros, mozos, bartenders… que se asignan a los eventos.

No es un usuario del sistema. No se elimina: se desactiva (RN02).
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.staff.domain.errors import StaffValidationError

CURRENCY = "PEN"
_NAME_MAX_LENGTH = 120
_DNI = re.compile(r"^\d{8}$")
_CE = re.compile(r"^[A-Z0-9]{9,12}$")
_PHONE = re.compile(r"^\d{9}$")


class DocumentType(StrEnum):
    DNI = "DNI"
    CE = "CE"  # carné de extranjería


class WorkerFunction(StrEnum):
    """R-STF-1 (provisional): lista fija de funciones."""

    COOK = "COOK"
    KITCHEN_ASSISTANT = "KITCHEN_ASSISTANT"
    WAITER = "WAITER"
    BARTENDER = "BARTENDER"
    COORDINATOR = "COORDINATOR"
    SETUP = "SETUP"
    OTHER = "OTHER"


class WorkerType(StrEnum):
    """R-STF-2 (provisional): no cambia ninguna regla; sirve para filtrar."""

    FIXED = "FIXED"
    EVENTUAL = "EVENTUAL"


@dataclass(frozen=True)
class WorkerDocument:
    """Documento de identidad: no se repite entre trabajadores (CA-15.2)."""

    type: DocumentType
    number: str

    @classmethod
    def of(cls, document_type: DocumentType, number: str) -> WorkerDocument:
        cleaned = "".join(number.split()).upper()
        if document_type is DocumentType.DNI and not _DNI.match(cleaned):
            raise StaffValidationError("El DNI debe tener 8 dígitos.")
        if document_type is DocumentType.CE and not _CE.match(cleaned):
            raise StaffValidationError(
                "El carné de extranjería debe tener de 9 a 12 letras o números."
            )
        return cls(document_type, cleaned)


@dataclass(frozen=True)
class WorkerData:
    """Datos que se registran y se modifican (CA-15.1, CA-15.3)."""

    name: str
    document_type: DocumentType
    document_number: str
    phone: str
    function: WorkerFunction
    worker_type: WorkerType
    reference_rate_cents: int


@dataclass
class Worker:
    id: UUID
    name: str
    document: WorkerDocument
    phone: str
    function: WorkerFunction
    worker_type: WorkerType
    reference_rate_cents: int  # R-STF-3: soles por evento, en céntimos
    active: bool
    created_by: UUID
    created_at: datetime
    updated_by: UUID
    updated_at: datetime

    @classmethod
    def register(cls, data: WorkerData, *, created_by: UUID, now: datetime) -> Worker:
        """Crea un trabajador activo. Que el documento no se repita lo revisa aplicación."""
        name, document, phone, rate = _validated(data)
        return cls(
            id=uuid4(),
            name=name,
            document=document,
            phone=phone,
            function=data.function,
            worker_type=data.worker_type,
            reference_rate_cents=rate,
            active=True,
            created_by=created_by,
            created_at=now,
            updated_by=created_by,
            updated_at=now,
        )

    def update(self, data: WorkerData, *, updated_by: UUID, now: datetime) -> None:
        """CA-15.3. Valida todo antes de asignar: si un dato falla, no cambia nada."""
        name, document, phone, rate = _validated(data)
        self.name = name
        self.document = document
        self.phone = phone
        self.function = data.function
        self.worker_type = data.worker_type
        self.reference_rate_cents = rate
        self._touch(updated_by, now)

    def set_active(self, active: bool, *, updated_by: UUID, now: datetime) -> None:
        """CA-15.4 y CA-15.5: no se elimina; sus asignaciones pasadas se conservan."""
        self.active = active
        self._touch(updated_by, now)

    def _touch(self, updated_by: UUID, now: datetime) -> None:
        self.updated_by = updated_by
        self.updated_at = now


def check_cents(cents: int, what: str) -> int:
    if isinstance(cents, bool) or not isinstance(cents, int) or cents < 0:
        raise StaffValidationError(f"{what} debe ser un monto en céntimos, cero o mayor.")
    return cents


def _validated(data: WorkerData) -> tuple[str, WorkerDocument, str, int]:
    name = " ".join(data.name.split())
    if not name:
        raise StaffValidationError("El nombre del trabajador es obligatorio.")
    if len(name) > _NAME_MAX_LENGTH:
        raise StaffValidationError(f"El nombre no puede superar {_NAME_MAX_LENGTH} caracteres.")
    document = WorkerDocument.of(data.document_type, data.document_number)
    phone = re.sub(r"[\s-]", "", data.phone)
    if not _PHONE.match(phone):
        raise StaffValidationError("El teléfono debe tener 9 dígitos.")
    rate = check_cents(data.reference_rate_cents, "La tarifa referencial")
    return name, document, phone, rate
