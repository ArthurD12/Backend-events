# Spec: Consultar la disponibilidad del personal

- **ID**: 034-staff-availability
- **Estado**: **borrador — Q1–Q10 cerradas (PO, 27/11/2026); pendiente de revisión final del PO antes de plan**
- **Módulos afectados**: `staff` (disponibilidad y consulta de agenda), `identity` (permiso `staff:availability`), `commercial` (solo lectura de datos del evento en conflicto, si aplica)
- **Historia**: HU16 (#17)

## 1. Problema y objetivo
Hoy la planificación de los servicios se hace con hojas de Excel y llamadas telefónicas para saber quién puede trabajar. No existe un lugar donde registrar que un trabajador **no puede** trabajar un día u horario (vacaciones, permiso, descanso), ni una forma rápida de ver, para una fecha y horario concretos, **quién está libre, quién ya está asignado a otro evento y quién avisó que no puede**. Esto provoca cruces de agenda descubiertos tarde, llamadas repetidas y personal que se compromete en dos eventos.

El objetivo es **consultar la disponibilidad del personal por fecha, horario y función**, y **registrar indisponibilidades planificadas**, para decidir a quién asignar con información confiable. En esta entrega lo hace el **administrador**: el **encargado de eventos no accede a la disponibilidad ni a datos de trabajadores o pagos** (solo verá quién está designado en un evento, en un PR aparte). La consulta se apoya en las asignaciones de HU17 y **no las crea, edita ni anula**; tampoco sustituye la validación de cruces que ya hace HU17. Para que ambas vistas no discrepen, la ocupación que informa HU16 se calcula con **el mismo criterio de solape que aplica HU17** (reutilizándolo a través de `staff`, sin reimplementarlo) y la equivalencia se verifica con una prueba automatizada (CA-16.21, §7).

## 2. Actores
- **Administrador**: único rol con acceso a la disponibilidad. **Consulta** y **registra, corrige y anula** indisponibilidades.
- **Encargado de eventos** (en el negocio, **"vendedor"**): **sin acceso** a la disponibilidad, ni de lectura (Q1/Q8 cerradas, PO 27/11/2026). Es un rol de ventas; no debe ver datos de trabajadores ni pagos. Solo podrá ver **quién está designado en un evento**, mediante otro permiso/PR de solo lectura.
- **Encargado de compras y almacén**: **sin acceso** a la disponibilidad del personal, ni de lectura (coherente con R-STF-5/R-STF-16 y R-ASG-14; Q8 cerrada).
- **Trabajador**: no es usuario del sistema; no inicia sesión ni consulta ni registra su propia disponibilidad.

## 3. Historias de usuario
- **HU16 (issue #17)**: Como **administrador**, quiero consultar la disponibilidad del personal por fecha, horario y función para planificar correctamente cada servicio. *(El PO acotó el acceso a administrador: el encargado de eventos queda sin lectura, 27/11/2026.)*
- **HU16 (soporte)**: Como administrador, quiero registrar la indisponibilidad de un trabajador (vacaciones, permiso, descanso) para que la consulta de disponibilidad la refleje al planificar.

## 4. Criterios de aceptación

### 4.1 Trazabilidad con el issue #17

| Criterio del issue | Criterios de aceptación |
|---|---|
| Se podrá registrar disponibilidad o indisponibilidad por fecha y horario | CA-16.1, CA-16.2, CA-16.13, CA-16.14 |
| La consulta permitirá filtrar al personal por función | CA-16.4, CA-16.11 |
| El sistema mostrará únicamente trabajadores activos | CA-16.5, CA-16.6 |
| El resultado indicará si el trabajador está libre, ocupado o no disponible | CA-16.7, CA-16.8, CA-16.9, CA-16.10, CA-16.12 |
| La información deberá considerar las asignaciones existentes | CA-16.3, CA-16.7, CA-16.8, CA-16.15 |
| (Tarea backend) Cruce de Trabajador con sus asignaciones activas en tiempo real | CA-16.3, CA-16.7, CA-16.15, CA-16.16 |
| Equivalencia entre la ocupación de HU16 y el rechazo por solape de HU17 | CA-16.21 |

### 4.2 Criterios

- **CA-16.1**: Dado el **administrador** (único rol autorizado), cuando registra para un trabajador **activo** una indisponibilidad con fecha y horario y un motivo o tipo obligatorio (Q2 cerrada), entonces queda guardada, es consultable y su alta registra usuario y fecha-hora.
- **CA-16.2**: Dada una indisponibilidad registrada, cuando se intenta guardar con fecha u horario inválidos —fin anterior o igual al inicio sin cruce admitido, fecha fuera de formato, trabajador inexistente o inactivo—, entonces se rechaza con un mensaje claro y no se guarda nada.
- **CA-16.3**: Dada una consulta de disponibilidad con un **intervalo** —fecha y horario, o **día completo** si se omite la hora (Q7 cerrada)—, cuando se ejecuta, entonces devuelve, para cada trabajador **activo** que cumpla el filtro, si está **libre**, **ocupado** o **no disponible** en ese intervalo, calculado **en el momento** a partir de las asignaciones vigentes y las indisponibilidades registradas.
- **CA-16.4**: Dada una consulta con un filtro por **función** (lista fija o "otro"), cuando se aplica, entonces solo aparecen los trabajadores cuya función corresponda; sin filtro, se consideran todas las funciones.
- **CA-16.5**: Dado un trabajador **inactivo**, cuando se consulta la disponibilidad en cualquier fecha, entonces **no aparece** en el resultado, aunque tuviera asignaciones o indisponibilidades antiguas.
- **CA-16.6**: Dado un trabajador desactivado después de tener registros, cuando se le reactiva, entonces vuelve a aparecer en las consultas de fechas en las que no esté ocupado ni indisponible, conservando su historial de indisponibilidad.
- **CA-16.7**: Dado un trabajador con **una o más asignaciones `ACTIVE` con `occupies=true`** cuyos eventos **no están cancelados** y que comparten **cualquier instante** con el intervalo consultado, cuando se calcula su estado, entonces figura como **ocupado**; si no comparte ningún instante, no cuenta como ocupación. Las asignaciones de eventos **finalizados sí cuentan** como ocupación (Q6 cerrada, opción (a)): se aplica **exactamente el mismo criterio de solape de HU17** (`list_active_overlaps`) reutilizado a través de `staff`, sin reimplementarlo.
- **CA-16.8**: Dado un trabajador **ocupado**, cuando se muestra el resultado, entonces se indica el **detalle del conflicto** —código del evento, fecha y horario de la asignación y, si aplica, la función—, sin exponer pago, tarifa, documento ni teléfono (Q9 cerrada). Si hay más de una asignación en conflicto, se enumeran.
- **CA-16.9**: Dado un trabajador con una **indisponibilidad registrada** que cubre el intervalo consultado, cuando se muestra el resultado, entonces figura como **no disponible** con su motivo/tipo y el intervalo que lo cubre (Q2 cerrada).
- **CA-16.10**: Dado un trabajador que a la vez tiene una **indisponibilidad** y una **asignación vigente** que cubren el intervalo consultado, cuando se muestra el resultado, entonces se informa **no disponible** (prevalece) **y además** se muestra el detalle de la asignación en conflicto (Q5 cerrada).
- **CA-16.11**: Dada una consulta con **filtro por función y estado** (libre, ocupado, no disponible), cuando se aplican, entonces el resultado contiene solo los trabajadores que cumplen ambos; si no hay ninguno, devuelve un resultado vacío, no un error.
- **CA-16.12**: Dado un trabajador **sin asignaciones ni indisponibilidades** en el intervalo consultado, cuando se consulta, entonces figura como **libre**.
- **CA-16.13**: Dada una **indisponibilidad** registrada, cuando se consultan fechas y horarios que **no** se cruzan con ella, entonces no afecta el estado del trabajador; solo lo marca **no disponible** en los intervalos que cubre.
- **CA-16.14**: Dada una indisponibilidad que **cruza la medianoche** —por ejemplo, de 22:00 a 02:00—, cuando se aplica el mismo criterio de horario de HU17 (R-ASG-4), entonces cubre la madrugada siguiente; dos intervalos contiguos (`[08:00,12:00)` y `[12:00,16:00)`) no se solapan.
- **CA-16.15**: Dada una asignación de un evento **cancelado**, cuando se calcula la ocupación, entonces **no cuenta** (R-ASG-12, liberación perezosa); la consulta aplica el mismo criterio efectivo que HU17 (que la excluye antes de comprobar el solape) aunque el dato derivado no se haya actualizado todavía, y **no escribe**, **no modifica** ni **dispara** la liberación. Dada una asignación de un evento **finalizado**, entonces **sí cuenta** como ocupación, igual que en HU17 (Q6 cerrada, opción (a)).
- **CA-16.16**: Dada una consulta de disponibilidad, cuando se ejecuta repetidamente sin cambios en asignaciones ni indisponibilidades, entonces el resultado es el mismo; la consulta es de **solo lectura** y no crea, edita, anula ni libera asignaciones.
- **CA-16.17**: Dado un usuario **sin sesión**, un **encargado de eventos**, un **encargado de compras y almacén**, o un rol sin el permiso `staff:availability`, cuando intenta **consultar, registrar, editar o anular** disponibilidad, entonces se le deniega el acceso y no se modifica nada. El único rol con acceso es el **administrador** (Q1/Q8 cerradas).
- **CA-16.18**: Dado un registro de indisponibilidad, cuando se **edita o anula** (Q4 cerrada), entonces el cambio exige **motivo obligatorio** y conserva usuario y fecha-hora, y el registro anterior no se borra físicamente.
- **CA-16.19**: Dada la consulta y el alta de asignaciones de HU17, cuando cambia una asignación (alta, edición o anulación) o una indisponibilidad, entonces la siguiente consulta de disponibilidad **refleja el cambio**, sin que HU16 redefina ni relaje la regla de no solape de HU17.
- **CA-16.20**: Dado un intervalo de consulta mayor que el máximo permitido —**31 días** (Q7 cerrada)—, cuando se ejecuta, entonces se rechaza con un mensaje que indica el rango máximo; no se ejecuta una consulta masiva.
- **CA-16.21**: Dado un mismo conjunto de asignaciones y un intervalo, cuando HU16 calcula la ocupación y HU17 evalúa un alta/edición equivalente, entonces ambos aplican el mismo criterio compartido: toda asignación que HU16 marca como **ocupada** es exactamente la que HU17 rechazaría con **409** —incluidos los eventos **finalizados**— y toda asignación de evento **cancelado** que HU16 no marca tampoco bloquea en HU17. La equivalencia se verifica con una prueba automatizada (ver §7).

## 5. Reglas de negocio

- **R-DIS-1**: La consulta de disponibilidad es de **solo lectura**: informa, no asigna ni modifica asignaciones. Toda escritura de asignaciones es de HU17 (R-ASG-*).
- **R-DIS-2** *(RN11, R-STF-4)*: solo se muestran **trabajadores activos**. La baja lógica y el historial siguen R-STF-2/R-STF-3; al reactivar, el trabajador vuelve a consultarse (R-STF-15).
- **R-DIS-3**: el resultado expresa **un estado por trabajador y por intervalo consultado**, con tres valores: **libre**, **ocupado** y **no disponible**. Se muestran los detalles de ambos conflictos (Q5 cerrada), pero el estado principal sigue siendo uno solo.
- **R-DIS-4** *(R-ASG-3, R-ASG-4, R-ASG-12; Q6 cerrada)*: se considera **ocupado** al trabajador con una asignación **`ACTIVE` con `occupies=true`** de un evento **no cancelado** que comparte algún instante con el intervalo consultado. El horario es **semiabierto** y admite cruce de medianoche; las asignaciones **anuladas** y las de eventos **cancelados** no ocupan. Las asignaciones de eventos **finalizados sí ocupan**, igual que en HU17. HU16 **no redefine** estas reglas: **reutiliza el mismo criterio de solape de HU17** (`list_active_overlaps` y la liberación de eventos cancelados) a través de `staff`, **sin reimplementarlo**; al ser de solo lectura, aplica el mismo criterio efectivo sin escribir ni disparar la liberación. La equivalencia se prueba con CA-16.21.
- **R-DIS-5**: una **indisponibilidad** es una marca de planificación sobre un trabajador y un intervalo (fecha y horario), con un motivo o tipo. No es una asignación, no genera pago, no modifica la ficha del trabajador y **no anula ni mueve** asignaciones ya existentes; solo se refleja en la consulta. **Q3 cerrada**: en esta entrega es **solo informativa** y **no bloquea** la asignación en HU17; el bloqueo queda como evolución explícita en un PR aparte, junto con R-STF-4.
- **R-DIS-6**: la disponibilidad registrada es **planificación**, no **asistencia**. Si el trabajador se presentó o faltó a un evento es HU18 y queda fuera de esta feature.
- **R-DIS-7** *(R-COT-1)*: las fechas y horas se interpretan en **`America/Lima`** y se guardan en UTC; la presentación vuelve a `America/Lima`. El intervalo es semiabierto `[inicio, fin)`.
- **R-DIS-8** *(R-STF-5/R-STF-16, R-ASG-14; Q1/Q8 cerradas)*: la autorización es por **permiso**. **Consultar, registrar, editar y anular** disponibilidad exigen el permiso `staff:availability`, que **solo tiene el administrador**. `staff:manage` **no da acceso** a disponibilidad: lo tienen administrador y encargado de eventos, y el encargado de eventos queda **fuera** de toda operación de disponibilidad, incluida la lectura. En el negocio, el encargado de eventos es de ventas y no debe ver datos de trabajadores ni pagos; solo verá **quién está designado en un evento** mediante otro permiso/PR de solo lectura.
- **R-DIS-9** *(Q9 cerrada)*: el resultado **nunca** expone pago acordado, tarifa, documento ni teléfono; como máximo, nombre, función y estado y, si está ocupado, el código, fecha, horario y función del evento en conflicto.
- **R-DIS-10**: una indisponibilidad **pasada** no desaparece por el paso del tiempo ni por desactivar al trabajador; se conserva para la consulta y el historial (Q10 cerrada).

### 5.1 Matriz de permisos (definitiva; Q1/Q8 cerradas)

| Acción | Permiso | Administrador | Encargado de eventos | Encargado de compras y almacén |
|---|---|:-:|:-:|:-:|
| Consultar disponibilidad | `staff:availability` | ✔ | – | – |
| Registrar indisponibilidad | `staff:availability` | ✔ | – | – |
| Editar / anular indisponibilidad (Q4 cerrada) | `staff:availability` | ✔ | – | – |


## 6. Fuera de alcance
- **Asistencia, historial laboral visible y evaluación** del trabajador (HU18, #19).
- **Planilla, liquidaciones y egresos** al personal (`ledger`); el pago acordado sigue en HU17 y no es egreso (R-PAG-3).
- **Crear, editar o anular asignaciones** y la validación de no solape: son de HU17 y no se redefinen aquí.
- **Editar la ficha del trabajador** o sus datos de contacto/tarifa.
- **Notificaciones** al trabajador (no es usuario) ni al encargado.
- **Sustituir el bloqueo de asignación por indisponibilidad**: el bloqueo (409) queda como **evolución explícita en otro PR** (Q3 cerrada); esta feature es solo informativa.
- **Frontend** (otro repositorio) y **multi-tenant** (una sola organización).
- Reportes históricos de disponibilidad, exportaciones y calendarios visuales.
- **Ajustar la ocupación cuando un evento finaliza antes de lo planificado**: si un evento termina antes, la asignación **sigue ocupando el horario original**; cambiarlo exige modificar HU17 y queda como **evolución futura**, fuera de esta feature.

## 7. Requisitos no funcionales
- **Consistencia en tiempo real**: el estado se calcula con las asignaciones e indisponibilidades vigentes al momento de la consulta; no se acepta un dato en caché desactualizado **[suposición]**.
- **Rendimiento**: la consulta debe responder con fluidez para un plantel de decenas a pocos cientos de trabajadores y un rango de fechas de hasta **31 días** por consulta (Q7 cerrada); sin consultas masivas sin límite.
- **Autorización**: se aplica en el servidor por permiso `staff:availability`; ninguna respuesta entrega datos de personal, pagos ni tarifas. El **encargado de eventos** y el **encargado de compras y almacén** no tienen acceso, ni de lectura (R-DIS-8/R-DIS-9).
- **Errores en español y accionables**: rango excedido, fechas inválidas y trabajador inexistente se explican sin exponer datos de más.
- **Auditoría** (RN03): todo alta, edición o anulación de indisponibilidad guarda usuario, fecha-hora y motivo (Q4 cerrada).
- **Fechas** en UTC, presentación en `America/Lima`; sin importes en esta feature.
- **Contrato OpenAPI**: `operationId` estables y sin cambios incompatibles dentro de `/v1`; `openapi.json` regenerado.
- **Sin dependencias ni servicios nuevos**; el permiso `staff:availability` se declara en la tabla de permisos sin migración de datos (precedente HU17).
- **Prueba de equivalencia HU16↔HU17**: con datos que incluyan asignaciones solapadas de eventos `SCHEDULED`, `CONFIRMED`, `IN_PROGRESS`, **`FINISHED`** y **`CANCELLED`**, verificar que el conjunto marcado **"ocupado"** por la consulta de HU16 coincide exactamente con el conjunto que hace que HU17 responda **409** (incluidos finalizados, excluidos cancelados). La prueba **no duplica la lógica**: compara los resultados de ambos caminos sobre el mismo criterio compartido.

## 8. Dependencias
- **HU17 (033-staff-assignments) implementada**: asignaciones con horario propio semiabierto, estados de evento, R-ASG-12 (liberación perezosa) y el cálculo interno de ocupación. HU16 **reutiliza** esas reglas a través de la superficie pública de `staff`; no las duplica ni las modifica.
- **HU15 (032-staff) implementada**: ficha del trabajador, estado activo/inactivo y función (opcional, lista fija + "otro"). La consulta obtiene estado y función por la superficie pública de `staff`. `staff:manage` sigue rigiendo la gestión de trabajadores, pero **no da acceso a disponibilidad**.
- **`commercial.public_api`**: solo si el resultado muestra el **código, fecha y horario del evento en conflicto** (Q9); se obtiene por su superficie pública, nunca por sus tablas. La consulta de disponibilidad **no** necesita datos de contrato, cotización ni pagos.
- **`identity`**: declara el permiso `staff:availability`, usado tanto para **consultar** como para **escribir**; **solo el administrador** lo recibe por defecto.
- **PR aparte (fuera de HU16)**: el cambio de permisos del encargado de eventos en HU15 y HU17 (quitarle lectura de personal/pagos) y el nuevo permiso de **solo lectura del personal designado por evento** se tratan en un **PR independiente**. Esta feature (HU16) **no modifica** HU15, HU17, su código ni sus spec/plan.
- **Un solo evento por asignación**, **una sola organización**; sin multi-tenant.

## 9. Supuestos
- El término **"disponibilidad"** del issue cubre dos cosas: **registrar indisponibilidad** y **consultar el estado**. No se registra "disponibilidad positiva": un trabajador sin indisponibilidad y sin asignación se considera **libre** por defecto.
- La consulta es de **solo lectura** y **no** dispara la liberación perezosa de R-ASG-12; por eso al calcular **excluye** las asignaciones de eventos **cancelados**, sin escribir, y **cuenta** las de eventos **finalizados** (Q6 cerrada, opción (a)). En ambos casos aplica el **mismo criterio efectivo que HU17** reutilizado a través de `staff`, sin reimplementarlo.
- El **administrador** es el único rol que consulta y escribe disponibilidad; el **encargado de eventos** (rol "vendedor") **no accede** a disponibilidad ni a datos de personal/pagos (Q1/Q8 cerradas).
- La **indisponibilidad** no es una asignación ni genera pago; es una marca de agenda y en esta entrega es **solo informativa** (Q3 cerrada).
- El estado **"no disponible"** depende del registro de indisponibilidad, que en esta entrega sí se implementa (Q1 cerrada).
- El **evento no tiene nombre propio**: su identificador es el código `EVT-AAAA-NNNN` (R-ASG-5).
- Volumen de **decenas a pocos cientos** de trabajadores y un rango de fechas de hasta **31 días** por consulta (Q7 cerrada).

## 10. Preguntas abiertas

> **Cerradas por el PO el 27/11/2026:** Q1 a Q10, incluida Q6 (opción (a): "ocupado" cuenta los eventos finalizados y excluye los cancelados, con el mismo criterio de HU17).
> **Estado:** borrador, pendiente de revisión final del PO antes de pasar a plan.

### Cerradas

- [x] **Q6 — Definición exacta de "ocupado".** **Cerrada (PO, 27/11/2026).**
  - Decisión: **(a)** "ocupado" = asignaciones `ACTIVE` con `occupies=true` que se solapan con el intervalo, **incluidos los eventos finalizados**; las asignaciones de eventos **cancelados no cuentan** (la liberación perezosa de HU17 las excluye antes de comprobar). HU16 **reutiliza el mismo criterio de solape de HU17** (`list_active_overlaps` y la liberación de eventos cancelados) a través de `staff`, **sin reimplementarlo**; al ser de solo lectura, aplica el mismo criterio efectivo sin escribir ni disparar la liberación. La equivalencia se verifica con CA-16.21 (§7).
  - Descartado: (b) excluir los eventos finalizados (exigiría cambiar HU17 en un PR aparte y rompería la equivalencia con el comportamiento actual).

- [x] **Q1 — ¿Quién registra la indisponibilidad y con qué permiso?** **Cerrada (PO, 27/11/2026).**
  - Decisión: se crea el permiso `staff:availability`, usado para **consultar y escribir** (registrar, editar, anular), **solo para el administrador**. El **encargado de eventos no accede a nada de disponibilidad, ni de lectura**. Motivo: es un rol de ventas y no debe ver datos de trabajadores ni pagos; solo verá quién está designado en un evento (otro permiso/PR).
  - Descartado: (b) reutilizar `staff:assign`; (c) que el encargado de eventos registre o consulte con `staff:manage`.

- [x] **Q2 — Granularidad y forma de la indisponibilidad.** **Cerrada (PO, 27/11/2026).**
  - Decisión: **(a)** intervalo con **fecha + hora de inicio + hora de fin**, **varios intervalos por día**, con **cruce de medianoche** como R-ASG-4, y **motivo/tipo obligatorio** (vacaciones, permiso, descanso, otro con descripción).
  - Descartado: (b) día completo únicamente; (c) motivo opcional.

- [x] **Q3 — ¿La indisponibilidad bloquea la asignación en HU17 (409) o es solo informativa?** **Cerrada (PO, 27/11/2026).**
  - Decisión: **solo informativa**; **no bloquea** la asignación en HU17. El bloqueo queda como **evolución explícita en otro PR**, junto con R-STF-4.
  - Evidencia de que "informativa" refleja el comportamiento actual: HU17 **no consulta disponibilidad en absoluto** (solo evento, trabajador activo, fecha y solape; ver `register_assignment.py:95-129`).
  - Descartado: (b) bloquear con 409 y (c) avisar sin bloquear en esta entrega.

- [x] **Q4 — ¿Se pueden editar o anular registros de indisponibilidad? ¿Con auditoría o append-only?** **Cerrada (PO, 27/11/2026).**
  - Decisión: **(a)** **editar y anular** con **motivo obligatorio**, **usuario** y **fecha-hora**, **sin borrado físico** (precedente R-ASG-8/R-ASG-9).
  - Descartado: (b) append-only; (c) sin edición ni anulación en esta versión.

- [x] **Q5 — Si un trabajador está a la vez no disponible y con asignación solapada, ¿qué estado prevalece?** **Cerrada (PO, 27/11/2026).**
  - Decisión: **(a)** prevalece **no disponible** y se muestran **ambos detalles** (indisponibilidad y evento en conflicto).
  - Descartado: (b) prevalece ocupado; (c) estado único "conflicto".

- [x] **Q7 — Entrada de la consulta sin horario y rango máximo.** **Cerrada (PO, 27/11/2026).**
  - Decisión: **(a)** sin hora = **día completo en `America/Lima`**; rango máximo de **31 días** por consulta.
  - Descartado: (b) rango máximo de 7 días; (c) exigir siempre fecha y horario, sin rango.

- [x] **Q8 — ¿La consulta exige `staff:manage` y compras queda sin acceso?** **Cerrada (PO, 27/11/2026).**
  - Decisión: la consulta exige **`staff:availability`**, **solo administrador**; el **encargado de eventos tampoco consulta** y el **encargado de compras y almacén queda sin acceso**, ni de lectura.
  - Descartado: (b) abrir la consulta a compras con `events:read`.

- [x] **Q9 — ¿Qué datos devuelve el resultado?** **Cerrada (PO, 27/11/2026).**
  - Decisión: **(a)** **nombre, función y estado**; si está ocupado, **código, fecha, horario y función** del evento en conflicto; **nunca** pago, tarifa, documento ni teléfono.
  - Descartado: (b) añadir teléfono; (c) sin detalle del evento en conflicto.

- [x] **Q10 — ¿La indisponibilidad pasada sigue visible? ¿Se conserva al desactivar al trabajador?** **Cerrada (PO, 27/11/2026).**
  - Decisión: **(a)** se **conserva siempre**, también al desactivar al trabajador; este solo deja de aparecer en consultas futuras por estar inactivo (R-DIS-2), sin borrar el historial.
  - Descartado: (b) archivar/ocultar al pasar la fecha; (c) eliminar al desactivar.

