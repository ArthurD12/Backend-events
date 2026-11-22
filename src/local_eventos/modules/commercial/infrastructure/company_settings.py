"""Datos de Darze para los documentos, leídos del `.env` (ADR 0004).

Todos son opcionales salvo el nombre comercial. Lo que no esté configurado no se imprime.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict

from local_eventos.modules.commercial.application.quotes.ports.document import CompanyProfile


class CompanySettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="COMPANY_", extra="ignore")

    name: str = "Darze"
    ruc: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None

    def profile(self) -> CompanyProfile:
        def clean(value: str | None) -> str | None:
            return value.strip() or None if value else None

        return CompanyProfile(
            name=self.name.strip() or "Darze",
            ruc=clean(self.ruc),
            address=clean(self.address),
            phone=clean(self.phone),
            email=clean(self.email),
        )
