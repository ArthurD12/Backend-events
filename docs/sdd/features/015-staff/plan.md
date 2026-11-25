# Plan: Personal, disponibilidad y asignaciones

- **Spec**: ./spec.md
- **Estado**: borrador

## 1. Módulos y fronteras
- `staff` (nuevo, hoy vacío): trabajadores, indisponibilidades y asignaciones.
- `staff` → `commercial.public_api`: nuevo `event_lookup(session)` → `EventInfo` (id, código, estado, fecha, hora de inicio y fin). Para validar el evento y tomar su horario por defecto.
- `commercial` → `staff.public_api` **solo por un puerto**: `CancelEvent` recibe un `AssignmentReleaser` (Protocol definido en `commercial.application`). Lo implementa `staff.public_api.assignment_releaser(session)` y se conecta en `commercial.presentation`. Así `commercial.application` no importa `staff` y no hay ciclo de imports (R-STF-5).
- `identity`: permisos nuevos `staff:manage` (administrador y encargado de eventos) y `staff:read` (los tres roles).

## 2. Modelo de dominio (`staff.domain`, sin frameworks)
- `Worker`: id, nombre, documento (`DocumentType` DNI/CE + número), teléfono, `WorkerFunction` (R-STF-1), `WorkerType` (R-STF-2), `reference_rate_cents` (≥ 0), activo, auditoría. Validaciones: DNI 8 dígitos, CE 9–12 alfanuméricos, teléfono 9 dígitos, nombre ≤ 120.
- `Period` (value object): `starts_at`, `ends_at` en UTC, `ends_at > starts_at`. `Period.on(date, start, end)` convierte de hora de Lima y suma un día si `end < start` (R-STF-4). `overlaps(other)` con intervalos semiabiertos `[inicio, fin)`: terminar a las 18:00 y empezar a las 18:00 no se cruza.
- `Unavailability`: id, worker_id, `Period`, motivo ≤ 200, auditoría.
- `Assignment`: id, worker_id, event_id, event_code (copia; el código no cambia), `WorkerFunction`, `Period`, `agreed_pay_cents` ≥ 0, estado `ACTIVE | WITHDRAWN`, retiro (motivo, usuario, fecha). `withdraw()` solo desde `ACTIVE`.
- `Availability` (resultado de consulta): `FREE | BUSY(event_code, period) | UNAVAILABLE(period)`; ocupado gana a no disponible (CA-16.4).

## 3. Casos de uso
| Caso de uso | Tipo | Errores (`code`) |
|---|---|---|
| `RegisterWorker`, `UpdateWorker` | command | `staff.document_taken` 409, `staff.validation` 422 |
| `SetWorkerActive` | command | `staff.worker_not_found` 404 |
| `ListWorkers` (función, tipo, estado, texto) | query | — |
| `AddUnavailability`, `RemoveUnavailability` | command | `staff.worker_not_found` 404, `staff.validation` 422 |
| `CheckAvailability` (fecha, inicio, fin, función?) | query | `staff.validation` 422 |
| `AssignWorker` | command | `staff.event_not_found` 404, `staff.event_not_assignable` 409, `staff.worker_inactive` 409, `staff.worker_unavailable` 409, `staff.assignment_overlap` 409 (con `event_code` y horario) |
| `WithdrawAssignment` | command | `staff.assignment_not_found` 404, `staff.assignment_already_withdrawn` 409 |
| `ListEventAssignments` | query | — |
| `ReleaseEventAssignments` (para `commercial`) | command | — |

`AssignWorker` revisa el cruce en aplicación para dar el mensaje con el código del evento. Si dos peticiones pasan la revisión a la vez, la restricción de exclusión rechaza la segunda y el repositorio traduce el `ExclusionViolation` a `staff.assignment_overlap` (sin código de evento en ese caso raro).

