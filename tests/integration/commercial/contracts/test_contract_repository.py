"""Contratos y pagos contra PostgreSQL real (HU41–HU42). Necesita Docker.

Las tablas, el índice único y los triggers se crean con las migraciones, igual que en producción.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.commercial.application.contracts.errors import (
    ContractAlreadyExistsError,
)
from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
)
from local_eventos.modules.commercial.application.contracts.use_cases.payments import (
    GetContractAccount,
    NewPayment,
    RecordContractPayment,
)
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.domain.contracts.contract import (
    Contract,
    ContractStatus,
    ContractValidationError,
)
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventDetails,
    EventType,
    LineKind,
    LineUnit,
    Quote,
    QuoteLine,
    QuoteStatus,
)
from local_eventos.modules.commercial.infrastructure.client_repository import (
    SqlAlchemyClientRepository,
)
from local_eventos.modules.commercial.infrastructure.contract_repository import (
    SqlAlchemyContractRepository,
)
from local_eventos.modules.commercial.infrastructure.quote_repository import (
    SqlAlchemyQuoteRepository,
)
from local_eventos.modules.ledger.application.ports.payment_repository import PaymentEntry
from local_eventos.modules.ledger.application.use_cases.payments import (
    ContractPaymentEntries,
    RecordPayment,
)
from local_eventos.modules.ledger.domain.payment import Payment, PaymentKind, PaymentMethod
from local_eventos.modules.ledger.infrastructure.payment_repository import (
    SqlAlchemyPaymentRepository,
)
from local_eventos.shared.infrastructure.db import create_engine
from tests.unit.commercial.quotes.fakes import FakeClock

pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[4]
TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, tzinfo=UTC)


@pytest.fixture(scope="module")
def database_url() -> Iterator[str]:
    with PostgresContainer("postgres:17-alpine", driver="asyncpg") as postgres:
        url = postgres.get_connection_url()
        with pytest.MonkeyPatch.context() as patch:
            patch.setenv("DATABASE_URL", url)
            command.upgrade(Config(str(ROOT / "alembic.ini")), "head")
        yield url


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    engine = create_engine(database_url)
    yield engine
    async with engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE commercial_event_services, commercial_events, commercial_event_counters,"
                " ledger_payment_voids, ledger_payments, ledger_payment_counters,"
                " commercial_contracts, commercial_contract_counters,"
                " commercial_quote_lines, commercial_quotes,"
                " commercial_client_document_corrections, commercial_clients"
            )
        )
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _accepted_quote(sessions: async_sessionmaker[AsyncSession], number: str) -> Quote:
    client = Client.register(
        name="José Ramírez", document_type=DocumentType.DNI, document_number=number,
        phone="987654321",
    )  # fmt: skip
    quote = Quote.create(
        code=f"COT-2026-{number[-4:]}",
        client_id=client.id,
        details=EventDetails(
            event_type=EventType.WEDDING,
            event_date=date(2026, 12, 19),
            start_time=time(20),
            end_time=time(3),
            venue="SJL",
            guests=100,
        ),  # fmt: skip
        lines=[
            QuoteLine(
                kind=LineKind.EXTRA,
                description="Paquete",
                unit=LineUnit.PER_UNIT,
                quantity=1,
                unit_price_cents=545_000,
            )  # fmt: skip
        ],
        created_by=uuid4(),
        now=NOW,
        today=TODAY,
    )
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)
        await SqlAlchemyQuoteRepository(session).add(quote)
    quote.change_status(QuoteStatus.ACCEPTED, TODAY)
    async with sessions.begin() as session:
        await SqlAlchemyQuoteRepository(session).update(quote)
    return quote


def _contract(quote: Quote, code: str = "CON-2026-0001") -> Contract:
    return Contract.generate(code=code, quote=quote, today=TODAY, created_by=uuid4(), now=NOW)


def _advance(contract: Contract) -> Payment:
    return Payment.record(
        number=f"PAG-T-{uuid4().hex[:12]}",
        contract_id=contract.id, kind=PaymentKind.ADVANCE, amount_cents=contract.advance_cents,
        method=PaymentMethod.TRANSFER, reference="Op. 1", paid_on=TODAY, recorded_by=uuid4(),
        now=NOW, today=TODAY,
    )  # fmt: skip


async def test_ca42_guarda_firma_y_anulacion_con_sus_pagos(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract = _contract(await _accepted_quote(sessions, "40000001"))
    payment = _advance(contract)
    async with sessions.begin() as session:
        await SqlAlchemyContractRepository(session).add(contract)
        await SqlAlchemyPaymentRepository(session).add(payment)
        contract.sign(
            signed_on=TODAY, signer_name="José Ramírez", advance_payment_id=payment.id,
            recorded_by=uuid4(), now=NOW, today=TODAY,
        )  # fmt: skip
        await SqlAlchemyContractRepository(session).update(contract)
    contract.cancel(
        reason="Canceló", refund_cents=None, refund_payment_id=None, note=None,
        cancelled_by=uuid4(), now=NOW,
    )  # fmt: skip
    async with sessions.begin() as session:
        await SqlAlchemyContractRepository(session).update(contract)

    async with sessions() as session:
        saved = await SqlAlchemyContractRepository(session).get(contract.id)
        by_quote = await SqlAlchemyContractRepository(session).get_by_quote(contract.quote_id)
        payments = await SqlAlchemyPaymentRepository(session).list_for_contract(contract.id)

    assert saved == contract == by_quote
    assert payments == [payment]


async def test_ca41_1_dos_contratos_simultaneos_de_la_misma_cotizacion(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    quote = await _accepted_quote(sessions, "40000002")

    async def generate(code: str) -> str:
        try:
            async with sessions.begin() as session:
                await SqlAlchemyContractRepository(session).add(_contract(quote, code))
            return "ok"
        except ContractAlreadyExistsError:
            return "duplicado"

    results = await asyncio.gather(generate("CON-2026-0001"), generate("CON-2026-0002"))

    assert sorted(results) == ["duplicado", "ok"]


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE commercial_contracts SET advance_cents = 1",
        "UPDATE commercial_contracts SET status = 'PENDING_SIGNATURE', signed_on = NULL",
    ],
)
async def test_ca42_2_la_base_bloquea_modificar_un_contrato_firmado(
    sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    contract = _contract(await _accepted_quote(sessions, "40000003"))
    payment = _advance(contract)
    async with sessions.begin() as session:
        await SqlAlchemyContractRepository(session).add(contract)
        await SqlAlchemyPaymentRepository(session).add(payment)
        contract.sign(
            signed_on=TODAY, signer_name="José", advance_payment_id=payment.id,
            recorded_by=uuid4(), now=NOW, today=TODAY,
        )  # fmt: skip
        await SqlAlchemyContractRepository(session).update(contract)

    with pytest.raises(DBAPIError, match="firmado"):
        async with sessions.begin() as session:
            await session.execute(text(statement))


@pytest.mark.parametrize(
    "statement", ["UPDATE ledger_payments SET amount_cents = 1", "DELETE FROM ledger_payments"]
)
async def test_regla_5_los_pagos_no_se_modifican_ni_se_borran(
    sessions: async_sessionmaker[AsyncSession], statement: str
) -> None:
    contract = _contract(await _accepted_quote(sessions, "40000004"))
    async with sessions.begin() as session:
        await SqlAlchemyContractRepository(session).add(contract)
        await SqlAlchemyPaymentRepository(session).add(_advance(contract))

    with pytest.raises(DBAPIError, match="pagos no se modifican"):
        async with sessions.begin() as session:
            await session.execute(text(statement))


async def test_busca_y_codigos_sin_repetir(sessions: async_sessionmaker[AsyncSession]) -> None:
    first = _contract(await _accepted_quote(sessions, "40000005"), "CON-2026-0001")
    async with sessions.begin() as session:
        repository = SqlAlchemyContractRepository(session)
        await repository.add(first)
        numbers = [await repository.next_number(2026) for _ in range(3)]

    async with sessions() as session:
        found, total = await SqlAlchemyContractRepository(session).search(
            ContractFilters(text="jose ramirez", status=ContractStatus.PENDING_SIGNATURE),
            limit=10, offset=0,
        )  # fmt: skip

    assert numbers == [1, 2, 3]
    assert (total, found[0].code) == (1, "CON-2026-0001")


async def _signed_in_db(sessions: async_sessionmaker[AsyncSession], number: str) -> Contract:
    contract = _contract(await _accepted_quote(sessions, number), f"CON-2026-{number[-4:]}")
    advance = _advance(contract)
    contract.sign(
        signed_on=TODAY, signer_name="José", advance_payment_id=advance.id,
        recorded_by=uuid4(), now=NOW, today=TODAY,
    )  # fmt: skip
    async with sessions.begin() as session:
        await SqlAlchemyContractRepository(session).add(contract)
        await SqlAlchemyPaymentRepository(session).add(advance)
    return contract


class _SlowEntries(ContractPaymentEntries):
    """Tarda tras leer los pagos: sin el bloqueo, dos pagos leerían el mismo saldo."""

    async def __call__(self, contract_id: UUID) -> list[PaymentEntry]:
        entries = await super().__call__(contract_id)
        await asyncio.sleep(0.3)
        return entries


async def _pay(sessions: async_sessionmaker[AsyncSession], contract: Contract, amount: int) -> None:
    async with sessions.begin() as session:
        payments = SqlAlchemyPaymentRepository(session)
        await RecordContractPayment(
            SqlAlchemyContractRepository(session),
            _SlowEntries(payments),
            RecordPayment(payments),
            FakeClock(),
        )(
            contract.id,
            NewPayment(amount_cents=amount, paid_on=TODAY, method=PaymentMethod.CASH),
            recorded_by=uuid4(),
        )


async def test_ca19_2_pagar_hasta_saldo_cero_y_el_siguiente_falla(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract = await _signed_in_db(sessions, "40000011")
    rest = contract.total_cents - contract.advance_cents

    await _pay(sessions, contract, rest - 1_000)
    await _pay(sessions, contract, 1_000)
    with pytest.raises(ContractValidationError) as error:
        await _pay(sessions, contract, 1)

    async with sessions() as session:
        account = await GetContractAccount(
            SqlAlchemyContractRepository(session),
            ContractPaymentEntries(SqlAlchemyPaymentRepository(session)),
            FakeClock(),
        )(contract.id)
    assert error.value.code == "payment.exceeds_balance"
    assert (account.balance.paid_cents, account.balance.balance_cents) == (contract.total_cents, 0)


async def test_dos_pagos_simultaneos_no_superan_el_saldo(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    """La fila del contrato se bloquea (FOR UPDATE): el segundo pago ve el saldo del primero."""
    contract = await _signed_in_db(sessions, "40000012")
    rest = contract.total_cents - contract.advance_cents

    results = await asyncio.gather(
        _pay(sessions, contract, rest), _pay(sessions, contract, rest), return_exceptions=True
    )

    failures = [r for r in results if isinstance(r, Exception)]
    assert len(failures) == 1
    assert isinstance(failures[0], ContractValidationError)
    assert failures[0].code == "payment.exceeds_balance"
    async with sessions() as session:
        entries = await SqlAlchemyPaymentRepository(session).entries_for_contract(contract.id)
    assert sum(e.payment.amount_cents for e in entries) == contract.total_cents
