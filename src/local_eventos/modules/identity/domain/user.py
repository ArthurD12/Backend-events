"""Usuario del sistema: una cuenta personal por trabajador de Darze (HU02, RN01).

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
La contraseña nunca llega aquí en texto: la entidad solo guarda su hash.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from uuid import UUID, uuid4

from local_eventos.modules.identity.domain.errors import UserValidationError
from local_eventos.modules.identity.domain.permissions import Permission, Role, permissions_of

PASSWORD_MIN_LENGTH = 8  # R-ID-1 (provisional, 22/11/2026)
_PASSWORD_MAX_LENGTH = 128
_NAME_MAX_LENGTH = 120
_EMAIL_MAX_LENGTH = 254
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class User:
    id: UUID
    name: str
    email: str
    password_hash: str
    role: Role
    active: bool = True

    @classmethod
    def create(
        cls, *, name: str, email: str, password_hash: str, role: Role, active: bool = True
    ) -> User:
        """Crea la cuenta. Que el correo no se repita se verifica en aplicación."""
        return cls(
            id=uuid4(),
            name=_clean_name(name),
            email=normalize_email(email),
            password_hash=password_hash,
            role=role,
            active=active,
        )

    def update(self, *, name: str, email: str, role: Role) -> None:
        """Valida todo antes de asignar: si un dato falla, no cambia nada."""
        new_name = _clean_name(name)
        new_email = normalize_email(email)
        self.name = new_name
        self.email = new_email
        self.role = role

    def set_password_hash(self, password_hash: str) -> None:
        self.password_hash = password_hash

    def deactivate(self) -> None:
        """Desactiva sin eliminar: su historial y sus operaciones se conservan (RN02)."""
        self.active = False

    def activate(self) -> None:
        self.active = True

    @property
    def is_active_admin(self) -> bool:
        return self.active and self.role is Role.ADMIN

    @property
    def permissions(self) -> frozenset[Permission]:
        return permissions_of(self.role)


def normalize_email(email: str) -> str:
    """El correo identifica la cuenta: sin espacios y en minúsculas ("Ana@X.pe" = "ana@x.pe")."""
    cleaned = email.strip().lower()
    if len(cleaned) > _EMAIL_MAX_LENGTH or not _EMAIL_PATTERN.match(cleaned):
        raise UserValidationError("user.email_invalid", "El correo electrónico no es válido.")
    return cleaned


def check_password_policy(password: str) -> None:
    """Mínimo 8 caracteres, sin exigir símbolos (R-ID-1). El máximo evita abusos al cifrar."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise UserValidationError(
            "user.password_too_short",
            f"La contraseña debe tener al menos {PASSWORD_MIN_LENGTH} caracteres.",
        )
    if len(password) > _PASSWORD_MAX_LENGTH:
        raise UserValidationError(
            "user.password_too_long",
            f"La contraseña no puede superar {_PASSWORD_MAX_LENGTH} caracteres.",
        )


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise UserValidationError("user.name_required", "El nombre es obligatorio.")
    if len(cleaned) > _NAME_MAX_LENGTH:
        raise UserValidationError(
            "user.name_too_long", f"El nombre no puede superar {_NAME_MAX_LENGTH} caracteres."
        )
    return cleaned
