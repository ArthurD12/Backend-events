"""Traduce los errores de inventario a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.inventory.application.errors import InventoryNotFoundError
from local_eventos.modules.inventory.domain.errors import (
    InventoryRuleError,
    InventoryValidationError,
)
from local_eventos.shared.presentation.problems import problem_response


async def _validation(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, InventoryValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _rule(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, InventoryRuleError)
    return problem_response(
        status=409, title="Operación no permitida", code=error.code, detail=str(error)
    )


async def _not_found(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, InventoryNotFoundError)
    return problem_response(status=404, title="No encontrado", code=error.code, detail=str(error))


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(InventoryValidationError, _validation)
    app.add_exception_handler(InventoryRuleError, _rule)
    app.add_exception_handler(InventoryNotFoundError, _not_found)
