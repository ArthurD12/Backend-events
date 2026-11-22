"""Caso de uso: obtener la cotización en PDF (HU09).

Solo lee: nunca modifica la cotización (CA-09.5). Solo se entrega una cotización enviada o
aceptada, para no entregar por error un borrador, una rechazada o una vencida (R-PDF-1).
"""

from uuid import UUID

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.quotes.errors import (
    QuoteClientNotFoundError,
    QuoteNotFoundError,
    QuotePdfNotAvailableError,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.document import (
    CompanyProfile,
    QuoteDocument,
    QuoteDocumentRenderer,
)
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.modules.commercial.domain.quotes.quote import QuoteStatus

_DOWNLOADABLE = (QuoteStatus.SENT, QuoteStatus.ACCEPTED)


class GetQuoteDocument:
    def __init__(
        self,
        quotes: QuoteRepository,
        clients: ClientRepository,
        renderer: QuoteDocumentRenderer,
        company: CompanyProfile,
        clock: Clock,
    ) -> None:
        self._quotes = quotes
        self._clients = clients
        self._renderer = renderer
        self._company = company
        self._clock = clock

    async def __call__(self, quote_id: UUID) -> tuple[str, bytes]:
        """Devuelve el nombre del archivo (`COT-AAAA-NNNN.pdf`) y su contenido."""
        today = self._clock.today()
        quote = await self._quotes.get(quote_id)
        if quote is None:
            raise QuoteNotFoundError()
        if quote.effective_status(today) not in _DOWNLOADABLE:
            raise QuotePdfNotAvailableError()
        client = await self._clients.get(quote.client_id)
        if client is None:
            raise QuoteClientNotFoundError()
        content = self._renderer.render(
            QuoteDocument(quote=quote, client=client, company=self._company, issued_on=today)
        )
        return f"{quote.code}.pdf", content
