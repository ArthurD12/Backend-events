"""Caso de uso: el comprobante en PDF de un pago (HU20). Solo lee: no cambia nada."""

from uuid import UUID

from local_eventos.modules.commercial.application.clients.ports.client_repository import (
    ClientRepository,
)
from local_eventos.modules.commercial.application.contracts.errors import ContractNotFoundError
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.contracts.ports.receipt import (
    PaymentReceipt,
    PaymentReceiptRenderer,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.identity.public_api import UserNamesLookup
from local_eventos.modules.ledger.public_api import (
    PaymentEntriesLookup,
    PaymentEntry,
    PaymentFinder,
    PaymentKind,
    PaymentNotFoundError,
)


class RenderPaymentReceipt:
    def __init__(
        self,
        *,
        finder: PaymentFinder,
        entries: PaymentEntriesLookup,
        contracts: ContractRepository,
        clients: ClientRepository,
        events: EventRepository,
        names: UserNamesLookup,
        renderer: PaymentReceiptRenderer,
        company: CompanyProfile,
        clock: Clock,
    ) -> None:
        self._finder = finder
        self._entries = entries
        self._contracts = contracts
        self._clients = clients
        self._events = events
        self._names = names
        self._renderer = renderer
        self._company = company
        self._clock = clock

    async def __call__(self, payment_id: UUID) -> tuple[str, bytes]:
        """Devuelve el nombre del archivo (`PAG-AAAA-NNNN.pdf`) y su contenido."""
        entry = await self._finder(payment_id)
        if entry is None:
            raise PaymentNotFoundError()
        payment = entry.payment
        contract = await self._contracts.get(payment.contract_id)
        if contract is None:  # todo pago de contrato tiene su contrato; solo por si acaso
            raise ContractNotFoundError()
        client = await self._clients.get(contract.client_id)
        if client is None:  # la base lo impide con una FK; solo por si acaso
            raise ContractNotFoundError()
        event = await self._events.get_by_contract(contract.id)
        paid, refunded = _totals_after(await self._entries(contract.id), payment.id)
        names = await self._names([payment.recorded_by])
        content = self._renderer.render(
            PaymentReceipt(
                company=self._company,
                entry=entry,
                contract=contract,
                client=client,
                event_code=event.code if event else None,
                paid_after_cents=paid,
                balance_after_cents=contract.total_cents - paid + refunded,
                recorded_by_name=names.get(payment.recorded_by, ""),
                issued_on=self._clock.today(),
            )
        )
        return f"{payment.number}.pdf", content


def _totals_after(entries: list[PaymentEntry], payment_id: UUID) -> tuple[int, int]:
    """Pagado y devuelto hasta ese pago inclusive (CA-20.2), sin los otros pagos anulados.

    El pago del comprobante cuenta aunque esté anulado: muestra la cuenta como quedó al
    registrarlo; la marca ANULADO avisa que ya no vale (CA-20.3).
    """
    paid = refunded = 0
    for entry in entries:
        payment = entry.payment
        if payment.id == payment_id or not entry.is_voided:
            if payment.kind is PaymentKind.REFUND:
                refunded += payment.amount_cents
            else:
                paid += payment.amount_cents
        if payment.id == payment_id:
            break
    return paid, refunded
