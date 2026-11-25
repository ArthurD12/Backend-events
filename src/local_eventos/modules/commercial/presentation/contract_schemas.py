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
from local_eventos.modules.commercial.application.contracts.use_cases.payments import (
    ContractAccount,
    NewPayment,
)
from local_eventos.modules.commercial.domain.contracts.contract import (
    Contract,
    ContractBalance,
    ContractStatus,
)
from local_eventos.modules.ledger.public_api import PaymentEntry, PaymentKind, PaymentMethod


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


class ContractPaymentIn(BaseModel):
    amount_cents: int = Field(description="Mayor que cero y sin superar el saldo (RN14)")
    paid_on: date = Field(description="No puede ser futura (R-PAG-4)")
    method: PaymentMethod
    reference: str | None = Field(default=None, description="N.º de operación, voucher, etc.")

    def to_payment(self) -> NewPayment:
        return NewPayment(
            amount_cents=self.amount_cents,
            paid_on=self.paid_on,
            method=self.method,
            reference=self.reference,
        )


class VoidIn(BaseModel):
    reason: str = Field(description="Motivo obligatorio (RN17)")


class PaymentOut(BaseModel):
    id: UUID
    number: str = Field(description="PAG-AAAA-NNNN (CA-20.1)")
    kind: PaymentKind
    amount_cents: int
    method: PaymentMethod
    reference: str | None
    paid_on: date
    voided: bool = Field(description="Anulado: no cuenta en el saldo (CA-19.3)")

    @classmethod
    def from_entry(cls, entry: PaymentEntry) -> Self:
        payment = entry.payment
        return cls(
            id=payment.id,
            number=payment.number,
            kind=payment.kind,
            amount_cents=payment.amount_cents,
            method=payment.method,
            reference=payment.reference,
            paid_on=payment.paid_on,
            voided=entry.is_voided,
        )


class PaymentVoidOut(BaseModel):
    reason: str
    voided_by: UUID
    voided_by_name: str
    voided_at: datetime


class AccountPaymentOut(PaymentOut):
    recorded_by: UUID
    recorded_by_name: str = Field(description="Vacío si el usuario no existe")
    recorded_at: datetime
    voidable: bool = Field(description="Solo un pago parcial vigente se anula (CA-19.5)")
    void: PaymentVoidOut | None

    @classmethod
    def from_account_entry(cls, entry: PaymentEntry, names: dict[UUID, str]) -> Self:
        payment, void = entry.payment, entry.void
        return cls(
            **PaymentOut.from_entry(entry).model_dump(),
            recorded_by=payment.recorded_by,
            recorded_by_name=names.get(payment.recorded_by, ""),
            recorded_at=payment.recorded_at,
            voidable=payment.kind is PaymentKind.INSTALLMENT and void is None,
            void=PaymentVoidOut(
                reason=void.reason,
                voided_by=void.voided_by,
                voided_by_name=names.get(void.voided_by, ""),
                voided_at=void.voided_at,
            )
            if void
            else None,
        )


class ContractAccountOut(BaseModel):
    """CA-19.4: total, pagado, saldo, fecha límite y pagos con quién los registró."""

    contract_id: UUID
    contract_code: str
    status: ContractStatus
    total_cents: int
    paid_cents: int = Field(description="Pagos vigentes (adelanto incluido)")
    refunded_cents: int
    balance_cents: int = Field(description="Total − pagos vigentes + devoluciones (RN15)")
    balance_due_date: date
    overdue: bool = Field(description="Saldo vencido: solo un aviso (R-PAG-2)")
    currency: str = "PEN"
    payments: list[AccountPaymentOut]

    @classmethod
    def from_account(cls, account: ContractAccount, names: dict[UUID, str]) -> Self:
        contract, balance = account.contract, account.balance
        return cls(
            contract_id=contract.id,
            contract_code=contract.code,
            status=contract.status,
            total_cents=balance.total_cents,
            paid_cents=balance.paid_cents,
            refunded_cents=balance.refunded_cents,
            balance_cents=balance.balance_cents,
            balance_due_date=balance.due_date,
            overdue=account.overdue,
            payments=[AccountPaymentOut.from_account_entry(e, names) for e in account.entries],
        )


class ContractPaymentCreatedOut(BaseModel):
    payment: AccountPaymentOut
    account: ContractAccountOut


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
    paid_cents: int | None = Field(description="Pagos vigentes. Vacío sin `payments:record`")
    balance_cents: int | None = Field(
        description="Pendiente de firma: total − adelanto; firmado: total − pagos vigentes"
        " + devoluciones (RN15). Vacío sin `payments:record`"
    )
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
        payments: list[PaymentEntry],
        balance: ContractBalance | None,
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
            paid_cents=balance.paid_cents if balance else None,
            balance_cents=balance.balance_cents if balance else None,
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
            payments=[PaymentOut.from_entry(p) for p in payments],
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
