"""Punto de entrada de la API de Darze.

`fastapi dev src/local_eventos/main.py` usa la variable `app` de este archivo.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import async_sessionmaker

from local_eventos.modules.catalog.presentation import category_router, service_router
from local_eventos.modules.catalog.presentation.errors import (
    register_error_handlers as register_catalog_errors,
)
from local_eventos.modules.commercial.presentation import (
    activity_router,
    client_router,
    contract_router,
    event_router,
    payment_router,
    quote_router,
)
from local_eventos.modules.commercial.presentation.errors import (
    register_error_handlers as register_commercial_errors,
)
from local_eventos.modules.identity.presentation import (
    access_log_router,
    auth_router,
    user_router,
)
from local_eventos.modules.identity.presentation.errors import (
    register_error_handlers as register_identity_errors,
)
from local_eventos.modules.inventory.presentation import (
    movement_router as inventory_movement_router,
)
from local_eventos.modules.inventory.presentation import product_router
from local_eventos.modules.inventory.presentation.errors import (
    register_error_handlers as register_inventory_errors,
)
from local_eventos.modules.ledger.presentation import movement_router
from local_eventos.modules.ledger.presentation.errors import (
    register_error_handlers as register_ledger_errors,
)
from local_eventos.modules.reporting.presentation import dashboard_router
from local_eventos.modules.staff.presentation import worker_router
from local_eventos.modules.staff.presentation.errors import (
    register_error_handlers as register_staff_errors,
)
from local_eventos.shared.infrastructure.config import CorsSettings, Settings
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
        app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)
        yield
        await engine.dispose()

    app = FastAPI(title=API_TITLE, version=API_VERSION, lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CorsSettings().cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    app.include_router(auth_router.router)
    app.include_router(user_router.router)
    app.include_router(access_log_router.router)
    app.include_router(client_router.router)
    app.include_router(quote_router.router)
    app.include_router(contract_router.router)
    app.include_router(event_router.router)
    app.include_router(payment_router.router)
    app.include_router(movement_router.router)
    app.include_router(activity_router.router)
    app.include_router(dashboard_router.router)
    app.include_router(finance_router.router)
    app.include_router(category_router.router)
    app.include_router(service_router.router)
    app.include_router(worker_router.router)
    register_identity_errors(app)
    register_commercial_errors(app)
    register_ledger_errors(app)
    register_catalog_errors(app)
    register_staff_errors(app)
    return app


app = create_app()
