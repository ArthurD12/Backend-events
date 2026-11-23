# Plan: Cancelar un evento

- **Spec**: ./spec.md
- **Estado**: borrador, pendiente de aprobación

## 1. Módulos y fronteras
- `commercial`: el caso de uso cancela el evento y anula el contrato (mismo módulo).
- `ledger.public_api` (`payment_recorder`): registra la devolución, en la misma transacción.

## 2. Modelo de dominio
- `Event.cancel(reason, cancelled_by, now)`: exige estado programado o confirmado (`event.not_cancellable`, 409) y motivo (`event.reason_required`, 422). Guarda `Cancellation` (motivo, usuario, fecha y hora) y pasa a `CANCELLED`.
- El contrato se anula con su método `cancel` actual (motivo, devolución y pago).

## 3. Casos de uso
| Caso de uso | Entrada | Errores (`code`) |
|---|---|---|
| `CancelEvent` | `event_id`, `reason`, `refund_cents?`, `refund?` (fecha, medio, referencia), `note?` | `event.not_found` (404), `event.not_cancellable` (409), `event.reason_required` (422), `contract.refund_invalid` (422), `payment.*` (422) |

Orden: validar el evento y el contrato (incluida la devolución) **antes** de registrar el pago; después registrar la devolución, cancelar el evento y anular el contrato.

## 4. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `POST /v1/events/{id}/cancel` | `events_cancel` | `events:manage` y `payments:record` |

`EventOut` agrega `cancellation` (motivo, nota, fecha y hora) y `refund_cents`.

## 5. Persistencia
- Migración: `commercial_events` agrega `cancel_reason`, `cancelled_by` y `cancelled_at`, con CHECK `(status = 'CANCELLED') = (cancel_reason IS NOT NULL)`.
- El trigger de R-EVT-3 cambia: el contrato con evento se puede anular **solo si su evento está cancelado**.

## 6. Tests
- **Unit**: `Event.cancel` (estados permitidos, motivo), `CancelEvent` con fakes (con y sin devolución; devolución inválida no guarda nada; el contrato queda anulado), API con permisos (compras no cancela).
- **Integración**: de punta a punta (contrato → firma → evento → cancelar con devolución → contrato anulado con sus pagos); la base sigue rechazando anular el contrato de un evento no cancelado.

## 7. Frontend
- Detalle del evento: botón **"Cancelar evento"** (administrador y encargado de eventos) con el mismo formulario que anular contrato: motivo, devolución opcional y nota.
- Evento cancelado: etiqueta "Cancelado" y recuadro con el motivo y la devolución.
- Contrato: el aviso "ya es un evento" pasa a decir que se anula cancelando el evento, con un enlace al evento.

## 8. Riesgos
- R-EVT-4 y R-EVT-5 son provisionales: si el Product Owner decide otra cosa (por ejemplo, reprogramar sin anular el contrato), cambia el caso de uso, pero no la tabla.
