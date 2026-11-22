"""Repositorio de servicios en PostgreSQL (HU06): implementa el puerto `ServiceRepository`.

Traduce entre la entidad `Service` (reglas del negocio) y la fila `ServiceRow` (tabla).
No confirma la transacción: eso lo decide quien abre la sesión, una vez por petición.
"""

from uuid import UUID

from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from local_eventos.modules.catalog.domain.service import CURRENCY, PriceUnit, Service
from local_eventos.modules.catalog.infrastructure.orm_models import ServiceRow


class SqlAlchemyServiceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, service_id: UUID) -> Service | None:
        row = await self._session.get(ServiceRow, service_id)
        return _to_service(row) if row is not None else None

    async def add(self, service: Service) -> None:
        row = ServiceRow(id=service.id, currency=CURRENCY)
        _copy_to_row(service, row)
        self._session.add(row)
        await self._session.flush()

    async def update(self, service: Service) -> None:
        row = await self._session.get(ServiceRow, service.id)
        if row is None:
            raise LookupError(f"El servicio {service.id} no existe en la base de datos.")
        _copy_to_row(service, row)
        await self._session.flush()

    async def has_active_in_category(self, category_id: UUID) -> bool:
        query = select(
            exists().where(ServiceRow.category_id == category_id, ServiceRow.active.is_(True))
        )
        return bool(await self._session.scalar(query))

    async def search(
        self,
        text: str,
        *,
        category_id: UUID | None,
        active: bool | None,
        limit: int,
    ) -> list[Service]:
        query = select(ServiceRow)
        if text:
            query = query.where(func.lower(ServiceRow.name).contains(text.lower(), autoescape=True))
        if category_id is not None:
            query = query.where(ServiceRow.category_id == category_id)
        if active is not None:
            query = query.where(ServiceRow.active.is_(active))
        rows = await self._session.scalars(query.order_by(func.lower(ServiceRow.name)).limit(limit))
        return [_to_service(row) for row in rows]


def _to_service(row: ServiceRow) -> Service:
    return Service(
        id=row.id,
        name=row.name,
        category_id=row.category_id,
        price_unit=PriceUnit(row.price_unit),
        reference_price_cents=row.reference_price_cents,
        description=row.description,
        active=row.active,
    )


def _copy_to_row(service: Service, row: ServiceRow) -> None:
    row.name = service.name
    row.category_id = service.category_id
    row.price_unit = service.price_unit.value
    row.reference_price_cents = service.reference_price_cents
    row.description = service.description
    row.active = service.active
