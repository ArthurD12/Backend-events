# Spec: Planificación y estado del evento

- **ID**: 018-event-planning
- **Estado**: borrador
- **Módulos afectados**: `commercial` (eventos)
- **Historia**: HU11 (#12), el resto: la cancelación ya está hecha (011-cancel-event)

## 1. Problema y objetivo
Después de convertir el contrato en evento, cambian cosas: el cliente pasa la hora, cambia el piso del local o suben los invitados. Y el evento avanza: se confirma, se ejecuta y termina. Hoy nada de eso se puede registrar. El objetivo es editar la planificación y mover el evento por sus estados.

## 2. Actores
- **Administrador** y **encargado de eventos** (`events:manage`).
- **Encargado de compras y almacén**: solo consulta.

## 3. Historia
- **HU11**: Como encargado de eventos, quiero actualizar la planificación y el estado de un evento para controlar su ejecución.

## 4. Criterios de aceptación
- **CA-11.1**: El evento muestra su código, la cotización y el contrato de origen (ya existe; se mantiene).
- **CA-11.2**: Se editan fecha, hora de inicio y fin, lugar, invitados y responsable de coordinación. Todos son obligatorios; la fecha es hoy o futura (R-COT-4); invitados > 0; el responsable es un usuario activo, administrador o encargado de eventos (RN09).
- **CA-11.3**: Se muestran los servicios contratados (ya existe; se mantiene).
- **CA-11.4**: Estados: `programado → confirmado → en ejecución → finalizado`, uno a la vez y sin volver atrás. Cancelar sigue como en 011.
- **CA-11.5**: Cada cambio de planificación y de estado guarda quién, cuándo y qué cambió (RN03), y se ve como historial en el evento.
- **CA-11.6**: Cancelar no borra pagos, gastos ni movimientos (RN10): ya lo garantiza la base (sin FK entre módulos, append-only).

## 5. Reglas
- **R-EVT-6** *(equipo, provisional)*: la planificación se edita en **programado** y **confirmado**. En ejecución, finalizado o cancelado, no.
- **R-EVT-7** *(equipo, provisional)*: editar el evento **no cambia el contrato ni la cotización**: el contrato conserva lo firmado. Más invitados no recalcula el total; si el cliente paga más, se registra aparte (otra cotización o ingreso).
- **R-EVT-8** *(equipo, provisional)*: pasar a **en ejecución** solo el día del evento; pasar a **finalizado** solo desde en ejecución. No se exige saldo en cero para finalizar (el saldo se ve en la ficha).
- **R-EVT-9** *(equipo, provisional)*: si cambian fecha u horario, el sistema **avisa** que el personal asignado puede tener otro horario. La revisión de asignaciones es del módulo de personal (HU17).

## 6. Fuera de alcance
- Reprogramar con nuevo contrato o cambiar el precio.
- Volver de estado (p. ej., de confirmado a programado).
- Recalcular asignaciones de personal (Harold, HU17).

## 7. No funcionales
- Dos ediciones simultáneas: gana la última y ambas quedan en el historial.

## 8. Preguntas abiertas (para Harold o Darze)
- [ ] R-EVT-6: ¿se puede editar algo en ejecución (p. ej., invitados reales)?
- [ ] R-EVT-8: ¿hace falta saldo en cero para finalizar?
