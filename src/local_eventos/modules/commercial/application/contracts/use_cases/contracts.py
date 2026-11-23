"""Casos de uso de contratos (HU41–HU42).

El adelanto y la devolución se registran en el módulo de pagos (`ledger.public_api`) dentro de la
misma transacción que el contrato: o se guardan los dos, o ninguno (CA-42.5).
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from local_eventos.modules.commercial.application.contracts.errors import (
    ContractAlreadyExistsError,
    ContractNotFoundError,
    ContractQuoteNotFoundError,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
    ContractRepository,
    ContractSummary,
)
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventRepository,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.application.quotes.ports.quote_repository import (
    QuoteRepository,
)
from local_eventos.modules.commercial.domain.contracts.contract import (
    Contract,
    ContractRuleError,
    check_signature,
    format_contract_code,
)
from local_eventos.modules.ledger.public_api import (
    PaymentKind,
    PaymentMethod,
    PaymentRecorder,
    PaymentRequest,
)

MAX_PAGE_SIZE = 100


@dataclass(frozen=True)
class AdvancePayment:
    paid_on: date
    method: PaymentMethod
    reference: str | None = None


@dataclass(frozen=True)
class ContractPage:
    items: list[ContractSummary]
    total: int
    page: int
    page_size: int


class GenerateContract:
    def __init__(
        self, contracts: ContractRepository, quotes: QuoteRepository, clock: Clock
    ) -> None:
        self._contracts = contracts
        self._quotes = quotes
        self._clock = clock

    async def __call__(
        self, quote_id: UUID, *, created_by: UUID, advance_cents: int | None = None
    ) -> Contract:
        today = self._clock.today()
        quote = await self._quotes.get(quote_id)
        if quote is None:
            raise ContractQuoteNotFoundError()
        if await self._contracts.get_by_quote(quote_id) is not None:
            raise ContractAlreadyExistsError()
        # Valida todo con un código provisional: si algo falla, no se gasta un correlativo.
        Contract.generate(
            code="", quote=quote, today=today, created_by=created_by,
            now=self._clock.now(), advance_cents=advance_cents,
        )  # fmt: skip
        number = await self._contracts.next_number(today.year)
        contract = Contract.generate(
            code=format_contract_code(today.year, number),
            quote=quote,
            today=today,
            created_by=created_by,
            now=self._clock.now(),
            advance_cents=advance_cents,
        )
        await self._contracts.add(contract)
        return contract


class SignContract:
    """Firma y adelanto en un solo paso (R-CON-1)."""

    def __init__(
        self, contracts: ContractRepository, payments: PaymentRecorder, clock: Clock
    ) -> None:
        self._contracts = contracts
        self._payments = payments
        self._clock = clock

    async def __call__(
        self,
        contract_id: UUID,
        *,
        signed_on: date,
        signer_name: str,
        advance: AdvancePayment,
        recorded_by: UUID,
    ) -> Contract:
        today, now = self._clock.today(), self._clock.now()
        contract = await _get_or_fail(self._contracts, contract_id)
        contract.ensure_pending()
        check_signature(signed_on, signer_name, today)  # antes de registrar el pago
        payment = await self._payments(
            PaymentRequest(
                contract_id=contract.id,
                kind=PaymentKind.ADVANCE,
                amount_cents=contract.advance_cents,
                method=advance.method,
                reference=advance.reference,
                paid_on=advance.paid_on,
                recorded_by=recorded_by,
            ),
            now=now,
            today=today,
        )
        contract.sign(
            signed_on=signed_on,
            signer_name=signer_name,
            advance_payment_id=payment.id,
            recorded_by=recorded_by,
            now=now,
            today=today,
        )
        await self._contracts.update(contract)
        return contract


class CancelContract:
    """Anulación con motivo; si hubo devolución, se registra su monto (R-CON-3).

    Un contrato que ya se convirtió en evento no se anula aquí (R-EVT-3): el evento se cancela
    desde su propia pantalla (HU11).
    """

    def __init__(
        self,
        contracts: ContractRepository,
        payments: PaymentRecorder,
        clock: Clock,
        events: EventRepository,
    ) -> None:
        self._contracts = contracts
        self._payments = payments
        self._clock = clock
        self._events = events

    async def __call__(
        self,
        contract_id: UUID,
        *,
        reason: str,
        cancelled_by: UUID,
        refund_cents: int | None = None,
        refund: AdvancePayment | None = None,
        note: str | None = None,
    ) -> Contract:
        today, now = self._clock.today(), self._clock.now()
        contract = await _get_or_fail(self._contracts, contract_id)
        contract.check_cancellation(reason, refund_cents)
        event = await self._events.get_by_contract(contract.id)
        if event is not None and event.cancellation is None:
            raise ContractRuleError(
                "contract.has_event",
                "Este contrato ya es un evento: para anularlo, cancela el evento.",
            )
        refund_payment_id = None
        if refund_cents is not None:
            how = refund or AdvancePayment(paid_on=today, method=PaymentMethod.CASH)
            payment = await self._payments(
                PaymentRequest(
                    contract_id=contract.id,
                    kind=PaymentKind.REFUND,
                    amount_cents=refund_cents,
                    method=how.method,
                    reference=how.reference,
                    paid_on=how.paid_on,
                    recorded_by=cancelled_by,
                ),
                now=now,
                today=today,
            )
            refund_payment_id = payment.id
        contract.cancel(
            reason=reason,
            refund_cents=refund_cents,
            refund_payment_id=refund_payment_id,
            note=note,
            cancelled_by=cancelled_by,
            now=now,
        )
        await self._contracts.update(contract)
        return contract


class GetContract:
    def __init__(self, contracts: ContractRepository) -> None:
        self._contracts = contracts

    async def __call__(self, contract_id: UUID) -> Contract:
        return await _get_or_fail(self._contracts, contract_id)


class SearchContracts:
    def __init__(self, contracts: ContractRepository) -> None:
        self._contracts = contracts

    async def __call__(
        self, filters: ContractFilters, *, page: int = 1, page_size: int = 20
    ) -> ContractPage:
        page = max(page, 1)
        page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
        items, total = await self._contracts.search(
            ContractFilters(text=" ".join(filters.text.split()), status=filters.status),
            limit=page_size,
            offset=(page - 1) * page_size,
        )
        return ContractPage(items=items, total=total, page=page, page_size=page_size)


async def _get_or_fail(contracts: ContractRepository, contract_id: UUID) -> Contract:
    contract = await contracts.get(contract_id)
    if contract is None:
        raise ContractNotFoundError()
    return contract
