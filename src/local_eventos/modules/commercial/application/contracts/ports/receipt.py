"""Puerto para el comprobante interno de un pago (HU20).

La aplicación decide QUÉ va en el comprobante; la infraestructura decide CÓMO se dibuja
(ReportLab, como la cotización). No es boleta ni factura: Darze no las emite.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.commercial.domain.clients.client import Client
from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.ledger.public_api import PaymentEntry


@dataclass(frozen=True)
class PaymentReceipt:
    """CA-20.2: datos de Darze, cliente, contrato y evento, el pago y la cuenta después de él."""

    company: CompanyProfile
    entry: PaymentEntry
    contract: Contract
    client: Client
    event_code: str | None
    paid_after_cents: int
    balance_after_cents: int
    recorded_by_name: str
    issued_on: date  # fecha de emisión en Lima


class PaymentReceiptRenderer(Protocol):
    def render(self, receipt: PaymentReceipt) -> bytes:
        """Devuelve el PDF listo para descargar."""
        ...
