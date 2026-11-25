"""Errores de la capa de aplicación de personal. `code` es estable para el frontend."""

from local_eventos.modules.staff.domain.period import Period


class StaffApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class WorkerNotFoundError(StaffApplicationError):
    def __init__(self) -> None:
        super().__init__("staff.worker_not_found", "No se encontró el trabajador.")


class DocumentTakenError(StaffApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "staff.document_taken", "Ya hay un trabajador registrado con ese documento."
        )


class UnavailabilityNotFoundError(StaffApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "staff.unavailability_not_found", "No se encontró ese periodo de indisponibilidad."
        )


class EventNotFoundError(StaffApplicationError):
    def __init__(self) -> None:
        super().__init__("staff.event_not_found", "No se encontró el evento.")


class EventNotAssignableError(StaffApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "staff.event_not_assignable",
            "Solo se asigna personal a un evento programado, confirmado o en ejecución.",
        )


class WorkerInactiveError(StaffApplicationError):
    def __init__(self) -> None:
        super().__init__("staff.worker_inactive", "El trabajador está inactivo.")


class WorkerUnavailableError(StaffApplicationError):
    def __init__(self, period: Period) -> None:
        super().__init__(
            "staff.worker_unavailable",
            f"El trabajador marcó que no está disponible el {period.describe()}.",
        )


class AssignmentOverlapError(StaffApplicationError):
    """CA-17.4: dice con qué evento y horario choca. Sin datos si lo detectó la base (raro)."""

    def __init__(self, event_code: str | None = None, period: Period | None = None) -> None:
        message = "El trabajador ya tiene una asignación que se cruza con ese horario."
        if event_code is not None and period is not None:
            message = f"El trabajador ya está asignado a {event_code} el {period.describe()}."
        super().__init__("staff.assignment_overlap", message)
        self.event_code = event_code
        self.period = period


class AssignmentNotFoundError(StaffApplicationError):
    def __init__(self) -> None:
        super().__init__("staff.assignment_not_found", "No se encontró la asignación.")
