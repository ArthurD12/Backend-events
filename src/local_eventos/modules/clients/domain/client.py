"""Entidad Cliente de Darze (HU04).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

_DOCUMENT_LENGTH = {"DNI": 8, "RUC": 11}
_PHONE_PATTERN = re.compile(r"^\+?\d{7,15}$")
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_NAME_MAX_LENGTH = 150


class DocumentType(StrEnum):
    DNI = "DNI"
    RUC = "RUC"


class ClientValidationError(ValueError):
    """Dato de cliente inválido. `code` es estable para que el frontend lo traduzca."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Document:
    """Documento de identidad: identifica al cliente y no se repite (HU04)."""

    type: DocumentType
    number: str

    def __post_init__(self) -> None:
        expected = _DOCUMENT_LENGTH[self.type]
        if not (self.number.isdigit() and len(self.number) == expected):
            raise ClientValidationError(
                "client.document_invalid",
                f"El {self.type} debe tener {expected} dígitos.",
            )


@dataclass
class Client:
    id: UUID
    name: str
    document: Document
    phone: str
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
        email: str | None = None,
        address: str | None = None,
    ) -> Client:
        """Crea un cliente nuevo, activo, con sus datos validados."""
        return cls(
            id=uuid4(),
            name=_clean_name(name),
            document=Document(document_type, document_number.strip()),
            phone=_clean_phone(phone),
            email=_clean_email(email),
            address=_clean_optional(address),
        )

    def update_contact(
        self,
        *,
        name: str,
        phone: str,
        email: str | None = None,
        address: str | None = None,
    ) -> None:
        """Actualiza los datos de contacto. El documento se corrige con `correct_document`."""
        self.name = _clean_name(name)
        self.phone = _clean_phone(phone)
        self.email = _clean_email(email)
        self.address = _clean_optional(address)

    def correct_document(
        self,
        *,
        document_type: DocumentType,
        document_number: str,
        reason: str,
    ) -> Document:
        """Corrige un documento mal registrado y devuelve el anterior para la auditoría (RN03).

        Que el nuevo documento no pertenezca a otro cliente se verifica en la capa de aplicación.
        """
        if not reason.strip():
            raise ClientValidationError(
                "client.correction_reason_required",
                "Indica el motivo de la corrección.",
            )
        previous = self.document
        self.document = Document(document_type, document_number.strip())
        return previous

    def deactivate(self) -> None:
        """Desactiva sin eliminar: sus cotizaciones y eventos se conservan (RN02)."""
        self.active = False

    def activate(self) -> None:
        self.active = True


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ClientValidationError("client.name_required", "El nombre es obligatorio.")
    if len(cleaned) > _NAME_MAX_LENGTH:
        raise ClientValidationError(
            "client.name_too_long",
            f"El nombre no puede superar {_NAME_MAX_LENGTH} caracteres.",
        )
    return cleaned


def _clean_phone(phone: str) -> str:
    cleaned = re.sub(r"[\s-]", "", phone)
    if not _PHONE_PATTERN.match(cleaned):
        raise ClientValidationError(
            "client.phone_invalid",
            "El teléfono debe tener entre 7 y 15 dígitos.",
        )
    return cleaned


def _clean_email(email: str | None) -> str | None:
    cleaned = _clean_optional(email)
    if cleaned is None:
        return None
    if not _EMAIL_PATTERN.match(cleaned):
        raise ClientValidationError("client.email_invalid", "El correo no es válido.")
    return cleaned.lower()


def _clean_optional(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None
