"""Traduce los errores de clientes y cotizaciones a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.commercial.application.clients.errors import (
    ClientApplicationError,
    ClientNotFoundError,
    DuplicateDocumentError,
)
from local_eventos.modules.commercial.application.quotes.errors import (
    QuoteApplicationError,
    QuoteClientInactiveError,
    QuoteClientNotFoundError,
    QuoteNotFoundError,
    QuotePdfNotAvailableError,
    QuoteServiceInactiveError,
    QuoteServiceNotFoundError,
)
from local_eventos.modules.commercial.domain.clients.client import ClientValidationError
from local_eventos.modules.commercial.domain.quotes.quote import (
    QuoteRuleError,
    QuoteValidationError,
)
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


_QUOTE_STATUS = {
    QuoteNotFoundError: 404,
    QuoteClientNotFoundError: 404,
    QuoteServiceNotFoundError: 404,
    QuoteClientInactiveError: 409,
    QuoteServiceInactiveError: 409,
    QuotePdfNotAvailableError: 409,
}


async def _quote_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, QuoteValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _quote_rule_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, QuoteRuleError)
    return problem_response(
        status=409, title="Operación no permitida", code=error.code, detail=str(error)
    )


async def _quote_application_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, QuoteApplicationError)
    status = _QUOTE_STATUS.get(type(error), 422)
    return problem_response(
        status=status, title="Operación no permitida", code=error.code, detail=str(error)
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ClientValidationError, _client_validation_error)
    app.add_exception_handler(ClientApplicationError, _client_application_error)
    app.add_exception_handler(QuoteValidationError, _quote_validation_error)
    app.add_exception_handler(QuoteRuleError, _quote_rule_error)
    app.add_exception_handler(QuoteApplicationError, _quote_application_error)
