"""Pruebas de la normalización de búsqueda de personal (HU15, CA-15.8). Sin base de datos."""

from __future__ import annotations

import pytest

from local_eventos.modules.staff.application.search_text import (
    normalize_document,
    normalize_name,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("José Ramírez", "jose ramirez"),
        ("JOSÉ   RAMÍREZ", "jose ramirez"),
        ("  María   del   Carmen  ", "maria del carmen"),
        ("Ñandú Muñoz", "nandu munoz"),
        ("Müller", "muller"),
    ],
)
def test_normalize_name_sin_tildes_mayusculas_ni_espacios_sobrantes(
    raw: str, expected: str
) -> None:
    assert normalize_name(raw) == expected


def test_normalize_name_es_idempotente() -> None:
    once = normalize_name("José  Ramírez")
    assert normalize_name(once) == once


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" 44 125-896 ", "44125896"),
        ("001-234 567 890", "001234567890"),
        ("", ""),
        (" - ", ""),
    ],
)
def test_normalize_document_quita_espacios_y_guiones(raw: str, expected: str) -> None:
    assert normalize_document(raw) == expected
