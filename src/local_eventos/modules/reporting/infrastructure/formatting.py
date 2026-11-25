"""Cómo se escribe cada tipo de celda en las descargas (R-REP-3): fechas y horas de Lima,
soles con 2 decimales, cantidades sin ceros de sobra, Sí/No."""

from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from local_eventos.modules.reporting.application.reports.table import Cell, ColumnType

# Perú no usa horario de verano: Lima es siempre UTC−5 (sin base de zonas horarias, por Windows).
LIMA = timezone(timedelta(hours=-5), "America/Lima")


def lima(moment: datetime) -> str:
    return f"{moment.astimezone(LIMA):%d/%m/%Y %H:%M}"


def _quantity(value: Decimal, decimal_sep: str) -> str:
    text = format(value.normalize(), "f")
    return text.replace(".", decimal_sep)


def csv_cell(value: Cell, kind: ColumnType) -> str:
    """Excel en español: coma decimal y sin separador de miles (1234,50)."""
    return _cell(value, kind, money=lambda c: f"{c / 100:.2f}".replace(".", ","), sep=",")


def pdf_cell(value: Cell, kind: ColumnType) -> str:
    """Como en la cotización: S/ 1,234.50."""
    return _cell(value, kind, money=lambda c: f"S/ {c / 100:,.2f}", sep=".")


def _cell(value: Cell, kind: ColumnType, *, money: Callable[[int], str], sep: str) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Sí" if value else "No"
    if isinstance(value, date):
        return f"{value:%d/%m/%Y}"
    if isinstance(value, Decimal):
        return _quantity(value, sep)
    if kind is ColumnType.MONEY and isinstance(value, int):
        return money(value)
    return str(value)
