"""Errores de la capa de aplicación de compras. `code` es estable para el frontend."""

from local_eventos.modules.purchasing.domain.errors import PurchasingRuleError


class PurchasingNotFoundError(Exception):
    """Responde 404."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class EventNotFoundError(PurchasingNotFoundError):
    def __init__(self) -> None:
        super().__init__("purchasing.event_not_found", "No se encontró el evento.")


class SupplierNotFoundError(PurchasingNotFoundError):
    def __init__(self) -> None:
        super().__init__("purchasing.supplier_not_found", "No se encontró el proveedor.")


class PurchaseNotFoundError(PurchasingNotFoundError):
    def __init__(self) -> None:
        super().__init__("purchasing.purchase_not_found", "No se encontró la compra.")


class DocumentTakenError(PurchasingRuleError):
    def __init__(self) -> None:
        super().__init__(
            "purchasing.document_taken", "Ya existe un proveedor registrado con ese documento."
        )


class SupplierInactiveError(PurchasingRuleError):
    def __init__(self) -> None:
        super().__init__(
            "purchasing.supplier_inactive", "El proveedor está desactivado: actívalo para ordenar."
        )
