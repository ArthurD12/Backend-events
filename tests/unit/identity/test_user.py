"""Entidad Usuario, permisos por rol y política de contraseña (HU02, R-ID-1, R-ID-3)."""

import pytest

from local_eventos.modules.identity.domain.errors import UserValidationError
from local_eventos.modules.identity.domain.permissions import Permission, Role, permissions_of
from local_eventos.modules.identity.domain.user import User, check_password_policy


def _user(**changes: object) -> User:
    data: dict[str, object] = {
        "name": "  Ana   Torres ",
        "email": " Ana.Torres@Darze.pe ",
        "password_hash": "hash",
        "role": Role.EVENTS_MANAGER,
        **changes,
    }
    return User.create(**data)  # type: ignore[arg-type]


def test_ca02_1_crea_usuario_activo_con_datos_limpios() -> None:
    user = _user()

    assert user.name == "Ana Torres"
    assert user.email == "ana.torres@darze.pe"
    assert user.active is True


def test_ca02_1_puede_crearse_inactivo() -> None:
    assert _user(active=False).active is False


@pytest.mark.parametrize("email", ["", "ana", "ana@darze", "ana torres@darze.pe", "@darze.pe"])
def test_ca02_1_rechaza_correo_invalido(email: str) -> None:
    with pytest.raises(UserValidationError) as error:
        _user(email=email)
    assert error.value.code == "user.email_invalid"


def test_ca02_1_nombre_obligatorio() -> None:
    with pytest.raises(UserValidationError) as error:
        _user(name="   ")
    assert error.value.code == "user.name_required"


def test_r_id_1_contrasena_minimo_8_caracteres() -> None:
    check_password_policy("12345678")
    with pytest.raises(UserValidationError) as error:
        check_password_policy("1234567")
    assert error.value.code == "user.password_too_short"


def test_r_id_1_contrasena_con_maximo() -> None:
    with pytest.raises(UserValidationError) as error:
        check_password_policy("x" * 129)
    assert error.value.code == "user.password_too_long"


def test_ca02_3_actualiza_sin_cambios_parciales_si_un_dato_falla() -> None:
    user = _user()

    with pytest.raises(UserValidationError):
        user.update(name="Ana María", email="no-es-correo", role=Role.ADMIN)

    assert (user.name, user.role) == ("Ana Torres", Role.EVENTS_MANAGER)


def test_ca02_5_desactivar_no_borra_datos() -> None:
    user = _user()

    user.deactivate()

    assert user.active is False
    assert user.email == "ana.torres@darze.pe"


def test_r_id_3_permisos_segun_la_tabla_del_dominio() -> None:
    admin = _user(role=Role.ADMIN)
    eventos = _user(role=Role.EVENTS_MANAGER)
    compras = _user(role=Role.PURCHASING_MANAGER)

    assert admin.permissions == frozenset(Permission)
    assert eventos.permissions == {
        Permission.CLIENTS_MANAGE,
        Permission.CATALOG_READ,
        Permission.QUOTES_MANAGE,
        Permission.CONTRACTS_MANAGE,
        Permission.PAYMENTS_RECORD,
        Permission.EVENTS_MANAGE,
        Permission.EVENTS_READ,
        Permission.EVENT_NOTES_WRITE,
        Permission.INVENTORY_READ,
        Permission.STAFF_ROSTER_READ,  # 025: solo ve quién está designado
    }
    assert compras.permissions == {
        Permission.CATALOG_READ,
        Permission.EVENTS_READ,
        Permission.EVENT_NOTES_WRITE,  # R-ACT-5
        Permission.INVENTORY_READ,
        Permission.INVENTORY_MANAGE,
        Permission.PURCHASING_MANAGE,
    }
    # 025 (R-ASG-14): personal y pagos solo del administrador; el encargado de eventos
    # solo lee el personal designado y compras no tiene ningún permiso de personal.
    staff_permissions = {
        Permission.STAFF_MANAGE,
        Permission.STAFF_ASSIGN,
        Permission.STAFF_ROSTER_READ,
    }
    assert staff_permissions <= admin.permissions
    assert eventos.permissions & staff_permissions == {Permission.STAFF_ROSTER_READ}
    assert not compras.permissions & staff_permissions
    assert admin.is_active_admin and not eventos.is_active_admin


def test_ca16_17_disponibilidad_de_personal_solo_para_administrador() -> None:
    """HU16 (R-DIS-8): `staff:availability` solo lo tiene el administrador."""
    assert Permission.STAFF_AVAILABILITY in permissions_of(Role.ADMIN)
    assert Permission.STAFF_AVAILABILITY not in permissions_of(Role.EVENTS_MANAGER)
    assert Permission.STAFF_AVAILABILITY not in permissions_of(Role.PURCHASING_MANAGER)
    # R-STF-5/R-STF-16 y R-ASG-14: los permisos de staff no abren disponibilidad;
    # son permisos distintos (la matriz 403 por ruta se verifica en la API).
    otros_permisos_de_staff = {
        Permission.STAFF_MANAGE.value,
        Permission.STAFF_ROSTER_READ.value,
        Permission.STAFF_ASSIGN.value,
    }
    assert Permission.STAFF_AVAILABILITY.value not in otros_permisos_de_staff


def test_017_solo_admin_y_compras_gestionan_almacen_y_compras() -> None:
    eventos = _user(role=Role.EVENTS_MANAGER)
    compras = _user(role=Role.PURCHASING_MANAGER)
    admin = _user(role=Role.ADMIN)

    assert Permission.INVENTORY_READ in eventos.permissions
    assert Permission.INVENTORY_MANAGE not in eventos.permissions
    assert Permission.PURCHASING_MANAGE not in eventos.permissions
    for user in (compras, admin):
        assert {
            Permission.INVENTORY_READ,
            Permission.INVENTORY_MANAGE,
            Permission.PURCHASING_MANAGE,
        } <= user.permissions
