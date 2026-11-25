# Plan: Inventario, movimientos de almacén, proveedores y compras

- **Spec**: ./spec.md
- **Estado**: borrador

## 1. Módulos y fronteras
- `inventory` (nuevo): productos, movimientos, stock y alertas.
- `purchasing` (nuevo): proveedores, solicitudes y compras.
- `purchasing → inventory.public_api`: `product_lookup`, `low_stock_lookup` (faltantes) y `stock_receiver` (registra las entradas al recibir, en la misma transacción).
- `inventory → commercial.public_api.event_lookup` (lo crea el lote de personal): validar el evento de una salida.
- `identity`: `inventory:manage`, `inventory:read`, `purchasing:manage`.

## 2. Modelo de dominio
- `inventory.Product`: código (único, mayúsculas, ≤ 20), nombre, `Category` (R-INV-2), `Unit` (R-INV-1), `ProductKind` (CONSUMABLE/REUSABLE), stock mínimo ≥ 0, activo.
- `inventory.Movement` (inmutable): `MovementKind` = ENTRY, EXIT, RETURN, WASTE, ADJUSTMENT; cantidad > 0 (`Decimal`, 3 decimales) y signo según el tipo (ADJUSTMENT lleva signo); fecha; `event_id?` (obligatorio en EXIT y RETURN); costo unitario en céntimos (solo ENTRY); proveedor, lote y vencimiento (solo ENTRY); motivo (obligatorio en WASTE y ADJUSTMENT); usuario; `purchase_id?`.
- `inventory.StockLevel`: cantidad y costo promedio ponderado; `apply(movement)` rechaza dejarla negativa (`inventory.insufficient_stock`).
- `inventory.EventMaterials`: por evento y producto, salió, volvió, merma, y `pending_return` (solo reutilizables).
- `purchasing.Supplier`: razón social, `DocumentType` (RUC 11 dígitos / DNI 8), número único, contacto, teléfono, correo, dirección, activo.
- `purchasing.Purchase`: código `COM-AAAA-NNNN`, `event_id?`, estado (RN21), líneas (producto, cantidad pedida, costo unitario?, cantidad recibida, lote, vencimiento), proveedor (al ordenar), factura, total calculado. Transiciones: `order(supplier, costs)`, `receive(lines)`, `cancel(reason)`.

## 3. Casos de uso
| Caso de uso | Módulo | Errores (`code`) |
|---|---|---|
| `CreateProduct`, `UpdateProduct`, `SetProductActive`, `ListProducts` (con alertas), `GetProduct` (+ historial) | inventory | `inventory.code_taken` 409, `inventory.validation` 422 |
| `RecordEntry`, `RecordExit`, `RecordReturn`, `RecordWaste`, `RecordAdjustment` | inventory | `inventory.insufficient_stock` 409, `inventory.return_exceeds` 409, `inventory.event_not_assignable` 409, `inventory.product_inactive` 409 |
| `GetEventMaterials` | inventory | — |
| `CreateSupplier`, `UpdateSupplier`, `SetSupplierActive`, `ListSuppliers` | purchasing | `purchasing.document_taken` 409 |
| `CreatePurchaseRequest`, `SuggestShortages` | purchasing | `purchasing.validation` 422 |
| `OrderPurchase`, `ReceivePurchase`, `CancelPurchase`, `ListPurchases`, `GetPurchase` | purchasing | `purchasing.invalid_transition` 409, `purchasing.supplier_inactive` 409 |

## 4. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `GET/POST /v1/inventory/products`, `GET/PUT /v1/inventory/products/{id}` | `inventory_products_list/create/get/update` | read / manage |
| `POST /v1/inventory/products/{id}/activate`, `/deactivate` | `inventory_products_activate/deactivate` | manage |
| `GET /v1/inventory/products/{id}/movements` | `inventory_movements_list` | read |
| `POST /v1/inventory/movements/{entry,exit,return,waste,adjustment}` | `inventory_movements_entry` … | manage |
| `GET /v1/inventory/events/{event_id}/materials` | `inventory_event_materials` | read |
| `GET/POST /v1/purchasing/suppliers`, `GET/PUT …/{id}`, `…/{id}/activate`, `/deactivate` | `purchasing_suppliers_*` | manage |
| `GET /v1/purchasing/shortages` | `purchasing_shortages` | manage |
| `GET/POST /v1/purchasing/purchases`, `GET …/{id}` | `purchasing_purchases_list/create/get` | manage |
| `POST /v1/purchasing/purchases/{id}/{order,receive,cancel}` | `purchasing_purchases_order/receive/cancel` | manage |

## 5. Persistencia (una migración, encadenada después de la de pagos)
- `inventory_products` (código único), `inventory_movements` (append-only por trigger; `numeric(12,3)`; CHECK de campos según tipo), `inventory_stock` (product_id PK, `quantity numeric(12,3) CHECK (quantity >= 0)`, `avg_cost_cents`): se actualiza en la misma transacción que el movimiento, con `SELECT … FOR UPDATE`.
- `purchasing_suppliers` (documento único), `purchasing_purchases` (código único, CHECK de estado ↔ datos), `purchasing_purchase_lines` (FK mismo módulo; `product_id` sin FK).
- Sin FK entre módulos: `event_id`, `product_id`, `supplier_id` en movimientos son IDs.

## 6. Reglas aplicadas
RN18–RN25, RN21. Se agregan R-INV-1..5 y R-COM-1..2 a DOMAIN.md §11 (provisionales) y se cierra §10.3 provisionalmente.

## 7. Tests
- **Unit**: `StockLevel` (promedio ponderado, negativo), `Movement` (campos por tipo), `EventMaterials`, transiciones de `Purchase`, cada caso de uso con fakes, API (encargado de eventos solo lee).
- **Integración**: dos salidas simultáneas no dejan stock negativo; trigger append-only; `inventory_stock` = suma de movimientos; recibir una compra sube el stock y deja entradas con costo y proveedor; recibir dos veces falla.

## 8. Frontend
- Menú **Almacén**: productos con alertas (stock bajo, por vencer), formulario, detalle con historial; botones **Entrada**, **Salida**, **Devolución**, **Merma**, **Ajuste**.
- Evento: pestaña **Materiales** (salió / volvió / merma / falta devolver).
- Menú **Compras**: proveedores; compras con estados; **Nueva solicitud** con "Agregar faltantes"; **Ordenar** (proveedor y costos) y **Recibir** (cantidades, lote, vencimiento) con confirmación.

## 9. Riesgos
- Es el lote más grande y empieza de cero. Si falta tiempo, se recorta primero HU28 (solicitud con faltantes) y se compra directo.
- `numeric` en Python es `Decimal`: cuidar que Pydantic y el OpenAPI lo expongan como string decimal estable para el frontend.
