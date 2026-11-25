"""Errores del dominio de personal (HU15).

`code` es estable para que el frontend lo traduzca. Python puro: no importa FastAPI,
SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations


class StaffValidationError(ValueError):
    """Dato de trabajador inválido (responde 422). `code` es estable."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
