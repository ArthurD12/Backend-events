"""Forma JSON de un reporte (HU32–HU34). Es la misma `ReportTable` que se descarga en CSV y
PDF (CA-34.2): el frontend dibuja la tabla con `columns` y `rows` sin conocer cada reporte."""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field

from local_eventos.modules.reporting.application.reports.table import Cell, ReportTable

JsonCell = str | int | bool | None


class ReportFormat(StrEnum):
    JSON = "json"
    CSV = "csv"
    PDF = "pdf"


class ReportFilterOut(BaseModel):
    key: str
    label: str
    value: str = Field(description="Valor del filtro tal como se muestra")


class ReportColumnOut(BaseModel):
    key: str
    label: str
    type: str = Field(
        description="text, date (AAAA-MM-DD), money (céntimos), quantity (texto decimal), "
        "integer o boolean"
    )


class ReportTotalOut(BaseModel):
    key: str
    label: str
    type: str
    value: JsonCell = Field(description="`null`: sin dato o monto oculto")


class ReportOut(BaseModel):
    report: str = Field(description="events, cash, inventory, inventory_movements, purchases…")
    title: str
    generated_at: datetime
    currency: str = "PEN"
    filters: list[ReportFilterOut]
    columns: list[ReportColumnOut]
    rows: list[dict[str, JsonCell]] = Field(description="Una entrada por fila, por `key`")
    totals: list[ReportTotalOut]
    notes: list[str]

    @classmethod
    def from_table(cls, table: ReportTable) -> Self:
        keys = [c.key for c in table.columns]
        return cls(
            report=table.key,
            title=table.title,
            generated_at=table.generated_at,
            filters=[ReportFilterOut(key=f.key, label=f.label, value=f.value)
                     for f in table.filters],
            columns=[ReportColumnOut(key=c.key, label=c.label, type=c.type.value)
                     for c in table.columns],
            rows=[{k: _json(v) for k, v in zip(keys, row, strict=True)} for row in table.rows],
            totals=[ReportTotalOut(key=t.key, label=t.label, type=t.type.value,
                                   value=_json(t.value)) for t in table.totals],
            notes=list(table.notes),
        )  # fmt: skip


def _json(value: Cell) -> JsonCell:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    return value
