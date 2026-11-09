"""Errores del dominio del catálogo (HU06)."""


class CatalogValidationError(ValueError):
    """Dato del catálogo inválido. `code` es estable para que el frontend lo traduzca."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
