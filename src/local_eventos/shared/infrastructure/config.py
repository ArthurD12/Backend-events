"""Configuración de la aplicación, leída de variables de entorno o del archivo `.env`.

Ningún valor sensible tiene un valor por defecto: si falta, la aplicación no arranca (CA-9).
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_ASYNC_SCHEME = "postgresql+asyncpg"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    """URL de PostgreSQL con el driver async: postgresql+asyncpg://usuario:clave@host:puerto/bd"""

    @field_validator("database_url")
    @classmethod
    def _use_asyncpg(cls, url: str) -> str:
        return normalize_database_url(url)


def normalize_database_url(url: str) -> str:
    """Acepta también la URL tal como la entregan los proveedores (p. ej. Neon):
    `postgres://` o `postgresql://` con `sslmode=require` y `channel_binding=require`.

    asyncpg no entiende esos parámetros: usa `ssl=require` y negocia el resto solo.
    """
    parts = urlsplit(url)
    if parts.scheme not in {"postgres", "postgresql", _ASYNC_SCHEME}:
        return url
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(parts.query, keep_blank_values=True):
        if key == "sslmode":
            query.append(("ssl", value))
        elif key != "channel_binding":
            query.append((key, value))
    return urlunsplit(parts._replace(scheme=_ASYNC_SCHEME, query=urlencode(query)))


class CorsSettings(BaseSettings):
    """Desde qué páginas web se puede llamar a la API (no es un dato sensible).

    Por defecto, el frontend en desarrollo (`npm run dev` en el puerto 3000). En producción se
    define `CORS_ORIGINS` con la dirección real, p. ej. `["https://darze.example.com"]`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cors_origins: list[str] = ["http://localhost:3000"]


class AssistantSettings(BaseSettings):
    """Clave del proveedor del asistente (ADR 0005). Vacía: el asistente queda no disponible."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    anthropic_api_key: str = ""
