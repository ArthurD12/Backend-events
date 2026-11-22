"""Iniciar, renovar y cerrar sesión, con su registro en el historial (HU01, HU03)."""

from dataclasses import dataclass

import pytest

from local_eventos.modules.identity.application.errors import (
    NotAuthenticatedError,
    SessionExpiredError,
)
from local_eventos.modules.identity.application.use_cases.authentication import (
    AuthenticateAccessToken,
    Login,
    Logout,
    RefreshSession,
)
from local_eventos.modules.identity.domain.access_attempt import AccessResult
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.user import User

from .fakes import (
    FakeClock,
    FakePasswordHasher,
    FakeTokenIssuer,
    InMemoryAccessLogRepository,
    InMemorySessionRepository,
    InMemoryUserRepository,
)

PASSWORD = "clave-segura"


@dataclass
class World:
    users: InMemoryUserRepository
    sessions: InMemorySessionRepository
    log: InMemoryAccessLogRepository
    clock: FakeClock
    tokens: FakeTokenIssuer
    ana: User

    def login(self) -> Login:
        return Login(
            self.users, self.sessions, self.log, FakePasswordHasher(), self.tokens, self.clock
        )

    def refresh(self) -> RefreshSession:
        return RefreshSession(self.users, self.sessions, self.tokens, self.clock)

    def authenticate(self) -> AuthenticateAccessToken:
        return AuthenticateAccessToken(self.users, self.tokens)


@pytest.fixture
async def world() -> World:
    users = InMemoryUserRepository()
    clock = FakeClock()
    ana = User.create(
        name="Ana Torres",
        email="ana@darze.pe",
        password_hash=FakePasswordHasher().hash(PASSWORD),
        role=Role.EVENTS_MANAGER,
    )
    await users.add(ana)
    return World(
        users,
        InMemorySessionRepository(),
        InMemoryAccessLogRepository(),
        clock,
        FakeTokenIssuer(clock),
        ana,
    )


async def test_ca01_1_entra_con_credenciales_validas(world: World) -> None:
    issued = await world.login()(" ANA@darze.pe ", PASSWORD)

    assert issued is not None
    assert issued.user.id == world.ana.id
    assert (await world.authenticate()(issued.access_token)).id == world.ana.id
    assert [a.result for a in world.log.attempts] == [AccessResult.SUCCESS]


@pytest.mark.parametrize(
    ("email", "password"),
    [("ana@darze.pe", "equivocada"), ("nadie@darze.pe", PASSWORD), ("no-es-correo", PASSWORD)],
)
async def test_ca01_2_credenciales_incorrectas_rechazan_y_se_registran(
    world: World, email: str, password: str
) -> None:
    assert await world.login()(email, password) is None

    [attempt] = world.log.attempts
    assert attempt.result is AccessResult.INVALID_CREDENTIALS
    assert attempt.email == email
    assert world.sessions.sessions == {}


async def test_ca01_3_usuario_inactivo_no_entra_y_queda_el_motivo(world: World) -> None:
    world.ana.deactivate()
    await world.users.update(world.ana)

    assert await world.login()("ana@darze.pe", PASSWORD) is None
    assert world.log.attempts[0].result is AccessResult.INACTIVE_USER
    assert world.log.attempts[0].user_id == world.ana.id


async def test_ca03_1_registra_usuario_fecha_y_resultado(world: World) -> None:
    await world.login()("ana@darze.pe", PASSWORD)

    [attempt] = world.log.attempts
    assert attempt.user_id == world.ana.id
    assert attempt.occurred_at == world.clock.now()


async def test_ca01_6_renueva_y_rota_mientras_hay_actividad(world: World) -> None:
    issued = await world.login()("ana@darze.pe", PASSWORD)
    assert issued is not None

    world.clock.advance(minutes=25)
    renewed = await world.refresh()(issued.refresh_token)
    world.clock.advance(minutes=25)
    renewed_again = await world.refresh()(renewed.refresh_token)

    assert renewed_again.user.id == world.ana.id
    with pytest.raises(SessionExpiredError):
        await world.refresh()(issued.refresh_token)  # el token viejo ya no sirve


async def test_ca01_6_sesion_termina_tras_30_minutos_sin_actividad(world: World) -> None:
    issued = await world.login()("ana@darze.pe", PASSWORD)
    assert issued is not None

    world.clock.advance(minutes=30)

    with pytest.raises(SessionExpiredError):
        await world.refresh()(issued.refresh_token)


async def test_ca01_6_el_access_token_vence_a_los_15_minutos(world: World) -> None:
    issued = await world.login()("ana@darze.pe", PASSWORD)
    assert issued is not None

    world.clock.advance(minutes=15)

    with pytest.raises(SessionExpiredError):
        await world.authenticate()(issued.access_token)


async def test_ca01_5_cerrar_sesion_impide_renovar(world: World) -> None:
    issued = await world.login()("ana@darze.pe", PASSWORD)
    assert issued is not None

    await Logout(world.sessions, world.clock)(issued.refresh_token)
    await Logout(world.sessions, world.clock)(issued.refresh_token)  # dos veces no es error

    with pytest.raises(SessionExpiredError):
        await world.refresh()(issued.refresh_token)


async def test_ca02_4_usuario_desactivado_pierde_el_acceso_al_instante(world: World) -> None:
    issued = await world.login()("ana@darze.pe", PASSWORD)
    assert issued is not None

    world.ana.deactivate()
    await world.users.update(world.ana)

    with pytest.raises(SessionExpiredError):
        await world.authenticate()(issued.access_token)
    with pytest.raises(SessionExpiredError):
        await world.refresh()(issued.refresh_token)


async def test_ca01_7_sin_token_no_esta_autenticado(world: World) -> None:
    with pytest.raises(NotAuthenticatedError):
        await world.authenticate()(None)
    with pytest.raises(SessionExpiredError):
        await world.authenticate()("token-falso")
