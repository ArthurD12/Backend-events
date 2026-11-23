"""Traduce los errores de negocio del catálogo a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.catalog.application.errors import (
    CatalogApplicationError,
    CategoryHasActiveServicesError,
    CategoryInactiveError,
    CategoryNotFoundError,
    DuplicateCategoryNameError,
    ServiceNotFoundError,
)
from local_eventos.modules.catalog.domain.errors import CatalogValidationError
from local_eventos.shared.presentation.problems import problem_response

_STATUS = {
    CategoryNotFoundError: 404,
    ServiceNotFoundError: 404,
    DuplicateCategoryNameError: 409,
    CategoryInactiveError: 409,
    CategoryHasActiveServicesError: 409,
}


async def _catalog_validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, CatalogValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _catalog_application_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, CatalogApplicationError)
    status = _STATUS.get(type(error), 422)
    return problem_response(
        status=status, title="Operación no permitida", code=error.code, detail=str(error)
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(CatalogValidationError, _catalog_validation_error)
    app.add_exception_handler(CatalogApplicationError, _catalog_application_error)
