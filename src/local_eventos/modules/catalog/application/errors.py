"""Errores de la capa de aplicación del catálogo. `code` es estable para el frontend."""


class CatalogApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class CategoryNotFoundError(CatalogApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "catalog.category_not_found",
            "No se encontró una categoría con ese identificador.",
        )


class DuplicateCategoryNameError(CatalogApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "catalog.category_name_duplicated",
            "Ya existe una categoría con ese nombre.",
        )
