"""Eventos contra PostgreSQL real (HU10). Necesita Docker.

Prueba lo que solo la base puede garantizar: un evento por contrato aun con dos conversiones
simultáneas, y los triggers que cuidan la relación con el contrato.
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, date, datetime, time
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer

from local_eventos.modules.commercial.application.contracts.ports.contract_repository import (
    ContractFilters,
)
from local_eventos.modules.commercial.application.events.errors import EventAlreadyExistsError
from local_eventos.modules.commercial.application.events.ports.event_repository import (
    EventFilters,
)
from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType
from local_eventos.modules.commercial.domain.contracts.contract import (
    Contract,
    ContractRuleError,
    ContractStatus,
)
from local_eventos.modules.commercial.domain.events.event import (
    Event,
    EventRuleError,
    EventStatus,
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
from local_eventos.modules.commercial.infrastructure.event_repository import (
    SqlAlchemyEventRepository,
)
from local_eventos.modules.commercial.infrastructure.quote_repository import (
    SqlAlchemyQuoteRepository,
)
from local_eventos.shared.infrastructure.db import create_engine

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
                " commercial_contracts, commercial_quote_lines, commercial_quotes,"
                " commercial_client_document_corrections, commercial_clients"
            )
        )
    await engine.dispose()


@pytest.fixture
def sessions(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def _contract(
    sessions: async_sessionmaker[AsyncSession], number: str, *, signed: bool = True
) -> tuple[Contract, Quote]:
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
                kind=LineKind.SERVICE,
                description="Buffet criollo",
                unit=LineUnit.PER_PERSON,
                quantity=100,
                unit_price_cents=4500,
                service_id=uuid4(),
                catalog_price_cents=4500,
            ),  # fmt: skip
            QuoteLine(
                kind=LineKind.EXTRA,
                description="Movilidad",
                unit=LineUnit.PER_UNIT,
                quantity=1,
                unit_price_cents=15_000,
            ),  # fmt: skip
        ],
        created_by=uuid4(),
        now=NOW,
        today=TODAY,
    )
    async with sessions.begin() as session:
        await SqlAlchemyClientRepository(session).add(client)
        await SqlAlchemyQuoteRepository(session).add(quote)
    quote.change_status(QuoteStatus.ACCEPTED, TODAY)
    contract = Contract.generate(
        code=f"CON-2026-{number[-4:]}", quote=quote, today=TODAY, created_by=uuid4(), now=NOW
    )
    if signed:  # sin pago real: aquí solo importa el estado del contrato
        contract.sign(
            signed_on=TODAY, signer_name="José", advance_payment_id=uuid4(),
            recorded_by=uuid4(), now=NOW, today=TODAY,
        )  # fmt: skip
    async with sessions.begin() as session:
        await SqlAlchemyQuoteRepository(session).update(quote)
        await SqlAlchemyContractRepository(session).add(contract)
    return contract, quote


def _event(contract: Contract, quote: Quote, code: str = "EVT-2026-0001") -> Event:
    return Event.from_contract(
        code=code, contract=contract, quote=quote, coordinator_id=uuid4(), created_by=uuid4(),
        now=NOW,
    )  # fmt: skip


async def test_ca10_guarda_y_lee_el_evento_con_sus_servicios(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract, quote = await _contract(sessions, "40000001")
    event = _event(contract, quote)
    async with sessions.begin() as session:
        await SqlAlchemyEventRepository(session).add(event)

    async with sessions() as session:
        repository = SqlAlchemyEventRepository(session)
        saved = await repository.get(event.id)
        by_contract = await repository.get_by_contract(contract.id)
        found, total = await repository.search(
            EventFilters(text="jose", status=EventStatus.SCHEDULED, date_from=date(2026, 12, 19)),
            limit=10, offset=0,
        )  # fmt: skip

    assert saved == event == by_contract
    assert [s.description for s in event.services] == ["Buffet criollo", "Movilidad"]
    assert (total, found[0].code, found[0].client_name) == (1, "EVT-2026-0001", "José Ramírez")


async def test_ca10_5_dos_conversiones_simultaneas_del_mismo_contrato(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract, quote = await _contract(sessions, "40000002")

    async def convert(code: str) -> str:
        try:
            async with sessions.begin() as session:
                await SqlAlchemyEventRepository(session).add(_event(contract, quote, code))
            return "ok"
        except EventAlreadyExistsError:
            return "duplicado"

    results = await asyncio.gather(convert("EVT-2026-0001"), convert("EVT-2026-0002"))

    assert sorted(results) == ["duplicado", "ok"]


async def test_ca10_1_la_base_rechaza_evento_de_contrato_no_firmado(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    signed, quote = await _contract(sessions, "40000003")
    pending, _ = await _contract(sessions, "40000004", signed=False)
    event = _event(signed, quote)
    event.contract_id = pending.id  # saltándose el dominio, como haría un error de programación

    with pytest.raises(EventRuleError) as error:
        async with sessions.begin() as session:
            await SqlAlchemyEventRepository(session).add(event)
    assert error.value.code == "event.contract_not_ready"


async def test_r_evt_3_la_base_no_anula_un_contrato_con_evento(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract, quote = await _contract(sessions, "40000005")
    async with sessions.begin() as session:
        await SqlAlchemyEventRepository(session).add(_event(contract, quote))
    contract.cancel(
        reason="Canceló", refund_cents=None, refund_payment_id=None, note=None,
        cancelled_by=uuid4(), now=NOW,
    )  # fmt: skip

    with pytest.raises(ContractRuleError) as error:
        async with sessions.begin() as session:
            await SqlAlchemyContractRepository(session).update(contract)
    assert error.value.code == "contract.has_event"
    with pytest.raises(DBAPIError, match="R-EVT-3"):
        async with sessions.begin() as session:
            await session.execute(text("UPDATE commercial_contracts SET status = 'CANCELLED'"))


async def test_r_evt_3_con_evento_cancelado_el_contrato_si_se_anula(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract, quote = await _contract(sessions, "40000006")
    event = _event(contract, quote)
    async with sessions.begin() as session:
        await SqlAlchemyEventRepository(session).add(event)
    event.cancel(reason="Canceló", cancelled_by=uuid4(), now=NOW)
    contract.cancel(
        reason="Canceló", refund_cents=None, refund_payment_id=None, note=None,
        cancelled_by=uuid4(), now=NOW,
    )  # fmt: skip

    async with sessions.begin() as session:
        await SqlAlchemyEventRepository(session).update(event)
        await SqlAlchemyContractRepository(session).update(contract)

    async with sessions() as session:
        saved_event = await SqlAlchemyEventRepository(session).get(event.id)
        saved_contract = await SqlAlchemyContractRepository(session).get(contract.id)
    assert saved_event == event
    assert saved_contract is not None and saved_contract.status is ContractStatus.CANCELLED


async def test_ca11_c5_la_base_exige_motivo_al_cancelar(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract, quote = await _contract(sessions, "40000007")
    async with sessions.begin() as session:
        await SqlAlchemyEventRepository(session).add(_event(contract, quote))

    with pytest.raises(DBAPIError, match="cancelled_has_reason"):
        async with sessions.begin() as session:
            await session.execute(text("UPDATE commercial_events SET status = 'CANCELLED'"))


async def test_ca12_calendario_filtra_por_rango_y_tipo(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    contract, quote = await _contract(sessions, "40000008")  # boda del 19/12/2026
    event = _event(contract, quote)
    async with sessions.begin() as session:
        await SqlAlchemyEventRepository(session).add(event)

    async def found(**filters: object) -> list[str]:
        async with sessions() as session:
            items, _ = await SqlAlchemyEventRepository(session).search(
                EventFilters(**filters),  # type: ignore[arg-type]
                limit=100, offset=0,
            )  # fmt: skip
        return [item.code for item in items]

    december = {"date_from": date(2026, 12, 1), "date_to": date(2026, 12, 31)}
    assert await found(**december) == ["EVT-2026-0001"]
    assert await found(**december, event_type=EventType.WEDDING) == ["EVT-2026-0001"]
    assert await found(**december, event_type=EventType.BIRTHDAY) == []
    assert await found(date_from=date(2026, 12, 20), date_to=date(2026, 12, 31)) == []


async def test_ca05_contratos_y_eventos_filtrados_por_cliente(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    mine, my_quote = await _contract(sessions, "40000009")
    other, other_quote = await _contract(sessions, "40000010")
    async with sessions.begin() as session:
        await SqlAlchemyEventRepository(session).add(_event(mine, my_quote, "EVT-2026-0001"))
        await SqlAlchemyEventRepository(session).add(_event(other, other_quote, "EVT-2026-0002"))

    async with sessions() as session:
        events, _ = await SqlAlchemyEventRepository(session).search(
            EventFilters(client_id=mine.client_id), limit=100, offset=0
        )
        contracts, _ = await SqlAlchemyContractRepository(session).search(
            ContractFilters(client_id=mine.client_id), limit=100, offset=0
        )

    assert [e.code for e in events] == ["EVT-2026-0001"]
    assert [c.id for c in contracts] == [mine.id]
