"""Cotización en PDF (HU09): qué se entrega, cuándo se puede y que no cambia la cotización."""

from datetime import timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.application.quotes.errors import (
    QuoteNotFoundError,
    QuotePdfNotAvailableError,
)
from local_eventos.modules.commercial.application.quotes.ports.document import (
    CompanyProfile,
    QuoteDocument,
)
from local_eventos.modules.commercial.application.quotes.use_cases.query_quotes import (
    ChangeQuoteStatus,
)
from local_eventos.modules.commercial.application.quotes.use_cases.quote_document import (
    GetQuoteDocument,
)
from local_eventos.modules.commercial.domain.quotes.quote import QuoteStatus
from local_eventos.modules.commercial.infrastructure.company_settings import CompanySettings
from local_eventos.modules.commercial.infrastructure.quote_pdf import ReportLabQuoteRenderer, soles

from .world import World

COMPANY = CompanyProfile(name="Darze Catering", ruc="20123456789", phone="01 555 0000")


class SpyRenderer:
    def __init__(self) -> None:
        self.documents: list[QuoteDocument] = []

    def render(self, document: QuoteDocument) -> bytes:
        self.documents.append(document)
        return b"%PDF-falso"


def _use_case(world: World, renderer: object) -> GetQuoteDocument:
    return GetQuoteDocument(world.quotes, world.clients, renderer, COMPANY, world.clock)  # type: ignore[arg-type]


async def _sent_quote(world: World):  # type: ignore[no-untyped-def]
    quote = await world.create()(world.command(), created_by=uuid4())
    await ChangeQuoteStatus(world.quotes, world.clock)(quote.id, QuoteStatus.SENT)
    return quote


async def test_ca09_1_y_ca09_4_entrega_cliente_darze_y_nombre_del_archivo(world: World) -> None:
    quote = await _sent_quote(world)
    renderer = SpyRenderer()

    filename, content = await _use_case(world, renderer)(quote.id)

    [document] = renderer.documents
    assert filename == "COT-2026-0001.pdf"
    assert content == b"%PDF-falso"
    assert document.client.id == world.client.id
    assert document.company == COMPANY
    assert document.issued_on == world.clock.today()


async def test_ca09_5_generar_no_cambia_la_cotizacion(world: World) -> None:
    quote = await _sent_quote(world)
    before = world.quotes.quotes[quote.id]

    await _use_case(world, SpyRenderer())(quote.id)

    assert world.quotes.quotes[quote.id] == before


async def test_r_pdf_1_aceptada_si_se_descarga(world: World) -> None:
    quote = await _sent_quote(world)
    await ChangeQuoteStatus(world.quotes, world.clock)(quote.id, QuoteStatus.ACCEPTED)

    filename, _ = await _use_case(world, SpyRenderer())(quote.id)

    assert filename.endswith(".pdf")


@pytest.mark.parametrize("final", [None, QuoteStatus.REJECTED])
async def test_r_pdf_1_borrador_y_rechazada_no_se_descargan(
    world: World, final: QuoteStatus | None
) -> None:
    quote = await world.create()(world.command(), created_by=uuid4())
    if final:
        await ChangeQuoteStatus(world.quotes, world.clock)(quote.id, final)

    with pytest.raises(QuotePdfNotAvailableError) as error:
        await _use_case(world, SpyRenderer())(quote.id)
    assert error.value.code == "quote.pdf_not_available"


async def test_r_pdf_1_vencida_no_se_descarga(world: World) -> None:
    quote = await world.create()(
        world.command(valid_until=world.clock.today() + timedelta(days=1)), created_by=uuid4()
    )
    await ChangeQuoteStatus(world.quotes, world.clock)(quote.id, QuoteStatus.SENT)
    world.clock.advance(days=3)

    with pytest.raises(QuotePdfNotAvailableError):
        await _use_case(world, SpyRenderer())(quote.id)


async def test_cotizacion_inexistente(world: World) -> None:
    with pytest.raises(QuoteNotFoundError):
        await _use_case(world, SpyRenderer())(uuid4())


async def test_ca09_2_y_ca09_3_el_pdf_lleva_los_datos_registrados(world: World) -> None:
    quote = await _sent_quote(world)
    client = await world.clients.get(quote.client_id)
    assert client is not None

    pdf = ReportLabQuoteRenderer(compress=False).render(
        QuoteDocument(quote=quote, client=client, company=COMPANY, issued_on=world.clock.today())
    )

    assert pdf.startswith(b"%PDF")
    for text in (
        quote.code,
        soles(quote.total_cents),
        "20123456789",
        client.document.number,
        "Movilidad",
        "20:00 a 03:00",
        "Local Los Jardines",
    ):
        assert text.encode() in pdf, text


def test_soles_en_formato_peruano() -> None:
    assert soles(4550) == "S/ 45.50"
    assert soles(545_000) == "S/ 5,450.00"


def test_datos_de_darze_vacios_no_se_imprimen(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COMPANY_NAME", "  Darze Catering ")
    monkeypatch.setenv("COMPANY_RUC", "   ")
    monkeypatch.delenv("COMPANY_PHONE", raising=False)

    profile = CompanySettings(_env_file=None).profile()

    assert profile == CompanyProfile(name="Darze Catering")
