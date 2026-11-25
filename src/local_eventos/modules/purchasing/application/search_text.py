"""Búsqueda sin distinguir mayúsculas ni tildes; PostgreSQL usa la misma tabla con `translate()`."""

WITH_ACCENTS = "áéíóúàèìòùäëïöüñ"
WITHOUT_ACCENTS = "aeiouaeiouaeioun"

_TABLE = str.maketrans(WITH_ACCENTS, WITHOUT_ACCENTS)


def normalize(text: str) -> str:
    return text.lower().translate(_TABLE)
