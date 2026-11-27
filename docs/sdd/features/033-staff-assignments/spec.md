# Spec: Asignación de trabajadores a eventos

- **ID**: 033-staff-assignments
- **Estado**: aprobado (PO, 25/11/2026), con las recomendaciones Q1–Q8 aceptadas
- **Módulos afectados**: `staff` (asignaciones), `identity` (permiso `staff:assign`), `commercial` (consulta del evento por `public_api`), `reporting` (ficha consolidada, consumo de `staff.public_api`)
- **Historia**: HU17 (#18)


> **Actualización del 27/11/2026 (feature 025, aprobada por el Product Owner a partir de la aclaración del cliente):** el encargado de eventos es de ventas y **ya no tiene `staff:manage`**: no ve datos de trabajadores, asignaciones ni pagos, y recibe 403 en estas rutas. Solo ve el personal designado de un evento (nombre y función) con `staff_roster:read`. Donde este documento diga que el encargado de eventos accede, prevalece `docs/sdd/features/025-sales-staff-permissions/spec.md` y DOMAIN.md §9 y §11.

## 1. Problema y objetivo
Hoy Darze decide quién trabaja en cada evento de forma verbal o en hojas de Excel. No queda un registro confiable de **quién trabajó, con qué función, en qué horario y por cuánto se acordó pagarle**, y es fácil asignar a la misma persona a dos eventos que se cruzan. La ficha consolidada del evento (HU14) tampoco puede mostrar al personal porque esa información no existe.

El objetivo es **asignar trabajadores activos a un evento**, con función, horario y pago acordado, **impidiendo cruces de horario** de un mismo trabajador entre todos sus eventos. La asignación es la base del historial laboral (HU18) y del bloque «Personal asignado» de la ficha del evento; el pago acordado aquí **no es un egreso** hasta que se registre en el ledger (R-PAG-3).

## 2. Actores
- **Administrador**: crea, edita, anula y consulta asignaciones. Es el único que crea y edita (decisión del PO, 25/11/2026).
- **Encargado de eventos** (en el negocio, **"vendedor"**): consulta las asignaciones de los eventos; **no crea, no edita y no anula**. El historial por trabajador es HU18.
- **Encargado de compras y almacén**: **sin acceso** a las asignaciones, ni de lectura (decisión del PO, 25/11/2026; coherente con R-STF-5/R-STF-16).
- **Trabajador**: no es usuario del sistema; no inicia sesión ni consulta sus asignaciones.

> El issue #18 está redactado «como encargado de eventos». La decisión del PO del 25/11/2026 limita la escritura al administrador mediante el permiso `staff:assign`; este spec recoge esa decisión. Si el PO quisiera habilitar al encargado, es un cambio en la tabla de permisos, no en el modelo de negocio.

## 3. Historia
- **HU17**: Como encargado de eventos, quiero asignar trabajadores a un evento y recibir alertas de cruces para evitar duplicidad de horarios.

## 4. Criterios de aceptación

### 4.1 Trazabilidad con el issue #18

| Criterio del issue | Criterios de aceptación |
|---|---|
| Seleccionar un evento activo y asignar trabajadores disponibles | CA-17.1, CA-17.2, CA-17.3, CA-17.24, CA-17.26 |
| Cada asignación indica función, horario y pago acordado | CA-17.4, CA-17.5, CA-17.6, CA-17.22 |
| Impedir asignar en horarios coincidentes | CA-17.7, CA-17.8, CA-17.9, CA-17.11 |
| Mensaje con el evento que genera el conflicto | CA-17.10 |
| La lista del evento muestra trabajadores y funciones | CA-17.12, CA-17.21 |

### 4.2 Criterios

- **CA-17.1**: Dado un administrador autenticado con `staff:assign`, un trabajador **activo** y un evento en `programado` o `confirmado`, cuando registra una asignación con función, horario y pago, entonces queda guardada, asociada al evento y visible en la lista del evento.
- **CA-17.2**: Dado un trabajador **inactivo**, cuando se intenta asignarlo, entonces se rechaza con un mensaje claro y no se guarda ninguna asignación (RN11, R-STF-4).
- **CA-17.3**: Dado un evento `finalizado` o `cancelado`, cuando se intenta asignar a un trabajador, entonces se rechaza con un mensaje que indica el estado del evento y no se crea nada.
- **CA-17.4**: Dado un alta de asignación, cuando falta la función, el horario o el pago, entonces se rechaza y no se guarda parcialmente.
- **CA-17.5**: Dado un trabajador con función en su ficha, cuando se le asigna, entonces la función de la ficha se **propone** como valor inicial; si el administrador no la cambia, la asignación la **copia** (lista fija o "otro" con su descripción breve) y la conserva aunque después cambie la ficha del trabajador (R-STF-12, R-STF-17).
- **CA-17.6**: Dada una asignación con pago acordado, cuando el administrador cambia la **tarifa referencial** de la ficha del trabajador, entonces el pago de la asignación **no cambia**; y cuando cambia el pago de la asignación, la tarifa de la ficha tampoco cambia (R-STF-7, R-STF-8, RN13).
- **CA-17.7**: Dado un trabajador con una asignación vigente en un evento, cuando se intenta asignarlo a otro evento en un horario que comparte **cualquier instante**, entonces se rechaza y no se crea la segunda asignación (RN12).
- **CA-17.8**: Dados dos intervalos **contiguos** del mismo trabajador —por ejemplo, `[08:00, 12:00)` y `[12:00, 16:00)`—, cuando se guardan, entonces ambos se aceptan; el intervalo es **semiabierto** y el instante de fin no ocupa.
- **CA-17.9**: Dado un trabajador con una asignación que cruza la medianoche —por ejemplo, `[22:00, 02:00)`—, cuando se intenta otra asignación que comparte cualquier instante de la madrugada siguiente, entonces se detecta el cruce y se rechaza (R-COT-1).
- **CA-17.10**: Dado un cruce de horario, cuando se rechaza la asignación, entonces el mensaje **identifica el evento en conflicto** por su **código**, su **fecha** y su **horario**, y no expone datos personales innecesarios. Si hay más de un evento en conflicto, los enumera.
- **CA-17.11**: Dadas dos solicitudes **simultáneas** que asignan al mismo trabajador en horarios superpuestos, cuando se procesan, entonces **solo una** queda guardada y la otra recibe el rechazo por cruce; no quedan dos asignaciones solapadas (RN12, garantía de la base de datos).
- **CA-17.12**: Dado un evento con asignaciones, cuando se consulta su lista, entonces se ven **todos los trabajadores asignados vigentes** con su **nombre**, **función** (y descripción si es "otro") y **horario**, ordenados por hora de inicio.
- **CA-17.13**: Dada una asignación vigente, cuando el administrador edita horario, función o pago, entonces los valores nuevos se ven en la lista y el cambio queda registrado con **usuario, fecha-hora y motivo** (RN03).
- **CA-17.14**: Dada una edición de horario que genera un cruce con otra asignación del mismo trabajador, cuando se intenta guardar, entonces se rechaza con el detalle del evento en conflicto y la asignación **conserva sus valores anteriores**.
- **CA-17.15**: Dada una asignación existente, cuando se intenta cambiar el **trabajador** o el **evento**, entonces se rechaza: esos dos datos son inmutables. Para corregirlos se anula la asignación y se crea una nueva.
- **CA-17.16**: Dada una asignación vigente, cuando el administrador la **anula** indicando un motivo, entonces deja de contar como ocupación y de aparecer en la lista vigente del evento, **sigue existiendo** en el historial con su motivo, usuario y fecha-hora, y no se borra físicamente.
- **CA-17.17**: Dado un usuario sin sesión o un encargado de compras y almacén, cuando intenta leer, crear, editar o anular una asignación, entonces se le deniega el acceso y no se modifica nada; dado un encargado de eventos, cuando intenta crear, editar o anular, entonces se le deniega, pero **sí** puede leer (R-ASG-14).
- **CA-17.18**: Dada cualquier alta, edición o anulación, cuando se consulta la historia de la asignación, entonces se puede reconstruir **quién** lo hizo, **cuándo**, **qué** cambió (valores anteriores y nuevos de horario, función y pago) y **por qué** cuando corresponda; el historial no se edita ni se elimina (RN03).
- **CA-17.19**: Dado un evento cuya **fecha u horario** cambia, cuando se guarda el cambio, entonces el sistema **solo avisa** que el personal asignado puede tener otro horario (R-EVT-9); **no** recalcula ni mueve las asignaciones, que permanecen con su horario hasta que el administrador las revise.
- **CA-17.20**: Dado un evento **cancelado**, cuando se consultan sus asignaciones, entonces se conservan en el historial con la indicación de evento cancelado, dejan de contar como ocupación del trabajador y no se borran (RN10, por analogía).
- **CA-17.21**: Dada la consulta pública de asignaciones de un evento que expone `staff`, cuando un módulo autorizado la consume, entonces obtiene nombre, función (con descripción si es "otro") y horario de las asignaciones vigentes —**nunca el pago**—; si no hay ninguna, devuelve una lista vacía. La ficha consolidada (HU14, ya implementada) la usará para su bloque «Personal asignado» sustituyendo su adaptador nulo.
- **CA-17.22**: Dado un alta o edición con datos inválidos —horario sin inicio o fin, fin igual a inicio, fecha u hora fuera de formato, pago negativo o con decimales, función "otro" sin descripción, trabajador inexistente o evento inexistente—, cuando se intenta guardar, entonces se rechaza con un mensaje claro y no se guarda nada.
- **CA-17.23** *(Q1 aprobada)*: Dado un mismo trabajador y un mismo evento, cuando se registran dos asignaciones con horarios **no superpuestos** —por ejemplo, montaje y servicio—, entonces ambas se aceptan y se muestran por separado.
- **CA-17.24** *(Q3 y Q4 aprobadas)*: Dado un evento `en ejecución`, cuando se crea o edita una asignación, entonces se permite (con las mismas validaciones); dado un evento `finalizado`, cuando se intenta editar o anular una asignación, entonces se rechaza porque el registro es de solo lectura.
- **CA-17.25** *(Q7 aprobada)*: Dado un trabajador con asignaciones **futuras vigentes**, cuando se intenta desactivarlo, entonces se rechaza hasta que esas asignaciones se anulen o se reasignen; las asignaciones pasadas o anuladas no bloquean la baja.
- **CA-17.26** *(Q6 aprobada)*: Dado un trabajador **sin función** en su ficha, cuando se le asigna, entonces el administrador debe elegir una función para esa asignación (lista fija o "otro" con descripción) y la ficha del trabajador **no se modifica**.

## 5. Reglas de negocio

- **R-ASG-1** *(RN13, HU17)*: toda asignación indica **evento, trabajador, función, horario y pago acordado**; los cinco son obligatorios. El trabajador y el evento se fijan al crearla y no se cambian después.
- **R-ASG-2** *(RN11, R-STF-4)*: solo se asignan trabajadores **activos**. Un trabajador que se desactiva después conserva sus asignaciones e historial; no se borran.
- **R-ASG-3** *(RN12, ARCHITECTURE.md §6)*: un trabajador **no puede tener dos asignaciones vigentes que compartan algún instante**, en el mismo evento o en eventos distintos. La garantía real es una **restricción de exclusión en PostgreSQL**, no solo la validación de la aplicación; la prueba de concurrencia es obligatoria.
- **R-ASG-4** *(R-COT-1)*: el horario de la asignación es propio: **fecha + hora de inicio + hora de fin**. Si la hora de fin es menor que la de inicio, termina al **día siguiente**; si es igual, es inválido (duración cero). Se interpreta en `America/Lima` y se guarda en UTC; la presentación vuelve a `America/Lima`.
- **R-ASG-5** *(issue #18, decisión del PO)*: ante un cruce, la respuesta es **409** e incluye el **código del evento** en conflicto, su **fecha** y su **horario**. El evento no tiene un campo «nombre» propio: su identificador estable es el código `EVT-AAAA-NNNN`.
- **R-ASG-6** *(R-STF-12, R-STF-17, RN13; decisión del PO, 25/11/2026)*: la ficha **propone** la función al asignar. El administrador puede **elegir otra** de la lista fija (cocinero, mozo, bartender, ayudante, coordinador) o "otro" con descripción breve obligatoria, porque un trabajador puede cubrir distintas funciones según el evento. La asignación conserva la función elegida aunque la ficha cambie después.
- **R-ASG-7** *(RN13, R-STF-7, R-STF-8, R-PAG-3)*: el **pago acordado** es obligatorio, entero en **céntimos de `PEN`** y **mayor o igual a cero**. Es independiente de la tarifa referencial de la ficha y **no es un egreso** hasta que se registre en el ledger; cambiarlo aquí no altera ningún movimiento contable.
- **R-ASG-8** *(decisión del PO, 25/11/2026; RN03)*: las asignaciones se pueden **editar** (horario, función y pago) y **anular**, pero **no se borran físicamente**. Toda edición y toda anulación guardan usuario, fecha-hora y motivo; el motivo es obligatorio en ambas (RN03).
- **R-ASG-9** *(RN03)*: el historial de la asignación es **de solo inserción**: conserva cada operación y, en las ediciones, los valores anteriores y nuevos de horario, función y pago. No se pierde aunque el trabajador se desactive o el evento se cancele.
- **R-ASG-10** *(R-EVT-5, R-EVT-6, R-EVT-8; Q4 aprobada)*: se asigna en eventos **`programado`** y **`confirmado`**; **nunca** en `finalizado` ni `cancelado`. En `en ejecución` se permite crear y editar (reemplazos el día del evento).
- **R-ASG-11** *(R-EVT-9)*: si cambia la fecha u horario del evento, el sistema **solo avisa**; no recalcula, no mueve ni anula asignaciones. La revisión y corrección son manuales y quedan auditadas.
- **R-ASG-12** *(RN10, por analogía)*: al cancelarse un evento, sus asignaciones **se conservan** en el historial, dejan de contar como ocupación y no bloquean al trabajador; no se eliminan.
- **R-ASG-13** *(regla 3 de AGENTS.md)*: la asignación referencia el evento **por ID, sin clave foránea** a tablas de `commercial`; los datos del evento (código, estado, fecha y horario) se obtienen por su `public_api`, nunca por consulta directa a sus tablas.
- **R-ASG-14** *(decisiones del PO, 25/11/2026; R-STF-5/R-STF-16)*: crear, editar y anular exigen `staff:assign`, concedido **solo al administrador**. Leer exige `staff:manage`, que tienen administrador y encargado de eventos; esa lectura incluye el **pago acordado** (decisión del PO, 25/11/2026). El encargado de compras y almacén **no tiene ninguno de los dos**, ni de lectura.
- **R-ASG-15** *(Q1 aprobada)*: un mismo trabajador puede tener **más de una asignación al mismo evento** si los horarios **no se superponen**; se muestran como líneas separadas.
- **R-ASG-16** *(R-STF-15; Q7 aprobada)*: no se puede **desactivar** a un trabajador con asignaciones **futuras vigentes**; primero hay que anularlas o reasignarlas. Las pasadas o anuladas no bloquean.
- **R-ASG-17** *(R-STF-13; Q6 aprobada)*: como la función de la ficha es opcional, si el trabajador no tiene función, la asignación **exige elegirla** en ese momento y **no modifica la ficha** del trabajador.
- **R-ASG-18** *(Q3 aprobada)*: el pago y el horario se pueden corregir mientras el evento está `programado`, `confirmado` o `en ejecución`, siempre con motivo y auditoría; cuando el evento pasa a `finalizado`, la asignación queda **de solo lectura**. Una corrección posterior se resuelve fuera de la asignación (ledger), no reescribiendo el acuerdo.

### 5.1 Matriz de permisos

| Acción | Permiso exigido | Administrador | Encargado de eventos | Encargado de compras y almacén |
|---|---|:-:|:-:|:-:|
| Crear asignación | `staff:assign` | ✔ | – | – |
| Editar horario, función o pago | `staff:assign` | ✔ | – | – |
| Anular asignación | `staff:assign` | ✔ | – | – |
| Leer lista y detalle de asignaciones | `staff:manage` | ✔ | ✔ | – |
| Ver «Personal asignado» en la ficha consolidada (HU14) | `staff:manage` (Q8) | ✔ | ✔ | – |

- El **encargado de compras** conserva `events:read` para la ficha del evento, pero **no** recibe datos de personal; se le oculta el bloque «Personal asignado» (Q8).
- `DOMAIN.md` §9 todavía dice «Eventos y asignaciones: compras = lectura». Es una **deuda documental**: la fila debe dividirse en «Eventos» (compras: lectura) y «Asignaciones» (compras: –), como se hizo con «Personal» en HU15. La decisión de negocio ya está tomada.

### 5.2 Auditoría e historial

- **Acciones auditadas**: `CREATED` (alta), `UPDATED` (edición de horario, función o pago) y `CANCELLED` (anulación).
- **Datos mínimos por registro**: asignación, acción, usuario, fecha-hora (UTC) y motivo. En `UPDATED`, además, los valores anteriores y nuevos de los campos modificados. El motivo es obligatorio tanto en `UPDATED` como en `CANCELLED` (RN03).
- **Inmutabilidad**: el historial no se edita ni se elimina; si falla su escritura, el cambio de la asignación no queda guardado (no puede existir un cambio sin trazabilidad).
- **Conservación**: se mantiene aunque el trabajador se desactive, el evento se cancele o la asignación se anule. La consulta visible del historial por trabajador corresponde a HU18; HU17 garantiza que exista y sea completo.
- **Datos sensibles**: el pago acordado solo se muestra a quienes tienen `staff:manage` (administrador y encargado de eventos); nunca al encargado de compras y almacén (decisión del PO, 25/11/2026).

### 5.3 Cambios del evento, cancelaciones y bloqueos

- **Cambio de fecha u horario** (R-EVT-9): el evento guarda el cambio y devuelve el aviso de que el personal puede requerir revisión. Las asignaciones **no se mueven**; el administrador las revisa y, si corresponde, las edita (con motivo) o las anula. El sistema no impide el cambio del evento por tener asignaciones.
- **Paso a `en ejecución`**: no altera las asignaciones ni sus pagos; se permite corregir mientras el evento siga en ejecución (Q3 aprobada).
- **Paso a `finalizado`**: las asignaciones quedan de solo lectura; se conservan para el historial y la ficha del evento.
- **Cancelación del evento**: las asignaciones se conservan, dejan de ocupar al trabajador y no se borran; no se exige anularlas una por una para liberar la agenda.
- **Desactivación del trabajador**: se bloquea si tiene asignaciones futuras vigentes (Q7 aprobada); si solo tiene pasadas o anuladas, se permite y el historial se conserva.
- **Anulación de una asignación**: deja de ocupar, de aparecer en la lista vigente y de contar para el evento; permanece en la historia. Si ya existía un egreso en el ledger, su corrección es del ledger (fuera de alcance), no de la asignación.

### 5.4 Integración con la ficha consolidada del evento (HU14)

- Para la ficha consolidada, HU17 expone una **lectura resumida** de las asignaciones vigentes de un evento: nombre del trabajador, función (y descripción si es "otro") y horario. Esa lectura **no** incluye documento, teléfono, tarifa ni pago; el detalle completo de la asignación solo se entrega a quien tiene `staff:manage`.
- La ficha consolidada (HU14, `019-event-sheet`) **ya está implementada** (PR #64) y hoy usa el adaptador nulo `NoEventStaff`; cuando `staff` publique `event_assignments`, `reporting` sustituye ese adaptador para poblar **«Personal asignado»** (CA-14.3). Ese cambio es del dueño de `reporting`; HU17 solo deja la consulta lista y lo anota en `docs/sdd/COORDINACION.md`.
- Si no hay asignaciones vigentes, la consulta pública devuelve una lista vacía; el texto «Sin información de personal» lo decide la ficha (HU14).
- `reporting` consume `staff.public_api`; no lee tablas de `staff` (regla 3 de AGENTS.md).
- Para el encargado de compras y almacén se **oculta el bloque** (Q8), coherente con R-ASG-14.

## 6. Fuera de alcance
- **Disponibilidad e indisponibilidad** del trabajador y la consulta «libre/ocupado» (HU16, #17): HU17 solo valida **activo** y **sin solape al guardar**; no implementa agendas ni filtros de disponibilidad.
- **Asistencia, historial laboral visible y evaluación** del trabajador (HU18, #19).
- **Liquidaciones, planilla y egresos** al personal (`ledger`). El pago acordado es informativo hasta que se registre un egreso (R-PAG-3).
- Recalcular, mover o anular asignaciones automáticamente al cambiar la fecha u horario del evento (R-EVT-9).
- Notificaciones al trabajador (no es usuario) ni al encargado.
- Editar la ficha del trabajador desde la asignación; solo se copia su función.
- Crear o modificar eventos, contratos o cotizaciones desde esta feature.
- Implementar o modificar la ficha consolidada del evento (HU14, `019-event-sheet`); HU17 solo expone `event_assignments` y el cambio del adaptador lo hace el dueño de `reporting`.
- Frontend (otro repositorio).

## 7. Requisitos no funcionales
- **Concurrencia**: dos altas simultáneas que se solapan no deben quedar ambas; la base de datos debe rechazar la segunda. Se prueba con dos transacciones reales.
- **Auditoría**: cada alta, edición y anulación deja rastro inmutable con usuario y fecha-hora; las ediciones y anulaciones, además, con su motivo. El historial se conserva siempre.
- **Autorización**: se aplica en el servidor por permiso; ninguna respuesta entrega datos de personal o pagos a roles sin `staff:manage`.
- **Errores en español y accionables**: el mensaje de cruce permite identificar el evento, la fecha y el horario; no expone documento, teléfono ni tarifa.
- **Dinero**: enteros en **céntimos de `PEN`**; nunca decimales. **Fechas**: UTC en almacenamiento, `America/Lima` en presentación.
- **Contrato OpenAPI**: `operationId` estables y sin cambios incompatibles dentro de `/v1`; `openapi.json` regenerado.
- **Volumen**: decenas a pocos cientos de trabajadores y decenas de asignaciones por evento; la lista del evento debe responder con fluidez sin paginación pesada **[suposición]**.

## 8. Dependencias y supuestos
- **HU15 (032-staff) implementada**: existen las fichas de trabajadores, el permiso `staff:manage` y la consulta de solo lectura que devuelve estado y función del trabajador. HU17 la usa para rechazar inactivos y copiar la función.
- **`commercial` expone la consulta del evento** (código, estado, fecha, hora de inicio y fin) por `public_api`; el evento se referencia por ID, sin FK entre módulos.
- **HU11 (018-event-planning) implementada**: estados y reglas R-EVT-5/6/8/9. HU17 no los redefine.
- **HU14 (019-event-sheet)**: implementada (PR #64) con adaptador nulo `NoEventStaff`; HU17 solo deja la consulta pública lista y coordina el cambio del adaptador con el dueño de `reporting` (`docs/sdd/COORDINACION.md` §4). No se modifica la ficha en esta feature.
- **Permisos en código**: `identity` los define en una tabla; el administrador recibe todos por defecto. Agregar `staff:assign` no requiere migración de base de datos.
- **Un solo evento por asignación** y **una sola organización**; no hay multi-tenant.
- **El evento no tiene nombre propio**: su identificador es el código `EVT-AAAA-NNNN`. El issue menciona «código/nombre»; se usa el código.
- **El evento nace de un contrato firmado con adelanto** (RN07/RN08): HU17 no revalida contrato, adelanto ni cotización; confía en que el evento existe y es válido.
- **"Disponible" en HU17** significa **activo y sin solape**; la indisponibilidad planificada llegará con HU16 y, cuando exista, deberá consultarse antes de asignar.
- **Pago acordado**: es un acuerdo, no un pago; no genera movimiento en el ledger (R-PAG-3). Los importes son céntimos enteros de `PEN`.
- **Zona horaria**: las horas del evento y de la asignación se interpretan en `America/Lima`; el cruce de medianoche sigue R-COT-1.
- **PostgreSQL** es la base del sistema; la garantía de no solape se apoya en una restricción del motor, no solo en la aplicación.
- **Sin dependencias ni servicios nuevos**; no se prevé ADR por la regla 11, salvo que el plan introduzca una extensión del motor y el equipo lo exija.

## 9. Decisiones del PO (25/11/2026)

> Aprobadas con las recomendaciones del equipo. Un cambio posterior se trata como cambio de alcance y exige actualizar este spec y `DOMAIN.md` §11.

- [x] **Q1 — ¿Más de una asignación del mismo trabajador al mismo evento?** ¿Se permite, por ejemplo, montaje y servicio en horarios no superpuestos?
  - **Decisión**: sí, permitirlas si no se solapan; se muestran como líneas separadas y cada una con su pago. La regla de no solape (RN12) ya evita el doble uso.
- [x] **Q2 — ¿Se puede anular una asignación o solo editarla?** ¿Con qué motivo?
  - **Decisión**: permitir **anular** con motivo obligatorio, sin borrado físico. Sin anulación, una asignación que no ocurrió (el trabajador canceló) quedaría como ocupación y como personal del evento. Se conserva en el historial y deja de bloquear.
- [x] **Q3 — ¿Se bloquean pago y horario cuando el evento pasa a `en ejecución` o `finalizado`?**
  - **Decisión**: en `en ejecución` todavía se corrige (con motivo y auditoría); en `finalizado` la asignación es de solo lectura. Así se protege lo acordado sin impedir ajustes del día.
- [x] **Q4 — ¿Qué estados del evento permiten asignar?** ¿`en ejecución` permite altas?
  - **Decisión**: `programado` y `confirmado` siempre; `en ejecución` **sí** para altas y reemplazos del día; `finalizado` y `cancelado`, nunca.
- [x] **Q5 — ¿El horario de la asignación es libre o debe coincidir con el del evento?**
  - **Decisión**: horario propio, precargado con el del evento y ajustable para montaje/desmontaje; debe empezar el día del evento (o el siguiente si cruza la medianoche). Si negocio quiere limitarlo estrictamente al horario del evento, se restringe.
- [x] **Q6 — ¿Qué función se usa si la ficha del trabajador no tiene función?** (En HU15 la función es opcional.)
  - **Decisión**: exigir la función en la asignación; si la ficha la tiene, se precarga y se copia; si no, el administrador la elige y la ficha **no** se modifica.
- [x] **Q7 — ¿Se puede desactivar a un trabajador con asignaciones futuras?** (R-STF-15 lo dejó para HU17.)
  - **Decisión**: bloquear la baja hasta anular o reasignar esas asignaciones; las pasadas o anuladas no bloquean. Evita trabajadores inactivos con eventos pendientes.
- [x] **Q8 — ¿El encargado de compras ve el bloque «Personal asignado» de la ficha consolidada?**
  - **Decisión**: **no**. La decisión 25/11/2026 le quita todo acceso a asignaciones; `DOMAIN.md` §9 debe dividir la fila «Eventos y asignaciones». Si negocio prefiere que vea el bloque por operación, habría que exceptuar solo nombre/función/horario y dejar fuera el pago.

- **Función distinta a la de la ficha (decisión del PO, 25/11/2026)**: se permite. La ficha propone la función y el administrador puede elegir otra de la lista (o "otro" con descripción); la asignación conserva la elegida (R-ASG-6).
