"""Traduce los errores del asistente a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.assistant.application.errors import (
    AssistantError,
    AssistantProviderError,
    AssistantRateLimitedError,
    AssistantUnavailableError,
    QueryNotFoundError,
)
from local_eventos.shared.presentation.problems import problem_response


def problem_for(error: AssistantError) -> JSONResponse:
    if isinstance(error, AssistantUnavailableError):
        return problem_response(status=503, title="Asistente no disponible", code=error.code,
                                detail=str(error))  # fmt: skip
    if isinstance(error, AssistantRateLimitedError):
        return problem_response(status=429, title="Demasiadas preguntas", code=error.code,
                                detail=str(error))  # fmt: skip
    if isinstance(error, QueryNotFoundError):
        return problem_response(status=404, title="Consulta no encontrada", code=error.code,
                                detail=str(error))  # fmt: skip
    assert isinstance(error, AssistantProviderError)
    return problem_response(status=502, title="Falló el proveedor del asistente", code=error.code,
                            detail=str(error))  # fmt: skip


async def _assistant_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AssistantError)
    return problem_for(error)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AssistantError, _assistant_error)
