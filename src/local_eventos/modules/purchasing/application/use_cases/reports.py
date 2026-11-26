"""Consultas de solo lectura de compras para `reporting` (HU31–HU34)."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from uuid import UUID

from local_eventos.modules.purchasing.application.ports.repositories import (
    PurchaseFilters,
    PurchaseRepository,
    SupplierRepository,
)
from local_eventos.modules.purchasing.domain.purchase import PurchaseStatus

MAX_REPORT_PURCHASES = 5_000  # un año de una MYPE no llega a tanto
# Perú no usa horario de verano: el día de Lima va de 00:00 a 24:00 en UTC−5 (AGENTS.md, regla 4).
_LIMA = timezone(timedelta(hours=-5), "America/Lima")


@dataclass(frozen=True)
class PurchaseReportItem:
    """Una compra para el reporte (CA-32.4). Fechas en hora de Lima."""

    id: UUID
    code: str
    created_on: date
    supplier_name: str | None
    status: PurchaseStatus
    total_cents: int | None  # sin costos (solicitada), no hay total
    received_on: date | None
    event_id: UUID | None


class ListPurchaseReport:
    def __init__(self, purchases: PurchaseRepository, suppliers: SupplierRepository) -> None:
        self._purchases = purchases
        self._suppliers = suppliers

    async def __call__(
        self, date_from: date, date_to: date, status: PurchaseStatus | None = None
    ) -> list[PurchaseReportItem]:
        """Compras creadas en el rango (días de Lima), de la más antigua a la más reciente."""
        found, _ = await self._purchases.search(
            PurchaseFilters(
                status=status,
                created_from=datetime.combine(date_from, time(), _LIMA),
                created_before=datetime.combine(date_to + timedelta(days=1), time(), _LIMA),
            ),
            limit=MAX_REPORT_PURCHASES,
            offset=0,
        )
        supplier_ids = list({p.supplier_id for p in found if p.supplier_id})
        names = {s.id: s.name for s in await self._suppliers.get_many(supplier_ids)}
        return [
            PurchaseReportItem(
                id=p.id,
                code=p.code,
                created_on=p.created.at.astimezone(_LIMA).date(),
                supplier_name=names.get(p.supplier_id) if p.supplier_id else None,
                status=p.status,
                total_cents=p.total_cents,
                received_on=p.received.at.astimezone(_LIMA).date() if p.received else None,
                event_id=p.event_id,
            )
            for p in sorted(found, key=lambda p: (p.created.at, p.code))
        ]


@dataclass(frozen=True)
class OpenPurchases:
    """Compras abiertas (CA-31.11): solicitadas u ordenadas."""

    requested: int
    ordered: int

    @property
    def total(self) -> int:
        return self.requested + self.ordered


class CountOpenPurchases:
    def __init__(self, purchases: PurchaseRepository) -> None:
        self._purchases = purchases

    async def __call__(self) -> OpenPurchases:
        counts = await self._purchases.count_by_status()
        return OpenPurchases(
            requested=counts.get(PurchaseStatus.REQUESTED, 0),
            ordered=counts.get(PurchaseStatus.ORDERED, 0),
        )
