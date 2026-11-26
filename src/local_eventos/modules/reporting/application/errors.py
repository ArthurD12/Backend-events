"""Errores de la capa de aplicación de reportes. `code` es estable para el frontend."""


class ReportingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReportRangeInvalidError(ReportingError):
    def __init__(self, max_days: int) -> None:
        super().__init__(
            "report.range_invalid",
            f"El rango debe ir de una fecha a otra igual o posterior, de hasta {max_days} días.",
        )


class ReportEventNotFoundError(ReportingError):
    def __init__(self) -> None:
        super().__init__("event.not_found", "No se encontró el evento.")


class ReportUnavailableError(ReportingError):
    """El reporte depende de un módulo que aún no publica sus datos (responde 503)."""

    def __init__(self, what: str) -> None:
        super().__init__("report.unavailable", f"{what} todavía no está disponible.")
