"""Traduce los errores de reportes a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.reporting.application.errors import (
    ReportEventNotFoundError,
    ReportingError,
    ReportUnavailableError,
)
from local_eventos.shared.presentation.problems import problem_response


async def _reporting_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ReportingError)
    if isinstance(error, ReportUnavailableError):
        return problem_response(status=503, title="Reporte no disponible", code=error.code,
                                detail=str(error))  # fmt: skip
    status = 404 if isinstance(error, ReportEventNotFoundError) else 422
    return problem_response(status=status, title="Consulta inválida", code=error.code,
                            detail=str(error))  # fmt: skip


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ReportingError, _reporting_error)
