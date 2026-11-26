"""Requerimiento de materiales de un evento (HU25): cálculo puro, sin guardar nada (R-REC-2).

Por servicio contratado × su receta se obtiene lo requerido por producto; el faltante es lo
requerido menos lo que ya salió, lo reservado y lo disponible (CA-25.2).
"""

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from local_eventos.modules.inventory.domain.quantity import ZERO
from local_eventos.modules.inventory.domain.recipe import RecipeLine


@dataclass(frozen=True)
class ContractedService:
    service_id: UUID
    description: str
    quantity: int  # unidades contratadas


@dataclass(frozen=True)
class RequiredMaterials:
    by_product: dict[UUID, Decimal]
    without_recipe: list[str]  # CA-25.3


def required_materials(
    services: list[ContractedService], recipes: dict[UUID, list[RecipeLine]], guests: int
) -> RequiredMaterials:
    """CA-25.1: por persona × invitados; por servicio × cantidad contratada (R-REC-1)."""
    required: dict[UUID, Decimal] = {}
    without: list[str] = []
    for service in services:
        recipe = recipes.get(service.service_id)
        if not recipe:
            without.append(service.description)
            continue
        for line in recipe:
            amount = line.required_for(guests=guests, contracted=service.quantity)
            required[line.product_id] = required.get(line.product_id, ZERO) + amount
    return RequiredMaterials(required, without)


def shortage(required: Decimal, out: Decimal, reserved: Decimal, available: Decimal) -> Decimal:
    """CA-25.2: lo que falta comprar; nunca negativo."""
    return max(ZERO, required - out - reserved - available)
