# Plan: Pagos, comprobante, ingresos y egresos, flujo de caja

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 25/11/2026)

## 1. Módulos y fronteras
- `ledger` guarda todo el dinero: pagos, anulaciones de pagos, movimientos y anulaciones de movimientos. No conoce contratos ni eventos más que por ID.
- `commercial` registra y anula los pagos del contrato (como ya hace con el adelanto): lee el total del contrato, calcula el saldo con `ledger.public_api.payments_lookup` y llama a `payment_recorder` / `payment_voider`. Así no hay dependencia `ledger → commercial` (evita el ciclo).
- `reporting` arma el flujo de caja y el resultado por evento con `ledger.public_api` (sumas por rango, por contrato y por evento) y `commercial.public_api` (evento → contrato y total). Es el único módulo que junta datos de otros.
- `identity`: permiso nuevo `finance:read` (solo administrador).

## 2. Modelo de dominio
- `ledger.domain.Payment`: se agrega `number` (`PAG-AAAA-NNNN`) y `PaymentKind.INSTALLMENT` (pago parcial). Sigue inmutable.
- `ledger.domain.PaymentVoid`: payment_id, motivo (1–500), usuario, fecha. Un pago tiene a lo sumo una anulación. `ADVANCE` y `REFUND` no se anulan por aquí.
- `ledger.domain.CashMovement`: id, `MovementType` (INCOME/EXPENSE), `MovementCategory` (SUPPLIES, STAFF, TRANSPORT, OTHER_EXPENSE / OTHER_INCOME; la categoría debe corresponder al tipo), concepto (1–200), monto > 0, medio, referencia, fecha (no futura), `event_id?`, auditoría.
- `ledger.domain.MovementVoid`: igual que `PaymentVoid`.
- `commercial.domain.Contract`: `balance_cents` deja de ser `total − adelanto` y pasa a calcularse con los pagos vigentes: `ContractBalance(total, paid, refunded)` con `paid_cents`, `balance_cents`, `is_overdue(today)`.

## 3. Casos de uso
| Caso de uso | Módulo | Errores (`code`) |
|---|---|---|
| `RecordContractPayment` | commercial | `contract.not_found` 404, `contract.not_signed` 409, `payment.exceeds_balance` 422, `payment.*` 422 |
| `VoidContractPayment` | commercial | `payment.not_found` 404, `payment.not_voidable` 409, `payment.already_voided` 409, `payment.reason_required` 422 |
| `GetContractAccount` (total, pagado, saldo, pagos con anulación) | commercial | `contract.not_found` 404 |
| `RenderPaymentReceipt` (PDF) | commercial (tiene cliente y evento) | `payment.not_found` 404 |
| `RecordMovement`, `VoidMovement`, `ListMovements` | ledger | `movement.*` 422/404/409 |
| `GetCashFlow(from, to)` | reporting | `report.range_invalid` 422 (máx. 366 días) |
| `GetEventResult(event_id)` | reporting | `event.not_found` 404 |

## 4. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `GET /v1/contracts/{id}/account` | `contracts_account_get` | `payments:record` |
| `POST /v1/contracts/{id}/payments` | `contracts_payments_create` | `payments:record` |
| `POST /v1/payments/{id}/void` | `payments_void` | `payments:record` |
| `GET /v1/payments/{id}/receipt.pdf` | `payments_receipt_pdf` | `payments:record` |
| `GET /v1/movements` · `POST /v1/movements` | `movements_list` · `movements_create` | `payments:record` |
| `POST /v1/movements/{id}/void` | `movements_void` | `payments:record` |
| `GET /v1/reports/cash-flow?from&to` | `reports_cash_flow` | `finance:read` |
| `GET /v1/reports/events/{id}/result` | `reports_event_result` | `finance:read` |

`ContractOut` y `EventOut` agregan `paid_cents` y `balance_cents` (campos nuevos, compatibles).

## 5. Persistencia (una migración, encadenada **después** de la de personal)
- `ledger_payments`: columna `number` única (las filas existentes reciben número en la migración, por orden de registro) y `kind` acepta `INSTALLMENT`.
- `ledger_payment_voids` (payment_id único, FK mismo módulo), `ledger_movements`, `ledger_movement_voids` (movement_id único).
- Correlativo por año con la misma técnica que `COT`/`CON`/`EVT`.
- Append-only: trigger que rechaza `UPDATE` y `DELETE` en las cuatro tablas.
- Concurrencia: `RecordContractPayment` bloquea la fila del contrato (`SELECT … FOR UPDATE`) antes de sumar los pagos.
- Índices: pagos por `contract_id`; movimientos por `occurred_on` y por `event_id`.

## 6. Reglas aplicadas
RN14–RN17, R-CON-3, R-CON-4. Se agregan R-PAG-1 a R-PAG-4 a DOMAIN.md §11 (provisionales).

## 7. Tests
- **Unit**: `ContractBalance` (con anulados y devoluciones), `PaymentVoid` (adelanto no se anula), `CashMovement` (categoría ↔ tipo, fecha futura), cada caso de uso con fakes, API (403 para compras; `finance:read` solo admin), el PDF tiene el número y el saldo.
- **Integración**: pagar hasta saldo 0 y el siguiente falla; dos pagos simultáneos no superan el saldo; el trigger rechaza `UPDATE`/`DELETE`; flujo de caja de un rango con anulados.

## 8. Frontend
- **Contrato / Evento**: tarjeta **Cuenta** (total, pagado, saldo, vence el…, aviso de vencido), tabla de pagos con **Descargar comprobante** y **Anular**; botón **Registrar pago** con el saldo como máximo.
- Menú **Caja**: lista de ingresos y egresos con filtros, **Nuevo ingreso / egreso** (evento opcional), **Anular** con motivo.
- Menú **Flujo de caja** (solo administrador): rango de fechas, totales y por categoría, por mes.
- Evento: tarjeta **Resultado económico** (solo administrador): cobrado vs. egresos y resultado.

## 9. Riesgos
- Cambiar `balance_cents` del contrato toca HU41/HU42: sus tests deben seguir verdes con solo el adelanto.
- Dos migraciones en paralelo (personal y esta): esta se crea **después** de unir personal, encadenada a su head.
