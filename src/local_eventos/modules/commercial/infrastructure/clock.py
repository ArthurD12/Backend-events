"""Reloj del sistema para cotizaciones: instante en UTC y fecha de Lima.

Perú no usa horario de verano: Lima es siempre UTC−5. Se usa un desfase fijo en vez de la base
de zonas horarias porque Windows no la trae instalada (ver INSTALACION.md, problemas frecuentes).
"""

from datetime import UTC, date, datetime, timedelta, timezone

LIMA = timezone(timedelta(hours=-5), "America/Lima")


class LimaClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self) -> date:
        return datetime.now(LIMA).date()
