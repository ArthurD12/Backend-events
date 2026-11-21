"""Forma de los datos de clientes en la API (lo que envía y recibe el frontend).

Solo describen la forma: las reglas (DNI de 8 dígitos, teléfono válido…) las aplica el
dominio, así hay una sola fuente de verdad y el mismo `code` de error en todos lados.
"""

from typing import Self
from uuid import UUID

from pydantic import BaseModel

from local_eventos.modules.commercial.domain.clients.client import Client, DocumentType


class ClientCreate(BaseModel):
    name: str
    document_type: DocumentType
    document_number: str
    phone: str
    email: str | None = None
    address: str | None = None


class ClientContactUpdate(BaseModel):
    name: str
    phone: str
    email: str | None = None
    address: str | None = None


class ClientOut(BaseModel):
    id: UUID
    name: str
    document_type: DocumentType
    document_number: str
    phone: str
    email: str | None
    address: str | None
    active: bool

    @classmethod
    def from_client(cls, client: Client) -> Self:
        return cls(
            id=client.id,
            name=client.name,
            document_type=client.document.type,
            document_number=client.document.number,
            phone=client.phone,
            email=client.email,
            address=client.address,
            active=client.active,
        )
