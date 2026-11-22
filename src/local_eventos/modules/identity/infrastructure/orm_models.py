"""Tablas de identidad en PostgreSQL (HU01–HU03). Prefijo `identity_` por ser de este módulo.

Estas clases describen las tablas, no son las entidades del dominio: los repositorios
traducen entre unas y otras.
"""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from local_eventos.shared.infrastructure.orm import Base


class UserRow(Base):
    __tablename__ = "identity_users"
    __table_args__ = (
        CheckConstraint(
            "role IN ('ADMIN', 'EVENTS_MANAGER', 'PURCHASING_MANAGER')", name="role_valid"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(254))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    active: Mapped[bool]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# El correo no se repite sin importar mayúsculas (CA-02.2), ni registrándolo dos a la vez.
Index("uq_identity_users_email_lower", func.lower(UserRow.email), unique=True)


class SessionRow(Base):
    """Solo se guarda el hash del refresh token: si alguien lee la tabla, no puede usarlo."""

    __tablename__ = "identity_sessions"

    id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("identity_users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AccessLogRow(Base):
    """Historial de accesos (HU03). Un trigger de la migración impide UPDATE y DELETE."""

    __tablename__ = "identity_access_log"
    __table_args__ = (
        CheckConstraint(
            "result IN ('SUCCESS', 'INVALID_CREDENTIALS', 'INACTIVE_USER')", name="result_valid"
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    email: Mapped[str] = mapped_column(String(254))
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("identity_users.id"), index=True)
    result: Mapped[str] = mapped_column(String(20))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
