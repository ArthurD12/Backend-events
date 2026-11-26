"""Reporte en CSV para Excel (CA-33.1, R-REP-1): UTF-8 con BOM (tildes correctas) y `;`.

Encabezados, una fila por fila de la tabla y, tras una línea vacía, los totales.
"""

import csv
from io import StringIO

from local_eventos.modules.commercial.public_api import CompanyProfile
from local_eventos.modules.reporting.application.reports.table import ReportTable
from local_eventos.modules.reporting.infrastructure.formatting import csv_cell


class CsvExporter:
    media_type = "text/csv; charset=utf-8"
    extension = "csv"

    def export(self, table: ReportTable, company: CompanyProfile) -> bytes:
        buffer = StringIO()
        writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
        writer.writerow([c.label for c in table.columns])
        for row in table.rows:
            writer.writerow([csv_cell(v, c.type) for v, c in zip(row, table.columns, strict=True)])
        if table.totals:
            writer.writerow([])
            for total in table.totals:
                writer.writerow([total.label, csv_cell(total.value, total.type)])
        return buffer.getvalue().encode("utf-8-sig")
