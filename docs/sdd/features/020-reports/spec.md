# Spec: Dashboard completo y reportes con exportación

- **ID**: 020-reports
- **Estado**: aprobado (César Suclupe, 25/11/2026)
- **Módulos afectados**: `reporting` (agrega datos de otros por su `public_api`), `commercial`, `ledger`, `inventory`, `purchasing`, `staff` (solo lectura)
- **Historias**: HU31 (#32, completar), HU32–HU34 (#33)

## 1. Problema y objetivo
El panel del administrador hoy solo muestra cotizaciones, porque se hizo antes de que existieran eventos, pagos y almacén. Además Darze no puede sacar un listado para revisar el mes o entregarlo a su contador. El objetivo es un **panel con la situación real** y una **central de reportes** que se filtran y se descargan.

## 2. Actores
- **Administrador**: panel completo y todos los reportes (DOMAIN.md §9: reportes financieros solo administrador).
- **Encargado de eventos**: reporte de eventos.
- **Encargado de compras y almacén**: reporte de almacén y de compras.

## 3. Historias
- **HU31**: Como administrador, quiero visualizar indicadores generales en un dashboard para conocer rápidamente la situación operativa de Darze.
- **HU32–HU34**: Generar reportes operativos y financieros, con exportación, para la toma de decisiones.

## 4. Criterios de aceptación
### HU31 — Panel (se suma a lo que ya existe en 031)
- **CA-31.7**: **Próximos eventos** (14 días): código, fecha, cliente, estado y saldo por cobrar. Reemplaza "próximas fechas" de cotizaciones aceptadas.
- **CA-31.8**: **Caja del mes**: ingresos, egresos y saldo del mes elegido (mismo cálculo que el flujo de caja, HU22).
- **CA-31.9**: **Cobros pendientes**: total por cobrar de contratos firmados y cuántos tienen el saldo **vencido**.
- **CA-31.10**: **Alertas de almacén**: cuántos productos están en stock bajo y cuántos por vencer, con acceso a la lista.
- **CA-31.11**: **Compras abiertas**: cuántas están solicitadas u ordenadas.
- Se mantiene CA-31.1, CA-31.2, CA-31.4, CA-31.5 y CA-31.6.

### HU32–HU34 — Reportes
- **CA-32.1**: **Reporte de eventos** por rango de fechas del evento, estado y cliente: código, fecha, cliente, tipo, invitados, estado, total contratado, pagado y saldo (montos solo con `payments:record`).
- **CA-32.2**: **Reporte de caja** por rango: cada movimiento (pagos de clientes, devoluciones, ingresos y egresos) con fecha, tipo, categoría, concepto, evento, monto y si está anulado; totales al pie. Solo administrador.
- **CA-32.3**: **Reporte de almacén**: stock actual por producto (categoría, unidad, stock, mínimo, costo promedio, valor), con alertas; y movimientos por rango.
- **CA-32.4**: **Reporte de compras** por rango y estado: código, proveedor, estado, total, fecha de recepción.
- **CA-32.5**: **Reporte de personal**: trabajadores con función, tipo y estado. Las asignaciones por evento se suman cuando Harold exponga HU17.
- **CA-33.1**: Cada reporte se ve en pantalla con sus filtros y se **descarga en CSV** (abre en Excel, con tildes correctas).
- **CA-34.1**: Cada reporte se **descarga en PDF** con los datos de Darze, el título, los filtros usados, la fecha de generación y los totales.
- **CA-34.2**: Lo descargado coincide con lo que se ve en pantalla.

## 5. Reglas
- **R-REP-1** *(equipo, provisional)*: la exportación a hoja de cálculo es **CSV** (UTF-8 con BOM, separador `;`, que Excel en español abre directo). No se agrega `openpyxl` (regla 11). Si se exige `.xlsx`, se hace con un ADR.
- **R-REP-2** *(equipo, provisional)*: un reporte cubre como máximo **366 días**.
- **R-REP-3** *(equipo, provisional)*: los montos van en soles con 2 decimales; las fechas en hora de Lima.
- Ningún número se inventa: sin datos, se muestra vacío.

## 6. Fuera de alcance
- Gráficos de varios meses y comparativos interanuales.
- Programar el envío de reportes por correo.
- Reportes de la IA.

## 7. No funcionales
- Un reporte de un año de datos de una MYPE responde en menos de 3 s. **[suposición]**
- El PDF usa ReportLab (ya está, ADR 0004).

## 8. Preguntas abiertas
- [ ] R-REP-1: ¿el profesor exige `.xlsx` o basta CSV que abra en Excel?
