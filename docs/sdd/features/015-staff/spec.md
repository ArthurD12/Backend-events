# Spec: Personal, disponibilidad y asignaciones

- **ID**: 015-staff
- **Estado**: borrador
- **Módulos afectados**: `staff` (nuevo), `commercial` (consulta de eventos y liberar asignaciones al cancelar), `identity` (permisos nuevos)
- **Historias**: HU15 (#16), HU16 (#17), HU17 (#18)

## 1. Problema y objetivo
Darze arma un equipo distinto para cada evento (cocineros, mozos, bartenders…). Hoy lo coordina por teléfono y en Excel, y a veces cita a la misma persona a dos eventos que se cruzan. El objetivo es tener el registro del personal, ver quién está libre para un horario y asignarlo al evento sin que se crucen sus horarios.

## 2. Actores
- **Administrador** y **encargado de eventos** (`staff:manage`): registran y editan trabajadores, su indisponibilidad y las asignaciones (DOMAIN.md §9: "Eventos, personal y asignaciones").
- **Encargado de compras y almacén** (`staff:read`): solo consulta.

## 3. Historias
- **HU15**: Como administrador, quiero registrar y mantener los datos del personal para controlar a los trabajadores disponibles para los eventos.
- **HU16**: Como encargado de eventos, quiero consultar la disponibilidad del personal por fecha, horario y función para planificar correctamente cada servicio.
- **HU17**: Como encargado de eventos, quiero asignar trabajadores a un evento y recibir alertas de cruces para evitar duplicidad de horarios.

## 4. Criterios de aceptación
### HU15 — Datos del personal
- **CA-15.1**: Se registra nombre, documento (DNI o CE), teléfono, función, tipo de trabajador y tarifa referencial (soles por evento).
- **CA-15.2**: Dos trabajadores no tienen el mismo documento (`staff.document_taken`, 409). Lo garantiza la base de datos.
- **CA-15.3**: Se modifican todos los datos; el documento solo si no lo tiene otro trabajador.
- **CA-15.4**: Un trabajador se activa o desactiva. No se elimina (RN02).
- **CA-15.5**: Desactivarlo no borra sus asignaciones pasadas. Un trabajador inactivo no se puede asignar.
- **CA-15.6**: La lista se filtra por función, estado y texto (nombre o documento, sin distinguir tildes, como clientes).

### HU16 — Disponibilidad
- **CA-16.1**: Se registra un periodo de **indisponibilidad** de un trabajador (fecha, hora de inicio y fin, motivo opcional) y se puede quitar.
- **CA-16.2**: La consulta recibe fecha, hora de inicio y hora de fin, y filtra por función opcional.
- **CA-16.3**: Solo muestra trabajadores **activos**.
- **CA-16.4**: Cada trabajador sale como **libre**, **ocupado** (tiene una asignación que se cruza; se muestra con qué evento) o **no disponible** (tiene una indisponibilidad que se cruza). Si tiene ambas, sale como ocupado.

### HU17 — Asignaciones
- **CA-17.1**: Se asigna un trabajador a un evento **programado, confirmado o en ejecución**.
- **CA-17.2**: Cada asignación indica función, horario (por defecto el del evento) y pago acordado (por defecto la tarifa referencial del trabajador).
- **CA-17.3**: Un trabajador no tiene dos asignaciones vigentes con horarios que se cruzan (RN12). Lo garantiza PostgreSQL (AGENTS.md, regla 7).
- **CA-17.4**: Si se cruza, el error (`staff.assignment_overlap`, 409) dice **el código del evento** y el horario con el que choca.
- **CA-17.5**: Tampoco se asigna a alguien inactivo (`staff.worker_inactive`, 409) ni en un horario que marcó como no disponible (`staff.worker_unavailable`, 409).
- **CA-17.6**: El detalle del evento muestra todos los trabajadores asignados con su función, horario y pago acordado.
- **CA-17.7**: Una asignación se puede **retirar** (con motivo opcional). No se borra: queda registrada como retirada, con quién y cuándo, y deja de bloquear el horario.

## 5. Reglas
- **R-STF-1** *(equipo, provisional)*: **funciones** de lista fija: Cocinero, Ayudante de cocina, Mozo, Bartender, Coordinador, Montaje, Otro.
- **R-STF-2** *(equipo, provisional)*: **tipo de trabajador**: Fijo o Eventual. No cambia ninguna regla; sirve para filtrar.
- **R-STF-3** *(equipo, provisional)*: la tarifa referencial es **por evento** (como el cobro del personal, DOMAIN.md §4.1 regla 3). El pago acordado se puede cambiar en cada asignación y puede ser 0 (ayuda sin pago).
- **R-STF-4** *(equipo, provisional)*: el horario de la asignación puede ser distinto del evento (p. ej., cocina llega antes), pero empieza el día del evento. Igual que el evento, si la hora de fin es menor que la de inicio, termina al día siguiente (R-COT-1).
- **R-STF-5** *(equipo, provisional)*: **cancelar un evento retira todas sus asignaciones** en el mismo paso, con el motivo "Evento cancelado". Así sus trabajadores quedan libres.
- **R-STF-6** *(equipo, provisional)*: un trabajador puede tener **varias asignaciones en el mismo evento** si los horarios no se cruzan (p. ej., montaje en la mañana y mozo en la noche).
- **R-STF-7** *(equipo, provisional)*: el responsable de coordinación del evento sigue siendo un usuario del sistema (R-EVT-2). Asignar un trabajador con función "Coordinador" no lo cambia.

## 6. Fuera de alcance
- Asistencia y pago efectivo a los trabajadores (HU18 y egresos, HU21).
- Disponibilidad recurrente (p. ej., "nunca los lunes").
- Calendario visual del personal: la consulta devuelve una lista por horario.
- Que un trabajador sea usuario del sistema.

## 7. No funcionales
- Dos asignaciones simultáneas que se cruzan: solo una se guarda (restricción de exclusión).
- Auditoría: quién creó, editó, retiró, y cuándo (RN03).
- Horarios en hora de Lima en pantalla; en la base, `timestamptz` en UTC (regla 4).

## 8. Preguntas abiertas
- [ ] R-STF-1 y R-STF-2: confirmar con Darze la lista de funciones y tipos.
- [ ] R-STF-5: ¿cancelar el evento libera al personal automáticamente, o se avisa y se decide uno por uno?
