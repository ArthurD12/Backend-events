"""Pruebas de la búsqueda de clientes (HU04). Sin base de datos."""

import pytest

from local_eventos.modules.clients.application.use_cases.search_clients import (
    MAX_RESULTS,
    SearchClients,
    SearchClientsQuery,
)
from local_eventos.modules.clients.domain.client import Client, DocumentType

from .fakes import InMemoryClientRepository


async def _repository() -> InMemoryClientRepository:
    repository = InMemoryClientRepository()
    for name, document_type, number, phone in [
        ("Familia Quispe Mamani", DocumentType.DNI, "44125896", "987654321"),
        ("Empresa FAMAQ S.A.C.", DocumentType.RUC, "20547896321", "014567890"),
        ("Colegio San Martín", DocumentType.RUC, "20125478963", "016543210"),
    ]:
        await repository.add(
            Client.register(
                name=name,
                document_type=document_type,
                document_number=number,
                phone=phone,
            )
        )
    return repository


async def _names(
    repository: InMemoryClientRepository, query: SearchClientsQuery
) -> list[str]:
    return [client.name for client in await SearchClients(repository)(query)]


@pytest.mark.asyncio
async def test_hu04_busca_por_parte_del_nombre_sin_importar_mayusculas() -> None:
    repository = await _repository()

    assert await _names(repository, SearchClientsQuery(text="quispe")) == [
        "Familia Quispe Mamani"
    ]


@pytest.mark.asyncio
async def test_hu04_busca_por_documento() -> None:
    repository = await _repository()

    assert await _names(repository, SearchClientsQuery(text="20547896321")) == [
        "Empresa FAMAQ S.A.C."
    ]


@pytest.mark.asyncio
async def test_hu04_busca_por_telefono_aunque_se_escriba_con_espacios() -> None:
    repository = await _repository()

    assert await _names(repository, SearchClientsQuery(text="987 654")) == [
        "Familia Quispe Mamani"
    ]


@pytest.mark.asyncio
async def test_hu04_texto_vacio_lista_todos_ordenados_por_nombre() -> None:
    repository = await _repository()

    assert await _names(repository, SearchClientsQuery()) == [
        "Colegio San Martín",
        "Empresa FAMAQ S.A.C.",
        "Familia Quispe Mamani",
    ]


@pytest.mark.asyncio
async def test_hu04_excluye_inactivos_salvo_que_se_pidan() -> None:
    repository = await _repository()
    inactive = next(
        c for c in repository.clients.values() if c.name.startswith("Colegio")
    )
    inactive.deactivate()

    assert "Colegio San Martín" not in await _names(repository, SearchClientsQuery())
    assert "Colegio San Martín" in await _names(
        repository, SearchClientsQuery(include_inactive=True)
    )


@pytest.mark.asyncio
async def test_hu04_limita_la_cantidad_de_resultados() -> None:
    repository = InMemoryClientRepository()
    for i in range(MAX_RESULTS + 5):
        await repository.add(
            Client.register(
                name=f"Cliente {i:03d}",
                document_type=DocumentType.DNI,
                document_number=f"{10000000 + i}",
                phone="987654321",
            )
        )

    assert len(await SearchClients(repository)(SearchClientsQuery())) == MAX_RESULTS
