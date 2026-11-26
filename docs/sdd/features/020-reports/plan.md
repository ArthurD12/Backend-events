# Plan: Dashboard completo y reportes con exportación

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 25/11/2026)

## 1. Módulos y fronteras
- Todo en `reporting`. Lee por `public_api` de `commercial` (eventos y cuentas), `ledger` (movimientos y sumas), `inventory` (stock, alertas, movimientos), `purchasing` (compras) y `staff` (trabajadores: **solo lectura**, por una consulta que se pide a Harold en `COORDINACION.md`; mientras no exista, el reporte de personal queda deshabilitado con un mensaje).
- Se agregan a esos `public_api` solo **consultas de lectura** que falten.

## 2. Diseño
- `reporting.application.reports`: un caso de uso por reporte que devuelve un `ReportTable` (título, filtros aplicados, columnas con tipo — texto, fecha, soles, cantidad —, filas y totales). La misma tabla alimenta JSON, CSV y PDF: así CA-34.2 se cumple por construcción.
- `reporting.infrastructure.exporters`: `CsvExporter` (UTF-8 BOM, `;`, decimales con coma) y `PdfExporter` (ReportLab, horizontal, encabezado con `COMPANY_*`).
- `GetDashboard` se amplía con los bloques de CA-31.7 a CA-31.11.

## 3. API
| Ruta | `operationId` | Permiso |
|---|---|---|
| `GET /v1/dashboard` (respuesta ampliada, campos nuevos) | `dashboard_get` | `dashboard:read` |
| `GET /v1/reports/{events,cash,inventory,inventory-movements,purchases,staff}` | `reports_<nombre>` | según CA (permisos existentes) |
| mismo path con `?format=csv` o `?format=pdf` | mismo `operationId`, otra media | igual |

Errores: `report.range_invalid` (422), `report.unavailable` (503, personal sin consulta).

## 4. Persistencia
- Ninguna tabla nueva. Consultas con índices existentes; si alguna es lenta, índice en una migración aparte.

## 5. Tests
- Unit: cada caso de uso con fakes (filtros, totales, montos ocultos sin permiso), CSV (BOM, `;`, tildes, decimales), PDF (contiene título y totales), panel con datos y vacío.
- Integración: un escenario con evento, pagos, movimientos y compra; el CSV y el JSON tienen las mismas filas.

## 6. Frontend
- Inicio (admin): tarjetas nuevas (próximos eventos, caja del mes, cobros pendientes, alertas de almacén, compras abiertas) con enlaces.
- Menú **Reportes**: una pestaña por reporte con filtros, tabla y botones **Descargar CSV** / **Descargar PDF** (según permisos).

## 7. Riesgos
- Si el profesor exige `.xlsx`, se agrega `openpyxl` con ADR (medio día).
- Reporte de personal depende de Harold.
