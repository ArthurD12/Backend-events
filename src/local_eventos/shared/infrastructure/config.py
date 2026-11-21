"""Configuración de la aplicación, leída de variables de entorno o del archivo `.env`.

Ningún valor sensible tiene un valor por defecto: si falta, la aplicación no arranca (CA-9).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    """URL de PostgreSQL con el driver async: postgresql+asyncpg://usuario:clave@host:puerto/bd"""


class CorsSettings(BaseSettings):
    """Desde qué páginas web se puede llamar a la API (no es un dato sensible).

    Por defecto, el frontend en desarrollo (`npm run dev` en el puerto 3000). En producción se
    define `CORS_ORIGINS` con la dirección real, p. ej. `["https://darze.example.com"]`.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cors_origins: list[str] = ["http://localhost:3000"]
