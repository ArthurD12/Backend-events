"""Búsqueda sin distinguir mayúsculas ni tildes: "azucar" encuentra "Azúcar".

PostgreSQL aplica la misma tabla de equivalencias con `translate()`, así la búsqueda en
memoria (pruebas) y en la base coinciden.
"""

WITH_ACCENTS = "áéíóúàèìòùäëïöüñ"
WITHOUT_ACCENTS = "aeiouaeiouaeioun"

_TABLE = str.maketrans(WITH_ACCENTS, WITHOUT_ACCENTS)


def normalize(text: str) -> str:
    return text.lower().translate(_TABLE)
