"""Conversión entre la hora local de `America/Lima` y UTC (HU16).

Perú no aplica horario de verano: se usa el offset fijo `-05:00`, como el resto del
proyecto (R-COT-1, R-ASG-4). Estas funciones puras centralizan la conversión para
que los value objects de horario no dupliquen la lógica.

Python puro: este archivo no importa FastAPI, SQLAlchemy ni Pydantic (AGENTS.md, regla 2).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, timezone

LIMA = timezone(timedelta(hours=-5), "America/Lima")
"""Zona horaria de `America/Lima` con offset fijo `-05:00`, sin horario de verano."""


def local_to_utc(day: date, local_time: time) -> datetime:
    """Interpreta una fecha y hora locales de Lima y devuelve el instante UTC aware.

    Args:
        day: Fecha local (sin zona horaria).
        local_time: Hora local de Lima (sin zona horaria).

    Returns:
        El instante equivalente en UTC, con `tzinfo=UTC`.
    """
    return datetime.combine(day, local_time, tzinfo=LIMA).astimezone(UTC)


def utc_to_local(value: datetime) -> datetime:
    """Convierte un instante UTC aware a la fecha y hora local de Lima.

    Args:
        value: Instante con zona horaria (normalmente UTC).

    Returns:
        El mismo instante expresado en `America/Lima` (offset `-05:00`).

    Raises:
        ValueError: Si `value` no es un `datetime` con zona horaria.
    """
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("La fecha y hora deben incluir zona horaria.")
    return value.astimezone(LIMA)
