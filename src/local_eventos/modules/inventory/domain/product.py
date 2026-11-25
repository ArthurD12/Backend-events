"""Producto del almacén (HU23): insumo, vajilla, mantelería… con su stock mínimo.

Python puro: no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from local_eventos.modules.inventory.domain.errors import InventoryValidationError
from local_eventos.modules.inventory.domain.quantity import to_quantity

_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")
CODE_MAX_LENGTH = 20
NAME_MAX_LENGTH = 150


class Unit(StrEnum):
    """R-INV-1: unidades de lista fija."""

    UNIT = "UNIT"
    KG = "KG"
    G = "G"
    LITER = "LITER"
    ML = "ML"
    DOZEN = "DOZEN"
    PACKAGE = "PACKAGE"
    BOX = "BOX"


class Category(StrEnum):
    """R-INV-2: categorías de lista fija."""

    SUPPLIES = "SUPPLIES"  # Insumos
    BEVERAGES = "BEVERAGES"  # Bebidas
    DINNERWARE = "DINNERWARE"  # Vajilla
    GLASSWARE = "GLASSWARE"  # Cristalería
    CUTLERY = "CUTLERY"  # Cubiertos
    LINENS = "LINENS"  # Mantelería
    FURNITURE = "FURNITURE"  # Mobiliario
    DISPOSABLES = "DISPOSABLES"  # Descartables
    CLEANING = "CLEANING"  # Limpieza
    OTHER = "OTHER"  # Otros


class ProductKind(StrEnum):
    CONSUMABLE = "CONSUMABLE"  # se gasta en el evento
    REUSABLE = "REUSABLE"  # vuelve al almacén (vajilla, mantelería…)


@dataclass
class Product:
    id: UUID
    code: str
    name: str
    category: Category
    unit: Unit
    kind: ProductKind
    min_stock: Decimal
    active: bool = True

    @classmethod
    def create(
        cls,
        *,
        code: str,
        name: str,
        category: Category,
        unit: Unit,
        kind: ProductKind,
        min_stock: Decimal,
    ) -> Product:
        return cls(
            id=uuid4(),
            code=clean_code(code),
            name=_clean_name(name),
            category=category,
            unit=unit,
            kind=kind,
            min_stock=_clean_min_stock(min_stock),
        )

    def update(
        self,
        *,
        code: str,
        name: str,
        category: Category,
        unit: Unit,
        kind: ProductKind,
        min_stock: Decimal,
    ) -> None:
        """Valida todo antes de asignar: si un dato es inválido, el producto no cambia."""
        new_code, new_name = clean_code(code), _clean_name(name)
        new_min = _clean_min_stock(min_stock)
        self.code, self.name, self.min_stock = new_code, new_name, new_min
        self.category, self.unit, self.kind = category, unit, kind

    def deactivate(self) -> None:
        """CA-23.3: no se elimina nunca; se desactiva (RN02)."""
        self.active = False

    def activate(self) -> None:
        self.active = True


def clean_code(code: str) -> str:
    """Código en mayúsculas y sin espacios: `vas-01` → `VAS-01`."""
    cleaned = code.strip().upper()
    if not cleaned:
        raise InventoryValidationError("El código es obligatorio.")
    if len(cleaned) > CODE_MAX_LENGTH:
        raise InventoryValidationError(f"El código no puede superar {CODE_MAX_LENGTH} caracteres.")
    if not _CODE_PATTERN.match(cleaned):
        raise InventoryValidationError(
            "El código solo admite letras sin tilde, números, punto, guion y guion bajo."
        )
    return cleaned


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise InventoryValidationError("El nombre es obligatorio.")
    if len(cleaned) > NAME_MAX_LENGTH:
        raise InventoryValidationError(f"El nombre no puede superar {NAME_MAX_LENGTH} caracteres.")
    return cleaned


def _clean_min_stock(value: Decimal) -> Decimal:
    quantity = to_quantity(value)
    if quantity < 0:
        raise InventoryValidationError("El stock mínimo no puede ser negativo.")
    return quantity
