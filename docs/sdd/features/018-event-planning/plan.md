# Plan: Planificación y estado del evento

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 25/11/2026)

## 1. Módulos
- `commercial` (eventos). `identity.public_api.CoordinatorLookup` para el responsable.

## 2. Dominio
- `Event.update_planning(date, start, end, venue, guests, coordinator_id, by, now, today)` → `EventChange` con los campos cambiados (antes/después). `event.not_editable` (409) fuera de programado/confirmado.
- `Event.confirm(by, now)`, `Event.start(by, now, today)` (solo el día del evento), `Event.finish(by, now)`: `event.invalid_transition` (409).
- `EventChange` (inmutable): acción (`PLANNING_UPDATED`, `CONFIRMED`, `STARTED`, `FINISHED`, `CANCELLED`), detalle JSON de campos, usuario, fecha.

## 3. Casos de uso y API
| Caso de uso | Ruta | `operationId` | Permiso |
|---|---|---|---|
| `UpdateEventPlanning` | `PUT /v1/events/{id}/planning` | `events_planning_update` | `events:manage` |
| `ConfirmEvent` / `StartEvent` / `FinishEvent` | `POST /v1/events/{id}/{confirm,start,finish}` | `events_confirm` / `events_start` / `events_finish` | `events:manage` |
| `ListEventChanges` | `GET /v1/events/{id}/changes` | `events_changes_list` | `events:read` |

La respuesta de `events_planning_update` incluye `warnings: ["staff_may_need_review"]` si cambian fecha u horario (R-EVT-9).

## 4. Persistencia
- `commercial_event_changes` (FK a eventos, solo inserción con trigger). `CancelEvent` también escribe su cambio.
- Migración encadenada al head de `developer-b`.

## 5. Tests
- Unit: transiciones permitidas y prohibidas, día del evento para iniciar, campos inválidos, historial; API con permisos.
- Integración: editar y avanzar estados deja historial; el trigger rechaza UPDATE/DELETE.

## 6. Frontend
- Evento: botón **Editar planificación** (modal con los campos y el aviso de personal); **stepper** de estados con el botón del siguiente paso; pestaña **Historial**.
