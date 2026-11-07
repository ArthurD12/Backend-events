"""Pruebas de la corrección de documento con auditoría (HU04, RN03). Sin base de datos."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from local_eventos.modules.clients.application.errors import (
    ClientNotFoundError,
    DocumentUnchangedError,
    DuplicateDocumentError,
)
from local_eventos.modules.clients.application.use_cases.correct_client_document import (
    CorrectClientDocument,
    CorrectClientDocumentCommand,
)
from local_eventos.modules.clients.domain.client import (
    Client,
    ClientValidationError,
    DocumentType,
)

from .fakes import InMemoryClientRepository

FIXED_NOW = datetime(2026, 11, 7, 15, 30, tzinfo=UTC)
USER_ID = uuid4()


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


def _command(
    client: Client, number: str = "44125869", reason: str = "Error de digitación"
) -> CorrectClientDocumentCommand:
    return CorrectClientDocumentCommand(
        client_id=client.id,
        document_type=DocumentType.DNI,
        document_number=number,
        reason=reason,
        corrected_by=USER_ID,
    )


def _use_case(repository: InMemoryClientRepository) -> CorrectClientDocument:
    return CorrectClientDocument(repository, now=lambda: FIXED_NOW)


@pytest.mark.asyncio
async def test_hu04_corrige_documento_y_registra_auditoria() -> None:
    repository, client = await _repository_with_client()

    await _use_case(repository)(_command(client))

    assert repository.clients[client.id].document.number == "44125869"
    [correction] = repository.corrections
    assert correction.previous.number == "44125896"
    assert correction.new.number == "44125869"
    assert correction.reason == "Error de digitación"
    assert correction.corrected_by == USER_ID
    assert correction.corrected_at == FIXED_NOW


@pytest.mark.asyncio
async def test_hu04_no_corrige_a_un_documento_de_otro_cliente() -> None:
    repository, client = await _repository_with_client()
    other = Client.register(
        name="Rosa Vargas Flores",
        document_type=DocumentType.DNI,
        document_number="44125869",
        phone="912345678",
    )
    await repository.add(other)

    with pytest.raises(DuplicateDocumentError):
        await _use_case(repository)(_command(client))

    assert repository.clients[client.id].document.number == "44125896"
    assert repository.corrections == []


@pytest.mark.asyncio
async def test_hu04_rechaza_documento_igual_al_actual() -> None:
    repository, client = await _repository_with_client()

    with pytest.raises(DocumentUnchangedError):
        await _use_case(repository)(_command(client, number="44125896"))

    assert repository.corrections == []


@pytest.mark.asyncio
async def test_hu04_correccion_sin_motivo_no_deja_rastro() -> None:
    repository, client = await _repository_with_client()

    with pytest.raises(ClientValidationError):
        await _use_case(repository)(_command(client, reason="   "))

    assert repository.clients[client.id].document.number == "44125896"
    assert repository.corrections == []


@pytest.mark.asyncio
async def test_hu04_corregir_cliente_inexistente_falla() -> None:
    repository, _ = await _repository_with_client()
    ghost = Client.register(
        name="Nadie",
        document_type=DocumentType.DNI,
        document_number="11111111",
        phone="912345678",
    )

    with pytest.raises(ClientNotFoundError):
        await _use_case(repository)(_command(ghost))
