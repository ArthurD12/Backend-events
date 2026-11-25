"""Dominio de inventario (HU23, HU26): producto, movimientos, stock y materiales del evento."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from local_eventos.modules.inventory.domain.errors import (
    InsufficientStockError,
    InventoryValidationError,
)
from local_eventos.modules.inventory.domain.event_materials import EventMaterials
from local_eventos.modules.inventory.domain.movement import Movement, MovementKind
from local_eventos.modules.inventory.domain.product import (
    Category,
    Product,
    ProductKind,
    Unit,
)
from local_eventos.modules.inventory.domain.quantity import to_quantity
from local_eventos.modules.inventory.domain.stock import (
    StockLevel,
    is_expiring_soon,
    is_low_stock,
    next_expiry,
)

from .fakes import NOW, TODAY

PRODUCT = uuid4()
USER = uuid4()
EVENT = uuid4()


def _move(kind: MovementKind, quantity: str, **extra: object) -> Movement:
    return Movement.record(
        kind=kind, product_id=PRODUCT, quantity=Decimal(quantity), recorded_by=USER,
        now=NOW, today=TODAY, **extra,  # type: ignore[arg-type]
    )  # fmt: skip


def _entry(quantity: str, cost: int, **extra: object) -> Movement:
    return _move(MovementKind.ENTRY, quantity, unit_cost_cents=cost, **extra)


def test_ca23_1_producto_con_codigo_en_mayusculas_y_datos_validos() -> None:
    product = Product.create(
        code=" vas-01 ", name="  Vaso   de vidrio ", category=Category.GLASSWARE,
        unit=Unit.UNIT, kind=ProductKind.REUSABLE, min_stock=Decimal("24"),
    )  # fmt: skip

    assert (product.code, product.name, product.min_stock) == ("VAS-01", "Vaso de vidrio", 24)
    assert product.active is True


@pytest.mark.parametrize(
    ("code", "name", "min_stock"),
    [("", "Azúcar", "0"), ("A" * 21, "Azúcar", "0"), ("AZ 1", "Azúcar", "0"),
     ("AZ-1", " ", "0"), ("AZ-1", "Azúcar", "-1"), ("AZ-1", "Azúcar", "0.0001")],
)  # fmt: skip
def test_ca23_1_datos_invalidos(code: str, name: str, min_stock: str) -> None:
    with pytest.raises(InventoryValidationError) as error:
        Product.create(
            code=code, name=name, category=Category.SUPPLIES, unit=Unit.KG,
            kind=ProductKind.CONSUMABLE, min_stock=Decimal(min_stock),
        )  # fmt: skip
    assert error.value.code == "inventory.validation"


def test_ca23_3_se_desactiva_y_reactiva() -> None:
    product = Product.create(
        code="AZ", name="Azúcar", category=Category.SUPPLIES, unit=Unit.KG,
        kind=ProductKind.CONSUMABLE, min_stock=Decimal(0),
    )  # fmt: skip
    product.deactivate()
    assert product.active is False
    product.activate()
    assert product.active is True


def test_r_inv_1_cantidad_con_hasta_3_decimales() -> None:
    assert to_quantity(Decimal("1.5")) == Decimal("1.500")
    assert str(to_quantity("2")) == "2.000"
    with pytest.raises(InventoryValidationError):
        to_quantity(Decimal("1.2345"))
    with pytest.raises(InventoryValidationError):
        to_quantity("abc")


def test_ca23_2_entrada_con_costo_lote_y_vencimiento() -> None:
    supplier = uuid4()
    entry = _entry("10", 350, supplier_id=supplier, lot=" L-1 ", expires_on=date(2027, 1, 1))

    assert entry.quantity == Decimal("10.000")
    assert (entry.unit_cost_cents, entry.supplier_id, entry.lot) == (350, supplier, "L-1")
    assert entry.occurred_on == TODAY
    assert entry.stock_delta == Decimal(10)


@pytest.mark.parametrize(
    ("kind", "quantity", "extra"),
    [
        (MovementKind.ENTRY, "1", {}),  # sin costo
        (MovementKind.ENTRY, "1", {"unit_cost_cents": -1}),
        (MovementKind.ENTRY, "0", {"unit_cost_cents": 1}),
        (MovementKind.EXIT, "1", {}),  # sin evento
        (MovementKind.RETURN, "1", {}),
        (MovementKind.EXIT, "1", {"event_id": EVENT, "unit_cost_cents": 1}),
        (MovementKind.EXIT, "-1", {"event_id": EVENT}),
        (MovementKind.WASTE, "1", {}),  # sin motivo
        (MovementKind.ADJUSTMENT, "0", {"reason": "conteo"}),
        (MovementKind.ADJUSTMENT, "1", {"reason": "conteo", "event_id": EVENT}),
        (MovementKind.WASTE, "1", {"reason": "rota", "occurred_on": TODAY + timedelta(1)}),
    ],
)
def test_campos_segun_el_tipo(kind: MovementKind, quantity: str, extra: dict[str, object]) -> None:
    with pytest.raises(InventoryValidationError):
        _move(kind, quantity, **extra)


def test_signo_de_cada_tipo_en_el_stock() -> None:
    assert _move(MovementKind.EXIT, "2", event_id=EVENT).stock_delta == Decimal(-2)
    assert _move(MovementKind.RETURN, "2", event_id=EVENT).stock_delta == Decimal(2)
    assert _move(MovementKind.WASTE, "2", reason="rota").stock_delta == Decimal(-2)
    assert _move(MovementKind.WASTE, "2", reason="rota", event_id=EVENT).stock_delta == 0
    assert _move(MovementKind.ADJUSTMENT, "-1.5", reason="conteo").stock_delta == Decimal("-1.5")


def test_r_inv_3_costo_promedio_ponderado() -> None:
    level = StockLevel(PRODUCT).apply(_entry("10", 100)).apply(_entry("30", 200))

    assert level.quantity == Decimal(40)
    assert level.avg_cost_cents == 175  # (10×100 + 30×200) / 40
    assert level.value_cents == 7000
    after_exit = level.apply(_move(MovementKind.EXIT, "40", event_id=EVENT))
    assert after_exit.quantity == 0
    assert after_exit.apply(_entry("1", 90)).avg_cost_cents == 90  # sin stock: costo nuevo


def test_rn20_el_stock_no_queda_negativo() -> None:
    level = StockLevel(PRODUCT).apply(_entry("2.5", 100))

    with pytest.raises(InsufficientStockError) as error:
        level.apply(_move(MovementKind.EXIT, "3", event_id=EVENT))

    assert error.value.code == "inventory.insufficient_stock"
    assert error.value.available == Decimal("2.5")


def test_ca23_5_stock_bajo_y_por_vencer() -> None:
    assert is_low_stock(Decimal(5), Decimal(5))
    assert not is_low_stock(Decimal(6), Decimal(5))
    assert is_expiring_soon(TODAY + timedelta(15), TODAY)
    assert is_expiring_soon(TODAY - timedelta(1), TODAY)
    assert not is_expiring_soon(TODAY + timedelta(16), TODAY)
    assert not is_expiring_soon(None, TODAY)


def test_ca23_5_vencimiento_solo_de_entradas_con_stock_vigente() -> None:
    old = _entry("10", 100, expires_on=date(2026, 12, 1), occurred_on=date(2026, 11, 1))
    new = _entry("10", 100, expires_on=date(2027, 6, 1), occurred_on=date(2026, 11, 20))

    assert next_expiry(Decimal(8), [old, new]) == date(2027, 6, 1)  # lo antiguo ya salió
    assert next_expiry(Decimal(15), [old, new]) == date(2026, 12, 1)
    assert next_expiry(Decimal(0), [old, new]) is None


def test_ca26_6_materiales_del_evento() -> None:
    moves = [
        _move(MovementKind.EXIT, "100", event_id=EVENT),
        _move(MovementKind.RETURN, "90", event_id=EVENT),
        _move(MovementKind.WASTE, "4", event_id=EVENT, reason="rotos"),
    ]

    plates = EventMaterials.from_movements(PRODUCT, ProductKind.REUSABLE, moves)
    sugar = EventMaterials.from_movements(PRODUCT, ProductKind.CONSUMABLE, moves)

    assert (plates.out, plates.returned, plates.wasted) == (100, 90, 4)
    assert plates.pending_return == Decimal(6)
    assert sugar.at_event == Decimal(6) and sugar.pending_return == 0
