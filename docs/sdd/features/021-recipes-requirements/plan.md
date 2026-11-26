# Plan: Insumos por servicio, requerimiento del evento y documento de compra

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 26/11/2026)

## 1. Módulos
- `inventory`: `Recipe` (por `service_id` del catálogo, sin FK), `Reservation`, `EventRequirement`. Lee `catalog.public_api` (servicio y su forma de cobro) y `commercial.public_api` (`event_detail`: estado, invitados, servicios contratados con `service_id` y cantidad).
- `purchasing`: "faltantes del evento" (usa `inventory.public_api.event_requirement`), PDF de compra (ReportLab, como `quote_pdf.py`), egreso con `ledger.public_api` (registrar movimiento).
- `commercial.CancelEvent` / `FinishEvent` liberan reservas por un puerto (como R-STF-5): `ReservationReleaser` en `commercial.application`, conectado en `commercial.presentation` con `inventory.public_api`. Sin ciclos de import.

## 2. API
| Ruta | `operationId` | Permiso |
|---|---|---|
| `GET/PUT /v1/inventory/recipes/{service_id}` | `inventory_recipe_get` / `inventory_recipe_put` | read / manage |
| `GET /v1/inventory/events/{event_id}/requirement` | `inventory_event_requirement` | `inventory:read` |
| `POST /v1/inventory/events/{event_id}/reservations` · `DELETE …/{product_id}` | `inventory_reservations_create` / `_delete` | manage |
| `POST /v1/purchasing/purchases/from-event/{event_id}` | `purchasing_purchases_from_event` | `purchasing:manage` |
| `GET /v1/purchasing/purchases/{id}/pdf` | `purchasing_purchases_pdf` | `purchasing:manage` |
| `POST /v1/purchasing/purchases/{id}/expense` | `purchasing_purchases_expense` | `purchasing:manage` y `payments:record` |

## 3. Persistencia (una migración, encadenada al head)
- `inventory_recipe_lines` (service_id, product_id, quantity numeric(12,3) > 0, basis PER_PERSON|PER_SERVICE; único service+product).
- `inventory_reservations` (event_id, product_id, quantity > 0, estado ACTIVE|CONSUMED|RELEASED, auditoría); disponible = stock − reservas activas (FOR UPDATE como en salidas).
- `purchasing_purchases.expense_movement_id` (nullable, único) para "una sola vez".

## 4. Tests
- Unit: cálculo del requerimiento (por persona/servicio, redondeo, sin receta, faltante ≥ 0), reservas (no negativo, consumo en salida, liberación), compra desde evento, PDF (contiene código y total), egreso único.
- Integración: escenario evento + receta + stock + reserva + salida + compra desde faltantes + recepción + egreso.

## 5. Frontend
- Catálogo → servicio: sección **Insumos** (tabla editable producto / cantidad / por persona o por servicio, Guardar).
- Evento → pestaña **Materiales**: bloque **Requerimiento** (tabla requerido / salido / reservado / disponible / faltante en rojo), **Reservar** y **Generar solicitud de compra**.
- Compra: botones **Descargar PDF** y **Registrar egreso** (si recibida).
