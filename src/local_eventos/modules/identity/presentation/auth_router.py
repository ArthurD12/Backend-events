"""Endpoints de sesión (HU01). Traducen HTTP ⇄ caso de uso; sin reglas de negocio."""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from local_eventos.modules.identity.application.use_cases.authentication import (
    Login,
    Logout,
    RefreshSession,
)
from local_eventos.modules.identity.presentation.dependencies import (
    AccessLog,
    CurrentUser,
    Hasher,
    Now,
    Sessions,
    Tokens,
    Users,
    get_current_user,
)
from local_eventos.modules.identity.presentation.identity_schemas import (
    LoginIn,
    MeOut,
    RefreshIn,
    TokenOut,
)
from local_eventos.shared.presentation.problems import Problem, problem_response

router = APIRouter(prefix="/v1/auth", tags=["sesión"])

_Responses = dict[int | str, dict[str, Any]]

_EXPIRED: _Responses = {401: {"model": Problem, "description": "`auth.session_expired`"}}


@router.post(
    "/login",
    operation_id="auth_login",
    response_model=TokenOut,
    responses={401: {"model": Problem, "description": "`auth.invalid_credentials`"}},
)
async def login(
    body: LoginIn,
    users: Users,
    sessions: Sessions,
    access_log: AccessLog,
    hasher: Hasher,
    tokens: Tokens,
    clock: Now,
) -> TokenOut | JSONResponse:
    """Inicia sesión con correo y contraseña. Cada intento queda en el historial de accesos.

    Si se rechaza, la respuesta no dice si falló el correo, la contraseña o el estado de la
    cuenta. Se responde (no se lanza un error) para que el intento fallido sí se guarde.
    """
    issued = await Login(users, sessions, access_log, hasher, tokens, clock)(
        body.email, body.password
    )
    if issued is None:
        return problem_response(
            status=status.HTTP_401_UNAUTHORIZED,
            title="Acceso rechazado",
            code="auth.invalid_credentials",
            detail="Correo o contraseña incorrectos, o la cuenta está desactivada.",
        )
    return TokenOut.from_tokens(issued)


@router.post("/refresh", operation_id="auth_refresh", responses=_EXPIRED)
async def refresh(
    body: RefreshIn, users: Users, sessions: Sessions, tokens: Tokens, clock: Now
) -> TokenOut:
    """Entrega un access token nuevo. El refresh token cambia en cada uso: guarda el nuevo."""
    return TokenOut.from_tokens(
        await RefreshSession(users, sessions, tokens, clock)(body.refresh_token)
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, operation_id="auth_logout")
async def logout(body: RefreshIn, sessions: Sessions, clock: Now) -> None:
    """Cierra la sesión: el refresh token deja de servir. Cerrar dos veces no es error."""
    await Logout(sessions, clock)(body.refresh_token)


@router.get("/me", operation_id="auth_me", responses=_EXPIRED)
async def me(user: Annotated[CurrentUser, Depends(get_current_user)], users: Users) -> MeOut:
    """Perfil y permisos del usuario actual: con ellos el frontend arma el menú (CA-01.4)."""
    found = await users.get(user.id)
    assert found is not None  # get_current_user ya verificó que existe y está activo
    return MeOut.from_user(found)
