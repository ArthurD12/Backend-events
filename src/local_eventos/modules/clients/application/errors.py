"""Errores de la capa de aplicación del módulo clients. `code` es estable para el frontend."""


class ClientApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class DuplicateDocumentError(ClientApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "client.document_duplicated",
            "Ya existe un cliente registrado con ese documento.",
        )


class ClientNotFoundError(ClientApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "client.not_found",
            "No se encontró un cliente con ese identificador.",
        )
