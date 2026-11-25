"""Errores de la capa de aplicación de eventos. `code` es estable para el frontend."""


class EventApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EventNotFoundError(EventApplicationError):
    def __init__(self) -> None:
        super().__init__("event.not_found", "No se encontró el evento.")


class EventAlreadyExistsError(EventApplicationError):
    def __init__(self) -> None:
        super().__init__("event.already_exists", "Este contrato ya se convirtió en evento.")


class EventCoordinatorInvalidError(EventApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "event.coordinator_invalid",
            "El responsable debe ser un administrador o encargado de eventos activo.",
        )


class EventRangeInvalidError(EventApplicationError):
    def __init__(self, max_days: int) -> None:
        super().__init__(
            "event.range_invalid",
            f"El periodo debe terminar después de empezar y no superar {max_days} días.",
        )


class ActivityNotFoundError(EventApplicationError):
    def __init__(self) -> None:
        super().__init__("activity.not_found", "No se encontró la actividad.")


class ActivityResponsibleInvalidError(EventApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "activity.responsible_invalid",
            "El responsable debe ser un administrador o encargado de eventos activo.",
        )


class NoteNotFoundError(EventApplicationError):
    def __init__(self) -> None:
        super().__init__("note.not_found", "No se encontró la observación.")


class NoteNotAuthorError(EventApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "note.not_author", "Solo su autor o un administrador edita la observación."
        )
