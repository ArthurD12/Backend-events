"""Puerto de los exportadores de reportes (CSV y PDF). La aplicación arma la tabla; la
infraestructura decide cómo se escribe (CA-33.1, CA-34.1)."""

from typing import Protocol

from local_eventos.modules.commercial.public_api import CompanyProfile
from local_eventos.modules.reporting.application.reports.table import ReportTable


class ReportExporter(Protocol):
    media_type: str
    extension: str

    def export(self, table: ReportTable, company: CompanyProfile) -> bytes: ...
