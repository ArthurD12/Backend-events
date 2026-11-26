# ADR 0007 — Base de zonas horarias `tzdata`

- **Estado:** aceptada por el equipo (26/11/2026)
- **Contexto:** el sistema calcula fechas y horas en `America/Lima` con `zoneinfo` de la biblioteca estándar (fecha del evento, día de ejecución, reportes, PDF y asistente). `zoneinfo` lee la base de zonas horarias del sistema operativo; Linux y Docker la traen, pero **Windows no**, y ahí `ZoneInfo("America/Lima")` falla con `ZoneInfoNotFoundError`. La regla 11 de AGENTS.md pide un ADR para cualquier dependencia nueva.

## Decisión
Agregar el paquete `tzdata` (datos oficiales de la IANA publicados por la Python Software Foundation) a las dependencias de ejecución. `zoneinfo` lo usa automáticamente cuando el sistema no tiene la base.

## Consecuencias
- El backend y las pruebas funcionan igual en Windows, Linux y Docker sin instalar nada más.
- Es solo datos (sin código nativo) y se actualiza con `uv lock --upgrade-package tzdata` cuando cambien las reglas horarias.
- Documentado en `STACK.md`, `README.md` e `INSTALACION.md` (regla 13).
