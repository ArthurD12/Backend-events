# Plan: Panel de indicadores del administrador (primera parte)

- **Spec**: ./spec.md
- **Estado**: borrador (pendiente de aprobación)

## 1. Módulos y fronteras
- **`reporting`** es el único lugar que cruza datos de varios módulos (ARCHITECTURE.md). Expone `GET /v1/dashboard` y arma la respuesta pidiendo a cada módulo sus números por su `public_api`.
- **`commercial.public_api`** expone una consulta de solo lectura, `QuoteStats`: conteos, monto aceptado, próximas fechas y recientes. `reporting` nunca lee tablas de `commercial`.
- **`identity`**: permiso nuevo `dashboard:read`, solo para el administrador.
- Cuando existan caja y stock, sus módulos expondrán su consulta y `reporting` las sumará a la misma respuesta.

## 2. Casos de uso
| Caso de uso | Módulo | Entrada | Salida |
|---|---|---|---|
| `GetQuoteStats` | commercial | mes (año, mes), hoy (Lima) | borradores, enviadas vigentes, creadas, aceptadas y monto aceptado del mes, próximas fechas aceptadas (30 días), 5 recientes |
| `GetDashboard` | reporting | mes | `{month, quotes: {...}}` |

## 3. API
- `GET /v1/dashboard?month=AAAA-MM` (por defecto, el mes actual de Lima) → `operationId: dashboard_get`. Permiso `dashboard:read`; 401 o 403 si no.

## 4. Persistencia
Sin tablas nuevas: consultas de agregación sobre `commercial_quotes` y `commercial_clients` en el repositorio de cotizaciones.

## 5. Tests
- **Unit**: `GetQuoteStats` con el repositorio en memoria (mes, vencidas fuera de pendientes, próximas ordenadas); API del dashboard con permisos (admin 200; eventos y compras 403).
- **Integración**: agregaciones en PostgreSQL real y endpoint de punta a punta.

## 6. Frontend
- El Inicio muestra el panel si el usuario tiene `dashboard:read`; si no, las tarjetas de hoy.
- Panel: 4 tarjetas de indicadores, un selector de mes, una lista de próximas fechas y una tabla de las 5 recientes. Diseño de Figma, solo con datos reales.

## 7. Riesgos
- Sin dependencias nuevas.
- "Aceptadas en el mes" usa la fecha de creación (spec §5), y la pantalla lo dice.
