"""Errores de la capa de aplicación de ledger. `code` es estable para el frontend."""


class LedgerApplicationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PaymentNotFoundError(LedgerApplicationError):
    def __init__(self) -> None:
        super().__init__("payment.not_found", "No se encontró el pago.")


class PaymentAlreadyVoidedError(LedgerApplicationError):
    def __init__(self) -> None:
        super().__init__("payment.already_voided", "El pago ya está anulado.")


class MovementNotFoundError(LedgerApplicationError):
    def __init__(self) -> None:
        super().__init__("movement.not_found", "No se encontró el movimiento.")


class MovementAlreadyVoidedError(LedgerApplicationError):
    def __init__(self) -> None:
        super().__init__("movement.already_voided", "El movimiento ya está anulado.")
