# Plan: Cotizaciones

- **Spec**: ./spec.md
- **Estado**: borrador (pendiente de aprobación)

## 1. Módulos y fronteras
- **`commercial`**, submódulo `quotes` en cada capa (ADR 0003): `domain/quotes/`, `application/quotes/`, tablas `commercial_quote*`.
  - Usa a los clientes del mismo módulo por su puerto `ClientRepository`, para verificar que el cliente existe y está activo.
- **`catalog`** se consulta solo por `catalog.public_api` (`ServiceLookup` → `ServiceSummary`): nombre, unidad, precio y si está activo. No hay FK hacia tablas del catálogo: se guarda el `service_id` como referencia (regla 3 de AGENTS.md).
- **`identity`**: permiso nuevo `quotes:manage` (administrador y encargado de eventos, DOMAIN.md §9). Se registra `created_by` con el `CurrentUser`.

## 2. Modelo de dominio (Python puro)
- **`EventType`**: `WEDDING`, `BIRTHDAY`, `QUINCEANERA`, `CORPORATE`, `GRADUATION` (promoción), `OTHER`.
- **`QuoteStatus`** guardado: `DRAFT`, `SENT`, `ACCEPTED`, `REJECTED`. **`EXPIRED`** se calcula: estado `DRAFT` o `SENT` con `valid_until` anterior a hoy (Lima).
- **`QuoteLine`**: `kind` (`SERVICE` | `EXTRA`), `service_id` (solo en SERVICE), `description` (nombre congelado o texto libre), `price_unit`, `quantity` (> 0), `unit_price_cents` (≥ 0, precio acordado), `catalog_price_cents` (solo en SERVICE, precio del catálogo al agregarla), `subtotal_cents = quantity × unit_price_cents`.
- **`Quote`** (agregado): `id`, `code`, `client_id`, `event_type`, `event_date`, `start_time`, `end_time`, `venue`, `guests`, `valid_until`, `notes`, `lines`, `status`, `created_by`, `created_at`.
  - Invariantes: al menos una línea; `guests > 0`; `start_time ≠ end_time` (si fin < inicio, termina al día siguiente); `event_date ≥ hoy`; `valid_until ≥ hoy`; `total_cents` = suma de subtotales.
  - `update(...)` solo en `DRAFT` y no vencida → si no, `quote.not_editable`.
  - `change_status(nuevo, hoy)` según R-COT-3 → si no, `quote.invalid_transition` (o `quote.expired` si venció).

## 3. Casos de uso
| Caso de uso | Tipo | Entrada | Salida | Errores (`code`) |
|---|---|---|---|---|
| `CreateQuote` | command | cliente, evento, líneas, vigencia opcional | cotización | `quote.client_not_found`, `quote.client_inactive`, `quote.service_not_found`, `quote.service_inactive`, `quote.*_invalid` |
| `UpdateQuote` | command | id + mismos datos | cotización | los anteriores + `quote.not_found`, `quote.not_editable` |
| `ChangeQuoteStatus` | command | id, estado | cotización | `quote.not_found`, `quote.invalid_transition`, `quote.expired` |
| `GetQuote` | query | id | cotización con líneas | `quote.not_found` |
| `SearchQuotes` | query | texto (código o cliente), cliente, estado, rango de fechas del evento, página | página de resúmenes | – |

Detalles de las líneas al crear o editar:
- **SERVICE**: se consulta `ServiceLookup`. Al crear, el servicio debe estar activo; se congelan su nombre, unidad y precio de catálogo. Si no se envía precio, se usa el del catálogo. Si no se envía cantidad: invitados (por persona) o 1 (por unidad).
- Al **editar**, una línea de un servicio que ya estaba en la cotización conserva su nombre y su precio de catálogo congelados, aunque el servicio haya cambiado o se haya desactivado después. Solo los servicios **nuevos** deben estar activos.
- **EXTRA**: descripción (1–200) y monto; cantidad 1 por defecto.
- **Vigencia**: si no se envía, es hoy + 15 días.

