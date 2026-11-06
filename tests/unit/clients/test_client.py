"""Pruebas de la entidad Cliente (HU04). Sin base de datos."""

import pytest

from local_eventos.modules.clients.domain.client import (
    Client,
    ClientValidationError,
    DocumentType,
)


def _register(**overrides: str | None) -> Client:
    data: dict[str, str | None] = {
        "name": "Familia Quispe Mamani",
        "document_number": "44125896",
        "phone": "987 654 321",
    }
    data.update(overrides)
    return Client.register(
        name=data["name"] or "",
        document_type=DocumentType.DNI,
        document_number=data["document_number"] or "",
        phone=data["phone"] or "",
        email=data.get("email"),
        address=data.get("address"),
    )


def test_hu04_registra_cliente_activo_con_datos_limpios() -> None:
    client = _register(name="  Familia   Quispe  ", email="María@Correo.PE")

    assert client.active is True
    assert client.name == "Familia Quispe"
    assert client.phone == "987654321"
    assert client.email == "maría@correo.pe"
    assert client.address is None


def test_hu04_correo_y_direccion_son_opcionales() -> None:
    client = _register(email=None, address="   ")

    assert client.email is None
    assert client.address is None


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"name": "   "}, "client.name_required"),
        ({"name": "x" * 151}, "client.name_too_long"),
        ({"document_number": "1234"}, "client.document_invalid"),
        ({"document_number": "4412589A"}, "client.document_invalid"),
        ({"phone": "12"}, "client.phone_invalid"),
        ({"email": "sin-arroba"}, "client.email_invalid"),
    ],
)
def test_hu04_rechaza_datos_invalidos(overrides: dict[str, str], code: str) -> None:
    with pytest.raises(ClientValidationError) as error:
        _register(**overrides)

    assert error.value.code == code


def test_hu04_ruc_exige_11_digitos() -> None:
    with pytest.raises(ClientValidationError):
        Client.register(
            name="Empresa FAMAQ S.A.C.",
            document_type=DocumentType.RUC,
            document_number="44125896",
            phone="014567890",
        )

    company = Client.register(
        name="Empresa FAMAQ S.A.C.",
        document_type=DocumentType.RUC,
        document_number="20547896321",
        phone="014567890",
    )
    assert company.document.number == "20547896321"


def test_hu04_actualiza_contacto_sin_cambiar_documento() -> None:
    client = _register()
    document = client.document

    client.update_contact(name="Familia Quispe", phone="912345678", address="SJL, Lima")

    assert client.phone == "912345678"
    assert client.address == "SJL, Lima"
    assert client.document == document


def test_hu04_desactivar_conserva_el_cliente() -> None:
    client = _register()

    client.deactivate()
    assert client.active is False

    client.activate()
    assert client.active is True
