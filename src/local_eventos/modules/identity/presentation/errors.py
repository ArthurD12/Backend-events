"""Traduce los errores de identidad a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.identity.application.errors import (
    DuplicateEmailError,
    ForbiddenError,
    IdentityApplicationError,
    LastAdminError,
    NotAuthenticatedError,
    SessionExpiredError,
    UserNotFoundError,
)
from local_eventos.modules.identity.domain.errors import UserValidationError
from local_eventos.shared.presentation.problems import problem_response

_STATUS = {
    NotAuthenticatedError: 401,
    SessionExpiredError: 401,
    ForbiddenError: 403,
    UserNotFoundError: 404,
    DuplicateEmailError: 409,
    LastAdminError: 409,
}


async def _user_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, UserValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _identity_application_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, IdentityApplicationError)
    status = _STATUS.get(type(error), 422)
    response = problem_response(
        status=status, title="Operación no permitida", code=error.code, detail=str(error)
    )
    if status == 401:
        response.headers["WWW-Authenticate"] = "Bearer"
    return response


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(UserValidationError, _user_validation_error)
    app.add_exception_handler(IdentityApplicationError, _identity_application_error)
