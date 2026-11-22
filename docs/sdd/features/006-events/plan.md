# Plan: Convertir el contrato en evento

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 22/11/2026)

## 1. Módulos y fronteras
- **`commercial`**, submódulo `events` (ADR 0003): lee el contrato y su cotización del mismo módulo. FK `contract_id` (única), `quote_id` y `client_id`.
- **`identity.public_api`** expone `coordinator_lookup(session)`: usuarios **activos** con rol administrador o encargado de eventos (`id`, `name`). Sirve para validar al responsable y para la lista de la pantalla. No expone correos ni otros datos.
- Permisos nuevos: `events:manage` (administrador y encargado de eventos) y `events:read` (los tres roles, DOMAIN.md §9).

## 2. Modelo de dominio
**`Event`** (`commercial/domain/events`): `id`, `code`, `contract_id`, `quote_id`, `client_id`, `event_type`, `event_date`, `start_time`, `end_time`, `venue`, `guests`, `coordinator_id`, `status` (`SCHEDULED`, `CONFIRMED`, `IN_PROGRESS`, `FINISHED`, `CANCELLED`; nace en `SCHEDULED`), `services` (copia de las líneas: tipo, servicio, descripción, unidad y cantidad), `created_by`, `created_at`.
- `Event.from_contract(contract, quote, coordinator_id, …)`: exige `contract.can_become_event` (CA-10.1) y copia los datos (CA-10.2).
- **Contrato**: `cancel` rechaza con `contract.has_event` si ya tiene evento (R-EVT-3).

## 3. Casos de uso
| Caso de uso | Entrada | Errores (`code`) |
|---|---|---|
| `ConvertContractToEvent` | `contract_id`, `coordinator_id?` (por defecto, quien convierte) | `event.contract_not_ready` (409), `event.already_exists` (409), `event.coordinator_invalid` (422), `contract.not_found` (404) |
| `GetEvent`, `SearchEvents` | id; texto (código o cliente), estado, rango de fechas, página | `event.not_found` |
| `ListCoordinators` | — | — |

## 4. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `POST /v1/events` | `events_convert` | `events:manage` |
| `GET /v1/events` · `GET /v1/events/{id}` | `events_search` · `events_get` | `events:read` |
| `GET /v1/events/coordinators` | `events_coordinators` | `events:manage` |

`ContractOut` agrega `event_id`, para mostrar "Convertir en evento" o "Ver evento".

## 5. Persistencia
- `commercial_events`: `contract_id` **único** (CA-10.5, aun con dos peticiones simultáneas), `code` único, CHECK de estado e invitados > 0; índices por fecha y estado.
- `commercial_event_services`: copia de los servicios (`event_id` FK, posición, tipo, servicio, descripción, unidad, cantidad > 0).
- `commercial_event_counters` (`year`, `last`).

## 6. Tests
- **Unit**: `Event.from_contract` (solo firmado, copia exacta, horario que cruza medianoche), conversión con fakes (responsable válido o inválido, por defecto quien convierte, doble conversión), contrato con evento no se anula, API con permisos (compras: lee pero no convierte).
- **Integración**: evento único por contrato con dos conversiones simultáneas; de punta a punta: cotización → contrato → firma → evento.

## 7. Frontend
- Contrato firmado: botón **"Convertir en evento"** (con el responsable preseleccionado) o **"Ver evento"**.
- `/eventos` (lista con búsqueda, estado y fechas) y `/eventos/[id]` (detalle de solo lectura: datos, servicios, responsable y enlaces al contrato y la cotización).
- Menú "Eventos" para los tres roles.

## 8. Riesgos
- Sin migraciones sobre tablas existentes, salvo la nueva relación evento-contrato. Sin dependencias nuevas.
