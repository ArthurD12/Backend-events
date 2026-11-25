"""Búsqueda sin distinguir mayúsculas ni tildes, como la de clientes (CA-15.6).

"Jose Ramirez" encuentra a "José Ramírez". La base aplica la misma tabla con `translate()`.
Es una copia de la regla de `commercial`: un módulo no importa capas internas de otro.
"""

WITH_ACCENTS = "áéíóúàèìòùäëïöüñ"
WITHOUT_ACCENTS = "aeiouaeiouaeioun"

_TABLE = str.maketrans(WITH_ACCENTS, WITHOUT_ACCENTS)


def normalize(text: str) -> str:
    return text.lower().translate(_TABLE)
