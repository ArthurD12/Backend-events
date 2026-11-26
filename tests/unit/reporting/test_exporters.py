"""Exportadores de reportes (CA-33.1, CA-34.1, CA-34.2): CSV para Excel y PDF horizontal."""

import csv
from datetime import date
from decimal import Decimal
from io import StringIO

from local_eventos.modules.commercial.public_api import CompanyProfile
from local_eventos.modules.reporting.application.reports.cash import GetCashReport
from local_eventos.modules.reporting.application.reports.table import (
    Column,
    ColumnType,
    Filter,
    ReportTable,
    Total,
)
from local_eventos.modules.reporting.infrastructure.csv_exporter import CsvExporter
from local_eventos.modules.reporting.infrastructure.pdf_exporter import PdfExporter

from .report_fakes import NOW, FixedClock, cash_entries, event_refs

COMPANY = CompanyProfile(name="Darze Catering", ruc="20123456789", phone="987654321")
TABLE = ReportTable(
    key="demo",
    title="Reporte de almacén",
    generated_at=NOW,
    filters=(Filter("from", "Desde", "01/11/2026"), Filter("category", "Categoría", "Mantelería")),
    columns=(
        Column("product", "Producto"),
        Column("date", "Fecha", ColumnType.DATE),
        Column("stock", "Stock", ColumnType.QUANTITY),
        Column("value", "Valor", ColumnType.MONEY),
        Column("low", "Stock bajo", ColumnType.BOOLEAN),
        Column("guests", "Invitados", ColumnType.INTEGER),
    ),
    rows=(
        ("Mantel de algodón; blanco", date(2026, 11, 5), Decimal("4.500"), 123_450, True, 120),
        ("Café", None, Decimal("10.000"), None, False, None),
    ),
    totals=(Total("value", "Valor del stock", ColumnType.MONEY, 123_450),),
)


def test_ca33_1_csv_utf8_con_bom_punto_y_coma_y_coma_decimal() -> None:
    content = CsvExporter().export(TABLE, COMPANY)

    assert content.startswith(b"\xef\xbb\xbf")
    rows = list(csv.reader(StringIO(content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0] == ["Producto", "Fecha", "Stock", "Valor", "Stock bajo", "Invitados"]
    assert rows[1] == ["Mantel de algodón; blanco", "05/11/2026", "4,5", "1234,50", "Sí", "120"]
    assert rows[2] == ["Café", "", "10", "", "No", ""]
    assert rows[3] == []
    assert rows[4] == ["Valor del stock", "1234,50"]
    assert "ó".encode() in content


def test_ca34_1_pdf_con_darze_titulo_filtros_fecha_y_totales() -> None:
    pdf = PdfExporter(compress=False).export(TABLE, COMPANY)

    assert pdf.startswith(b"%PDF")
    for text in (
        "Darze Catering",
        "RUC 20123456789",
        "REPORTE DE ALMAC",  # la tilde va codificada en el PDF
        "01/11/2026",
        "Generado: 25/11/2026 10:30",  # hora de Lima
        "S/ 1,234.50",
        "Valor del stock",
        "TOTALES",
    ):
        assert text.encode() in pdf, text


def test_pdf_vacio_lo_dice() -> None:
    empty = ReportTable("demo", "Vacío", NOW, (), TABLE.columns, (), ())

    assert b"Sin datos para estos filtros." in PdfExporter(compress=False).export(empty, COMPANY)


async def test_ca34_2_el_csv_tiene_las_mismas_filas_que_la_tabla() -> None:
    table = await GetCashReport(cash_entries, event_refs, FixedClock())(
        date(2026, 11, 1), date(2026, 11, 30)
    )

    content = CsvExporter().export(table, COMPANY).decode("utf-8-sig")
    rows = list(csv.reader(StringIO(content), delimiter=";"))

    assert len(rows) == 1 + len(table.rows) + 1 + len(table.totals)
    assert rows[1][:2] == ["05/11/2026", "Pago de cliente"]
    assert rows[-1] == ["Saldo del periodo", "4000,00"]
