"""Puerto para generar el documento de un contrato (HU43).

La aplicación decide QUÉ va en el documento; la infraestructura decide CÓMO se dibuja (ReportLab,
como la cotización, ADR 0004).
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.commercial.domain.clients.client import Client
from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.commercial.domain.quotes.quote import Quote

# R-PDF-4 (provisional): texto fijo que solo reproduce lo ya decidido; Darze debe confirmarlo.
CONTRACT_TERMS: tuple[str, ...] = (
    "Los precios están expresados en soles (PEN) y no incluyen IGV aparte.",
    "El adelanto pactado confirma la reserva de la fecha del evento. El saldo se paga "
    "hasta la fecha límite indicada en este contrato.",
    "Los servicios y montos de este contrato son los de la cotización aceptada y no se "
    "modifican. Para cambiar algo de un contrato firmado, este se anula y se hace una "
    "cotización nueva.",
    "Política de cancelación: la anulación del contrato se registra con su motivo. Darze no "
    "aplica penalidades ni devoluciones automáticas; si corresponde devolver parte de lo "
    "pagado, se acuerda entre las partes y se registra al anular.",
)


@dataclass(frozen=True)
class ContractDocument:
    """CA-43.1 a CA-43.4: lo registrado, sin recalcular con el catálogo."""

    contract: Contract
    quote: Quote  # sus líneas congeladas son los servicios del contrato
    client: Client
    company: CompanyProfile
    terms: tuple[str, ...]
    issued_on: date  # fecha de emisión en Lima


class ContractDocumentRenderer(Protocol):
    def render(self, document: ContractDocument) -> bytes:
        """Devuelve el PDF listo para descargar."""
        ...
