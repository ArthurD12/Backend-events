"""Proveedor de Darze (HU27). Python puro: no importa FastAPI, SQLAlchemy ni Pydantic."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.purchasing.domain.errors import PurchasingValidationError

_DOCUMENT_LENGTH = {"DNI": 8, "RUC": 11}
_PHONE_PATTERN = re.compile(r"^\+?\d{7,15}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NAME_MAX_LENGTH = 150
TEXT_MAX_LENGTH = 300


class DocumentType(StrEnum):
    RUC = "RUC"
    DNI = "DNI"


@dataclass
class Supplier:
    id: UUID
    name: str  # razón social
    document_type: DocumentType
    document_number: str
    phone: str
    contact_name: str | None = None
    email: str | None = None
    address: str | None = None
    active: bool = True

    @classmethod
    def register(
        cls,
        *,
        name: str,
        document_type: DocumentType,
        document_number: str,
        phone: str,
        contact_name: str | None = None,
        email: str | None = None,
        address: str | None = None,
    ) -> Supplier:
        supplier = cls(
            id=uuid4(), name="", document_type=document_type, document_number="", phone=""
        )
        supplier.update(
            name=name, document_type=document_type, document_number=document_number,
            phone=phone, contact_name=contact_name, email=email, address=address,
        )  # fmt: skip
        return supplier

    def update(
        self,
        *,
        name: str,
        document_type: DocumentType,
        document_number: str,
        phone: str,
        contact_name: str | None = None,
        email: str | None = None,
        address: str | None = None,
    ) -> None:
        """Valida todo antes de asignar: si un dato es inválido, el proveedor no cambia."""
        values = (
            _clean_name(name),
            _clean_document(document_type, document_number),
            _clean_phone(phone),
            _clean_optional(contact_name, "El contacto"),
            _clean_email(email),
            _clean_optional(address, "La dirección"),
        )
        self.name, self.document_number, self.phone = values[0], values[1], values[2]
        self.contact_name, self.email, self.address = values[3], values[4], values[5]
        self.document_type = document_type

    def deactivate(self) -> None:
        """CA-27.3: no se elimina; se desactiva (RN02)."""
        self.active = False

    def activate(self) -> None:
        self.active = True


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise PurchasingValidationError("La razón social es obligatoria.")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise PurchasingValidationError(
            f"La razón social no puede superar {NAME_MAX_LENGTH} caracteres."
        )
    return cleaned


def _clean_document(document_type: DocumentType, number: str) -> str:
    cleaned = number.strip()
    expected = _DOCUMENT_LENGTH[document_type]
    if not (cleaned.isdigit() and len(cleaned) == expected):
        raise PurchasingValidationError(f"El {document_type} debe tener {expected} dígitos.")
    return cleaned


def _clean_phone(phone: str) -> str:
    cleaned = re.sub(r"[\s-]", "", phone)
    if not _PHONE_PATTERN.match(cleaned):
        raise PurchasingValidationError("El teléfono debe tener entre 7 y 15 dígitos.")
    return cleaned


def _clean_email(email: str | None) -> str | None:
    cleaned = _clean_optional(email, "El correo")
    if cleaned is not None and not _EMAIL_PATTERN.match(cleaned):
        raise PurchasingValidationError("El correo no es válido.")
    return cleaned.lower() if cleaned else None


def _clean_optional(value: str | None, label: str) -> str | None:
    cleaned = " ".join((value or "").split()) or None
    if cleaned and len(cleaned) > TEXT_MAX_LENGTH:
        raise PurchasingValidationError(f"{label} no puede superar {TEXT_MAX_LENGTH} caracteres.")
    return cleaned
