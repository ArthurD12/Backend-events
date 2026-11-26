"""Superficie pública del módulo purchasing: única vía de uso por otros módulos.

`reporting` lee aquí las compras para su reporte y el panel (solo lectura).
"""

from datetime import date
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.purchasing import composition
from local_eventos.modules.purchasing.application.use_cases.reports import (
    CountOpenPurchases,
    ListPurchaseReport,
    OpenPurchases,
    PurchaseReportItem,
)
from local_eventos.modules.purchasing.domain.purchase import PurchaseStatus


class PurchaseReportLookup(Protocol):
    """Compras creadas en el rango (días de Lima), opcionalmente de un estado (CA-32.4)."""

    async def __call__(
        self, date_from: date, date_to: date, status: PurchaseStatus | None = None
    ) -> list[PurchaseReportItem]: ...


class OpenPurchasesLookup(Protocol):
    """Cuántas compras están solicitadas u ordenadas (CA-31.11)."""

    async def __call__(self) -> OpenPurchases: ...


def purchases_report(session: AsyncSession) -> PurchaseReportLookup:
    return ListPurchaseReport(
        composition.purchase_repository(session), composition.supplier_repository(session)
    )


def open_purchases(session: AsyncSession) -> OpenPurchasesLookup:
    return CountOpenPurchases(composition.purchase_repository(session))


__all__ = [
    "OpenPurchases",
    "OpenPurchasesLookup",
    "PurchaseReportItem",
    "PurchaseReportLookup",
    "PurchaseStatus",
    "open_purchases",
    "purchases_report",
]
