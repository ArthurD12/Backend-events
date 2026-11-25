# Plan: Ficha consolidada del evento

- **Spec**: ./spec.md
- **Estado**: borrador

## 1. Módulos
- `reporting.GetEventSheet(event_id, viewer_permissions)`: el único que junta módulos (como el dashboard).
- Lee de: `commercial.public_api` (evento, cliente, servicios, cuenta del contrato, actividades y observaciones), `inventory.public_api` (materiales del evento), `staff.public_api` (asignaciones del evento, **si existe**: puerto `EventStaffLookup` con un adaptador que devuelve `None` mientras Harold no lo publique).
- Se agregan a esos `public_api` las consultas de solo lectura que falten.

## 2. API
| Ruta | `operationId` | Permiso |
|---|---|---|
| `GET /v1/reports/events/{id}/sheet` | `reports_event_sheet` | `events:read` |

Respuesta por bloques: `event`, `client`, `services`, `staff` (o `null`), `materials`, `account` (o `null` sin `payments:record`), `follow_up`.

## 3. Persistencia
- Ninguna tabla nueva.

## 4. Tests
- Unit con fakes de cada lookup: bloques completos; `account` en `null` para compras; `staff` en `null` sin el módulo.
- Integración: evento real con pagos, salidas y actividades.

## 5. Frontend
- Evento: botón **Ficha** → página `/eventos/{id}/ficha` de una sola hoja con tarjetas (Resumen, Servicios, Equipo, Materiales, Finanzas, Seguimiento) y estilos de impresión (`@media print`).
