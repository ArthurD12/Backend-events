"""Forma de los datos del catálogo en la API (lo que envía y recibe el frontend).

Solo describen la forma: las reglas (nombre obligatorio, precio no negativo…) las aplica el
dominio, así hay una sola fuente de verdad y el mismo `code` de error en todos lados.
"""

from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.catalog.domain.category import Category
from local_eventos.modules.catalog.domain.service import CURRENCY, PriceUnit, Service


class CategoryIn(BaseModel):
    name: str


class CategoryOut(BaseModel):
    id: UUID
    name: str
    active: bool

    @classmethod
    def from_category(cls, category: Category) -> Self:
        return cls(id=category.id, name=category.name, active=category.active)


class ServiceIn(BaseModel):
    name: str
    category_id: UUID
    price_unit: PriceUnit = Field(description="PER_PERSON (buffet) o PER_UNIT (lo demás)")
    reference_price_cents: int = Field(
        description="Precio referencial en céntimos: S/ 45.00 = 4500"
    )
    description: str | None = None


class ServiceOut(BaseModel):
    id: UUID
    name: str
    category_id: UUID
    price_unit: PriceUnit
    reference_price_cents: int
    currency: str
    description: str | None
    active: bool

    @classmethod
    def from_service(cls, service: Service) -> Self:
        return cls(
            id=service.id,
            name=service.name,
            category_id=service.category_id,
            price_unit=service.price_unit,
            reference_price_cents=service.reference_price_cents,
            currency=CURRENCY,
            description=service.description,
            active=service.active,
        )
