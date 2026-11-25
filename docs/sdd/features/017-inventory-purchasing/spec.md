# Spec: Inventario, movimientos de almacén, proveedores y compras

- **ID**: 017-inventory-purchasing
- **Estado**: aprobado (César Suclupe, 25/11/2026)
- **Módulos afectados**: `inventory` (nuevo), `purchasing` (nuevo), `commercial` (consulta de eventos), `identity` (permisos)
- **Historias**: HU23 (#20), HU26 (#23), HU27 (#28), HU28 (#29, adaptada), HU29 (#30)

## 1. Problema y objetivo
El almacén de Darze (insumos, vajilla, mantelería) se lleva en Excel. No se sabe cuánto hay, qué falta para un evento ni qué vajilla no volvió. El objetivo es registrar productos y cada movimiento, ver el stock y sus alertas, controlar lo que sale y vuelve de cada evento, y comprar a proveedores lo que falta.

## 2. Actores
- **Encargado de compras y almacén** y **administrador** (`inventory:manage`, `purchasing:manage`): todo el almacén y las compras (DOMAIN.md §9).
- **Encargado de eventos** (`inventory:read`): consulta stock y lo que salió para sus eventos.

## 3. Historias
- **HU23**: registrar productos y consultar sus existencias.
- **HU26**: registrar salidas, devoluciones y mermas por evento.
- **HU27**: registrar y consultar proveedores.
- **HU28**: generar una solicitud de compra con los materiales faltantes.
- **HU29**: registrar y controlar la recepción de compras.

## 4. Criterios de aceptación
### HU23 — Productos y existencias
- **CA-23.1**: Producto con código único, nombre, categoría, unidad de medida, stock mínimo, tipo (**consumible** o **reutilizable**) y estado.
- **CA-23.2**: Una **entrada** registra cantidad, costo unitario, proveedor (opcional), lote (opcional) y vencimiento (opcional).
- **CA-23.3**: Un producto con movimientos no se elimina; solo se desactiva. Uno sin movimientos tampoco se elimina (RN02): se desactiva.
- **CA-23.4**: Stock actual = suma de movimientos; se ve el historial de movimientos del producto.
- **CA-23.5**: Alertas en la lista: `is_low_stock` (stock ≤ mínimo) y `expiring_soon` (alguna entrada con stock vigente vence en 15 días o menos, o ya venció).

### HU26 — Salidas, devoluciones y mermas
- **CA-26.1**: Una **salida** indica evento, producto, cantidad, fecha y responsable (quien registra). El evento debe estar programado, confirmado o en ejecución.
- **CA-26.2**: No se saca más que el stock disponible (RN20): `inventory.insufficient_stock` (409) con el disponible.
- **CA-26.3**: Una **devolución** regresa al almacén lo que salió para un evento y no se usó, o la vajilla. No supera lo que salió menos lo ya devuelto y lo perdido.
- **CA-26.4**: Una **merma** registra cantidad y motivo (RN24). Puede ser de almacén o de un evento.
- **CA-26.5**: Todos los movimientos actualizan el stock y los de evento quedan asociados a él (RN22).
- **CA-26.6**: Por evento se ve qué salió, qué volvió, qué se perdió y qué **reutilizable falta devolver**.

### HU27 — Proveedores
- **CA-27.1**: Razón social, documento (RUC o DNI, único), contacto, teléfono, correo y dirección opcional.
- **CA-27.2**: Búsqueda por nombre o documento, sin distinguir tildes.
- **CA-27.3**: Se edita y se desactiva; no se elimina.

### HU28 — Solicitud de compra (adaptada)
- **CA-28.1**: Una solicitud tiene líneas (producto, cantidad) y se puede vincular a un evento.
- **CA-28.2**: El botón **"Agregar faltantes"** propone, para los productos con stock bajo, la cantidad para volver al mínimo; se editan antes de guardar.
- **CA-28.3**: El cálculo de faltantes **por menú y por invitados** (HU24–HU25) queda para el lote de prioridad 2; cuando exista, alimentará esta misma solicitud.

### HU29 — Compras y recepción
- **CA-29.1**: Estados `solicitada → ordenada → recibida | cancelada` (RN21). Al ordenar se elige proveedor y costo unitario de cada línea.
- **CA-29.2**: Al **recibir** se confirman cantidades reales, lote y vencimiento por línea; se generan las entradas de almacén con su costo y proveedor. Solo entonces sube el stock.
- **CA-29.3**: Recibir es una sola vez y pide confirmación. Una compra recibida o cancelada no cambia.
- **CA-29.4**: Se registra el número de factura o boleta del proveedor (opcional) y el total.

## 5. Reglas
- **R-INV-1** *(equipo, provisional)*: unidades de lista fija: unidad, kg, g, litro, ml, docena, paquete, caja. Cantidades con hasta 3 decimales.
- **R-INV-2** *(equipo, provisional)*: categorías de producto de lista fija: Insumos, Bebidas, Vajilla, Cristalería, Cubiertos, Mantelería, Mobiliario, Descartables, Limpieza, Otros.
- **R-INV-3** *(equipo, provisional; responde DOMAIN.md §10.3)*: **costo promedio ponderado** para mostrar el valor del stock. El lote y el vencimiento sirven para las alertas; las salidas no se asignan a lotes.
- **R-INV-4** *(equipo, provisional)*: el vencimiento próximo es a **15 días**.
- **R-INV-5** *(equipo, provisional)*: los movimientos no se editan ni se borran. Un error se corrige con un **ajuste** (positivo o negativo) con motivo (regla 5).
- **R-COM-1** *(equipo, provisional)*: pagar al proveedor se registra aparte como egreso de insumos (HU21). Recibir la compra no crea el egreso.
- **R-COM-2** *(equipo, provisional)*: la recepción es completa: no hay recepciones parciales. Si llegó menos, se recibe la cantidad real.

## 6. Fuera de alcance
- HU24 (insumos por menú) y HU25 (requerimiento por evento): prioridad 2.
- HU30 (consultar y documentar compras con adjuntos).
- Varios almacenes, transferencias y códigos de barras.

## 7. No funcionales
- Dos salidas simultáneas no dejan stock negativo: bloqueo de la fila del producto (`FOR UPDATE`) y CHECK en la base.
- Append-only en movimientos (trigger que rechaza UPDATE/DELETE).

## 8. Preguntas abiertas
- [ ] R-INV-3: confirmar con Darze el costo promedio ponderado.
- [ ] ¿El encargado de eventos puede registrar salidas para su evento, o solo almacén?
