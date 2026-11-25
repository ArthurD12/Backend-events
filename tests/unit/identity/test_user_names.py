"""Nombres de usuarios por ID para otros módulos (quién registró un pago), activos o no."""

from uuid import uuid4

from local_eventos.modules.identity.application.use_cases.user_names import UserNames
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.user import User

from .fakes import InMemoryUserRepository


async def test_devuelve_solo_los_pedidos_incluidos_los_inactivos() -> None:
    users = InMemoryUserRepository()
    active = User.create(name="Ana", email="ana@darze.pe", password_hash="x", role=Role.ADMIN)
    inactive = User.create(
        name="Luis", email="luis@darze.pe", password_hash="x", role=Role.EVENTS_MANAGER,
        active=False,
    )  # fmt: skip
    other = User.create(name="Eva", email="eva@darze.pe", password_hash="x", role=Role.ADMIN)
    for user in (active, inactive, other):
        await users.add(user)

    names = await UserNames(users)([active.id, inactive.id, uuid4()])

    assert names == {active.id: "Ana", inactive.id: "Luis"}
    assert await UserNames(users)([]) == {}
