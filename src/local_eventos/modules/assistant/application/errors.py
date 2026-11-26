"""Errores del asistente. `code` es estable para el frontend."""


class AssistantError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AssistantUnavailableError(AssistantError):
    def __init__(self) -> None:
        super().__init__("assistant.unavailable", "El asistente no está disponible por ahora.")


class AssistantRateLimitedError(AssistantError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            "assistant.rate_limited",
            f"Llegaste al límite de {limit} preguntas por hora. Inténtalo más tarde.",
        )


class AssistantProviderError(AssistantError):
    """Falló el proveedor del modelo (límite, red o error del servicio)."""

    def __init__(self, message: str = "El proveedor del asistente no respondió.") -> None:
        super().__init__("assistant.provider_error", message)
