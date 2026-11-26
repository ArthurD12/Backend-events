"""Contrato en PDF (HU43): qué se entrega, cuándo se puede y que no cambia el contrato."""

from uuid import uuid4

import pytest

from local_eventos.modules.commercial.application.contracts.errors import (
    ContractNotFoundError,
    ContractPdfNotAvailableError,
)
from local_eventos.modules.commercial.application.contracts.ports.document import (
    CONTRACT_TERMS,
    ContractDocument,
)
from local_eventos.modules.commercial.application.contracts.use_cases.contract_document import (
    GetContractDocument,
)
from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile
from local_eventos.modules.commercial.domain.contracts.contract import Contract
from local_eventos.modules.commercial.infrastructure.contract_pdf import ReportLabContractRenderer
from local_eventos.modules.commercial.infrastructure.quote_pdf import soles
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from tests.unit.current_user import signed_in_as

from .test_contract_api import Api, api  # noqa: F401 - fixture
from .test_contract_use_cases import Setup, setup  # noqa: F401 - fixture

COMPANY = CompanyProfile(name="Darze Catering", ruc="20123456789", phone="01 555 0000")


class SpyRenderer:
    def __init__(self) -> None:
        self.documents: list[ContractDocument] = []

    def render(self, document: ContractDocument) -> bytes:
        self.documents.append(document)
        return b"%PDF-falso"


def _in_pdf(text: str) -> bytes:
    """Cómo queda el texto en un PDF sin comprimir: tildes y ñ salen como `\\355`."""
    return "".join(c if ord(c) < 128 else f"\\{ord(c):03o}" for c in text).encode("ascii")


def _use_case(setup: Setup, renderer: object) -> GetContractDocument:  # noqa: F811
    return GetContractDocument(
        setup.contracts, setup.world.quotes, setup.world.clients,
        renderer, COMPANY, setup.world.clock,
    )  # type: ignore[arg-type]  # fmt: skip


async def _pending(setup: Setup) -> Contract:  # noqa: F811
    quote = await setup.accepted_quote()
    return await setup.generate()(quote.id, created_by=uuid4(), advance_cents=200_000)


async def _signed(setup: Setup) -> Contract:  # noqa: F811
    contract = await _pending(setup)
    await setup.sign()(
        contract.id, signed_on=setup.world.clock.today(), signer_name="José Ramírez",
        advance=setup.advance(), recorded_by=uuid4(),
    )  # fmt: skip
    return contract


async def test_ca43_1_entrega_cliente_darze_cotizacion_y_nombre_del_archivo(
    setup: Setup,  # noqa: F811
) -> None:
    contract = await _pending(setup)
    renderer = SpyRenderer()

    filename, content = await _use_case(setup, renderer)(contract.id)

    [document] = renderer.documents
    assert (filename, content) == ("CON-2026-0001.pdf", b"%PDF-falso")
    assert document.client.id == setup.world.client.id
    assert document.quote.id == contract.quote_id
    assert document.company == COMPANY
    assert document.terms == CONTRACT_TERMS
    assert document.issued_on == setup.world.clock.today()


async def test_r_pdf_2_pendiente_y_firmado_se_descargan(setup: Setup) -> None:  # noqa: F811
    signed = await _signed(setup)
    pending_quote = await setup.accepted_quote()
    pending = await setup.generate()(pending_quote.id, created_by=uuid4())

    for contract in (signed, pending):
        filename, _ = await _use_case(setup, SpyRenderer())(contract.id)
        assert filename == f"{contract.code}.pdf"


async def test_r_pdf_2_anulado_no_se_descarga(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)
    await setup.cancel()(
        contract.id, reason="El cliente canceló", cancelled_by=uuid4(),
        refund_cents=None, refund=None, note=None,
    )  # fmt: skip

    with pytest.raises(ContractPdfNotAvailableError) as error:
        await _use_case(setup, SpyRenderer())(contract.id)
    assert error.value.code == "contract.pdf_not_available"


async def test_ca43_5_generar_no_cambia_el_contrato(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)
    before = repr(setup.contracts.contracts[contract.id])

    await _use_case(setup, SpyRenderer())(contract.id)

    assert repr(setup.contracts.contracts[contract.id]) == before


async def test_contrato_inexistente(setup: Setup) -> None:  # noqa: F811
    with pytest.raises(ContractNotFoundError):
        await _use_case(setup, SpyRenderer())(uuid4())


async def test_ca43_2_a_ca43_4_el_pdf_lleva_lo_registrado(setup: Setup) -> None:  # noqa: F811
    contract = await _signed(setup)
    renderer = SpyRenderer()
    await _use_case(setup, renderer)(contract.id)
    [document] = renderer.documents
    client = document.client

    pdf = ReportLabContractRenderer(compress=False).render(document)

    assert pdf.startswith(b"%PDF")
    for text in (
        contract.code,
        "20123456789",
        client.document.number,
        "Movilidad",
        "20:00 a 03:00",
        "Local Los Jardines",
        soles(contract.total_cents),
        soles(200_000),
        soles(contract.total_cents - 200_000),
        "Firmado el",
        "José Ramírez",
        "Política de cancelación",
        "Firma del cliente",
        "Por Darze Catering",
    ):
        assert _in_pdf(text) in pdf, text


async def test_pendiente_no_dice_firmado(setup: Setup) -> None:  # noqa: F811
    contract = await _pending(setup)
    renderer = SpyRenderer()
    await _use_case(setup, renderer)(contract.id)

    pdf = ReportLabContractRenderer(compress=False).render(renderer.documents[0])

    assert b"Pendiente de firma" in pdf and b"Firmado el" not in pdf


def test_ca43_6_api_pdf_estado_y_permisos(api: Api) -> None:  # noqa: F811
    contract = api.generate(api.accepted_quote(500_000)).json()
    url = f"/v1/contracts/{contract['id']}"

    pending = api.client.get(f"{url}/pdf")
    api.sign(contract["id"])
    signed = api.client.get(f"{url}/pdf")
    api.client.post(f"{url}/cancel", json={"reason": "El cliente canceló"})
    cancelled = api.client.get(f"{url}/pdf")
    missing = api.client.get("/v1/contracts/00000000-0000-0000-0000-000000000000/pdf")

    for response in (pending, signed):
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"
        assert response.headers["content-disposition"] == (
            'attachment; filename="CON-2026-0001.pdf"'
        )
        assert response.content.startswith(b"%PDF")
    assert (cancelled.status_code, cancelled.json()["code"]) == (409, "contract.pdf_not_available")
    assert (missing.status_code, missing.json()["code"]) == (404, "contract.not_found")
    assert api.client.get(url).json()["status"] == "CANCELLED"


def test_compras_no_descarga_el_contrato(api: Api) -> None:  # noqa: F811
    contract = api.generate(api.accepted_quote(500_000)).json()
    api.client.app.dependency_overrides[get_current_user] = signed_in_as(  # type: ignore[attr-defined]
        Role.PURCHASING_MANAGER
    )

    response = api.client.get(f"/v1/contracts/{contract['id']}/pdf")

    assert (response.status_code, response.json()["code"]) == (403, "auth.forbidden")
