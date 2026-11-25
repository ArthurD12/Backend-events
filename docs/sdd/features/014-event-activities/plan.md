# Plan: Actividades y observaciones del evento

- **Spec**: ./spec.md
- **Estado**: borrador

## 1. Módulos y fronteras
- `commercial` (submódulo `events`): las actividades y observaciones son parte del evento.
- `identity.public_api.CoordinatorLookup` (ya existe): validar el responsable (usuario activo, administrador o encargado de eventos) y mostrar nombres.
- `identity`: permiso nuevo `event_notes:write` para los tres roles (R-ACT-5). Actividades siguen con `events:manage`; ver todo, con `events:read`.

## 2. Modelo de dominio (`commercial.domain.events`)
- `EventActivity`: id, event_id, descripción (1–200), estado `PENDING | DONE`, `responsible_id`, creado (usuario, fecha), completado (usuario, fecha) o `None`. `complete(by, now)` y `reopen(by, now)` cambian el estado y devuelven un `ActivityChange` (acción, usuario, fecha) para el historial (CA-13.3).
- `EventNote`: id, event_id, texto (1–1000), creado (usuario, fecha), última edición (usuario, fecha) o `None`. `edit(text, by, now)`.
- Reglas en `Event`: `can_manage_activities` (programado, confirmado, en ejecución) y `can_take_notes` (todo menos cancelado) (R-ACT-2).
- **R-ACT-6** *(equipo, provisional)*: una observación la edita **su autor o un administrador**.

## 3. Casos de uso
| Caso de uso | Tipo | Errores (`code`) |
|---|---|---|
| `AddActivity(event_id, description, responsible_id?)` | command | `event.not_found` 404, `event.activities_closed` 409, `activity.responsible_invalid` 422, `activity.validation` 422 |
| `CompleteActivity`, `ReopenActivity` | command | `activity.not_found` 404, `event.activities_closed` 409, `activity.already_done` / `activity.already_pending` 409 |
| `ChangeActivityResponsible` | command | `activity.responsible_invalid` 422 |
| `AddNote(event_id, text)` | command | `event.notes_closed` 409, `note.validation` 422 |
| `EditNote(note_id, text)` | command | `note.not_found` 404, `note.not_author` 403, `event.notes_closed` 409 |
| `GetEventLog(event_id)` | query | `event.not_found` 404 |

## 4. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `GET /v1/events/{id}/activities` | `events_activities_list` | `events:read` |
| `POST /v1/events/{id}/activities` | `events_activities_create` | `events:manage` |
| `POST /v1/activities/{id}/complete` · `/reopen` | `activities_complete` · `activities_reopen` | `events:manage` |
| `PUT /v1/activities/{id}/responsible` | `activities_responsible_update` | `events:manage` |
| `GET /v1/events/{id}/notes` | `events_notes_list` | `events:read` |
| `POST /v1/events/{id}/notes` | `events_notes_create` | `event_notes:write` |
| `PUT /v1/notes/{id}` | `notes_update` | `event_notes:write` |

Las respuestas traen el nombre del responsable, de quien creó y de quien completó o editó.

## 5. Persistencia (una migración)
- `commercial_event_activities` (FK a `commercial_events`, mismo módulo; índice por evento), `commercial_event_activity_changes` (historial, solo inserción), `commercial_event_notes` (FK a eventos; índice por evento y fecha).
- `responsible_id`, `created_by`, etc.: UUID **sin FK** a `identity` (regla 3).
- La migración se encadena al head de `developer-b` cuando se una; si antes entra otra (personal o pagos), se ajusta `down_revision`.

## 6. Tests
- **Unit**: estados permitidos, transiciones, autor o admin al editar, cada caso de uso con fakes, API (compras crea observación pero no actividad; 403 al editar nota ajena).
- **Integración**: crear, completar y reabrir guarda el historial; evento cancelado rechaza todo; finalizado acepta solo observaciones.

## 7. Frontend
- Detalle del evento, pestaña **Seguimiento**: lista de actividades con casilla (pendiente/completada), responsable y quién la completó; botón **Nueva actividad**.
- Debajo, **Bitácora**: observaciones de la más reciente a la más antigua, con autor, fecha y "editado"; caja para escribir; **Editar** en las propias (o todas, si es administrador).

## 8. Riesgos
- R-ACT-3 (borrar actividad) y R-ACT-6 (quién edita) son provisionales: cambiar cualquiera es una regla en el dominio, sin tocar las tablas.
