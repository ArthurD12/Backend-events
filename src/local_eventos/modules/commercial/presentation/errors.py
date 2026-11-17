"""Traduce los errores de negocio de commercial a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.commercial.application.clients.errors import (
    ClientApplicationError,
    ClientNotFoundError,
    DuplicateDocumentError,
)
from local_eventos.modules.commercial.domain.clients.client import ClientValidationError
from local_eventos.shared.presentation.problems import problem_response

_STATUS = {ClientNotFoundError: 404, DuplicateDocumentError: 409}


async def _client_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ClientValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _client_application_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ClientApplicationError)
    status = _STATUS.get(type(error), 422)
    return problem_response(
        status=status, title="Operación no permitida", code=error.code, detail=str(error)
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ClientValidationError, _client_validation_error)
    app.add_exception_handler(ClientApplicationError, _client_application_error)
