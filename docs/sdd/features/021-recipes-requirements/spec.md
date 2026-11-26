# Spec: Insumos por servicio, requerimiento del evento y documento de compra

- **ID**: 021-recipes-requirements
- **Estado**: borrador
- **Módulos afectados**: `inventory` (recetas, requerimiento, reservas), `purchasing` (faltantes del evento, PDF, egreso), `commercial` y `catalog` (solo lectura), `ledger` (registrar egreso)
- **Historias**: HU24 (#21), HU25 (#22), HU30 (#31)

## 1. Problema y objetivo
Hoy la solicitud de compra solo propone lo que está bajo el mínimo. Darze no puede saber cuánto arroz o cuántas copas necesita **un evento** según su menú e invitados. El objetivo: definir los insumos de cada servicio, calcular el requerimiento de cada evento contra el stock, apartar lo disponible y comprar lo que falta; y documentar cada compra.

## 2. Actores
- **Administrador** y **encargado de compras y almacén** (`inventory:manage`): recetas, reservas, compras.
- **Encargado de eventos** (`inventory:read`): ve el requerimiento de sus eventos.

## 3. Historias
- **HU24**: definir los insumos necesarios para cada menú o servicio.
- **HU25**: generar el requerimiento de materiales de un evento y compararlo con el stock.
- **HU30**: consultar y documentar las compras.

## 4. Criterios de aceptación
### HU24 — Insumos por servicio
- **CA-24.1**: Para un servicio del catálogo se agregan insumos: producto, cantidad y base **por persona** o **por servicio** (una vez por cada unidad contratada).
- **CA-24.2**: La unidad es la del producto (R-INV-1). Un producto aparece una sola vez por servicio.
- **CA-24.3**: Se guardan todos los insumos de un servicio en una sola operación (reemplaza la lista).
- **CA-24.4**: Cambiar la receta no cambia lo que ya salió para eventos pasados (los movimientos no se tocan).

### HU25 — Requerimiento del evento
- **CA-25.1**: Para un evento programado, confirmado o en ejecución se calcula: por cada servicio contratado × su receta → cantidad requerida por producto (por persona × invitados del evento; por servicio × cantidad contratada).
- **CA-25.2**: Por producto se ve: requerido, ya salido al evento, reservado para el evento, disponible en almacén y **faltante** = requerido − salido − reservado − disponible (mínimo 0).
- **CA-25.3**: Los servicios sin receta se listan aparte como "sin insumos definidos".
- **CA-25.4**: Se puede **reservar** lo disponible para el evento. Una reserva no deja stock negativo: el disponible para otros = stock − reservas vigentes.
- **CA-25.5**: Registrar una salida al evento consume primero su reserva. Cancelar o finalizar el evento libera sus reservas.
- **CA-25.6**: Desde el requerimiento, **"Generar solicitud de compra"** crea una solicitud con los faltantes, vinculada al evento (cumple el CA original de HU28).

### HU30 — Documentar compras
- **CA-30.1**: Historial de compras con filtros (ya existe: estado, proveedor, evento, fechas).
- **CA-30.2**: Cada compra se descarga en **PDF** (orden de compra): datos de Darze, proveedor, líneas, totales, estado, factura y evento.
- **CA-30.3**: Una compra **recibida** puede registrarse como **egreso de insumos** (HU21) con un botón: monto = total de la compra, evento de la compra, concepto con el código. Una sola vez por compra.

## 5. Reglas
- **R-REC-1** *(equipo, provisional)*: las cantidades por persona se redondean **hacia arriba** a 3 decimales.
- **R-REC-2** *(equipo, provisional)*: el requerimiento se calcula al momento (no se guarda). Para un evento finalizado o cancelado se muestra solo lo que salió (pestaña Materiales).
- **R-REC-3** *(equipo, provisional)*: una reserva es un apartado sin movimiento de stock; vence al cancelar o finalizar el evento.
- **R-COM-3** *(equipo, provisional; cambia R-COM-1)*: el egreso de una compra recibida se registra con un clic, no automáticamente.

## 6. Fuera de alcance
- Recetas por variantes o tamaños de porción; mermas estimadas.
- Reservas parciales por lote o vencimiento.
- Adjuntar el comprobante del proveedor como archivo.
