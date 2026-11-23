"""Regla de búsqueda de clientes: sin distinguir mayúsculas ni tildes (DOMAIN.md §4.1, regla 2).

"Jose Ramirez" encuentra a "José Ramírez". La base de datos aplica la misma tabla de
equivalencias con `translate()`, así la búsqueda en memoria y en PostgreSQL coinciden.
"""

WITH_ACCENTS = "áéíóúàèìòùäëïöüñ"
WITHOUT_ACCENTS = "aeiouaeiouaeioun"

_TABLE = str.maketrans(WITH_ACCENTS, WITHOUT_ACCENTS)


def normalize(text: str) -> str:
    """Minúsculas y sin tildes: la forma en que se comparan nombres al buscar."""
    return text.lower().translate(_TABLE)
