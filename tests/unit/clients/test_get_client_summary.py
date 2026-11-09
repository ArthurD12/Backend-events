"""Pruebas de la consulta pública de clientes (HU04). Sin base de datos."""

from uuid import uuid4

import pytest

from local_eventos.modules.clients.application.use_cases.get_client_summary import (
    GetClientSummary,
)
from local_eventos.modules.clients.domain.client import Client, DocumentType
from local_eventos.modules.clients.public_api import ClientLookup, ClientSummary

from .fakes import InMemoryClientRepository


def _saved_client(repository: InMemoryClientRepository) -> Client:
    client = Client.register(
        name="Empresa FAMAQ S.A.C.",
        document_type=DocumentType.RUC,
        document_number="20547896321",
        phone="014567890",
        email="eventos@famaq.pe",
    )
    repository.clients[client.id] = client
    return client


@pytest.mark.asyncio
async def test_hu04_devuelve_el_resumen_del_cliente() -> None:
    repository = InMemoryClientRepository()
    client = _saved_client(repository)

    summary = await GetClientSummary(repository)(client.id)

    assert summary == ClientSummary(
        id=client.id,
        name="Empresa FAMAQ S.A.C.",
        document_type="RUC",
        document_number="20547896321",
        phone="014567890",
        email="eventos@famaq.pe",
        active=True,
    )


@pytest.mark.asyncio
async def test_hu04_cliente_inexistente_devuelve_none() -> None:
    summary = await GetClientSummary(InMemoryClientRepository())(uuid4())

    assert summary is None


@pytest.mark.asyncio
async def test_hu04_informa_si_el_cliente_esta_desactivado() -> None:
    repository = InMemoryClientRepository()
    client = _saved_client(repository)
    client.deactivate()

    summary = await GetClientSummary(repository)(client.id)

    assert summary is not None
    assert summary.active is False


@pytest.mark.asyncio
async def test_hu04_el_resumen_es_una_copia_de_solo_lectura() -> None:
    repository = InMemoryClientRepository()
    client = _saved_client(repository)
    lookup: ClientLookup = GetClientSummary(repository)

    summary = await lookup(client.id)
    client.update_contact(name="FAMAQ Eventos S.A.C.", phone="014567890")

    assert summary is not None
    assert summary.name == "Empresa FAMAQ S.A.C."
