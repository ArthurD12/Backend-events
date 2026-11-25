"""Dominio de compras (HU27–HU29): proveedor y transiciones de la compra (RN21)."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from local_eventos.modules.purchasing.domain.errors import (
    InvalidTransitionError,
    PurchasingValidationError,
)
from local_eventos.modules.purchasing.domain.purchase import (
    Purchase,
    PurchaseStatus,
    ReceivedLine,
    format_purchase_code,
)
from local_eventos.modules.purchasing.domain.supplier import DocumentType, Supplier

NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)
USER = uuid4()
SUGAR, OIL = uuid4(), uuid4()


def _supplier(**changes: object) -> Supplier:
    data: dict[str, object] = {
        "name": " Distribuidora  Lima SAC ", "document_type": DocumentType.RUC,
        "document_number": "20123456789", "phone": "987 654-321", **changes,
    }  # fmt: skip
    return Supplier.register(**data)  # type: ignore[arg-type]


def _purchase() -> Purchase:
    return Purchase.request(
        code="COM-2026-0001", lines=[(SUGAR, Decimal("10")), (OIL, Decimal("2.5"))],
        created_by=USER, now=NOW,
    )  # fmt: skip


def test_ca27_1_proveedor_con_datos_limpios() -> None:
    supplier = _supplier(email=" Ventas@Dlima.PE ", contact_name="Luis")

    assert supplier.name == "Distribuidora Lima SAC"
    assert (supplier.phone, supplier.email, supplier.active) == (
        "987654321",
        "ventas@dlima.pe",
        True,
    )


@pytest.mark.parametrize(
    "changes",
    [{"name": " "}, {"document_number": "2012345678"},
     {"document_type": DocumentType.DNI, "document_number": "20123456789"},
     {"phone": "12"}, {"email": "no-es-correo"}],
)  # fmt: skip
def test_ca27_1_datos_invalidos(changes: dict[str, object]) -> None:
    with pytest.raises(PurchasingValidationError):
        _supplier(**changes)


def test_ca27_3_editar_invalido_no_cambia_nada_y_se_desactiva() -> None:
    supplier = _supplier()
    with pytest.raises(PurchasingValidationError):
        supplier.update(name="Nuevo", document_type=DocumentType.RUC,
                        document_number="20123456789", phone="1")  # fmt: skip
    assert supplier.name == "Distribuidora Lima SAC"
    supplier.deactivate()
    assert supplier.active is False


def test_codigo_com_aaaa_nnnn() -> None:
    assert format_purchase_code(2026, 7) == "COM-2026-0007"


def test_ca28_1_solicitud_valida() -> None:
    with pytest.raises(PurchasingValidationError):
        Purchase.request(code="X", lines=[], created_by=USER, now=NOW)
    with pytest.raises(PurchasingValidationError):
        Purchase.request(code="X", lines=[(SUGAR, Decimal(1)), (SUGAR, Decimal(2))],
                         created_by=USER, now=NOW)  # fmt: skip
    with pytest.raises(PurchasingValidationError):
        Purchase.request(code="X", lines=[(SUGAR, Decimal("0.0001"))], created_by=USER, now=NOW)
    purchase = _purchase()
    assert purchase.status is PurchaseStatus.REQUESTED and purchase.total_cents is None


def test_ca29_1_ordenar_con_proveedor_y_costos() -> None:
    purchase = _purchase()
    supplier = uuid4()

    with pytest.raises(PurchasingValidationError):
        purchase.order(supplier_id=supplier, unit_costs={SUGAR: 380}, ordered_by=USER, now=NOW)
    purchase.order(
        supplier_id=supplier, unit_costs={SUGAR: 380, OIL: 999}, ordered_by=USER, now=NOW
    )

    assert purchase.status is PurchaseStatus.ORDERED and purchase.supplier_id == supplier
    assert purchase.total_cents == 3800 + 2498  # 2.5 × 999 = 2497.5 → 2498
    with pytest.raises(InvalidTransitionError):
        purchase.order(supplier_id=supplier, unit_costs={SUGAR: 1, OIL: 1}, ordered_by=USER,
                       now=NOW)  # fmt: skip


def test_ca29_2_recibir_con_cantidades_reales_una_sola_vez() -> None:
    purchase = _purchase()
    with pytest.raises(InvalidTransitionError):  # aún no se ordenó
        purchase.receive(lines=[], received_by=USER, now=NOW)
    purchase.order(supplier_id=uuid4(), unit_costs={SUGAR: 400, OIL: 1000}, ordered_by=USER,
                   now=NOW)  # fmt: skip
    with pytest.raises(PurchasingValidationError):  # falta una línea
        purchase.receive(lines=[ReceivedLine(SUGAR, Decimal(9))], received_by=USER, now=NOW)

    purchase.receive(
        lines=[ReceivedLine(SUGAR, Decimal(9), lot="L1", expires_on=date(2027, 1, 1)),
               ReceivedLine(OIL, Decimal(0))],
        received_by=USER, now=NOW, invoice_number=" F001-123 ",
    )  # fmt: skip

    assert purchase.status is PurchaseStatus.RECEIVED
    assert purchase.lines[0].received_quantity == Decimal(9) and purchase.lines[0].lot == "L1"
    assert purchase.total_cents == 3600 and purchase.invoice_number == "F001-123"
    with pytest.raises(InvalidTransitionError):
        purchase.receive(lines=[], received_by=USER, now=NOW)
    with pytest.raises(InvalidTransitionError):
        purchase.cancel(reason="tarde", cancelled_by=USER, now=NOW)


def test_recibir_nada_no_se_permite() -> None:
    purchase = _purchase()
    purchase.order(supplier_id=uuid4(), unit_costs={SUGAR: 1, OIL: 1}, ordered_by=USER, now=NOW)

    with pytest.raises(PurchasingValidationError):
        purchase.receive(lines=[ReceivedLine(SUGAR, Decimal(0)), ReceivedLine(OIL, Decimal(0))],
                         received_by=USER, now=NOW)  # fmt: skip


def test_cancelar_con_motivo() -> None:
    purchase = _purchase()
    with pytest.raises(PurchasingValidationError):
        purchase.cancel(reason=" ", cancelled_by=USER, now=NOW)
    purchase.cancel(reason="Ya no se necesita", cancelled_by=USER, now=NOW)
    assert purchase.status is PurchaseStatus.CANCELLED
    with pytest.raises(InvalidTransitionError):
        purchase.order(supplier_id=uuid4(), unit_costs={SUGAR: 1, OIL: 1}, ordered_by=USER,
                       now=NOW)  # fmt: skip
