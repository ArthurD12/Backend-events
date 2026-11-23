# ADR 0002 — Adaptación al dominio de Darze

- **Estado:** propuesta (pendiente de aprobación del equipo)
- **Contexto:** la estructura inicial del repositorio describía un local de eventos con salones alquilados por horas. El proyecto real es el sistema de **Darze**, empresa de catering que atiende en el lugar del cliente, con el flujo `cotización → contrato → evento` validado por la empresa (documento del proyecto: RN01–RN33, RF01–RF104, HU01–HU43).

## Decisiones
| Tema | Decisión | Motivo |
|---|---|---|
| Arquitectura | Se mantiene el monolito modular con Clean Architecture y las reglas de ADR 0001 | Sigue siendo adecuada para una organización y dos desarrolladores |
| Módulos eliminados | `venues` (salones) y `bookings` (reservas por horas) | Darze no tiene salones propios ni alquila por horas |
| Módulos nuevos | `quotes`, `contracts`, `events`, `staff`, `purchasing`, `assistant` | Corresponden a las épicas E03–E05, E07 y E09 del Product Backlog |
| Módulos que se mantienen | `identity`, `clients`, `catalog` (servicios), `inventory` (almacén y requerimientos), `ledger` (pagos e ingresos), `reporting` (dashboard y reportes) | Coinciden con el dominio de Darze |
| Restricción de solape | Pasa de reservas por salón a **asignaciones por trabajador** (RN12) | Es el recurso que no puede usarse dos veces a la misma hora en Darze |
| Agente de IA | Módulo `assistant` dentro del backend, solo de consulta, con funciones controladas, permisos por rol y registro de cada consulta. El modelo de lenguaje es un proveedor externo detrás de un puerto | El agente es parte central del producto (HU35–HU40) y no un servicio opcional; reemplaza la integración por push de ADR 0001 |

## Consecuencias
- `docs/DOMAIN.md`, `AGENTS.md`, `README.md`, `ARCHITECTURE.md` y la skill de dominio se actualizan al nuevo dominio.
- El nombre del paquete `local_eventos` se mantiene por ahora para no romper rutas; renombrarlo requiere una decisión aparte.
- El proveedor del modelo de lenguaje (OpenAI API según el documento del proyecto) se agrega como dependencia con su propio ADR cuando se implemente `assistant`.
