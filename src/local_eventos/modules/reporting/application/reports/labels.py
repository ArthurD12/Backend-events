"""Nombres en español de los valores fijos, tal como se ven en pantalla y en las descargas."""

from local_eventos.modules.commercial.public_api import EventStatus, EventType
from local_eventos.modules.inventory.public_api import Category, MovementKind, ProductKind, Unit
from local_eventos.modules.ledger.public_api import CashEntryKind, MovementCategory, PaymentKind
from local_eventos.modules.purchasing.public_api import PurchaseStatus

EVENT_STATUS = {
    EventStatus.SCHEDULED: "Programado",
    EventStatus.CONFIRMED: "Confirmado",
    EventStatus.IN_PROGRESS: "En ejecución",
    EventStatus.FINISHED: "Finalizado",
    EventStatus.CANCELLED: "Cancelado",
}
EVENT_TYPE = {
    EventType.WEDDING: "Matrimonio",
    EventType.BIRTHDAY: "Cumpleaños",
    EventType.QUINCEANERA: "Quinceañero",
    EventType.CORPORATE: "Corporativo",
    EventType.GRADUATION: "Promoción",
    EventType.OTHER: "Otro",
}
CASH_KIND = {
    CashEntryKind.CLIENT_PAYMENT: "Pago de cliente",
    CashEntryKind.REFUND: "Devolución",
    CashEntryKind.INCOME: "Ingreso",
    CashEntryKind.EXPENSE: "Egreso",
}
CASH_CATEGORY = {
    MovementCategory.SUPPLIES: "Insumos",
    MovementCategory.STAFF: "Personal",
    MovementCategory.TRANSPORT: "Transporte",
    MovementCategory.OTHER_EXPENSE: "Otros egresos",
    MovementCategory.OTHER_INCOME: "Otros ingresos",
}
PAYMENT_KIND = {
    PaymentKind.ADVANCE: "Adelanto",
    PaymentKind.INSTALLMENT: "Pago parcial",
    PaymentKind.REFUND: "Devolución",
}
PRODUCT_CATEGORY = {
    Category.SUPPLIES: "Insumos",
    Category.BEVERAGES: "Bebidas",
    Category.DINNERWARE: "Vajilla",
    Category.GLASSWARE: "Cristalería",
    Category.CUTLERY: "Cubiertos",
    Category.LINENS: "Mantelería",
    Category.FURNITURE: "Mobiliario",
    Category.DISPOSABLES: "Descartables",
    Category.CLEANING: "Limpieza",
    Category.OTHER: "Otros",
}
UNIT = {
    Unit.UNIT: "Unidad",
    Unit.KG: "kg",
    Unit.G: "g",
    Unit.LITER: "Litro",
    Unit.ML: "ml",
    Unit.DOZEN: "Docena",
    Unit.PACKAGE: "Paquete",
    Unit.BOX: "Caja",
}
PRODUCT_KIND = {ProductKind.CONSUMABLE: "Consumible", ProductKind.REUSABLE: "Reutilizable"}
MOVEMENT_KIND = {
    MovementKind.ENTRY: "Entrada",
    MovementKind.EXIT: "Salida",
    MovementKind.RETURN: "Devolución",
    MovementKind.WASTE: "Merma",
    MovementKind.ADJUSTMENT: "Ajuste",
}
PURCHASE_STATUS = {
    PurchaseStatus.REQUESTED: "Solicitada",
    PurchaseStatus.ORDERED: "Ordenada",
    PurchaseStatus.RECEIVED: "Recibida",
    PurchaseStatus.CANCELLED: "Cancelada",
}
