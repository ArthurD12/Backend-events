# Plan: Contrato, firma y adelanto

- **Spec**: ./spec.md
- **Estado**: borrador (pendiente de aprobación)

## 1. Módulos y fronteras
- **`commercial`**, submódulo `contracts` (ADR 0003): lee la cotización directamente (mismo módulo); FK `quote_id` y `client_id` dentro de `commercial`.
- **`ledger`** (nuevo contenido): registro de pagos. `commercial` lo usa **solo por `ledger.public_api`** (`record_payment`), dentro de la misma transacción: si falla el pago, no se firma el contrato, y al revés.
- **`identity`**: permisos `contracts:manage` y `payments:record` para administrador y encargado de eventos.

## 2. Modelo de dominio
**`Contract`** (`commercial/domain/contracts`):
- `id`, `code`, `quote_id`, `client_id`, `event_date`, `total_cents`, `advance_cents`, `balance_due_date = event_date − 7 días`, `status` (`PENDING_SIGNATURE` | `SIGNED` | `CANCELLED`), `created_by`, `created_at`.
- `signature`: `signed_on`, `signer_name`, `advance_payment_id`, `recorded_by`, `recorded_at`.
- `cancellation`: `reason` (obligatorio), `refund_cents` (opcional, ≤ adelanto pagado), `note`, `cancelled_by`, `cancelled_at`.
- Métodos: `generate(quote, advance?)` (CA-41.1 a CA-41.5), `sign(...)` (solo desde pendiente), `cancel(...)` (desde pendiente o firmado), `can_become_event` (firmado y con adelanto, CA-42.3).
- Los servicios y montos del contrato son los de la cotización aceptada, que la base ya impide modificar (trigger de 004-quotes). El contrato copia cliente, fecha del evento y total, y referencia la cotización para el detalle: no hay campos editables (CA-41.2).

**`Payment`** (`ledger/domain`): `id`, `contract_id`, `kind` (`ADVANCE` | `REFUND`), `amount_cents > 0`, `currency = PEN`, `method` (`CASH` | `TRANSFER` | `CARD` | `YAPE_PLIN`), `reference`, `paid_on`, `recorded_by`, `recorded_at`. Inmutable.

## 3. Casos de uso
| Caso de uso | Entrada | Errores (`code`) |
|---|---|---|
| `GenerateContract` | `quote_id`, `advance_cents?` | `contract.quote_not_accepted`, `contract.already_exists` (409), `contract.advance_invalid` (422), `quote.not_found` |
| `SignContract` | id, `signed_on`, `signer_name`, adelanto (`paid_on`, `method`, `reference`) | `contract.not_pending` (409), `contract.*_invalid` (422) |
| `CancelContract` | id, `reason`, `refund_cents?`, `note?` | `contract.already_cancelled` (409), `contract.reason_required`, `contract.refund_invalid` (422) |
| `GetContract`, `SearchContracts` | id; texto (código o cliente), estado, página | `contract.not_found` |

Al firmar, el adelanto se registra con `ledger.public_api.record_payment(kind=ADVANCE)`. Al anular con devolución, con `kind=REFUND`.

## 4. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `POST /v1/contracts` | `contracts_generate` | `contracts:manage` |
| `GET /v1/contracts` · `GET /v1/contracts/{id}` | `contracts_search` · `contracts_get` | `contracts:manage` |
| `POST /v1/contracts/{id}/sign` | `contracts_sign` | `contracts:manage` + `payments:record` |
| `POST /v1/contracts/{id}/cancel` | `contracts_cancel` | `contracts:manage` + `payments:record` |

`QuoteOut` agrega `contract_id` (si existe), para que el detalle de la cotización muestre "Generar contrato" o "Ver contrato".

## 5. Persistencia (migración)
- `commercial_contracts`: `quote_id` **único** (CA-41.1 y R-CON-5, aun con dos peticiones simultáneas), `code` único, CHECKs de estado, `0 < advance_cents <= total_cents`, y datos de firma o anulación presentes según el estado. Trigger: un contrato `SIGNED` o `CANCELLED` no cambia sus montos ni su firma; solo se permite pasar de `SIGNED` a `CANCELLED` (CA-42.2).
- `commercial_contract_counters` (`year`, `last`).
- `ledger_payments`: FK-free (`contract_id` es una referencia entre módulos), CHECK `amount_cents > 0`, y trigger que impide UPDATE y DELETE (AGENTS.md, regla 5).

## 6. Tests
- **Unit**: entidad `Contract` (50 %, redondeo, ajuste, saldo a −7 días, transiciones, anulación con motivo y devolución ≤ pagado); casos de uso con fakes (cotización no aceptada, segundo contrato, pago registrado al firmar); API (permisos para admin, eventos y compras; 409 y 422).
- **Integración**: contrato único por cotización con dos generaciones simultáneas, triggers de contrato y de pagos, y flujo de punta a punta (cotización aceptada → contrato → firma con adelanto → pago en el ledger → anulación con devolución).

## 7. Frontend (repo `frontend-events`)
- En el detalle de una cotización aceptada: botón **"Generar contrato"** (con el adelanto editable, 50 % sugerido) o **"Ver contrato"**.
- Pantallas `/contratos` (lista con búsqueda y estado) y `/contratos/[id]` (detalle, **"Registrar firma y adelanto"** y **"Anular"** con su motivo).
- Menú: "Contratos" en Gestión comercial.

## 8. Riesgos
- Primer uso del módulo `ledger`: se fija aquí la forma de los pagos que usarán HU19–HU22.
- Sin dependencias nuevas.
