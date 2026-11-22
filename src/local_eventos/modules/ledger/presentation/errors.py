"""Traduce los errores de datos de pagos a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.ledger.domain.payment import LedgerValidationError
from local_eventos.shared.presentation.problems import problem_response


async def _ledger_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, LedgerValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(LedgerValidationError, _ledger_validation_error)
