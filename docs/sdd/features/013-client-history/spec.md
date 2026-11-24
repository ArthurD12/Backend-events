# Spec: Historial del cliente

- **ID**: 013-client-history
- **Estado**: aprobado (César Suclupe, 24/11/2026)
- **Módulos afectados**: `commercial` (clientes, cotizaciones, contratos y eventos; solo lectura)
- **Historia**: HU05 (#6), RF11

## 1. Problema y objetivo
Hoy, para saber qué ha contratado un cliente, hay que buscarlo por separado en cotizaciones, contratos y eventos. El objetivo es ver en un solo lugar su relación comercial con Darze: qué se le cotizó, qué contrató y qué eventos tuvo.

## 2. Actores
- **Encargado de eventos** y **administrador** (`clients:manage`, DOMAIN.md §9).
- El **encargado de compras y almacén** no ve clientes (no tiene `clients:manage`).

## 3. Historia
- **HU05**: Como encargado de eventos, quiero consultar el historial de cotizaciones y eventos de un cliente para conocer su relación comercial con Darze.

## 4. Criterios de aceptación
- **CA-05.1**: Se muestran todas las **cotizaciones** del cliente.
- **CA-05.2**: Se muestran sus **eventos** en cualquier estado: programados, confirmados, en ejecución, finalizados o cancelados.
- **CA-05.3**: Cada registro muestra **código, fecha, importe y estado**:
  - cotización: fecha del evento, total y estado (incluido "Vencida");
  - evento: fecha del evento, **total del contrato** y estado.
- **CA-05.4**: Solo lo consultan usuarios con `clients:manage`. Los demás reciben `auth.forbidden`.
- **CA-05.5**: Cada registro enlaza a su detalle.

## 5. Reglas
- **R-HIS-1** *(equipo, provisional)*: el historial muestra también un **resumen**: cuántas cotizaciones tiene, cuántas fueron aceptadas, cuántos eventos tuvo y el **total contratado**. El total contratado es la suma de los contratos firmados, sin contar los anulados.
- Orden: de la fecha de evento **más reciente a la más antigua**.
- Un cliente **desactivado** también tiene historial (RN02: no se borra, se desactiva).

## 6. Fuera de alcance
- Pagos del cliente (los pagos están en el contrato, HU19–HU22).
- Exportar el historial.
- Notas o seguimiento comercial del cliente.

## 7. No funcionales
- Una sola consulta por pestaña, sin paginación. **[suposición]** Una MYPE no tendrá cientos de cotizaciones por cliente; si ocurre, se agrega paginación.
