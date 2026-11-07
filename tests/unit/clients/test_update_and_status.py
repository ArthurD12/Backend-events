"""Pruebas de actualizar, desactivar y reactivar clientes (HU04). Sin base de datos."""

from uuid import uuid4

import pytest

from local_eventos.modules.clients.application.errors import ClientNotFoundError
from local_eventos.modules.clients.application.use_cases.change_client_status import (
    ActivateClient,
    DeactivateClient,
)
from local_eventos.modules.clients.application.use_cases.update_client_contact import (
    UpdateClientContact,
    UpdateClientContactCommand,
)
from local_eventos.modules.clients.domain.client import (
    Client,
    ClientValidationError,
    DocumentType,
)

from .fakes import InMemoryClientRepository


async def _repository_with_client() -> tuple[InMemoryClientRepository, Client]:
    repository = InMemoryClientRepository()
    client = Client.register(
        name="Familia Quispe Mamani",
        document_type=DocumentType.DNI,
        document_number="44125896",
        phone="987654321",
    )
    await repository.add(client)
    return repository, client


@pytest.mark.asyncio
async def test_hu04_actualiza_datos_de_contacto() -> None:
    repository, client = await _repository_with_client()

    updated = await UpdateClientContact(repository)(
        UpdateClientContactCommand(
            client_id=client.id,
            name="Familia Quispe",
            phone="912345678",
            address="SJL, Lima",
        )
    )

    assert repository.clients[client.id].phone == "912345678"
    assert updated.address == "SJL, Lima"


@pytest.mark.asyncio
async def test_hu04_actualizar_cliente_inexistente_falla() -> None:
    repository, _ = await _repository_with_client()

    with pytest.raises(ClientNotFoundError) as error:
        await UpdateClientContact(repository)(
            UpdateClientContactCommand(client_id=uuid4(), name="X", phone="912345678")
        )

    assert error.value.code == "client.not_found"


@pytest.mark.asyncio
async def test_hu04_actualizacion_invalida_no_cambia_el_cliente() -> None:
    repository, client = await _repository_with_client()

    with pytest.raises(ClientValidationError):
        await UpdateClientContact(repository)(
            UpdateClientContactCommand(
                client_id=client.id, name="Familia Quispe", phone="12"
            )
        )

    assert repository.clients[client.id].phone == "987654321"
    assert repository.clients[client.id].name == "Familia Quispe Mamani"


@pytest.mark.asyncio
async def test_hu04_desactiva_y_reactiva_sin_eliminar() -> None:
    repository, client = await _repository_with_client()

    await DeactivateClient(repository)(client.id)
    assert repository.clients[client.id].active is False

    await ActivateClient(repository)(client.id)
    assert repository.clients[client.id].active is True


@pytest.mark.asyncio
async def test_hu04_desactivar_cliente_inexistente_falla() -> None:
    repository, _ = await _repository_with_client()

    with pytest.raises(ClientNotFoundError):
        await DeactivateClient(repository)(uuid4())
