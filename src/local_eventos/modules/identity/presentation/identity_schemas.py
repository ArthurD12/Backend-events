"""Forma de los datos de identidad en la API (lo que envía y recibe el frontend).

Solo describen la forma: las reglas (correo válido, clave de 8 caracteres…) las aplica el
dominio, así hay una sola fuente de verdad y el mismo `code` de error en todos lados.
La contraseña nunca aparece en una respuesta.
"""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from local_eventos.modules.identity.application.ports.access_log_repository import (
    AccessLogEntry,
)
from local_eventos.modules.identity.application.use_cases.authentication import (
    ACCESS_TOKEN_TTL,
    IssuedTokens,
)
from local_eventos.modules.identity.application.use_cases.search_access_log import AccessLogPage
from local_eventos.modules.identity.domain.access_attempt import AccessResult
from local_eventos.modules.identity.domain.permissions import Permission, Role
from local_eventos.modules.identity.domain.user import User


class LoginIn(BaseModel):
    email: str
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class MeOut(BaseModel):
    """Perfil del usuario: el frontend muestra solo los módulos de `permissions` (CA-01.4)."""

    id: UUID
    name: str
    email: str
    role: Role
    permissions: list[Permission]

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            permissions=sorted(user.permissions),
        )


class TokenOut(BaseModel):
    access_token: str = Field(description="Va en `Authorization: Bearer ...`. Dura 15 minutos.")
    token_type: str = "bearer"
    expires_in: int = Field(description="Segundos que dura el access token")
    refresh_token: str = Field(
        description="Renueva el acceso en `POST /v1/auth/refresh`. Vence tras 30 min sin uso."
    )
    user: MeOut

    @classmethod
    def from_tokens(cls, tokens: IssuedTokens) -> Self:
        return cls(
            access_token=tokens.access_token,
            expires_in=int(ACCESS_TOKEN_TTL.total_seconds()),
            refresh_token=tokens.refresh_token,
            user=MeOut.from_user(tokens.user),
        )


class UserCreate(BaseModel):
    name: str
    email: str
    password: str
    role: Role
    active: bool = True


class UserUpdate(BaseModel):
    name: str
    email: str
    role: Role
    new_password: str | None = Field(
        default=None, description="Solo si el administrador asigna una contraseña nueva"
    )


class UserOut(BaseModel):
    id: UUID
    name: str
    email: str
    role: Role
    active: bool

    @classmethod
    def from_user(cls, user: User) -> Self:
        return cls(id=user.id, name=user.name, email=user.email, role=user.role, active=user.active)


class AccessLogEntryOut(BaseModel):
    id: int
    email: str = Field(description="Correo que se escribió al intentar entrar")
    user_id: UUID | None
    user_name: str | None
    result: AccessResult
    occurred_at: datetime

    @classmethod
    def from_entry(cls, entry: AccessLogEntry) -> Self:
        return cls(
            id=entry.id,
            email=entry.email,
            user_id=entry.user_id,
            user_name=entry.user_name,
            result=entry.result,
            occurred_at=entry.occurred_at,
        )


class AccessLogPageOut(BaseModel):
    items: list[AccessLogEntryOut]
    total: int
    page: int
    page_size: int

    @classmethod
    def from_page(cls, page: AccessLogPage) -> Self:
        return cls(
            items=[AccessLogEntryOut.from_entry(entry) for entry in page.items],
            total=page.total,
            page=page.page,
            page_size=page.page_size,
        )
