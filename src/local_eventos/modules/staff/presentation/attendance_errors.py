"""Traduce los errores de asistencia a respuestas HTTP con `code` estable (HU18, plan §4.3).

- 404: trabajador inexistente (`staff.worker_not_found`). El 404 de asignación
  (`staff.assignment_not_found`) lo registra `staff.presentation.errors` (HU17).
- 409: asignación anulada o aún no terminada (`staff.attendance_not_due`,
  `staff.attendance_assignment_cancelled`).
- 422: rango/paginación inválidos (`staff.attendance_date_range_invalid`) y los
  errores de dominio del estado/motivo con su propio `code`.

No existe `staff.event_not_found`: un evento huérfano se devuelve con los campos
en `null` (R-ATT-23). Todas las respuestas usan Problem Details.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.staff.application.attendance_errors import (
    AttendanceAssignmentCancelledError,
    AttendanceDateRangeInvalidError,
    AttendanceNotDueError,
    AttendanceWorkerNotFoundError,
)
from local_eventos.modules.staff.domain.attendance_errors import (
    AttendanceReasonRequiredError,
    AttendanceStatusInvalidError,
)
from local_eventos.shared.presentation.problems import problem_response

__all__ = ["register_error_handlers"]


def _not_found_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AttendanceWorkerNotFoundError)
    return problem_response(status=404, title="No encontrado", code=error.code, detail=str(error))


def _conflict_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, AttendanceNotDueError | AttendanceAssignmentCancelledError)
    return problem_response(
        status=409, title="Operación no permitida", code=error.code, detail=str(error)
    )


def _invalid_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(
        error,
        AttendanceDateRangeInvalidError
        | AttendanceStatusInvalidError
        | AttendanceReasonRequiredError,
    )
    return problem_response(status=422, title="Dato inválido", code=error.code, detail=str(error))


def register_error_handlers(app: FastAPI) -> None:
    """Registra los manejadores de asistencia en la aplicación FastAPI."""
    app.add_exception_handler(AttendanceWorkerNotFoundError, _not_found_error)
    app.add_exception_handler(AttendanceNotDueError, _conflict_error)
    app.add_exception_handler(AttendanceAssignmentCancelledError, _conflict_error)
    app.add_exception_handler(AttendanceDateRangeInvalidError, _invalid_error)
    app.add_exception_handler(AttendanceStatusInvalidError, _invalid_error)
    app.add_exception_handler(AttendanceReasonRequiredError, _invalid_error)
