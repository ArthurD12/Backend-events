"""Traducción entre `Period` (dominio) y `tstzrange` `[inicio, fin)` (PostgreSQL)."""

from datetime import datetime

from sqlalchemy.dialects.postgresql import Range

from local_eventos.modules.staff.domain.period import Period


def to_range(period: Period) -> Range[datetime]:
    return Range(period.starts_at, period.ends_at, bounds="[)")


def to_period(value: Range[datetime]) -> Period:
    assert value.lower is not None and value.upper is not None  # CHECK NOT isempty(period)
    return Period(starts_at=value.lower, ends_at=value.upper)
