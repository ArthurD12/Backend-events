"""Traduce los errores del personal a respuestas HTTP con su `code` estable (plan §5.3).

Los datos inválidos del dominio responden 422 con `staff.*`; un documento repetido,
409 con `staff.document_duplicated`; un id inexistente, 404 con `staff.not_found`.
Todas las respuestas usan el formato Problem Details del resto de la API.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.staff.application.errors import (
    DuplicateDocumentError,
    StaffApplicationError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.shared.presentation.problems import problem_response


async def _validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StaffValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _not_found_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, WorkerNotFoundError)
    return problem_response(status=404, title="No encontrado", code=error.code, detail=str(error))


async def _duplicate_document_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, DuplicateDocumentError)
    return problem_response(
        status=409,
        title="Operación no permitida",
        code=error.code,
        detail=str(error),
    )


async def _application_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StaffApplicationError)
    return problem_response(
        status=422, title="Operación no permitida", code=error.code, detail=str(error)
    )


def register_error_handlers(app: FastAPI) -> None:
    """Registra los manejadores de personal en la aplicación FastAPI."""
    app.add_exception_handler(StaffValidationError, _validation_error)
    app.add_exception_handler(DuplicateDocumentError, _duplicate_document_error)
    app.add_exception_handler(WorkerNotFoundError, _not_found_error)
    app.add_exception_handler(StaffApplicationError, _application_error)
