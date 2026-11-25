"""Traduce los errores del dinero a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.ledger.application.errors import (
    LedgerApplicationError,
    MovementNotFoundError,
    PaymentNotFoundError,
)
from local_eventos.modules.ledger.domain.payment import LedgerRuleError, LedgerValidationError
from local_eventos.shared.presentation.problems import problem_response

_STATUS = {PaymentNotFoundError: 404, MovementNotFoundError: 404}


async def _ledger_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, LedgerValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _ledger_rule_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, LedgerRuleError)
    return problem_response(
        status=409, title="Operación no permitida", code=error.code, detail=str(error)
    )


async def _ledger_application_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, LedgerApplicationError)
    return problem_response(
        status=_STATUS.get(type(error), 409),
        title="Operación no permitida",
        code=error.code,
        detail=str(error),
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LedgerValidationError, _ledger_validation_error)
    app.add_exception_handler(LedgerRuleError, _ledger_rule_error)
    app.add_exception_handler(LedgerApplicationError, _ledger_application_error)
