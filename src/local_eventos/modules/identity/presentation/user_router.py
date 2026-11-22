"""Endpoints de gestión de usuarios (HU02). Solo para el permiso `users:manage`."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, status

from local_eventos.modules.identity.application.use_cases.manage_users import (
    ActivateUser,
    CreateUser,
    CreateUserCommand,
    DeactivateUser,
    GetUser,
    ListUsers,
    UpdateUser,
    UpdateUserCommand,
)
from local_eventos.modules.identity.domain.permissions import Permission
from local_eventos.modules.identity.presentation.dependencies import (
    Hasher,
    Now,
    Sessions,
    Users,
    require_permission,
)
from local_eventos.modules.identity.presentation.identity_schemas import (
    UserCreate,
    UserOut,
    UserUpdate,
)
from local_eventos.shared.presentation.problems import Problem

router = APIRouter(
    prefix="/v1/users",
    tags=["usuarios"],
    dependencies=[Depends(require_permission(Permission.USERS_MANAGE))],
    responses={
        401: {"model": Problem, "description": "`auth.not_authenticated`, `auth.session_expired`"},
        403: {"model": Problem, "description": "`auth.forbidden`"},
    },
)

_Responses = dict[int | str, dict[str, Any]]

_NOT_FOUND: _Responses = {404: {"model": Problem, "description": "`user.not_found`"}}
_INVALID: _Responses = {
    422: {"model": Problem, "description": "Dato inválido: `user.password_too_short`, etc."}
}
_LAST_ADMIN: _Responses = {409: {"model": Problem, "description": "`user.last_admin`"}}


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    operation_id="users_create",
    responses={409: {"model": Problem, "description": "`user.email_duplicated`"}, **_INVALID},
)
async def create_user(body: UserCreate, users: Users, hasher: Hasher) -> UserOut:
    """Crea una cuenta personal. El correo no puede estar en otra cuenta."""
    user = await CreateUser(users, hasher)(
        CreateUserCommand(
            name=body.name,
            email=body.email,
            password=body.password,
            role=body.role,
            active=body.active,
        )
    )
    return UserOut.from_user(user)


@router.get("", operation_id="users_list")
async def list_users(users: Users, include_inactive: bool = False) -> list[UserOut]:
    """Usuarios ordenados por nombre."""
    found = await ListUsers(users)(include_inactive=include_inactive)
    return [UserOut.from_user(user) for user in found]


@router.get("/{user_id}", operation_id="users_get", responses=_NOT_FOUND)
async def get_user(user_id: UUID, users: Users) -> UserOut:
    return UserOut.from_user(await GetUser(users)(user_id))


@router.put(
    "/{user_id}",
    operation_id="users_update",
    responses={
        **_NOT_FOUND,
        **_INVALID,
        409: {"model": Problem, "description": "`user.email_duplicated`, `user.last_admin`"},
    },
)
async def update_user(
    user_id: UUID, body: UserUpdate, users: Users, sessions: Sessions, hasher: Hasher, clock: Now
) -> UserOut:
    """Modifica datos y rol. Con `new_password`, cambia la clave y cierra sus sesiones."""
    user = await UpdateUser(users, sessions, hasher, clock)(
        UpdateUserCommand(
            user_id=user_id,
            name=body.name,
            email=body.email,
            role=body.role,
            new_password=body.new_password,
        )
    )
    return UserOut.from_user(user)


@router.post(
    "/{user_id}/deactivate",
    operation_id="users_deactivate",
    responses={**_NOT_FOUND, **_LAST_ADMIN},
)
async def deactivate_user(user_id: UUID, users: Users, sessions: Sessions, clock: Now) -> UserOut:
    """Desactiva sin eliminar y cierra sus sesiones: deja de entrar al instante (RN02)."""
    return UserOut.from_user(await DeactivateUser(users, sessions, clock)(user_id))


@router.post("/{user_id}/activate", operation_id="users_activate", responses=_NOT_FOUND)
async def activate_user(user_id: UUID, users: Users) -> UserOut:
    return UserOut.from_user(await ActivateUser(users)(user_id))
