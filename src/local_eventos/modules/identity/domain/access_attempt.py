"""Intento de inicio de sesión, para el historial de accesos (HU03).

Se registra cada intento, con éxito o sin él. Es de solo inserción: nunca se modifica.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class AccessResult(StrEnum):
    SUCCESS = "SUCCESS"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INACTIVE_USER = "INACTIVE_USER"


@dataclass(frozen=True)
class AccessAttempt:
    email: str
    user_id: UUID | None
    result: AccessResult
    occurred_at: datetime
