"""Matriz de permisos de la API de asistencia (HU18, T-12).

Cierra la autorización por permiso de las dos rutas (R-ATT-14/CA-18.9/CA-18.10):

- `PATCH /v1/staff/assignments/{id}/attendance` exige `staff:attendance`.
- `GET /v1/staff/workers/{id}/attendance` exige `staff:manage`.

Solo el administrador (que tiene todos los permisos) obtiene 200 en ambas. Los
encargados de eventos y de compras reciben 403 `auth.forbidden`; sin sesión,
401 `auth.not_authenticated`. Un usuario con solo `staff_roster:read` o
`staff:assign` no abre ninguna de las dos rutas (CA-18.10).
"""

from __future__ import annotations

from collections.abc import Iterator
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from local_eventos.modules.identity.domain.permissions import (
    Permission,
    Role,
    permissions_of,
)
from local_eventos.modules.identity.public_api import CurrentUser, get_current_user
from tests.unit.staff.test_attendance_api import (
    GET_PATH,
    PATCH_PATH,
    Api,
    _build,
    _event_for,
    _history_row,
)
from tests.unit.staff.test_attendance_history import EVENT_A
from tests.unit.staff.test_attendance_update import (
    NOW,
    _assignment,
)

PATCH_BODY = {"status": "ATTENDED"}

_ROUTES = [
    ("patch", PATCH_PATH, PATCH_BODY),
    ("get", GET_PATH, None),
]


def _build_api() -> Api:
    return _build(
        events={EVENT_A: _event_for(EVENT_A, NOW.date())},
        assignment=_assignment(),
        rows=[_history_row(event_id=EVENT_A, start_at=NOW)],
    )


@pytest.fixture
def api() -> Iterator[Api]:
    built = _build_api()
    with built.client:
        yield built


def _as_permissions(api: Api, permissions: frozenset[Permission]) -> None:
    """Sustituye el usuario actual por uno con permisos explícitos."""
    app: FastAPI = api.client.app
    user = CurrentUser(
        id=uuid4(),
        name="Usuario de prueba",
        role=Role.ADMIN,
        permissions=permissions,
    )

    async def current_user() -> CurrentUser:
        return user

    app.dependency_overrides[get_current_user] = current_user


def _without_session(api: Api) -> None:
    app: FastAPI = api.client.app
    del app.dependency_overrides[get_current_user]


def _call(api: Api, method: str, path: str, body: dict[str, str] | None) -> httpx.Response:
    return api.client.request(method.upper(), path, json=body)


def test_admin_obtiene_200_en_ambas_rutas(api: Api) -> None:
    patch = api.client.patch(PATCH_PATH, json=PATCH_BODY)
    history = api.client.get(GET_PATH)

    assert patch.status_code == 200, patch.text
    assert history.status_code == 200, history.text


@pytest.mark.parametrize("role", [Role.EVENTS_MANAGER, Role.PURCHASING_MANAGER])
@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_encargados_sin_permiso_403(
    api: Api, role: Role, method: str, path: str, body: dict[str, str] | None
) -> None:
    api.as_role(role)

    response = _call(api, method, path, body)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "auth.forbidden"


@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_sin_sesion_401(api: Api, method: str, path: str, body: dict[str, str] | None) -> None:
    _without_session(api)

    response = _call(api, method, path, body)

    assert response.status_code == 401, response.text
    assert response.json()["code"] == "auth.not_authenticated"


@pytest.mark.parametrize(
    "permissions",
    [
        frozenset({Permission.STAFF_ROSTER_READ}),
        frozenset({Permission.STAFF_ASSIGN}),
    ],
)
@pytest.mark.parametrize(("method", "path", "body"), _ROUTES)
def test_permisos_ajenos_no_abren_ninguna_ruta(
    api: Api,
    permissions: frozenset[Permission],
    method: str,
    path: str,
    body: dict[str, str] | None,
) -> None:
    _as_permissions(api, permissions)

    response = _call(api, method, path, body)

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "auth.forbidden"


def test_staff_roster_read_no_abre_ninguna_ruta(api: Api) -> None:
    _as_permissions(api, frozenset({Permission.STAFF_ROSTER_READ}))

    patch = api.client.patch(PATCH_PATH, json=PATCH_BODY)
    history = api.client.get(GET_PATH)

    assert patch.status_code == 403, patch.text
    assert history.status_code == 403, history.text


def test_staff_attendance_solo_abre_patch(api: Api) -> None:
    _as_permissions(api, frozenset({Permission.STAFF_ATTENDANCE}))

    patch = api.client.patch(PATCH_PATH, json=PATCH_BODY)
    history = api.client.get(GET_PATH)

    assert patch.status_code == 200, patch.text
    assert history.status_code == 403, history.text


def test_staff_manage_solo_abre_historial(api: Api) -> None:
    _as_permissions(api, frozenset({Permission.STAFF_MANAGE}))

    patch = api.client.patch(PATCH_PATH, json=PATCH_BODY)
    history = api.client.get(GET_PATH)

    assert patch.status_code == 403, patch.text
    assert history.status_code == 200, history.text


def test_admin_por_rol_tiene_los_dos_permisos() -> None:
    admin = permissions_of(Role.ADMIN)

    assert Permission.STAFF_ATTENDANCE in admin
    assert Permission.STAFF_MANAGE in admin
    for role in (Role.EVENTS_MANAGER, Role.PURCHASING_MANAGER):
        assert Permission.STAFF_ATTENDANCE not in permissions_of(role)
        assert Permission.STAFF_MANAGE not in permissions_of(role)
    assert Permission.STAFF_ROSTER_READ in permissions_of(Role.EVENTS_MANAGER)
