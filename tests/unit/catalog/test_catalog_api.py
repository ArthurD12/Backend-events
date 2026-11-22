"""Pruebas de la API del catálogo (HU06) con repositorios en memoria. Sin base de datos."""

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from local_eventos.main import create_app
from local_eventos.modules.catalog.application.ports.category_repository import (
    CategoryRepository,
)
from local_eventos.modules.catalog.application.ports.service_repository import (
    ServiceRepository,
)
from local_eventos.modules.catalog.presentation.dependencies import (
    get_category_repository,
    get_service_repository,
)
from local_eventos.modules.identity.domain.permissions import Role
from local_eventos.modules.identity.public_api import get_current_user
from tests.unit.current_user import signed_in_as

from .fakes import InMemoryCategoryRepository, InMemoryServiceRepository

CATEGORIES = "/v1/catalog/categories"
SERVICES = "/v1/catalog/services"


async def _no_database() -> None:
    return None


@pytest.fixture
def api() -> Iterator[TestClient]:
    categories = InMemoryCategoryRepository()
    services = InMemoryServiceRepository()

    async def in_memory_categories() -> CategoryRepository:
        return categories

    async def in_memory_services() -> ServiceRepository:
        return services

    app = create_app(readiness_check=_no_database)
    app.dependency_overrides[get_category_repository] = in_memory_categories
    app.dependency_overrides[get_service_repository] = in_memory_services
    app.dependency_overrides[get_current_user] = signed_in_as(Role.ADMIN)
    with TestClient(app) as client:
        yield client


def _buffet(category_id: str, **changes: Any) -> dict[str, Any]:
    return {
        "name": "Buffet criollo",
        "category_id": category_id,
        "price_unit": "PER_PERSON",
        "reference_price_cents": 4500,
        "description": "Arroz con pollo y papa a la huancaína",
        **changes,
    }


def _category(api: TestClient, name: str = "Buffets") -> str:
    response = api.post(CATEGORIES, json={"name": name})
    assert response.status_code == 201
    category_id: str = response.json()["id"]
    return category_id


def test_hu06_crea_y_lista_categorias(api: TestClient) -> None:
    _category(api, "Mobiliario")
    response = api.post(CATEGORIES, json={"name": "  Bebidas  "})

    assert response.status_code == 201
    assert response.json()["name"] == "Bebidas"
    assert response.json()["active"] is True
    assert [c["name"] for c in api.get(CATEGORIES).json()] == ["Bebidas", "Mobiliario"]


def test_hu06_categoria_repetida_responde_409(api: TestClient) -> None:
    _category(api, "Bebidas")

    response = api.post(CATEGORIES, json={"name": "BEBIDAS"})

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "catalog.category_name_duplicated"


def test_hu06_nombre_vacio_responde_422_con_su_code(api: TestClient) -> None:
    response = api.post(CATEGORIES, json={"name": "   "})

    assert response.status_code == 422
    assert response.json()["code"] == "catalog.category_name_required"


def test_hu06_renombra_una_categoria(api: TestClient) -> None:
    category_id = _category(api, "Mobiliario")

    response = api.put(f"{CATEGORIES}/{category_id}", json={"name": "Mobiliario y menaje"})

    assert response.status_code == 200
    assert response.json()["name"] == "Mobiliario y menaje"


def test_hu06_categoria_inexistente_responde_404(api: TestClient) -> None:
    response = api.post(f"{CATEGORIES}/{uuid4()}/activate")

    assert response.status_code == 404
    assert response.json()["code"] == "catalog.category_not_found"


def test_hu06_no_desactiva_categoria_con_servicios_activos(api: TestClient) -> None:
    category_id = _category(api)
    service_id = api.post(SERVICES, json=_buffet(category_id)).json()["id"]

    blocked = api.post(f"{CATEGORIES}/{category_id}/deactivate")
    api.post(f"{SERVICES}/{service_id}/deactivate")
    allowed = api.post(f"{CATEGORIES}/{category_id}/deactivate")

    assert blocked.status_code == 409
    assert blocked.json()["code"] == "catalog.category_has_active_services"
    assert allowed.status_code == 200
    assert allowed.json()["active"] is False
    assert api.get(CATEGORIES).json() == []
    assert len(api.get(CATEGORIES, params={"include_inactive": True}).json()) == 1


