"""Punto de entrada de la API de Darze.

`fastapi dev src/local_eventos/main.py` usa la variable `app` de este archivo.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import async_sessionmaker  # ← NUEVO

from local_eventos.modules.commercial.presentation import client_router  # ← NUEVO
from local_eventos.modules.commercial.presentation.errors import (  # ← NUEVO
    register_error_handlers as register_commercial_errors,
)
from local_eventos.shared.infrastructure.config import Settings
from local_eventos.shared.infrastructure.db import check_database, create_engine
from local_eventos.shared.presentation import health
from local_eventos.shared.presentation.health import ReadinessCheck

API_TITLE = "Darze API"
API_VERSION = "1.0.0"


def create_app(readiness_check: ReadinessCheck | None = None) -> FastAPI:
    """Arma la aplicación. En las pruebas se pasa `readiness_check` para no usar la base de datos.

    Sin `readiness_check`, la configuración y la conexión se crean al arrancar (lifespan),
    no al importar este archivo: así importar `main` no exige un `.env`.
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if readiness_check is not None:
            app.state.readiness_check = readiness_check
            yield
            return
        settings = Settings()  # los valores vienen del entorno (.env)
        engine = create_engine(settings.database_url)

        async def check() -> None:
            await check_database(engine)

        app.state.readiness_check = check
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)  # ← NUEVO
        yield
        await engine.dispose()

    app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=lifespan)
    app.include_router(health.router)
    app.include_router(client_router.router)  # ← NUEVO
    register_commercial_errors(app)  # ← NUEVO
    return app


app = create_app()
