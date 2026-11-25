"""Pagos del contrato (HU19): registrar, anular y ver la cuenta.

`commercial` conoce el total del contrato; `ledger` guarda el dinero. Los pagos se registran y
anulan por `ledger.public_api` dentro de la misma transacción de la petición, así `ledger` no
depende de `commercial` (sin ciclo de imports).
"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from local_eventos.modules.commercial.application.contracts.errors import ContractNotFoundError
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractRepository,
)
from local_eventos.modules.commercial.application.quotes.ports.clock import Clock
from local_eventos.modules.commercial.domain.contracts.contract import Contract, ContractBalance
from local_eventos.modules.ledger.public_api import (
    PaymentEntriesLookup,
    PaymentEntry,
    PaymentKind,
    PaymentMethod,
    PaymentRecorder,
    PaymentRequest,
    PaymentVoider,
)

_PAID_KINDS = (PaymentKind.ADVANCE, PaymentKind.INSTALLMENT)


@dataclass(frozen=True)
class ContractAccount:
    """CA-19.4: total, pagado, saldo, fecha límite y la lista de pagos (adelanto incluido)."""

    contract: Contract
    balance: ContractBalance
    entries: list[PaymentEntry]
    overdue: bool


@dataclass(frozen=True)
class NewPayment:
    amount_cents: int
    paid_on: date
    method: PaymentMethod
    reference: str | None = None


def balance_of(contract: Contract, entries: list[PaymentEntry]) -> ContractBalance:
    """RN15 con los pagos vigentes: un pago anulado no cuenta (CA-19.3)."""
    active = [e.payment for e in entries if not e.is_voided]
    return ContractBalance.of(
        contract,
        paid_cents=sum(p.amount_cents for p in active if p.kind in _PAID_KINDS),
        refunded_cents=sum(p.amount_cents for p in active if p.kind is PaymentKind.REFUND),
    )


class GetContractAccount:
    def __init__(
        self, contracts: ContractRepository, entries: PaymentEntriesLookup, clock: Clock
    ) -> None:
        self._contracts = contracts
        self._entries = entries
        self._clock = clock

    async def __call__(self, contract_id: UUID) -> ContractAccount:
        contract = await self._contracts.get(contract_id)
        if contract is None:
            raise ContractNotFoundError()
        return await account_of(contract, self._entries, self._clock)


class RecordContractPayment:
    """Registra un pago parcial sin superar el saldo (CA-19.1, CA-19.2, RN14).

    Bloquea la fila del contrato antes de sumar los pagos: dos pagos simultáneos al mismo
    contrato se registran uno tras otro y el segundo ve el saldo que dejó el primero.
    """

    def __init__(
        self,
        contracts: ContractRepository,
        entries: PaymentEntriesLookup,
        payments: PaymentRecorder,
        clock: Clock,
    ) -> None:
        self._contracts = contracts
        self._entries = entries
        self._payments = payments
        self._clock = clock

    async def __call__(
        self, contract_id: UUID, payment: NewPayment, *, recorded_by: UUID
    ) -> tuple[ContractAccount, PaymentEntry]:
        contract = await self._contracts.get_for_update(contract_id)
        if contract is None:
            raise ContractNotFoundError()
        balance_of(contract, await self._entries(contract.id)).ensure_can_pay(payment.amount_cents)
        recorded = await self._payments(
            PaymentRequest(
                contract_id=contract.id,
                kind=PaymentKind.INSTALLMENT,
                amount_cents=payment.amount_cents,
                method=payment.method,
                reference=payment.reference,
                paid_on=payment.paid_on,
                recorded_by=recorded_by,
            ),
            now=self._clock.now(),
            today=self._clock.today(),
        )
        account = await account_of(contract, self._entries, self._clock)
        return account, PaymentEntry(payment=recorded)


class VoidContractPayment:
    """Anula un pago parcial con motivo (CA-19.5, RN17) y devuelve la cuenta actualizada."""

    def __init__(
        self,
        contracts: ContractRepository,
        entries: PaymentEntriesLookup,
        voider: PaymentVoider,
        clock: Clock,
    ) -> None:
        self._contracts = contracts
        self._entries = entries
        self._voider = voider
        self._clock = clock

    async def __call__(self, payment_id: UUID, *, reason: str, voided_by: UUID) -> ContractAccount:
        entry = await self._voider(
            payment_id, reason=reason, voided_by=voided_by, now=self._clock.now()
        )
        contract = await self._contracts.get(entry.payment.contract_id)
        if contract is None:  # todo pago de contrato tiene su contrato; solo por si acaso
            raise ContractNotFoundError()
        return await account_of(contract, self._entries, self._clock)


async def account_of(
    contract: Contract, entries: PaymentEntriesLookup, clock: Clock
) -> ContractAccount:
    found = await entries(contract.id)
    balance = balance_of(contract, found)
    return ContractAccount(
        contract=contract,
        balance=balance,
        entries=found,
        overdue=balance.is_overdue(clock.today()),
    )
