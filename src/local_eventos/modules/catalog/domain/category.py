"""Categoría de servicios: el administrador puede crear nuevas (HU06).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from local_eventos.modules.catalog.domain.errors import CatalogValidationError

_NAME_MAX_LENGTH = 60


@dataclass
class Category:
    id: UUID
    name: str
    active: bool = True

    @classmethod
    def create(cls, *, name: str) -> Category:
        """Crea una categoría activa. Que el nombre no se repita se verifica en aplicación."""
        return cls(id=uuid4(), name=_clean_name(name))

    def rename(self, *, name: str) -> None:
        self.name = _clean_name(name)

    def deactivate(self) -> None:
        """Desactiva sin eliminar: sus servicios conservan la referencia (RN02)."""
        self.active = False

    def activate(self) -> None:
        self.active = True


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise CatalogValidationError(
            "catalog.category_name_required",
            "El nombre de la categoría es obligatorio.",
        )
    if len(cleaned) > _NAME_MAX_LENGTH:
        raise CatalogValidationError(
            "catalog.category_name_too_long",
            f"El nombre de la categoría no puede superar {_NAME_MAX_LENGTH} caracteres.",
        )
    return cleaned
