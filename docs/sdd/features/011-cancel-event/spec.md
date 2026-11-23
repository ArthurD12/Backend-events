# Spec: Cancelar un evento

- **ID**: 011-cancel-event
- **Estado**: borrador, pendiente de aprobación
- **Módulos afectados**: `commercial` (submódulos `events` y `contracts`), `ledger` (devolución)
- **Historia**: HU11 (#12), **solo la parte de cancelar**. El resto de HU11 (editar la planificación y los otros cambios de estado) va en otro spec, cuando el Product Owner defina sus reglas.

## 1. Problema y objetivo
Con HU10, un contrato que ya es evento no se anula desde el contrato (R-EVT-3). Pero todavía no existe cancelar un evento, así que hoy **no hay forma de registrar que un cliente canceló un evento ya convertido**. El objetivo es cancelar el evento con un motivo y, en el mismo paso, dejar anulado su contrato y registrar la devolución si la hubo.

## 2. Actores
- **Administrador** y **encargado de eventos**: cancelan el evento (y registran la devolución, R-CON-4).
- **Encargado de compras y almacén**: solo ve que el evento está cancelado.

## 3. Historia
- **HU11** (parte): Como encargado de eventos, quiero cambiar el estado de un evento a **cancelado** para controlar su ejecución.

## 4. Criterios de aceptación
- **CA-11.C1**: Un evento programado o confirmado se puede cancelar. Uno finalizado o ya cancelado, no.
- **CA-11.C2**: El motivo es obligatorio (hasta 500 caracteres).
- **CA-11.C3**: Si se devolvió dinero, se registra el monto (mayor que cero y no mayor que el adelanto pagado), el medio, la fecha y una referencia opcional. El sistema no calcula penalidades.
- **CA-11.C4**: Al cancelar el evento, **su contrato queda anulado con el mismo motivo** y la devolución queda en sus pagos. Todo en un solo paso: o se guarda todo, o nada.
- **CA-11.C5**: Queda registrado quién canceló y cuándo (RN03).
- **CA-11.C6**: El evento cancelado sigue visible en la lista (filtro "Cancelado") y en su detalle se ve el motivo.

## 5. Reglas
- **R-EVT-3** *(equipo, provisional)*: sigue igual. El contrato con evento no se anula desde el contrato; se anula **cancelando el evento**.
- **R-EVT-4** *(equipo, provisional, a validar por el Product Owner)*: cancelar el evento **anula el contrato**. Si el cliente quiere otra fecha, se hace una cotización nueva (una cotización tiene un solo contrato, R-CON-5).
- **R-EVT-5** *(equipo, provisional)*: se cancela desde programado o confirmado. No desde "en ejecución" ni "finalizado".
- La devolución sigue la decisión del Product Owner del 22/11/2026: solo se registra, sin reglas automáticas (R-CON-3).

## 6. Fuera de alcance
- Editar fecha, horario, lugar, invitados o responsable; pasar a confirmado, en ejecución o finalizado (resto de HU11).
- Reprogramar un evento sin cancelarlo.
- Recuperar un evento cancelado.

## 7. No funcionales
- Si el registro de la devolución falla, ni el evento ni el contrato cambian.
- La base de datos impide anular el contrato de un evento que no está cancelado.
