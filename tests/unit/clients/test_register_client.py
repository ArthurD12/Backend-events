"""Pruebas del caso de uso RegisterClient (HU04). Sin base de datos."""

import pytest

from local_eventos.modules.clients.application.errors import DuplicateDocumentError
from local_eventos.modules.clients.application.use_cases.register_client import (
    RegisterClient,
    RegisterClientCommand,
)
from local_eventos.modules.clients.domain.client import (
    ClientValidationError,
    DocumentType,
)

from .fakes import InMemoryClientRepository


def _command(
    document_number: str = "44125896", phone: str = "987654321"
) -> RegisterClientCommand:
    return RegisterClientCommand(
        name="Familia Quispe Mamani",
        document_type=DocumentType.DNI,
        document_number=document_number,
        phone=phone,
    )


@pytest.mark.asyncio
async def test_hu04_registra_y_guarda_el_cliente() -> None:
    repository = InMemoryClientRepository()

    client = await RegisterClient(repository)(_command())

    assert repository.clients[client.id] is client
    assert client.active is True


@pytest.mark.asyncio
async def test_hu04_rechaza_documento_duplicado() -> None:
    repository = InMemoryClientRepository()
    register = RegisterClient(repository)
    await register(_command())

    with pytest.raises(DuplicateDocumentError) as error:
        await register(_command(phone="912345678"))

    assert error.value.code == "client.document_duplicated"
    assert len(repository.clients) == 1


@pytest.mark.asyncio
async def test_hu04_registra_clientes_con_documentos_distintos() -> None:
    repository = InMemoryClientRepository()
    register = RegisterClient(repository)

    await register(_command())
    await register(
        RegisterClientCommand(
            name="Empresa FAMAQ S.A.C.",
            document_type=DocumentType.RUC,
            document_number="20547896321",
            phone="014567890",
        )
    )

    assert len(repository.clients) == 2


@pytest.mark.asyncio
async def test_hu04_datos_invalidos_no_se_guardan() -> None:
    repository = InMemoryClientRepository()

    with pytest.raises(ClientValidationError):
        await RegisterClient(repository)(_command(phone="12"))

    assert repository.clients == {}
