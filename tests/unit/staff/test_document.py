"""Pruebas del documento del trabajador (HU15, R-STF-1). Sin base de datos."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from local_eventos.modules.staff.domain.document import Document, WorkerDocumentType
from local_eventos.modules.staff.domain.errors import StaffValidationError


def test_ca15_19_normaliza_y_valida() -> None:
    dni = Document(WorkerDocumentType.DNI, " 44 125-896 ")
    ce = Document(type=WorkerDocumentType.CE, number="001-234 567 890")

    assert dni.type is WorkerDocumentType.DNI
    assert dni.number == "44125896"
    assert ce.number == "001234567890"


@pytest.mark.parametrize("number", ["1234567", "123456789", "4412589A", "441258 96A"])
def test_dni_exige_exactamente_ocho_digitos(number: str) -> None:
    with pytest.raises(StaffValidationError) as error:
        Document(WorkerDocumentType.DNI, number)
    assert error.value.code == "staff.document_invalid"


@pytest.mark.parametrize("number", ["123456789", "1234567890", "123-456 789012"])
def test_ce_admite_entre_nueve_y_doce_digitos(number: str) -> None:
    expected = number.replace("-", "").replace(" ", "")
    assert Document(WorkerDocumentType.CE, number).number == expected


@pytest.mark.parametrize("number", ["12345678", "1234567890123"])
def test_ce_rechaza_fuera_de_rango(number: str) -> None:
    with pytest.raises(StaffValidationError) as error:
        Document(WorkerDocumentType.CE, number)
    assert error.value.code == "staff.document_invalid"


@pytest.mark.parametrize("number", ["", "   ", "- -", "4412-58 96A", "四四一二五八九六"])
def test_rechaza_vacio_o_no_numerico(number: str) -> None:
    with pytest.raises(StaffValidationError) as error:
        Document(WorkerDocumentType.DNI, number)
    assert error.value.code == "staff.document_invalid"


def test_documento_es_inmutable() -> None:
    document = Document(WorkerDocumentType.DNI, "44125896")

    with pytest.raises(FrozenInstanceError):
        document.number = "12345678"  # type: ignore[misc]
