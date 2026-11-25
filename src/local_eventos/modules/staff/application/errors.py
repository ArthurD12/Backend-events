"""Errores de la capa de aplicación del personal (HU15, CA-15.3/CA-15.4/CA-15.7).

`code` es estable para que el frontend y la API lo traduzcan (plan §2.4).
Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from local_eventos.modules.staff.domain.document import Document


class StaffApplicationError(Exception):
    """Error de negocio de un caso de uso de personal. `code` es estable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DuplicateDocumentError(StaffApplicationError):
    """Ya existe otro trabajador —activo o inactivo— con el mismo tipo + número."""

    def __init__(self, document: Document) -> None:
        super().__init__(
            "staff.document_duplicated",
            f"Ya existe un trabajador con {document.type.value} {document.number}.",
        )


class WorkerNotFoundError(StaffApplicationError):
    """No hay ningún trabajador con el identificador solicitado."""

    def __init__(self) -> None:
        super().__init__(
            "staff.not_found",
            "No se encontró un trabajador con ese identificador.",
        )
