# Spec: Pagos, comprobante, ingresos y egresos, flujo de caja

- **ID**: 016-payments-cash
- **Estado**: aprobado (César Suclupe, 25/11/2026)
- **Módulos afectados**: `commercial` (pagos del contrato y saldo), `ledger` (pagos, anulaciones, movimientos), `reporting` (flujo de caja y resultado por evento), `identity` (permiso `finance:read`)
- **Historias**: HU19 (#24), HU20 (#25), HU21 (#26), HU22 (#27)

## 1. Problema y objetivo
Hoy el sistema registra el adelanto, pero no el resto de lo que paga el cliente ni los gastos del evento. Darze no sabe cuánto le deben ni si un evento dejó ganancia. El objetivo es registrar cada pago con su saldo, entregar una constancia, anotar los ingresos y gastos, y ver el flujo de caja y el resultado de cada evento.

## 2. Actores
- **Administrador** y **encargado de eventos** (`payments:record`): registran pagos, ingresos y egresos, y anulan (R-CON-4; DOMAIN.md §9).
- **Administrador** (`finance:read`): flujo de caja y resultado económico (DOMAIN.md §9: reportes financieros solo administrador).
- **Encargado de compras y almacén**: no ve pagos ni dinero.

## 3. Historias
- **HU19**: registrar adelantos y pagos parciales para conocer el total pagado y el saldo pendiente.
- **HU20**: generar un comprobante interno por cada pago para entregar una constancia al cliente.
- **HU21**: registrar ingresos y egresos asociados a los eventos para controlar el movimiento económico.
- **HU22**: consultar el flujo de caja y el resultado económico de los eventos.

## 4. Criterios de aceptación
### HU19 — Pagos parciales
- **CA-19.1**: En un contrato **firmado**, se registra un pago: monto, fecha, medio (efectivo, transferencia, tarjeta, Yape/Plin) y referencia opcional.
- **CA-19.2**: El monto es mayor que cero y **no supera el saldo pendiente** (RN14): `payment.exceeds_balance` (422) con el saldo en el mensaje.
- **CA-19.3**: **Saldo = total del contrato − pagos + devoluciones** (RN15), contando solo pagos vigentes: un pago anulado no cuenta.
- **CA-19.4**: El contrato y el evento muestran total, pagado, saldo, fecha límite del saldo y la lista de pagos (adelanto incluido) con quién los registró.
- **CA-19.5**: Un pago se **anula** con motivo obligatorio. No se borra: queda el pago y su anulación, con quién y cuándo (RN17). El adelanto no se anula por aquí (se anula el contrato, R-CON-3).
- **CA-19.6**: En un contrato anulado no se registran pagos.

### HU20 — Comprobante
- **CA-20.1**: Cada pago tiene un número único `PAG-AAAA-NNNN`.
- **CA-20.2**: Se descarga el comprobante en PDF: datos de Darze, cliente, contrato y evento, número, fecha, monto, medio, referencia, total del contrato, pagado y saldo **después de ese pago**, y quién lo registró.
- **CA-20.3**: El comprobante de un pago anulado sale con la marca **ANULADO** y el motivo.

### HU21 — Ingresos y egresos
- **CA-21.1**: Se registra un **egreso** con fecha, concepto, monto, categoría (insumos, personal, transporte, otros), medio y referencia opcional; puede asociarse a un evento (RN16).
- **CA-21.2**: Se registra un **ingreso** que no es pago de un cliente (p. ej., alquiler de menaje), con los mismos datos y categoría "otros ingresos".
- **CA-21.3**: Un movimiento se **anula** con motivo obligatorio; queda el historial (RN17). No se edita.
- **CA-21.4**: La lista se filtra por fechas, tipo, categoría, evento y estado.

### HU22 — Flujo de caja y resultado
- **CA-22.1**: Entre dos fechas: ingresos (pagos de clientes netos de devoluciones + otros ingresos), egresos por categoría y saldo del periodo. Por fecha del movimiento, no de registro.
- **CA-22.2**: Desglose por mes cuando el rango supera un mes.
- **CA-22.3**: **Resultado de un evento**: cobrado al cliente (neto de devoluciones), egresos asociados por categoría y resultado (cobrado − egresos). También el total contratado y el saldo por cobrar.
- **CA-22.4**: Nada anulado entra en los cálculos.

## 5. Reglas
- **R-PAG-1** *(equipo, provisional)*: los pagos se registran contra el **contrato** (el evento lo muestra por su contrato), porque el contrato tiene el total.
- **R-PAG-2** *(equipo, provisional)*: se puede pagar después de la fecha límite del saldo y después del evento. El sistema solo avisa "saldo vencido".
- **R-PAG-3** *(equipo, provisional)*: el pago acordado al personal (HU17) **no** es un egreso hasta que se registra como egreso de categoría "personal".
- **R-PAG-4** *(equipo, provisional)*: la fecha de un pago o movimiento no puede ser futura (como el adelanto).

## 6. Fuera de alcance
- Pasarela de pagos, boletas o facturas (Darze no las emite).
- Editar un pago o movimiento (se anula y se registra otro).
- Pagos a proveedores desde compras (HU28–HU29): se registran como egreso de insumos.
- Exportar a Excel o PDF el flujo de caja (HU32–HU34).

## 7. No funcionales
- Dos pagos simultáneos al mismo contrato no superan el saldo: se bloquea la fila del contrato (`FOR UPDATE`).
- Append-only: pagos, anulaciones y movimientos solo se insertan (regla 5).
- Montos en céntimos; fechas `timestamptz`, en pantalla hora de Lima.

## 8. Preguntas abiertas
- [ ] ¿El encargado de eventos ve el resultado económico de su evento, o solo el administrador?
- [ ] Categorías de egreso: ¿bastan insumos, personal, transporte y otros?
