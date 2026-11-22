"""Crea el primer administrador del sistema. Uso: `just create-admin`.

Se ejecuta una vez al instalar el sistema: sin un administrador nadie puede crear usuarios.
Pide nombre, correo y contraseña en la terminal; la contraseña no se muestra al escribirla.
"""

import asyncio
import getpass

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from local_eventos.modules.identity import composition
from local_eventos.modules.identity.application.use_cases.manage_users import (
    CreateUser,
    CreateUserCommand,
)
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.domain.user import User
from local_eventos.shared.infrastructure.config import Settings
from local_eventos.shared.infrastructure.db import create_engine


async def create_admin(
    sessions: async_sessionmaker[AsyncSession], *, name: str, email: str, password: str
) -> User:
    """Guarda un administrador activo con las mismas reglas que la API (correo único, clave)."""
    async with sessions.begin() as session:
        return await CreateUser(
            composition.user_repository(session), composition.password_hasher()
        )(CreateUserCommand(name=name, email=email, password=password, role=Role.ADMIN))


async def _main() -> None:
    name = input("Nombre del administrador: ")
    email = input("Correo: ")
    password = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
    if password != getpass.getpass("Repite la contraseña: "):
        raise SystemExit("Las contraseñas no coinciden. No se creó nada.")
    engine = create_engine(Settings().database_url)
    try:
        user = await create_admin(
            async_sessionmaker(engine, expire_on_commit=False),
            name=name,
            email=email,
            password=password,
        )
    except Exception as error:  # muestra el motivo (correo repetido, clave corta…) sin traza
        raise SystemExit(f"No se creó el administrador: {error}") from error
    finally:
        await engine.dispose()
    print(f"Administrador creado: {user.name} <{user.email}>")


if __name__ == "__main__":
    asyncio.run(_main())
