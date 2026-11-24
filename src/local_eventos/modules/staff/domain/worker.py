"""Agregado `Worker` de Darze (HU15, R-STF-10..R-STF-15).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
La unicidad del documento no es invariante del agregado: se garantiza en la aplicación
y en PostgreSQL (plan §2.1).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from local_eventos.modules.staff.domain.document import Document, DocumentType
from local_eventos.modules.staff.domain.enums import (
    WorkerFunction,
    WorkerStatus,
    WorkerType,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.domain.money import Money

_NAME_MAX_LENGTH = 150
_PHONE_PATTERN = re.compile(r"^[0-9]+$")


@dataclass
class Worker:
    """Trabajador del plantel: datos de contacto, función, tarifa referencial y estado.

    Se construye con `Worker.register` (siempre `ACTIVE`) y se modifica con `update`.
    No existe borrado físico: la baja es un cambio de estado (R-STF-2).
    """

    id: UUID
    name: str
    document: Document
    phone: str | None
    function: WorkerFunction | None
    function_description: str | None
    worker_type: WorkerType | None
    rate: Money | None
    overtime_applies: bool
    overtime_rate: Money | None
    status: WorkerStatus

    @classmethod
    def register(
        cls,
        *,
        name: str,
        document_type: DocumentType,
        document_number: str,
        phone: str | None = None,
        function: WorkerFunction | None = None,
        function_description: str | None = None,
        worker_type: WorkerType | None = None,
        rate: Money | None = None,
        overtime_applies: bool = False,
        overtime_rate: Money | None = None,
        worker_id: UUID | None = None,
    ) -> Worker:
        """Registra un trabajador nuevo, siempre activo, validando todo antes de construir."""
        new_name = _clean_name(name)
        new_document = Document(document_type, document_number)
        new_phone = _clean_phone(phone)
        new_description = _clean_function_description(function, function_description)
        new_rate = _validate_rate(rate)
        new_overtime_rate = _validate_overtime(overtime_applies, overtime_rate)
        return cls(
            id=worker_id if worker_id is not None else uuid4(),
            name=new_name,
            document=new_document,
            phone=new_phone,
            function=function,
            function_description=new_description,
            worker_type=worker_type,
            rate=new_rate,
            overtime_applies=overtime_applies,
            overtime_rate=new_overtime_rate,
            status=WorkerStatus.ACTIVE,
        )

    def update(
        self,
        *,
        name: str,
        document_type: DocumentType,
        document_number: str,
        phone: str | None = None,
        function: WorkerFunction | None = None,
        function_description: str | None = None,
        worker_type: WorkerType | None = None,
        rate: Money | None = None,
        overtime_applies: bool = False,
        overtime_rate: Money | None = None,
    ) -> None:
        """Reemplaza los datos editables. Valida todo antes de mutar (como `Client`)."""
        new_name = _clean_name(name)
        new_document = Document(document_type, document_number)
        new_phone = _clean_phone(phone)
        new_description = _clean_function_description(function, function_description)
        new_rate = _validate_rate(rate)
        new_overtime_rate = _validate_overtime(overtime_applies, overtime_rate)

        self.name = new_name
        self.document = new_document
        self.phone = new_phone
        self.function = function
        self.function_description = new_description
        self.worker_type = worker_type
        self.rate = new_rate
        self.overtime_applies = overtime_applies
        self.overtime_rate = new_overtime_rate

    def activate(self) -> bool:
        """Reactiva al trabajador. Devuelve `True` solo si hubo cambio real."""
        if self.status is WorkerStatus.ACTIVE:
            return False
        self.status = WorkerStatus.ACTIVE
        return True

    def deactivate(self) -> bool:
        """Da de baja lógica al trabajador. Devuelve `True` solo si hubo cambio real."""
        if self.status is WorkerStatus.INACTIVE:
            return False
        self.status = WorkerStatus.INACTIVE
        return True


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise StaffValidationError(
            "staff.name_required", "El nombre del trabajador es obligatorio."
        )
    if len(cleaned) > _NAME_MAX_LENGTH:
        raise StaffValidationError(
            "staff.name_too_long",
            f"El nombre no puede superar {_NAME_MAX_LENGTH} caracteres.",
        )
    return cleaned


def _clean_phone(phone: str | None) -> str | None:
    if phone is None:
        return None
    cleaned = phone.strip()
    if not cleaned:
        return None
    if not _PHONE_PATTERN.match(cleaned):
        raise StaffValidationError(
            "staff.phone_invalid", "El teléfono solo admite dígitos."
        )
    return cleaned


def _clean_function_description(
    function: WorkerFunction | None, description: str | None
) -> str | None:
    cleaned = None if description is None else (" ".join(description.split()) or None)
    if function is WorkerFunction.OTHER:
        if cleaned is None:
            raise StaffValidationError(
                "staff.function_description_required",
                "La función «otro» exige una descripción.",
            )
        return cleaned
    if cleaned is not None:
        raise StaffValidationError(
            "staff.function_description_not_allowed",
            "Solo la función «otro» admite descripción.",
        )
    return None


def _validate_rate(rate: Money | None) -> Money | None:
    if rate is None:
        return None
    if not isinstance(rate, Money):
        raise StaffValidationError(
            "staff.rate_invalid", "La tarifa debe expresarse en céntimos enteros."
        )
    return rate


def _validate_overtime(
    overtime_applies: bool, overtime_rate: Money | None
) -> Money | None:
    if not isinstance(overtime_applies, bool):
        raise StaffValidationError(
            "staff.overtime_rate_invalid", "La marca de hora extra debe ser booleana."
        )
    if not overtime_applies:
        if overtime_rate is not None:
            raise StaffValidationError(
                "staff.overtime_rate_not_allowed",
                "Si no aplica hora extra, no corresponde un monto.",
            )
        return None
    if overtime_rate is None:
        raise StaffValidationError(
            "staff.overtime_rate_required",
            "Si aplica hora extra, el monto por hora extra es obligatorio.",
        )
    if not isinstance(overtime_rate, Money) or overtime_rate.cents <= 0:
        raise StaffValidationError(
            "staff.overtime_rate_invalid",
            "El monto por hora extra debe ser mayor que cero.",
        )
    return overtime_rate