**Código**: `COT-AAAA-NNNN`, con el año de creación (hora de Lima) y un correlativo por año (regla 8). Se obtiene con `INSERT … ON CONFLICT (year) DO UPDATE SET last = last + 1 RETURNING last` sobre `commercial_quote_counters`, que es atómico aunque se creen dos cotizaciones a la vez.

## 4. API (permiso `quotes:manage`)
| Método y ruta | `operationId` |
|---|---|
| `POST /v1/quotes` | `quotes_create` |
| `GET /v1/quotes?text=&client_id=&status=&event_date_from=&event_date_to=&page=&page_size=` | `quotes_search` |
| `GET /v1/quotes/{quote_id}` | `quotes_get` |
| `PUT /v1/quotes/{quote_id}` | `quotes_update` |
| `POST /v1/quotes/{quote_id}/status` | `quotes_change_status` |

- La respuesta incluye `status` (el efectivo, con `EXPIRED`), `total_cents`, `currency` y los `subtotal_cents` de cada línea. El total lo calcula siempre el servidor: el que envíe el frontend no se usa.
- Errores: 404 no encontrado; 409 para `not_editable`, `invalid_transition`, `expired`, `client_inactive` y `service_inactive`; 422 para datos inválidos.

## 5. Persistencia (migración Alembic)
- `commercial_quotes`: `id`, `code` (único), `client_id` (FK a `commercial_clients`: mismo módulo), `event_type`, `event_date` (date), `start_time` y `end_time` (time), `venue`, `guests`, `valid_until` (date), `notes`, `status`, `total_cents`, `currency` (`PEN`), `created_by` (uuid, sin FK porque es de otro módulo), `created_at`, `updated_at`. CHECK de estado, tipo de evento, `guests > 0`, `total_cents >= 0` y `start_time <> end_time`. Índices por `client_id`, `status` y `event_date`.
- `commercial_quote_lines`: `id`, `quote_id` (FK), `position`, `kind`, `service_id` (sin FK), `description`, `price_unit`, `quantity`, `unit_price_cents`, `catalog_price_cents`, `subtotal_cents`. CHECK de `quantity > 0`, montos ≥ 0 y `subtotal = quantity × unit_price`.
- `commercial_quote_counters`: `year` (PK), `last`.
- **Triggers (CA-08.4)**: rechazan cambiar el contenido de una cotización cuyo estado anterior no es `DRAFT` (solo se permite cambiar `status`), y rechazan insertar, cambiar o borrar líneas de una cotización que no está en `DRAFT`.
- La fecha y el horario del evento se guardan como fecha y hora **locales** (un plan, no un instante). `created_at` y `updated_at` van en `timestamptz` UTC (regla 4).

## 6. Reglas de negocio aplicadas
`DOMAIN.md` §4 (reglas 1, 2 y 6 a 14) y R-COT-1 a R-COT-5. Se agregan a `DOMAIN.md` §11 como provisionales.

## 7. Estrategia de tests
- **Unit**: entidad `Quote` (cálculo, horario que cruza medianoche, transiciones, vencida, no editable) y casos de uso con fakes (cliente inactivo, servicio inactivo, precio congelado al editar aunque el catálogo cambie, cantidad por persona = invitados, código); API en memoria (permisos, 404, 409 y 422).
- **Integración** (PostgreSQL real): repositorio, búsqueda y filtros (incluida la vencida), código sin duplicados con creaciones simultáneas y triggers que bloquean la edición.
- Cada prueba lleva su CA en el nombre (`test_ca07_5_...`).

## 8. Riesgos y ADRs
- Sin dependencias nuevas y sin ADR nuevo (cabe en ADR 0003).
- **Riesgo**: el estado "vencida" depende de la fecha de Lima; se calcula con un reloj inyectable para poder probarlo.
- **Frontend**: lista con filtros, formulario maestro-detalle con total en tiempo real y detalle con botones de estado. Va en su propio parche, después del backend.
- **Rama**: `feat/quotes`, desde `developer-b`, con PR hacia `developer-b`.

## 9. Impacto en reporting y documentación
Sin cambios en `reporting` todavía. Se actualizan `openapi.json`, `DOMAIN.md` §11 y la tabla de permisos (`quotes:manage`).
