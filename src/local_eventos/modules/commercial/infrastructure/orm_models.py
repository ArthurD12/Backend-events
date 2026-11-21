"""Tablas de clientes en PostgreSQL (HU04).

Estas clases describen las tablas, no son la entidad `Client` del dominio: el repositorio
traduce entre unas y otras. Prefijo `commercial_` por ser del módulo comercial (ADR 0003).
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base


class ClientRow(Base):
    __tablename__ = "commercial_clients"
    __table_args__ = (
        # El documento no se repite, aunque dos personas registren al mismo cliente a la vez.
        UniqueConstraint("document_type", "document_number"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(150))
    document_type: Mapped[str] = mapped_column(String(3))
    document_number: Mapped[str] = mapped_column(String(11))
    phone: Mapped[str] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DocumentCorrectionRow(Base):
    """Auditoría de correcciones de documento (RN03). Solo se insertan filas, nunca se editan."""

    __tablename__ = "commercial_client_document_corrections"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[UUID] = mapped_column(ForeignKey("commercial_clients.id"), index=True)
    previous_document_type: Mapped[str] = mapped_column(String(3))
    previous_document_number: Mapped[str] = mapped_column(String(11))
    new_document_type: Mapped[str] = mapped_column(String(3))
    new_document_number: Mapped[str] = mapped_column(String(11))
    reason: Mapped[str] = mapped_column(Text)
    corrected_by: Mapped[UUID]
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
