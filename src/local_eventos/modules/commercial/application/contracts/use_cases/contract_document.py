"""Caso de uso: obtener el contrato en PDF (HU43). Solo lee: nunca modifica el contrato.

Se descarga un contrato pendiente de firma o firmado; uno anulado no (R-PDF-2).
"""

from uuid import UUID

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.contracts.errors import (
    ContractNotFoundError,
    ContractPdfNotAvailableError,
    ContractQuoteNotFoundError,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.contracts.ports.document import (
    CONTRACT_TERMS,
    ContractDocument,
    ContractDocumentRenderer,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.modules.commercial.domain.contracts.contract import ContractStatus


class GetContractDocument:
    def __init__(
        self,
        contracts: ContractRepository,
        quotes: QuoteRepository,
        clients: ClientRepository,
        renderer: ContractDocumentRenderer,
        company: CompanyProfile,
        clock: Clock,
    ) -> None:
        self._contracts = contracts
        self._quotes = quotes
        self._clients = clients
        self._renderer = renderer
        self._company = company
        self._clock = clock

    async def __call__(self, contract_id: UUID) -> tuple[str, bytes]:
        """Devuelve el nombre del archivo (`CON-AAAA-NNNN.pdf`) y su contenido."""
        contract = await self._contracts.get(contract_id)
        if contract is None:
            raise ContractNotFoundError()
        if contract.status is ContractStatus.CANCELLED:
            raise ContractPdfNotAvailableError()
        quote = await self._quotes.get(contract.quote_id)
        if quote is None:  # el contrato nace de una cotización; solo por si acaso
            raise ContractQuoteNotFoundError()
        client = await self._clients.get(contract.client_id)
        if client is None:  # la base lo impide con una FK; solo por si acaso
            raise ContractNotFoundError()
        content = self._renderer.render(
            ContractDocument(
                contract=contract,
                quote=quote,
                client=client,
                company=self._company,
                terms=CONTRACT_TERMS,
                issued_on=self._clock.today(),
            )
        )
        return f"{contract.code}.pdf", content
