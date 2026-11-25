"""Traduce los errores de compras a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.purchasing.application.errors import PurchasingNotFoundError
from local_eventos.modules.purchasing.domain.errors import (
    PurchasingRuleError,
    PurchasingValidationError,
)
from local_eventos.shared.presentation.problems import problem_response


async def _validation(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, PurchasingValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _rule(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, PurchasingRuleError)
    return problem_response(
        status=409, title="Operación no permitida", code=error.code, detail=str(error)
    )


async def _not_found(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, PurchasingNotFoundError)
    return problem_response(status=404, title="No encontrado", code=error.code, detail=str(error))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(PurchasingValidationError, _validation)
    app.add_exception_handler(PurchasingRuleError, _rule)
    app.add_exception_handler(PurchasingNotFoundError, _not_found)
