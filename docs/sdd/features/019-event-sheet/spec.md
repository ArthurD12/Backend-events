# Spec: Ficha consolidada del evento

- **ID**: 019-event-sheet
- **Estado**: aprobado (César Suclupe, 25/11/2026)
- **Módulos afectados**: `reporting` (agregación), `commercial`, `inventory`, `staff` (de Harold) y `commercial` (pagos) por su `public_api`
- **Historia**: HU14 (#15)

## 1. Problema y objetivo
Antes de un evento, el encargado necesita ver todo junto: cliente, horario, lugar, qué se contrató, quién trabaja, qué materiales salieron, cuánto falta cobrar y las indicaciones. Hoy está repartido en varias pantallas. El objetivo es una **ficha de una página**, de solo lectura y siempre actualizada.

## 2. Actores
- **Administrador** y **encargado de eventos**: ven la ficha completa.
- **Encargado de compras y almacén** (`events:read`): ve la ficha **sin el bloque de pagos**.

## 3. Historia
- **HU14**: Como encargado de eventos, quiero consultar una ficha consolidada para conocer toda la información necesaria antes de ejecutar el evento.

## 4. Criterios de aceptación
- **CA-14.1**: Bloque **Evento y cliente**: código, estado, tipo, fecha, horario, lugar, invitados, responsable; cliente con documento y teléfono.
- **CA-14.2**: Bloque **Servicios contratados**: menús, bebidas y demás servicios con su cantidad (sin precios).
- **CA-14.3**: Bloque **Personal asignado**: nombre, función y horario. *Depende de HU17 (Harold)*: si su módulo aún no lo expone, el bloque dice "Sin información de personal".
- **CA-14.4**: Bloque **Materiales**: por producto, lo que salió, volvió, se perdió y lo que falta devolver (HU26). "Requeridos" llega con HU25 (prioridad 2).
- **CA-14.5**: Bloque **Pagos**: total, pagado, saldo, fecha límite y lista de pagos. Solo con `payments:record`.
- **CA-14.6**: Bloque **Seguimiento**: actividades pendientes y completadas, y las últimas observaciones (HU13).
- **CA-14.7**: Todo sale de los módulos en el momento de pedirla (nada copiado). Una sola petición.
- **CA-14.8**: Se puede **imprimir** (vista de impresión del navegador).

## 5. Reglas
- **R-FIC-1** *(equipo, provisional)*: la ficha es de solo lectura; cada bloque enlaza a su pantalla para editar.

## 6. Fuera de alcance
- PDF de la ficha (se usa imprimir del navegador).
- Requerimiento de materiales por menú (HU25).
