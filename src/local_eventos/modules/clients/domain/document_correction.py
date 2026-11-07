"""Registro de auditoría de una corrección de documento (RN03): quién, cuándo, qué y por qué."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from local_eventos.modules.clients.domain.client import Document


@dataclass(frozen=True)
class DocumentCorrection:
    client_id: UUID
    previous: Document
    new: Document
    reason: str
    corrected_by: UUID
    corrected_at: datetime
