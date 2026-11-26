"""Puerto: dónde se guardan los pagos y sus anulaciones. Solo se agregan y se leen."""

from dataclasses import dataclass
from datetime import date
from typing import Protocol
from uuid import UUID

from local_eventos.modules.ledger.domain.payment import Payment, PaymentKind, PaymentVoid


@dataclass(frozen=True)
class PaymentEntry:
    """Un pago con su anulación, si la tiene. Anulado no cuenta en ningún saldo (CA-19.3)."""

    payment: Payment
    void: PaymentVoid | None = None

    @property
    def is_voided(self) -> bool:
        return self.void is not None


@dataclass(frozen=True)
class MonthlyPaymentTotal:
    """Suma de pagos vigentes de un tipo en un mes, por fecha de pago (CA-22.1)."""

    year: int
    month: int
    kind: PaymentKind
    amount_cents: int


@dataclass(frozen=True)
class ContractPaidTotals:
    """Pagos vigentes de un contrato: pagado (adelanto y parciales) y devuelto (RN15)."""

    paid_cents: int = 0
    refunded_cents: int = 0


class PaymentRepository(Protocol):
    async def add(self, payment: Payment) -> None: ...

    async def next_number(self, year: int) -> int:
        """Siguiente correlativo del año para el número PAG-AAAA-NNNN."""
        ...

    async def get(self, payment_id: UUID) -> PaymentEntry | None: ...

    async def list_for_contract(self, contract_id: UUID) -> list[Payment]:
        """Pagos del contrato, del más antiguo al más reciente."""
        ...

    async def entries_for_contract(self, contract_id: UUID) -> list[PaymentEntry]:
        """Pagos del contrato con su anulación, del más antiguo al más reciente."""
        ...

    async def add_void(self, void: PaymentVoid) -> None:
        """Si el pago ya tiene anulación, lanza `PaymentAlreadyVoidedError`."""
        ...

    async def monthly_totals(self, date_from: date, date_to: date) -> list[MonthlyPaymentTotal]:
        """Pagos vigentes del rango, sumados por mes y tipo."""
        ...

    async def paid_totals(self, contract_ids: list[UUID]) -> dict[UUID, ContractPaidTotals]:
        """Pagos vigentes de esos contratos, sumados; los que no tienen pagos no aparecen."""
        ...

    async def entries_between(self, date_from: date, date_to: date) -> list[PaymentEntry]:
        """Pagos del rango (por fecha de pago) con su anulación, del más antiguo al más reciente."""
        ...
