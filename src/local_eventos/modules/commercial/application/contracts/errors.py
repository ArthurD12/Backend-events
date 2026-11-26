"""Errores de la capa de aplicación de contratos. `code` es estable para el frontend."""


class ContractApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ContractNotFoundError(ContractApplicationError):
    def __init__(self) -> None:
        super().__init__("contract.not_found", "No se encontró el contrato.")


class ContractAlreadyExistsError(ContractApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "contract.already_exists",
            "Esta cotización ya tiene un contrato. Para otro, crea una cotización nueva.",
        )


class ContractQuoteNotFoundError(ContractApplicationError):
    def __init__(self) -> None:
        super().__init__("contract.quote_not_found", "No se encontró la cotización.")


class ContractPdfNotAvailableError(ContractApplicationError):
    def __init__(self) -> None:
        super().__init__(
            "contract.pdf_not_available",
            "Un contrato anulado no se descarga en PDF.",
        )
