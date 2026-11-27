"""Traduce los errores del personal a respuestas HTTP con su `code` estable (plan §5.3).

Los datos inválidos del dominio responden 422 con `staff.*`; un documento repetido,
409 con `staff.document_duplicated`; un id inexistente, 404 con `staff.not_found`.
Todas las respuestas usan el formato Problem Details del resto de la API.
"""

from fastapi import FastAPI, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.responses import Response

from local_eventos.modules.staff.application.errors import (
    AssignmentImmutableError,
    AssignmentNotFoundError,
    AssignmentOverlapError,
    DuplicateDocumentError,
    EventNotAssignableError,
    EventNotFoundError,
    StaffApplicationError,
    UnavailabilityCancelledError,
    UnavailabilityNotFoundError,
    WorkerHasFutureAssignmentsError,
    WorkerInactiveError,
    WorkerNotFoundError,
)
from local_eventos.modules.staff.domain.errors import StaffValidationError
from local_eventos.modules.staff.presentation.assignment_schemas import (
    AssignmentConflictOut,
    AssignmentProblem,
)
from local_eventos.shared.presentation.problems import problem_response


async def _validation_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, StaffValidationError)
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


async def _request_validation_error(request: Request, error: Exception) -> Response:
    assert isinstance(error, RequestValidationError)
    for item in error.errors():
        loc = item.get("loc", ())
        if item.get("type") == "string_too_long" and loc and loc[-1] == "function_description":
            return problem_response(
                status=422,
                title="Dato inválido",
                code="staff.function_description_too_long",
                detail="La descripción de la función no puede superar 120 caracteres.",
            )
    return await request_validation_exception_handler(request, error)


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


async def _assignment_not_found_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AssignmentNotFoundError)
    return problem_response(status=404, title="No encontrado", code=error.code, detail=str(error))


async def _event_not_found_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, EventNotFoundError)
    return problem_response(status=404, title="No encontrado", code=error.code, detail=str(error))


async def _unavailability_not_found_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, UnavailabilityNotFoundError)
    return problem_response(status=404, title="No encontrado", code=error.code, detail=str(error))


async def _unavailability_cancelled_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, UnavailabilityCancelledError)
    return problem_response(
        status=409, title="Operación no permitida", code=error.code, detail=str(error)
    )


async def _assignment_conflict_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(
        error,
        WorkerInactiveError
        | EventNotAssignableError
        | AssignmentImmutableError
        | WorkerHasFutureAssignmentsError,
    )
    return problem_response(
        status=409, title="Operación no permitida", code=error.code, detail=str(error)
    )


async def _assignment_overlap_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AssignmentOverlapError)
    problem = AssignmentProblem(
        title="Conflicto de horario",
        status=409,
        code=error.code,
        detail=str(error),
        conflicts=[
            AssignmentConflictOut(
                event_code=conflict.event_code,
                event_date=conflict.event_date,
                start_time=conflict.start_time,
                end_time=conflict.end_time,
            )
            for conflict in error.conflicts
        ],
    )
    return JSONResponse(
        status_code=409,
        content=problem.model_dump(mode="json"),
        media_type="application/problem+json",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Registra los manejadores de personal en la aplicación FastAPI."""
    app.add_exception_handler(StaffValidationError, _validation_error)
    app.add_exception_handler(RequestValidationError, _request_validation_error)
    app.add_exception_handler(DuplicateDocumentError, _duplicate_document_error)
    app.add_exception_handler(WorkerNotFoundError, _not_found_error)
    app.add_exception_handler(AssignmentNotFoundError, _assignment_not_found_error)
    app.add_exception_handler(EventNotFoundError, _event_not_found_error)
    app.add_exception_handler(UnavailabilityNotFoundError, _unavailability_not_found_error)
    app.add_exception_handler(UnavailabilityCancelledError, _unavailability_cancelled_error)
    app.add_exception_handler(WorkerInactiveError, _assignment_conflict_error)
    app.add_exception_handler(EventNotAssignableError, _assignment_conflict_error)
    app.add_exception_handler(AssignmentImmutableError, _assignment_conflict_error)
    app.add_exception_handler(WorkerHasFutureAssignmentsError, _assignment_conflict_error)
    app.add_exception_handler(AssignmentOverlapError, _assignment_overlap_error)
    app.add_exception_handler(StaffApplicationError, _application_error)
