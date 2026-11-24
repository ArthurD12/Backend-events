"""Documento de identidad del trabajador (HU15, R-STF-1).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from local_eventos.modules.staff.domain.errors import StaffValidationError

_DOCUMENT_PATTERN = {
    "DNI": re.compile(r"^[0-9]{8}$"),
    "CE": re.compile(r"^[0-9]{9,12}$"),
}
_DOCUMENT_DIGITS = {"DNI": "8", "CE": "9 a 12"}


class DocumentType(StrEnum):
    DNI = "DNI"
    CE = "CE"


@dataclass(frozen=True)
class Document:
    """Documento normalizado del trabajador: tipo + número, sin espacios ni guiones."""

    type: DocumentType
    number: str

    def __post_init__(self) -> None:
        if not isinstance(self.type, DocumentType):
            raise StaffValidationError(
                "staff.document_invalid", "El tipo de documento debe ser DNI o CE."
            )
        if not isinstance(self.number, str):
            raise StaffValidationError(
                "staff.document_invalid", "El número de documento es obligatorio."
            )
        cleaned = re.sub(r"[\s-]", "", self.number)
        pattern = _DOCUMENT_PATTERN[self.type]
        if not pattern.match(cleaned):
            raise StaffValidationError(
                "staff.document_invalid",
                f"El {self.type} debe tener {_DOCUMENT_DIGITS[self.type]} dígitos.",
            )
        object.__setattr__(self, "number", cleaned)