def test_hu06_registra_un_servicio_con_precio_en_centimos(api: TestClient) -> None:
    category_id = _category(api)

    response = api.post(SERVICES, json=_buffet(category_id))

    assert response.status_code == 201
    body = response.json()
    assert body["reference_price_cents"] == 4500
    assert body["currency"] == "PEN"
    assert body["price_unit"] == "PER_PERSON"
    assert body["active"] is True


def test_hu06_precio_negativo_responde_422_con_su_code(api: TestClient) -> None:
    category_id = _category(api)

    response = api.post(SERVICES, json=_buffet(category_id, reference_price_cents=-100))

    assert response.status_code == 422
    assert response.json()["code"] == "catalog.price_invalid"


def test_hu06_no_registra_servicio_en_categoria_inactiva_o_inexistente(api: TestClient) -> None:
    category_id = _category(api)
    api.post(f"{CATEGORIES}/{category_id}/deactivate")

    inactive = api.post(SERVICES, json=_buffet(category_id))
    missing = api.post(SERVICES, json=_buffet(str(uuid4())))

    assert inactive.status_code == 409
    assert inactive.json()["code"] == "catalog.category_inactive"
    assert missing.status_code == 404
    assert missing.json()["code"] == "catalog.category_not_found"


def test_hu06_modifica_un_servicio(api: TestClient) -> None:
    category_id = _category(api)
    service_id = api.post(SERVICES, json=_buffet(category_id)).json()["id"]

    response = api.put(
        f"{SERVICES}/{service_id}",
        json=_buffet(category_id, name="Buffet criollo premium", reference_price_cents=5500),
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Buffet criollo premium"
    assert response.json()["reference_price_cents"] == 5500


def test_hu06_servicio_inexistente_responde_404(api: TestClient) -> None:
    category_id = _category(api)

    response = api.put(f"{SERVICES}/{uuid4()}", json=_buffet(category_id))

    assert response.status_code == 404
    assert response.json()["code"] == "catalog.service_not_found"


def test_hu06_busca_servicios_activos_por_texto_y_categoria(api: TestClient) -> None:
    buffets = _category(api, "Buffets")
    bebidas = _category(api, "Bebidas")
    api.post(SERVICES, json=_buffet(buffets))
    marino = api.post(SERVICES, json=_buffet(buffets, name="Buffet marino")).json()["id"]
    api.post(SERVICES, json=_buffet(bebidas, name="Chicha morada", price_unit="PER_UNIT"))
    api.post(f"{SERVICES}/{marino}/deactivate")

    def names(**params: Any) -> list[str]:
        return [s["name"] for s in api.get(SERVICES, params=params).json()]

    assert names(text="buffet") == ["Buffet criollo"]
    assert names(text="buffet", include_inactive=True) == ["Buffet criollo", "Buffet marino"]
    assert names(category_id=bebidas) == ["Chicha morada"]


def test_hu06_reactiva_un_servicio(api: TestClient) -> None:
    category_id = _category(api)
    service_id = api.post(SERVICES, json=_buffet(category_id)).json()["id"]
    api.post(f"{SERVICES}/{service_id}/deactivate")

    response = api.post(f"{SERVICES}/{service_id}/activate")

    assert response.status_code == 200
    assert response.json()["active"] is True


@pytest.mark.parametrize("role", [Role.EVENTS_MANAGER, Role.PURCHASING_MANAGER])
def test_ca01_7_los_encargados_leen_el_catalogo_pero_no_lo_modifican(
    api: TestClient, role: Role
) -> None:
    category_id = _category(api)
    api.app.dependency_overrides[get_current_user] = signed_in_as(role)  # type: ignore[attr-defined]

    read = api.get(SERVICES)
    create = api.post(CATEGORIES, json={"name": "Bebidas"})
    change = api.post(SERVICES, json=_buffet(category_id))

    assert read.status_code == 200
    assert api.get(CATEGORIES).status_code == 200
    assert create.status_code == 403
    assert change.status_code == 403
    assert create.json()["code"] == "auth.forbidden"


def test_ca01_7_catalogo_exige_sesion(api: TestClient) -> None:
    del api.app.dependency_overrides[get_current_user]  # type: ignore[attr-defined]

    assert api.get(CATEGORIES).status_code == 401
