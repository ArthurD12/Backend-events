"""La tabla de un reporte: título, filtros, columnas con su tipo, filas y totales.

Es lo único que conocen los exportadores (JSON, CSV y PDF). Los montos van en céntimos; las
fechas como `date` y el instante de generación en UTC: cada salida los formatea (R-REP-3).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from local_eventos.modules.reporting.application.errors import ReportRangeInvalidError

MAX_DAYS = 366  # R-REP-2

Cell = str | int | bool | date | Decimal | None
"""Valor de una celda. `None`: vacío (sin dato o monto oculto); nunca se inventa."""


class ColumnType(StrEnum):
    TEXT = "text"
    DATE = "date"
    MONEY = "money"  # céntimos de sol
    QUANTITY = "quantity"  # Decimal con hasta 3 decimales
    INTEGER = "integer"
    BOOLEAN = "boolean"


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    type: ColumnType = ColumnType.TEXT


@dataclass(frozen=True)
class Filter:
    """Filtro aplicado, ya escrito para mostrarse (p. ej., "Desde" → "01/11/2026")."""

    key: str
    label: str
    value: str


@dataclass(frozen=True)
class Total:
    key: str
    label: str
    type: ColumnType
    value: Cell


@dataclass(frozen=True)
class ReportTable:
    key: str  # events, cash, inventory…
    title: str
    generated_at: datetime  # UTC
    filters: tuple[Filter, ...]
    columns: tuple[Column, ...]
    rows: tuple[tuple[Cell, ...], ...]
    totals: tuple[Total, ...]
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("Cada fila debe tener una celda por columna.")


def check_range(date_from: date, date_to: date) -> None:
    """R-REP-2: de una fecha a otra igual o posterior, hasta 366 días."""
    if date_to < date_from or (date_to - date_from).days + 1 > MAX_DAYS:
        raise ReportRangeInvalidError(MAX_DAYS)


def day(value: date) -> str:
    """Fecha para leer: 05/11/2026."""
    return f"{value:%d/%m/%Y}"


def range_filters(date_from: date, date_to: date) -> tuple[Filter, Filter]:
    return Filter("from", "Desde", day(date_from)), Filter("to", "Hasta", day(date_to))
