"""Normalización del texto de búsqueda de personal (HU15, CA-15.8).

La búsqueda por nombre ignora mayúsculas, tildes y espacios sobrantes: «Jose
Ramirez» encuentra a «José Ramírez». El documento se compara sin espacios ni
guiones, igual que lo normaliza `Document`. Solo stdlib: no agrega dependencias
(AGENTS.md, regla 11).
"""

from __future__ import annotations

import unicodedata


def _without_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def normalize_name(text: str) -> str:
    """Nombre comparable: sin tildes, en minúsculas y con espacios colapsados."""
    return " ".join(_without_accents(text).casefold().split())


def normalize_document(text: str) -> str:
    """Documento comparable: sin espacios ni guiones (mismo criterio que `Document`)."""
    return "".join(char for char in text if not char.isspace() and char != "-")
