"""La URL de la base de datos se acepta tal como la entrega el proveedor (despliegue en Neon)."""

import pytest

from local_eventos.shared.infrastructure.config import normalize_database_url


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        (
            "postgresql://darze:clave@ep-x.us-east-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require",
            "postgresql+asyncpg://darze:clave@ep-x.us-east-2.aws.neon.tech/neondb?ssl=require",
        ),
        ("postgres://u:p@host:5432/bd", "postgresql+asyncpg://u:p@host:5432/bd"),
        (
            "postgresql+asyncpg://darze:clave@127.0.0.1:5433/darze?ssl=disable",
            "postgresql+asyncpg://darze:clave@127.0.0.1:5433/darze?ssl=disable",
        ),
        ("sqlite:///x.db", "sqlite:///x.db"),
    ],
)
def test_normaliza_la_url(given: str, expected: str) -> None:
    assert normalize_database_url(given) == expected
