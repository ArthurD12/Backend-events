"""Respuestas de error con el formato Problem Details (RFC 9457).

Todas las respuestas de error de la API tienen la misma forma, con un `code` de negocio estable
que el frontend usa para mostrar el mensaje (p. ej. `client.document_duplicated`).
"""

from fastapi.responses import JSONResponse
from pydantic import BaseModel


class Problem(BaseModel):
    """Error de negocio. `code` no cambia aunque cambie el texto de `detail`."""

    type: str = "about:blank"
    title: str
    status: int
    code: str
    detail: str


def problem_response(*, status: int, title: str, code: str, detail: str) -> JSONResponse:
    problem = Problem(title=title, status=status, code=code, detail=detail)
    return JSONResponse(
        status_code=status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )
