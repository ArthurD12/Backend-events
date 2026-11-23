"""Servicio del catálogo de Darze (HU06).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
El precio es referencial: la cotización lo copia y lo congela (AGENTS.md, regla 6).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.catalog.domain.errors import CatalogValidationError

CURRENCY = "PEN"
_NAME_MAX_LENGTH = 120
_DESCRIPTION_MAX_LENGTH = 500


class PriceUnit(StrEnum):
    """Cómo se cobra el servicio: el buffet por persona, lo demás por unidad."""

    PER_PERSON = "PER_PERSON"
    PER_UNIT = "PER_UNIT"


@dataclass
class Service:
    id: UUID
    name: str
    category_id: UUID
    price_unit: PriceUnit
    reference_price_cents: int
    description: str | None = None
    active: bool = True

    @classmethod
    def register(
        cls,
        *,
        name: str,
        category_id: UUID,
        price_unit: PriceUnit,
        reference_price_cents: int,
        description: str | None = None,
    ) -> Service:
        """Crea un servicio activo. Que la categoría exista se verifica en aplicación."""
        return cls(
            id=uuid4(),
            name=_clean_name(name),
            category_id=category_id,
            price_unit=price_unit,
            reference_price_cents=_check_price(reference_price_cents),
            description=_clean_description(description),
        )

    def update(
        self,
        *,
        name: str,
        category_id: UUID,
        price_unit: PriceUnit,
        reference_price_cents: int,
        description: str | None = None,
    ) -> None:
        """Modifica el servicio. Valida todo antes de asignar: si un dato falla, no cambia nada.

        Las cotizaciones ya hechas no cambian porque guardan su propia copia del precio.
        """
        new_name = _clean_name(name)
        new_price = _check_price(reference_price_cents)
        new_description = _clean_description(description)
        self.name = new_name
        self.category_id = category_id
        self.price_unit = price_unit
        self.reference_price_cents = new_price
        self.description = new_description

    def deactivate(self) -> None:
        """Desactiva sin eliminar: deja de ofrecerse en cotizaciones nuevas (RN02)."""
        self.active = False

    def activate(self) -> None:
        self.active = True


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise CatalogValidationError(
            "catalog.service_name_required", "El nombre del servicio es obligatorio."
        )
    if len(cleaned) > _NAME_MAX_LENGTH:
        raise CatalogValidationError(
            "catalog.service_name_too_long",
            f"El nombre del servicio no puede superar {_NAME_MAX_LENGTH} caracteres.",
        )
    return cleaned


def _check_price(cents: int) -> int:
    if isinstance(cents, bool) or not isinstance(cents, int) or cents < 0:
        raise CatalogValidationError(
            "catalog.price_invalid",
            "El precio debe ser un monto en céntimos, cero o mayor.",
        )
    return cents


def _clean_description(description: str | None) -> str | None:
    if description is None:
        return None
    cleaned = " ".join(description.split())
    if len(cleaned) > _DESCRIPTION_MAX_LENGTH:
        raise CatalogValidationError(
            "catalog.description_too_long",
            f"La descripción no puede superar {_DESCRIPTION_MAX_LENGTH} caracteres.",
        )
    return cleaned or None
