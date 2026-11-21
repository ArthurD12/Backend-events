"""Pruebas de la consulta pública del catálogo (HU06). Sin base de datos."""

from uuid import uuid4

import pytest

from local_eventos.modules.catalog.application.use_cases.get_service_summary import (
    GetServiceSummary,
)
from local_eventos.modules.catalog.domain.service import PriceUnit, Service
from local_eventos.modules.catalog.public_api import ServiceLookup, ServiceSummary

from .fakes import InMemoryServiceRepository


def _saved_service(repository: InMemoryServiceRepository) -> Service:
    service = Service.register(
        name="Buffet criollo",
        category_id=uuid4(),
        price_unit=PriceUnit.PER_PERSON,
        reference_price_cents=4500,
    )
    repository.services[service.id] = service
    return service


@pytest.mark.asyncio
async def test_hu06_devuelve_el_resumen_con_precio_en_centimos() -> None:
    repository = InMemoryServiceRepository()
    service = _saved_service(repository)

    summary = await GetServiceSummary(repository)(service.id)

    assert summary == ServiceSummary(
        id=service.id,
        name="Buffet criollo",
        category_id=service.category_id,
        price_unit="PER_PERSON",
        reference_price_cents=4500,
        currency="PEN",
        active=True,
    )


@pytest.mark.asyncio
async def test_hu06_servicio_inexistente_devuelve_none() -> None:
    summary = await GetServiceSummary(InMemoryServiceRepository())(uuid4())

    assert summary is None


@pytest.mark.asyncio
async def test_hu06_informa_si_el_servicio_esta_desactivado() -> None:
    repository = InMemoryServiceRepository()
    service = _saved_service(repository)
    service.deactivate()

    summary = await GetServiceSummary(repository)(service.id)

    assert summary is not None
    assert summary.active is False


@pytest.mark.asyncio
async def test_hu06_cambiar_el_catalogo_no_cambia_el_precio_ya_leido() -> None:
    repository = InMemoryServiceRepository()
    service = _saved_service(repository)
    lookup: ServiceLookup = GetServiceSummary(repository)

    summary = await lookup(service.id)
    service.update(
        name="Buffet criollo",
        category_id=service.category_id,
        price_unit=PriceUnit.PER_PERSON,
        reference_price_cents=5000,
    )

    assert summary is not None
    assert summary.reference_price_cents == 4500
