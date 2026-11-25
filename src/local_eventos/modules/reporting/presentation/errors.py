"""Traduce los errores de reportes a respuestas HTTP con su `code` estable."""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from local_eventos.modules.reporting.application.errors import (
    ReportEventNotFoundError,
    ReportingError,
)
from local_eventos.shared.presentation.problems import problem_response


async def _reporting_error(request: Request, error: Exception) -> JSONResponse:
    assert isinstance(error, ReportingError)
    status = 404 if isinstance(error, ReportEventNotFoundError) else 422
    return problem_response(status=status, title="Consulta inválida", code=error.code,
                            detail=str(error))  # fmt: skip


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ReportingError, _reporting_error)
