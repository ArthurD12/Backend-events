"""Endpoints de operación: `/health` (¿el proceso responde?) y `/ready` (¿puede atender?).

Quedan fuera de `/v1` porque no son parte del contrato con el frontend.
"""

from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

ReadinessCheck = Callable[[], Awaitable[None]]

router = APIRouter(tags=["operación"])


@router.get("/health", operation_id="health_live")
async def health() -> dict[str, str]:
    """Responde mientras el proceso esté vivo, aunque la base de datos no lo esté (CA-2)."""
    return {"status": "ok"}


@router.get("/ready", operation_id="health_ready")
async def ready(request: Request) -> JSONResponse:
    """`200` si la base de datos responde (CA-3); `503` sin detalles del error si no (CA-4)."""
    check: ReadinessCheck = request.app.state.readiness_check
    try:
        await check()
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready"})
    return JSONResponse(status_code=200, content={"status": "ready"})
