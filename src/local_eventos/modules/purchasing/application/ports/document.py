"""Puerto del documento PDF de la compra (orden de compra, HU30)."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from local_eventos.modules.commercial.public_api import CompanyProfile
from local_eventos.modules.inventory.public_api import ProductInfo
from local_eventos.modules.purchasing.domain.purchase import Purchase
from local_eventos.modules.purchasing.domain.supplier import Supplier


@dataclass(frozen=True)
class PurchaseDocument:
    purchase: Purchase
    products: dict[UUID, ProductInfo]
    supplier: Supplier | None
    company: CompanyProfile
    event_code: str | None


class PurchaseDocumentRenderer(Protocol):
    def render(self, document: PurchaseDocument) -> bytes: ...
