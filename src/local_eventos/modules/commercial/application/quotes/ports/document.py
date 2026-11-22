"""Puerto para generar el documento de una cotización (HU09).

La aplicación decide QUÉ va en el documento; la infraestructura decide CÓMO se dibuja (ReportLab,
ADR 0004). Así las reglas no dependen de la librería.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from local_eventos.modules.commercial.domain.clients.client import Client
from local_eventos.modules.commercial.domain.quotes.quote import Quote


@dataclass(frozen=True)
class CompanyProfile:
    """Datos de Darze para el encabezado. Los vacíos no se imprimen: nunca se inventan."""

    name: str
    ruc: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class QuoteDocument:
    quote: Quote
    client: Client
    company: CompanyProfile
    issued_on: date  # fecha de emisión en Lima


class QuoteDocumentRenderer(Protocol):
    def render(self, document: QuoteDocument) -> bytes:
        """Devuelve el PDF listo para descargar."""
        ...
