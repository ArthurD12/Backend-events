"""Matriz de autenticación y roles de la API de disponibilidad (HU16, T-16).

Todas las rutas exigen el permiso `staff:availability`; el cierre formal de la
matriz es T-20, aquí se deja la evidencia provisional de CA-16.17. Se usa la
aplicación real de `main.create_app()` para que la comprobación cubra también el
orden de los routers: un `422` de path param no debe confundirse con un `403`.

Casos cubiertos en las cinco rutas:

- sin sesión → 401 `auth.not_authenticated`;
- `EVENTS_MANAGER` → 403 `auth.forbidden`;
- `PURCHASING_MANAGER` → 403 `auth.forbidden`;
- administrador → la operación pasa la autorización y llega al caso de uso;
- un usuario que solo tiene `staff_roster:read` o `staff:assign` → 403.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from local_eventos.modules.identity.domain.permissions import Permission, Role
from tests.unit.staff.test_availability_api import (
    AVAILABILITY,
    BODY,
    MISSING_ID,
    UNAVAILABILITY,
)
from tests.unit.staff.test_availability_router_order import (
    UPDATE_BODY,
    AvailabilityApp,
    build_availability_app,
)

_AVAILABILITY_PARAMS = {"from_date": "2026-12-01", "to_date": "2026-12-01"}

_ROUTES: list[tuple[str, str, dict[str, Any] | None, dict[str, str] | None]] = [
    ("GET", AVAILABILITY, None, _AVAILABILITY_PARAMS),
    ("GET", UNAVAILABILITY, None, None),
    ("POST", UNAVAILABILITY, BODY, None),
    ("PUT", f"{UNAVAILABILITY}/{MISSING_ID}", UPDATE_BODY, None),
    ("POST", f"{UNAVAILABILITY}/{MISSING_ID}/cancel", {"reason": "Error"}, None),
]

_WITHOUT_AVAILABILITY = [
    frozenset({Permission.STAFF_ROSTER_READ}),
    frozenset({Permission.STAFF_ASSIGN}),
    frozenset({Permission.STAFF_ROSTER_READ, Permission.STAFF_ASSIGN}),
]


@pytest.fixture
def availability_app() -> Iterator[AvailabilityApp]:
    built = build_availability_app()
    with built.client:
        yield built


def _call(
    app: AvailabilityApp,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    params: dict[str, str] | None,
) -> Any:
    return app.client.request(method, path, json=body, params=params)


@pytest.mark.parametrize(("method", "path", "body", "params"), _ROUTES)
def test_sin_sesion_401(
    availability_app: AvailabilityApp,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    params: dict[str, str] | None,
) -> None:
    availability_app.without_session()

    response = _call(availability_app, method, path, body, params)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "auth.not_authenticated"
    assert response.status_code != 422, response.text


@pytest.mark.parametrize("role", [Role.EVENTS_MANAGER, Role.PURCHASING_MANAGER])
@pytest.mark.parametrize(("method", "path", "body", "params"), _ROUTES)
def test_roles_sin_permiso_403(
    availability_app: AvailabilityApp,
    role: Role,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    params: dict[str, str] | None,
) -> None:
    availability_app.as_role(role)

    response = _call(availability_app, method, path, body, params)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "auth.forbidden"
    assert response.status_code != 422, response.text


@pytest.mark.parametrize("permissions", _WITHOUT_AVAILABILITY)
@pytest.mark.parametrize(("method", "path", "body", "params"), _ROUTES)
def test_otros_permisos_de_staff_no_abren_disponibilidad(
    availability_app: AvailabilityApp,
    permissions: frozenset[Permission],
    method: str,
    path: str,
    body: dict[str, Any] | None,
    params: dict[str, str] | None,
) -> None:
    availability_app.as_permissions(permissions)

    response = _call(availability_app, method, path, body, params)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "auth.forbidden"


def test_admin_pasa_en_las_cinco_rutas(availability_app: AvailabilityApp) -> None:
    availability_app.as_role(Role.ADMIN)

    created = availability_app.client.post(UNAVAILABILITY, json=BODY)
    assert created.status_code == 201, created.text
    unavailability_id = created.json()["id"]

    availability = availability_app.client.get(AVAILABILITY, params=_AVAILABILITY_PARAMS)
    listed = availability_app.client.get(UNAVAILABILITY)
    updated = availability_app.client.put(f"{UNAVAILABILITY}/{unavailability_id}", json=UPDATE_BODY)
    cancelled = availability_app.client.post(
        f"{UNAVAILABILITY}/{unavailability_id}/cancel", json={"reason": "Error de registro"}
    )

    assert availability.status_code == 200, availability.text
    assert listed.status_code == 200, listed.text
    assert updated.status_code == 200, updated.text
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED"
