"""Forma de los datos de contratos en la API (HU41–HU42)."""

from datetime import date, datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractSummary,
)
from local_eventos.modules.commercial.application.contracts.use_cases.contracts import (
    AdvancePayment,
    ContractPage,
)
from local_eventos.modules.commercial.domain.contracts.contract import Contract, ContractStatus
from local_eventos.modules.ledger.public_api import Payment, PaymentKind, PaymentMethod


class ContractGenerateIn(BaseModel):
    quote_id: UUID
    advance_cents: int | None = Field(
        default=None, description="Adelanto pactado. Si se omite: 50 % del total"
    )


class PaymentIn(BaseModel):
    paid_on: date
    method: PaymentMethod
    reference: str | None = Field(default=None, description="N.º de operación, voucher, etc.")

    def to_payment(self) -> AdvancePayment:
        return AdvancePayment(paid_on=self.paid_on, method=self.method, reference=self.reference)


class ContractSignIn(BaseModel):
    signed_on: date
    signer_name: str
    advance: PaymentIn = Field(description="El pago del adelanto pactado (R-CON-1)")


class ContractCancelIn(BaseModel):
    reason: str
    refund_cents: int | None = Field(default=None, description="Solo si se devolvió dinero")
    refund: PaymentIn | None = Field(default=None, description="Cómo se devolvió")
    note: str | None = None


class PaymentOut(BaseModel):
    id: UUID
    kind: PaymentKind
    amount_cents: int
    method: PaymentMethod
    reference: str | None
    paid_on: date

    @classmethod
    def from_payment(cls, payment: Payment) -> Self:
        return cls(
            id=payment.id,
            kind=payment.kind,
            amount_cents=payment.amount_cents,
            method=payment.method,
            reference=payment.reference,
            paid_on=payment.paid_on,
        )


class SignatureOut(BaseModel):
    signed_on: date
    signer_name: str
    recorded_at: datetime


class CancellationOut(BaseModel):
    reason: str
    refund_cents: int | None
    note: str | None
    cancelled_at: datetime


class ContractOut(BaseModel):
    id: UUID
    code: str
    quote_id: UUID
    quote_code: str
    client_id: UUID
    client_name: str
    event_date: date
    total_cents: int
    advance_cents: int
    balance_cents: int
    balance_due_date: date
    currency: str = "PEN"
    status: ContractStatus
    can_become_event: bool = Field(description="Firmado y con adelanto pagado (CA-42.3)")
    signature: SignatureOut | None
    cancellation: CancellationOut | None
    payments: list[PaymentOut]
    event_id: UUID | None = Field(description="El evento, si el contrato ya se convirtió (HU10)")
    created_at: datetime

    @classmethod
    def from_contract(
        cls,
        contract: Contract,
        *,
        quote_code: str,
        client_name: str,
        payments: list[Payment],
        event_id: UUID | None = None,
    ) -> Self:
        signature, cancellation = contract.signature, contract.cancellation
        return cls(
            id=contract.id,
            code=contract.code,
            quote_id=contract.quote_id,
            quote_code=quote_code,
            client_id=contract.client_id,
            client_name=client_name,
            event_date=contract.event_date,
            total_cents=contract.total_cents,
            advance_cents=contract.advance_cents,
            balance_cents=contract.balance_cents,
            balance_due_date=contract.balance_due_date,
            status=contract.status,
            can_become_event=contract.can_become_event,
            signature=SignatureOut(
                signed_on=signature.signed_on,
                signer_name=signature.signer_name,
                recorded_at=signature.recorded_at,
            )
            if signature
            else None,
            cancellation=CancellationOut(
                reason=cancellation.reason,
                refund_cents=cancellation.refund_cents,
                note=cancellation.note,
                cancelled_at=cancellation.cancelled_at,
            )
            if cancellation
            else None,
            payments=[PaymentOut.from_payment(p) for p in payments],
            event_id=event_id,
            created_at=contract.created_at,
        )


class ContractSummaryOut(BaseModel):
    id: UUID
    code: str
    quote_id: UUID
    client_name: str
    event_date: date
    total_cents: int
    advance_cents: int
    status: ContractStatus

    @classmethod
    def from_summary(cls, summary: ContractSummary) -> Self:
        return cls(
            id=summary.id,
            code=summary.code,
            quote_id=summary.quote_id,
            client_name=summary.client_name,
            event_date=summary.event_date,
            total_cents=summary.total_cents,
            advance_cents=summary.advance_cents,
            status=summary.status,
        )


class ContractPageOut(BaseModel):
    items: list[ContractSummaryOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: ContractPage) -> Self:
        return cls(
            items=[ContractSummaryOut.from_summary(s) for s in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )
