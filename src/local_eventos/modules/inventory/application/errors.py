"""Errores de la capa de aplicación de inventario. `code` es estable para el frontend."""

from local_eventos.modules.inventory.domain.errors import InventoryRuleError


class InventoryNotFoundError(Exception):
    """Responde 404."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ProductNotFoundError(InventoryNotFoundError):
    def __init__(self) -> None:
        super().__init__(
            "inventory.product_not_found", "No se encontró un producto con ese identificador."
        )


class EventNotFoundError(InventoryNotFoundError):
    def __init__(self) -> None:
        super().__init__("inventory.event_not_found", "No se encontró el evento.")


class ServiceNotFoundError(InventoryNotFoundError):
    def __init__(self) -> None:
        super().__init__("inventory.service_not_found", "No se encontró el servicio del catálogo.")


class ReservationNotFoundError(InventoryNotFoundError):
    def __init__(self) -> None:
        super().__init__(
            "inventory.reservation_not_found",
            "El evento no tiene una reserva vigente del producto.",
        )


class InsufficientAvailableError(InventoryRuleError):
    """CA-25.4: no se aparta más de lo disponible (stock menos reservas vigentes)."""

    def __init__(self, available: object) -> None:
        super().__init__(
            "inventory.insufficient_available",
            f"No hay suficiente disponible para reservar: solo hay {available}.",
        )


class CodeTakenError(InventoryRuleError):
    def __init__(self) -> None:
        super().__init__("inventory.code_taken", "Ya existe un producto con ese código.")


class ProductInactiveError(InventoryRuleError):
    def __init__(self) -> None:
        super().__init__(
            "inventory.product_inactive",
            "El producto está desactivado: actívalo para registrar entradas o salidas.",
        )


class EventNotAssignableError(InventoryRuleError):
    def __init__(self) -> None:
        super().__init__(
            "inventory.event_not_assignable",
            "Solo salen materiales para un evento programado, confirmado o en ejecución.",
        )


class ReturnExceedsError(InventoryRuleError):
    def __init__(self, at_event: object) -> None:
        super().__init__(
            "inventory.return_exceeds",
            f"No se puede devolver más de lo que salió para el evento: quedan {at_event}.",
        )


class WasteExceedsError(InventoryRuleError):
    def __init__(self, at_event: object) -> None:
        super().__init__(
            "inventory.waste_exceeds",
            f"La merma del evento no supera lo que salió y no volvió: quedan {at_event}.",
        )
