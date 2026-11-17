"""Endpoints de clientes (HU04). Traducen HTTP ⇄ caso de uso; no contienen reglas de negocio.

Pendiente: corregir documento (RN03) necesita saber qué usuario corrige; se agrega con HU01.
"""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Query, status

from local_eventos.modules.commercial.application.clients.use_cases.change_client_status import (
    ActivateClient,
    DeactivateClient,
)
from local_eventos.modules.commercial.application.clients.use_cases.get_client import GetClient
from local_eventos.modules.commercial.application.clients.use_cases.register_client import (
    RegisterClient,
    RegisterClientCommand,
)
from local_eventos.modules.commercial.application.clients.use_cases.search_clients import (
    SearchClients,
    SearchClientsQuery,
)
from local_eventos.modules.commercial.application.clients.use_cases.update_client_contact import (
    UpdateClientContact,
    UpdateClientContactCommand,
)
from local_eventos.modules.commercial.presentation.client_schemas import (
    ClientContactUpdate,
    ClientCreate,
    ClientOut,
)
from local_eventos.modules.commercial.presentation.dependencies import Clients
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(prefix="/v1/clients", tags=["clientes"])

_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`client.not_found`"}}
_INVALID: _Responses = {
    422: {"model": Problem, "description": "Dato inválido: `client.*_invalid`, etc."}
}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="clients_register",
    responses={409: {"model": Problem, "description": "`client.document_duplicated`"}, **_INVALID},
)
async def register_client(body: ClientCreate, clients: Clients) -> ClientOut:
    """Registra un cliente nuevo, activo. El documento (DNI o RUC) no puede repetirse."""
    client = await RegisterClient(clients)(
        RegisterClientCommand(
            name=body.name,
            document_type=body.document_type,
            document_number=body.document_number,
            phone=body.phone,
            email=body.email,
            address=body.address,
        )
    )
    return ClientOut.from_client(client)


@router.get("", operation_id="clients_search")
async def search_clients(
    clients: Clients,
    text: Annotated[str, Query(description="Parte del nombre, documento o teléfono")] = "",
    include_inactive: bool = False,
) -> list[ClientOut]:
    """Busca por nombre (sin distinguir tildes), documento o teléfono. Máximo 50 resultados."""
    found = await SearchClients(clients)(
        SearchClientsQuery(text=text, include_inactive=include_inactive)
    )
    return [ClientOut.from_client(client) for client in found]


@router.get("/{client_id}", operation_id="clients_get", responses=_NOT_FOUND)
async def get_client(client_id: UUID, clients: Clients) -> ClientOut:
    """Ficha completa de un cliente, activo o no."""
    return ClientOut.from_client(await GetClient(clients)(client_id))


@router.put(
    "/{client_id}",
    operation_id="clients_update_contact",
    responses={**_NOT_FOUND, **_INVALID},
)
async def update_client_contact(
    client_id: UUID, body: ClientContactUpdate, clients: Clients
) -> ClientOut:
    """Actualiza nombre y datos de contacto. El documento no se cambia aquí."""
    client = await UpdateClientContact(clients)(
        UpdateClientContactCommand(
            client_id=client_id,
            name=body.name,
            phone=body.phone,
            email=body.email,
            address=body.address,
        )
    )
    return ClientOut.from_client(client)


@router.post("/{client_id}/deactivate", operation_id="clients_deactivate", responses=_NOT_FOUND)
async def deactivate_client(client_id: UUID, clients: Clients) -> ClientOut:
    """Desactiva sin eliminar: sus cotizaciones y eventos se conservan (RN02)."""
    return ClientOut.from_client(await DeactivateClient(clients)(client_id))


@router.post("/{client_id}/activate", operation_id="clients_activate", responses=_NOT_FOUND)
async def activate_client(client_id: UUID, clients: Clients) -> ClientOut:
    """Vuelve a activar un cliente desactivado."""
    return ClientOut.from_client(await ActivateClient(clients)(client_id))
