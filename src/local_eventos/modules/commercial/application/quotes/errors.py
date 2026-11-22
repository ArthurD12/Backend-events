"""Errores de la capa de aplicación de cotizaciones. `code` es estable para el frontend."""


class QuoteApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class QuoteNotFoundError(QuoteApplicationError):
    def __init__(self) -> None:
        super().__init__("quote.not_found", "No se encontró la cotización.")


class QuoteClientNotFoundError(QuoteApplicationError):
    def __init__(self) -> None:
        super().__init__("quote.client_not_found", "No se encontró el cliente.")


class QuoteClientInactiveError(QuoteApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "quote.client_inactive", "El cliente está desactivado: elige un cliente activo."
        )


class QuoteServiceNotFoundError(QuoteApplicationError):
    def __init__(self) -> None:
        super().__init__("quote.service_not_found", "No se encontró un servicio del catálogo.")


class QuoteServiceInactiveError(QuoteApplicationError):
    def __init__(self, name: str) -> None:
        super().__init__(
            "quote.service_inactive",
            f'El servicio "{name}" está desactivado: no se puede agregar a la cotización.',
        )


class QuotePdfNotAvailableError(QuoteApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "quote.pdf_not_available",
            "El PDF solo se descarga de una cotización enviada o aceptada. "
            "Si está en borrador, márcala como enviada primero.",
        )
