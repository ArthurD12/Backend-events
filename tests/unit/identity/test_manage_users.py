"""Gestión de usuarios por el administrador (HU02) y último administrador (R-ID-4)."""

from datetime import timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.identity.application.errors import (
    DuplicateEmailError,
    LastAdminError,
    UserNotFoundError,
)
from local_eventos.modules.identity.application.use_cases.manage_users import (
    ActivateUser,
    CreateUser,
    CreateUserCommand,
    DeactivateUser,
    ListUsers,
    UpdateUser,
    UpdateUserCommand,
)
from local_eventos.modules.identity.domain.errors import UserValidationError
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.session import Session
from local_eventos.modules.identity.domain.user import User

from .fakes import FakeClock, FakePasswordHasher, InMemorySessionRepository, InMemoryUserRepository


def _command(**changes: object) -> CreateUserCommand:
    data: dict[str, object] = {
        "name": "Luis Quispe",
        "email": "luis@darze.pe",
        "password": "clave-segura",
        "role": Role.PURCHASING_MANAGER,
        **changes,
    }
    return CreateUserCommand(**data)  # type: ignore[arg-type]


async def _create(users: InMemoryUserRepository, **changes: object) -> User:
    return await CreateUser(users, FakePasswordHasher())(_command(**changes))


def _update(users: InMemoryUserRepository, sessions: InMemorySessionRepository) -> UpdateUser:
    return UpdateUser(users, sessions, FakePasswordHasher(), FakeClock())


async def test_ca02_1_crea_usuario_con_la_clave_cifrada() -> None:
    users = InMemoryUserRepository()

    user = await _create(users)

    saved = users.users[user.id]
    assert saved.password_hash == "hashed:clave-segura"
    assert saved.role is Role.PURCHASING_MANAGER


async def test_ca02_2_correo_repetido_sin_importar_mayusculas() -> None:
    users = InMemoryUserRepository()
    await _create(users)

    with pytest.raises(DuplicateEmailError):
        await _create(users, email="LUIS@darze.pe", name="Otro Luis")


async def test_r_id_1_no_crea_con_clave_corta() -> None:
    with pytest.raises(UserValidationError) as error:
        await _create(InMemoryUserRepository(), password="1234567")
    assert error.value.code == "user.password_too_short"


async def test_ca02_3_modifica_datos_y_rol() -> None:
    users, sessions = InMemoryUserRepository(), InMemorySessionRepository()
    user = await _create(users)

    updated = await _update(users, sessions)(
        UpdateUserCommand(
            user_id=user.id, name="Luis A. Quispe", email="luisq@darze.pe", role=Role.ADMIN
        )
    )

    assert (updated.name, updated.email, updated.role) == (
        "Luis A. Quispe",
        "luisq@darze.pe",
        Role.ADMIN,
    )
    assert users.users[user.id].password_hash == "hashed:clave-segura"


async def test_ca02_3_clave_nueva_cierra_sus_sesiones() -> None:
    users, sessions = InMemoryUserRepository(), InMemorySessionRepository()
    user = await _create(users)
    clock = FakeClock()
    session = Session.start(user_id=user.id, token_hash="abc", now=clock.now())
    await sessions.add(session)

    await _update(users, sessions)(
        UpdateUserCommand(
            user_id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            new_password="otra-clave-segura",
        )
    )

    assert users.users[user.id].password_hash == "hashed:otra-clave-segura"
    assert not sessions.sessions[session.id].is_usable(clock.now() + timedelta(seconds=1))


async def test_ca02_2_no_modifica_al_correo_de_otra_cuenta() -> None:
    users, sessions = InMemoryUserRepository(), InMemorySessionRepository()
    await _create(users, email="ana@darze.pe", name="Ana")
    luis = await _create(users)

    with pytest.raises(DuplicateEmailError):
        await _update(users, sessions)(
            UpdateUserCommand(user_id=luis.id, name="Luis", email="ANA@darze.pe", role=luis.role)
        )
    assert users.users[luis.id].email == "luis@darze.pe"


async def test_ca02_4_desactivar_cierra_sus_sesiones() -> None:
    users, sessions = InMemoryUserRepository(), InMemorySessionRepository()
    clock = FakeClock()
    user = await _create(users)
    session = Session.start(user_id=user.id, token_hash="abc", now=clock.now())
    await sessions.add(session)

    await DeactivateUser(users, sessions, clock)(user.id)

    assert users.users[user.id].active is False
    assert sessions.sessions[session.id].revoked_at == clock.now()


async def test_ca02_5_desactivado_sigue_existiendo_y_se_reactiva() -> None:
    users = InMemoryUserRepository()
    user = await _create(users)
    await DeactivateUser(users, InMemorySessionRepository(), FakeClock())(user.id)

    assert await ListUsers(users)() == []
    assert len(await ListUsers(users)(include_inactive=True)) == 1
    assert (await ActivateUser(users)(user.id)).active is True


async def test_r_id_4_no_desactiva_ni_degrada_al_ultimo_admin() -> None:
    users, sessions = InMemoryUserRepository(), InMemorySessionRepository()
    admin = await _create(users, role=Role.ADMIN, email="admin@darze.pe")

    with pytest.raises(LastAdminError):
        await DeactivateUser(users, sessions, FakeClock())(admin.id)
    with pytest.raises(LastAdminError):
        await _update(users, sessions)(
            UpdateUserCommand(
                user_id=admin.id, name=admin.name, email=admin.email, role=Role.EVENTS_MANAGER
            )
        )


async def test_r_id_4_con_otro_admin_activo_si_se_puede() -> None:
    users, sessions = InMemoryUserRepository(), InMemorySessionRepository()
    admin = await _create(users, role=Role.ADMIN, email="admin@darze.pe")
    await _create(users, role=Role.ADMIN, email="admin2@darze.pe")

    assert (await DeactivateUser(users, sessions, FakeClock())(admin.id)).active is False


async def test_usuario_inexistente_responde_not_found() -> None:
    with pytest.raises(UserNotFoundError):
        await ActivateUser(InMemoryUserRepository())(uuid4())