## 4. API (prefijo `/v1/staff`, tag `staff`)
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `GET /workers` | `staff_workers_list` | `staff:read` |
| `POST /workers` | `staff_workers_create` | `staff:manage` |
| `GET /workers/{id}` | `staff_workers_get` | `staff:read` |
| `PUT /workers/{id}` | `staff_workers_update` | `staff:manage` |
| `POST /workers/{id}/activate`, `/deactivate` | `staff_workers_activate`, `staff_workers_deactivate` | `staff:manage` |
| `GET /workers/{id}/unavailability` | `staff_unavailability_list` | `staff:read` |
| `POST /workers/{id}/unavailability` | `staff_unavailability_create` | `staff:manage` |
| `DELETE /unavailability/{id}` | `staff_unavailability_delete` | `staff:manage` |
| `GET /availability?date&start&end&function` | `staff_availability_check` | `staff:read` |
| `GET /events/{event_id}/assignments` | `staff_assignments_list` | `staff:read` |
| `POST /events/{event_id}/assignments` | `staff_assignments_create` | `staff:manage` |
| `POST /assignments/{id}/withdraw` | `staff_assignments_withdraw` | `staff:manage` |

La indisponibilidad sí se borra (no es una operación con historial: es un aviso del trabajador). Errores con el formato actual (`code`, `message`, `details`).

## 5. Persistencia (una migración, encadenada al head actual)
- `CREATE EXTENSION IF NOT EXISTS btree_gist` (viene con PostgreSQL; Neon la permite).
- `staff_workers`: documento único `(document_type, document_number)`; índice por función y activo.
- `staff_unavailability`: worker_id FK (mismo módulo), `period tstzrange`, CHECK `NOT isempty(period)`.
- `staff_assignments`: worker_id FK (mismo módulo), `event_id uuid` **sin FK** (regla 3), `event_code`, función, `period tstzrange`, `agreed_pay_cents ≥ 0`, estado, datos de retiro; CHECK estado ↔ datos de retiro.
- **RN12**: `EXCLUDE USING gist (worker_id WITH =, period WITH &&) WHERE (status = 'ACTIVE')`. `tstzrange(inicio, fin, '[)')`.
- Antes de crear la migración: avisar a Harold y verificar `uv run alembic heads` = un solo head.

## 6. Reglas aplicadas
RN02, RN03, RN11, RN12, RN13 (DOMAIN.md §5). Se agregan R-STF-1 a R-STF-7 al registro de decisiones (§11) como provisionales.

## 7. Tests
- **Unit** (sin base): `Period` (medianoche, bordes semiabiertos), `Worker` (validaciones), `Assignment.withdraw`, cada caso de uso con fakes y reloj falso; API con repos en memoria (401, 403 para compras, 404, 409, 422).
- **Integración** (Testcontainers): documento único; la restricción de exclusión rechaza el cruce aunque se salte la aplicación (insert directo); dos asignaciones que se tocan en el borde se aceptan; retirar libera el horario; cancelar el evento retira sus asignaciones.
- **Arquitectura**: `just arch` sigue verde (`commercial.application` no importa `staff`).

## 8. Frontend (`Frontend-events`)
- Menú **Personal**: tabla con filtros (función, tipo, estado, búsqueda), formulario de alta y edición, activar o desactivar, y en el detalle del trabajador sus indisponibilidades y sus asignaciones.
- **Disponibilidad**: fecha, horario y función → lista con etiqueta Libre (verde), Ocupado (rojo, con el evento) y No disponible (gris).
- **Detalle del evento**: sección **Personal asignado** (función, horario, pago acordado, retirar) y botón **Asignar**, que abre la lista de disponibilidad del horario del evento; el error de cruce se muestra con el código del evento.
- Regenerar `schema.d.ts` desde el `openapi.json` nuevo.

## 9. Riesgos
- R-STF-5 cambia `CancelEvent`: si Darze prefiere no liberar automáticamente, se quita el puerto y nada más.
- La restricción de exclusión necesita `btree_gist`. Si Neon no la permitiera, la migración falla en el deploy: se prueba primero con la base de Neon de desarrollo, no en producción.
- Documentación: `DOMAIN.md` §5 y §11, `ARCHITECTURE.md` (dependencia `staff` → `commercial`), `openapi.json`.
