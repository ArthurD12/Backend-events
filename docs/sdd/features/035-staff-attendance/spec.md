# Spec: Registrar asistencia e historial del personal

- **ID**: 035-staff-attendance
- **Estado**: aprobado con ajustes (27/11/2026; evento huérfano 28/11/2026)
- **Módulos afectados**: `staff` (asistencia e historial), `identity` (permiso `staff:attendance`), `commercial` (solo lectura del evento por `public_api`)
- **Historia**: HU18 (#19)

## 1. Problema y objetivo

Darze ya puede asignar trabajadores a un evento con función, horario y pago acordado (HU17), pero **no registra qué ocurrió realmente después del evento**. Hoy no hay forma de saber si el trabajador se presentó o faltó, ni de consultar su participación histórica. Eso impide evaluar al personal, detectar incumplimientos y sostener con datos las decisiones de contratación o continuidad.

El objetivo es **registrar la asistencia por asignación** (cumplió / no cumplió) una vez terminado el evento, **corregirla dejando trazabilidad** de quién y cuándo la cambió y cuál era el valor anterior, y **consultar el historial de un trabajador** con la fecha, el evento, la función, el horario y el pago acordado. La asistencia es un dato de **evaluación**: no paga, no genera movimientos contables y no modifica la asignación de HU17 ni la disponibilidad de HU16.

## 2. Actores y permisos

### 2.1 Actores

- **Administrador**: único rol que **registra y corrige la asistencia** y que **consulta el historial** (incluido el pago acordado).
- **Encargado de eventos** (en el negocio, **"vendedor"**; es el mismo rol, no uno nuevo): **sin acceso** a la asistencia ni al historial con pagos. Su único acceso al personal sigue siendo `staff_roster:read` (quién está designado en un evento y con qué función, **sin pago**). HU18 no le añade ninguna operación.
- **Encargado de compras y almacén**: **sin acceso** a la asistencia ni al historial, ni de lectura.
- **Trabajador**: no es usuario del sistema; no inicia sesión ni registra ni consulta su propia asistencia.

### 2.2 Matriz de permisos

| Acción | Permiso exigido | Administrador | Encargado de eventos ("vendedor") | Encargado de compras y almacén |
|---|---|:-:|:-:|:-:|
| Registrar o corregir la asistencia de una asignación | `staff:attendance` | ✔ | – | – |
| Consultar el historial de un trabajador (incluye pago acordado) | `staff:manage` | ✔ | – | – |
| Ver el personal designado de un evento (existente, sin pago) | `staff_roster:read` | ✔ | ✔ | – |

- `staff:attendance` es un **permiso nuevo**, concedido **solo al administrador**, que lo recibe automáticamente por tener el conjunto completo de permisos. No cambia los permisos de HU15, HU16 ni HU17.
- `staff:manage` ya existe y **hoy solo lo tiene el administrador** (decisión del 27/11/2026, `DOMAIN.md` §9 y §11).
- El encargado de eventos y el de compras y almacén reciben **403** en ambas rutas de esta feature, aunque tengan `events:read` o `staff_roster:read`.

## 3. Historias de usuario

- **HU18 (issue #19)**: Como administrador, quiero registrar la asistencia y consultar el historial del personal para evaluar su participación en los eventos.
- **HU18 (soporte)**: Como administrador, quiero corregir una asistencia registrada por error y saber quién y cuándo la cambió, para que el historial sea confiable.
- **HU18 (soporte)**: Como administrador, quiero filtrar el historial de un trabajador por fechas y por evento, para revisar su participación en un periodo o en un evento concreto.

## 4. Trazabilidad con el issue #19

| Criterio del issue | Criterios de aceptación |
|---|---|
| Después del evento se podrá registrar la asistencia del personal asignado | CA-18.1, CA-18.2, CA-18.3, CA-18.17 |
| Se podrá indicar si el trabajador cumplió o no con su participación | CA-18.1, CA-18.2, CA-18.5 |
| El historial mostrará fecha, evento, función, horario y pago acordado | CA-18.6, CA-18.13, CA-18.20 |
| La consulta podrá filtrarse por trabajador, fecha o evento | CA-18.6, CA-18.7, CA-18.8 |
| Solo los usuarios autorizados podrán modificar la asistencia | CA-18.9, CA-18.10 |
| (Tarea backend) Endpoint PATCH para actualizar el estado de asistencia de una asignación | CA-18.1, CA-18.2, CA-18.3, CA-18.4, CA-18.11, CA-18.16 |
| (Tarea backend) Endpoint GET para extraer el historial de un trabajador específico | CA-18.5, CA-18.6, CA-18.7, CA-18.8, CA-18.14, CA-18.15 |

## 5. Criterios de aceptación

- **CA-18.1**: Dado un administrador autenticado con `staff:attendance`, una asignación **`ACTIVE`** cuya hora de fin (`end_at`, en UTC) ya pasó y **sin registro previo de asistencia**, cuando registra **`ATTENDED`** ("cumplió"), entonces la asignación queda con asistencia `ATTENDED`, se guarda **quién** y **cuándo** lo registró, y la respuesta refleja el nuevo estado **sin alterar** función, horario, pago ni estado de la asignación.
- **CA-18.2**: Dado el mismo contexto que CA-18.1, cuando el administrador registra **`NOT_ATTENDED`** ("no cumplió"), entonces la asignación queda con asistencia `NOT_ATTENDED` y se guarda quién y cuándo lo registró.
- **CA-18.3**: Dada una asignación `ACTIVE` cuya hora de fin **aún no ha pasado** (evento/asignación no terminado), cuando se intenta registrar la asistencia, entonces se rechaza con un error de conflicto que indica que la asignación todavía no termina y **no se guarda ningún registro**.
- **CA-18.4**: Dada una asignación **anulada** (`CANCELLED`), cuando se intenta registrar la asistencia —aunque su hora de fin ya haya pasado—, entonces se rechaza con un error de conflicto que indica que la asignación está anulada y **no se guarda ningún registro**.
- **CA-18.5**: Dada una asignación **sin registro de asistencia**, cuando aparece en el historial, entonces su estado de asistencia se muestra como **"sin registrar"** (`null`), distinguible de `NOT_ATTENDED`; no se interpreta como falta.
- **CA-18.6**: Dado un administrador autenticado con `staff:manage` y un **trabajador existente** (activo o inactivo), cuando consulta su historial, entonces obtiene **una fila por asignación** del trabajador con: fecha del evento, código y estado del evento, función (y descripción si es "otro"), horario (fecha/horas en `America/Lima` e instantes UTC), pago acordado en céntimos de `PEN` y estado de asistencia. Las filas se ordenan de la **más reciente a la más antigua** por el inicio de la asignación.
- **CA-18.7**: Dada una consulta de historial, cuando se aplican filtros opcionales por **rango de fechas del evento** (`desde`/`hasta`, inclusivos, en `America/Lima`) y/o por **evento** (`event_id`), entonces solo aparecen las asignaciones cuyo evento cumple los filtros; los filtros se pueden combinar. Si el rango es inválido (`desde` posterior a `hasta`), se rechaza con un error de validación y no se ejecuta la consulta. Sin coincidencias, se devuelve una lista vacía con total `0`, no un error.
- **CA-18.8**: Dada una consulta de historial con paginación, cuando se solicita una página, entonces se aplica la **paginación estándar del proyecto** (por defecto 20 filas, máximo 100) y la respuesta incluye el **total** de filas que cumplen los filtros. Una página fuera de rango devuelve la lista vacía con el total correcto.
- **CA-18.9**: Dado un usuario **sin sesión**, un **encargado de eventos** o un **encargado de compras y almacén**, cuando intenta registrar o corregir asistencia o consultar el historial, entonces se le deniega el acceso (401 si no hay sesión; 403 si el rol no tiene el permiso) y **no se modifica ni se expone nada**. Solo el administrador accede.
- **CA-18.10**: Dado un encargado de eventos, cuando consulta el personal designado de un evento, entonces sigue viendo **solo nombre y función, sin pago**, mediante `staff_roster:read`; HU18 **no le añade** asistencia, historial ni pagos, y no puede inferirlos por ninguna ruta de esta feature.
- **CA-18.11**: Dada una asignación con asistencia `ATTENDED`, cuando el administrador la corrige a `NOT_ATTENDED` (o al revés) **con un motivo no vacío**, entonces el nuevo valor prevalece, se conserva **el valor anterior**, **quién** hizo el cambio, **cuándo** y **el motivo**, y la corrección se puede hacer **en cualquier momento posterior**, sin límite de días. El historial de cambios es de solo inserción y no se edita ni se elimina. Si la corrección **no incluye motivo** (ausente, vacío o solo espacios), se rechaza con `422 staff.attendance_reason_required` y **no se modifica** la asistencia ni se crea registro de auditoría. El **primer registro** (`null` → `ATTENDED`/`NOT_ATTENDED`) **no** exige motivo (CA-18.1, CA-18.2).
- **CA-18.12**: Dada una asignación con asistencia `ATTENDED`, cuando el administrador vuelve a registrar `ATTENDED` (mismo valor), entonces la operación es **idempotente**: no crea un nuevo cambio ni altera la trazabilidad y devuelve el estado actual.
- **CA-18.13**: Dado un historial consultado con `staff:manage`, cuando se muestran los importes, entonces el **pago acordado** aparece como entero en **céntimos de `PEN`** (por ejemplo, `4500` para S/ 45.00), **no** genera ningún movimiento en el ledger y **no** se recalcula a partir de la tarifa del trabajador.
- **CA-18.14**: Dado un trabajador **inactivo** con asignaciones pasadas, cuando el administrador consulta su historial, entonces lo obtiene completo; la baja lógica del trabajador no borra ni oculta su historial.
- **CA-18.15**: Dado un identificador de asignación inexistente, cuando se intenta registrar su asistencia, entonces se responde **404**; dado un identificador de trabajador inexistente, cuando se consulta su historial, entonces se responde **404**. En ambos casos no se crea ni se modifica nada.
- **CA-18.16**: Dado un cuerpo de solicitud con estado de asistencia **faltante o distinto** de `ATTENDED`/`NOT_ATTENDED`, cuando se envía, entonces se rechaza con un error de validación y no se guarda nada.
- **CA-18.17**: Dada una asignación `ACTIVE` de un **evento cancelado** cuya hora de fin ya pasó, cuando el administrador registra la asistencia, entonces se permite y el historial la muestra con el evento en estado `CANCELLED`. Si la asignación aún no termina, aplica CA-18.3. HU18 **no inventa** ninguna otra política sobre eventos cancelados (devoluciones, pagos o sanciones).
- **CA-18.18**: Dado un trabajador con **varias asignaciones al mismo evento** (por ejemplo, montaje y servicio), cuando se consulta su historial, entonces aparecen como **filas separadas**, cada una con su propio horario, pago y estado de asistencia.
- **CA-18.19**: Dada una asistencia registrada o corregida, cuando se consulta la asignación, la disponibilidad o el ledger, entonces la asignación conserva su función, horario y pago, la ocupación/disponibilidad no cambia y **no se crea ningún ingreso ni egreso**; la asistencia es solo un dato de evaluación.
- **CA-18.20**: Dado un historial, cuando se revisan las fechas y horas, entonces la **fecha del evento** y el **horario de la asignación** se presentan también en `America/Lima` (fecha y horas locales) y se incluyen los instantes **UTC**; los importes van en céntimos de `PEN`. El evento se identifica por su **código** `EVT-AAAA-NNNN`, porque no tiene un nombre propio.
- **CA-18.21**: Dado un trabajador con asignaciones **anuladas**, cuando se consulta su historial, entonces esas asignaciones se incluyen con su estado `CANCELLED` y asistencia `null` (no se les puede registrar asistencia); las asignaciones `ACTIVE` sin registro muestran "sin registrar". Así se conserva la trazabilidad sin confundir una asignación anulada con una falta.
- **CA-18.22**: Dado un `event_id` que `commercial.public_api.event_lookup` **no resuelve** (evento huérfano), cuando el administrador registra o corrige la asistencia o consulta el historial, entonces la fila/respuesta se devuelve **igualmente** con `event_code`, `event_date` y `event_status` en **`null`**, sin responder 404 por el evento y sin descartar la fila; **no se inventan** datos del evento. En el historial, esas filas se **excluyen** cuando hay filtro `from`/`to` (por no tener `event_date`) y se **incluyen** cuando no hay filtro de fecha o cuando el filtro es por `event_id`. Existe un **test específico** para este caso.

### 5.1 Escenarios clave

- **Registrar "cumplió"** — Dado un administrador con `staff:attendance` y una asignación activa cuyo `end_at` ya pasó; cuando registra `ATTENDED`; entonces la asignación queda cumplida, con actor y fecha-hora, y sin cambios en horario ni pago.
- **Registrar "no cumplió"** — Dado el mismo contexto; cuando registra `NOT_ATTENDED`; entonces queda como no cumplida y el historial la muestra como falta (no como "sin registrar").
- **Evento no terminado** — Dada una asignación activa cuyo `end_at` está en el futuro; cuando se intenta registrar asistencia; entonces se rechaza con conflicto y no se guarda nada.
- **Asignación anulada** — Dada una asignación anulada, aunque su horario ya haya pasado; cuando se intenta registrar asistencia; entonces se rechaza y no se guarda nada.
- **Corrección auditada** — Dada una asistencia `ATTENDED`; cuando se corrige a `NOT_ATTENDED` con un motivo; entonces prevalece el nuevo valor y se conserva el anterior con quién, cuándo y el motivo.
- **Corrección sin motivo** — Dada una asistencia `ATTENDED`; cuando se intenta corregir a `NOT_ATTENDED` sin motivo; entonces se rechaza con 422 y no cambia nada.
- **Historial con filtros y paginación** — Dado un trabajador con varias asignaciones en distintos eventos y fechas; cuando se consulta con rango de fechas y evento y se pide una página; entonces solo aparecen las filas que cumplen, con el total correcto.
- **Permisos denegados** — Dado un encargado de eventos o un encargado de compras y almacén; cuando intenta registrar asistencia o consultar historial; entonces recibe 403 y no se modifica ni se expone nada.
- **Evento cancelado** — Dada una asignación activa de un evento cancelado ya terminado; cuando se registra asistencia; entonces se permite y el historial muestra el evento como cancelado.
- **Sin registro** — Dada una asignación activa terminada sin asistencia; cuando se consulta el historial; entonces se muestra "sin registrar", distinto de "no cumplió".
- **Evento huérfano** — Dada una asignación cuyo `event_id` no resuelve `commercial.public_api.event_lookup`; cuando se registra la asistencia (PATCH) o se consulta el historial (GET); entonces la fila/respuesta se devuelve con `event_code`, `event_date` y `event_status` en `null`, sin 404 por el evento y sin descartarla; con filtro `from`/`to` se excluye, y sin filtro de fecha o con `event_id` se incluye.

## 6. Reglas de negocio

- **R-ATT-1**: La asistencia se registra **por asignación** de HU17 (un registro por asignación), no por trabajador-evento. Una asignación puede tener una sola asistencia vigente.
- **R-ATT-2**: Los estados de asistencia son **`ATTENDED`** ("cumplió") y **`NOT_ATTENDED`** ("no cumplió"). No existe un tercer estado de asistencia.
- **R-ATT-3**: **No hay estado inicial**: una asignación sin registro aparece como **"sin registrar"** (`null`). "Sin registrar" **no** equivale a "no cumplió".
- **R-ATT-4**: Solo se registra asistencia sobre asignaciones **`ACTIVE`** (no anuladas). Una asignación `CANCELLED` no admite registro.
- **R-ATT-5**: Solo se registra asistencia cuando la asignación **ya terminó**: el instante actual debe ser **igual o posterior** a su `end_at` (UTC). Antes de ese momento se rechaza. El criterio decisivo es el `end_at` de la asignación, no el estado del evento.
- **R-ATT-6**: La asistencia registrada **se puede corregir en cualquier momento** posterior. Toda corrección conserva **quién**, **cuándo**, **el motivo**, **el valor anterior** y **el valor nuevo**; el valor nuevo prevalece. La corrección **exige motivo** (R-ATT-22).
- **R-ATT-7**: El historial de cambios de asistencia es **de solo inserción**: no se edita ni se elimina. No puede existir un cambio de asistencia sin su registro de trazabilidad (actor, fecha-hora, valor anterior, valor nuevo y, en la corrección, motivo); si la trazabilidad no se puede guardar, el cambio no se aplica.
- **R-ATT-8**: Un **evento cancelado** no impide registrar la asistencia de sus asignaciones `ACTIVE` una vez que estas terminaron; la asistencia se conserva y el historial muestra el evento como `CANCELLED`. HU18 no define consecuencias adicionales (pagos, devoluciones, sanciones) sobre eventos cancelados.
- **R-ATT-9**: El **historial** es una lista de **una fila por asignación** del trabajador, ordenada de la más reciente a la más antigua. Incluye asignaciones `ACTIVE` y `CANCELLED` (R-ATT-21).
- **R-ATT-10**: El historial exige **trabajador**. Los filtros por **rango de fechas del evento** (`desde`/`hasta`, inclusivos, en `America/Lima`) y por **evento** son opcionales y combinables. Un rango inválido se rechaza.
- **R-ATT-11**: Cada fila del historial muestra: fecha del evento, código y estado del evento, función (y descripción si es "otro"), horario de la asignación (local y UTC), pago acordado en céntimos de `PEN` y estado de asistencia (o "sin registrar").
- **R-ATT-12**: El evento se identifica por su **código** `EVT-AAAA-NNNN`; no tiene un nombre propio. Los datos del evento se obtienen por `commercial.public_api`, **sin clave foránea** entre módulos.
- **R-ATT-13**: Las fechas y horas se interpretan y presentan en `America/Lima`, y se almacenan/comparan en **UTC**. El dinero son **enteros en céntimos de `PEN`**.
- **R-ATT-14**: **Autorización**: registrar o corregir asistencia exige `staff:attendance` (**solo administrador**); consultar el historial (con pago) exige `staff:manage` (**solo administrador**). El encargado de eventos y el de compras y almacén reciben 403 en ambas rutas; el encargado de eventos conserva únicamente `staff_roster:read` (sin pago).
- **R-ATT-15**: La asistencia **no modifica** la asignación de HU17 (función, horario, pago ni estado), **no altera** la disponibilidad/ocupación de HU16 y **no genera** movimientos en el ledger. El pago acordado sigue siendo un acuerdo, no un egreso.
- **R-ATT-16**: Un trabajador **inactivo** conserva su historial de asistencia y este sigue siendo consultable por el administrador; la baja lógica no borra ni oculta el historial.
- **R-ATT-17**: Volver a registrar el **mismo estado** es **idempotente**: no crea un nuevo cambio ni otra entrada de trazabilidad, y **no exige motivo** (no hay corrección).
- **R-ATT-18**: El historial no expone datos de otros trabajadores ni de otros eventos: la consulta es por un trabajador concreto y solo devuelve sus asignaciones.
- **R-ATT-19**: La asistencia no se puede registrar sobre una asignación inexistente ni sobre un trabajador inexistente (404).
- **R-ATT-20**: El historial no incluye asistencia de personal **no asignado** ni marcaciones de entrada/salida: solo asignaciones de HU17.
- **R-ATT-21**: Las asignaciones **anuladas** se incluyen en el historial con su estado `CANCELLED` y asistencia `null`; no admiten registro y no deben confundirse con una falta.
- **R-ATT-22**: La **corrección** de una asistencia ya registrada (`ATTENDED` ↔ `NOT_ATTENDED`) **exige un motivo**: `reason` se recorta y debe quedar con entre 1 y 500 caracteres tras el recorte. El **primer registro** de una asignación sin asistencia previa (`null` → `ATTENDED`/`NOT_ATTENDED`) **no** exige motivo. Reintentar el mismo valor no exige motivo (R-ATT-17). Una corrección sin motivo se rechaza con `422 staff.attendance_reason_required` y no se guarda nada. Decisión aprobada el 27/11/2026.
- **R-ATT-23**: Si `commercial.public_api.event_lookup` **no resuelve** un `event_id` (evento huérfano), el historial y la respuesta del PATCH devuelven la fila **igualmente**, con `event_code`, `event_date` y `event_status` en **`null`**; **no** se responde 404 por el evento ni se descarta la fila (mismo criterio que el evento huérfano de HU16, T-22) y **no se inventan** datos del evento. Las filas con `event_date` nula **no coinciden** con los filtros `from`/`to` (se excluyen cuando hay filtro de fecha), pero **sí** se incluyen cuando no hay filtro de fecha y cuando el filtro es por `event_id`. El error `staff.event_not_found` **deja de usarse** en esta feature (ni PATCH ni GET). Decisión aprobada el 28/11/2026.

## 7. Contrato observable de la API

> Este apartado fija el contrato con el frontend; no prescribe tablas, clases ni SQL (eso corresponde al plan). Los `operationId` deben ser estables y no introducir cambios incompatibles dentro de `/v1`.

### 7.1 Registrar o corregir la asistencia

- **Método y ruta**: `PATCH /v1/staff/assignments/{assignment_id}/attendance`
- **operationId**: `staff_attendance_update`
- **Permiso**: `staff:attendance` (solo administrador)
- **Cuerpo**:
  ```json
  { "status": "ATTENDED", "reason": "Se registró por error; el trabajador sí asistió" }
  ```
  - `status` (obligatorio): `ATTENDED` | `NOT_ATTENDED`.
  - `reason` (opcional en el esquema): **obligatorio solo cuando es una corrección** (ya existía `ATTENDED` o `NOT_ATTENDED` y cambia al otro valor). En el **primer registro** (`null` → valor) y al reintentar el mismo valor es opcional o se ignora. Se recorta y, si se envía, admite de 1 a 500 caracteres. La obligatoriedad se evalúa en el servidor contra el estado vigente (R-ATT-22).
- **Respuesta 200** (`AttendanceOut`): datos de la asignación y su asistencia vigente:
  - `assignment_id`, `worker_id`, `worker_name`
  - `event_id`
  - `event_code`, `event_status` (`SCHEDULED` | `CONFIRMED` | `IN_PROGRESS` | `FINISHED` | `CANCELLED`): **anulables**; `null` si `commercial.public_api.event_lookup` no resuelve el evento (R-ATT-23, evento huérfano). No se responde 404 por el evento.
  - `function`, `function_description`
  - `event_date` (fecha del evento en `America/Lima`): **anulable**; `null` si el evento no se resuelve (R-ATT-23).
  - `start_time`, `end_time` (horas locales de la asignación)
  - `start_at`, `end_at` (instantes UTC, ISO 8601)
  - `pay_cents` (entero), `currency` (`PEN`)
  - `assignment_status` (`ACTIVE` | `CANCELLED`)
  - `attendance_status` (`ATTENDED` | `NOT_ATTENDED`)
  - `attendance_recorded_at` (UTC), `attendance_recorded_by` (usuario)
- **Errores**:
  - `401` sin sesión.
  - `403` rol sin `staff:attendance` (incluye encargado de eventos y compras).
  - `404` `staff.assignment_not_found` si la asignación no existe.
  - `409` `staff.attendance_not_due` si la asignación aún no termina.
  - `409` `staff.attendance_assignment_cancelled` si la asignación está anulada.
  - `422` `staff.attendance_status_invalid` si el estado falta o no es válido.
  - `422` `staff.attendance_reason_required` si es una **corrección** (cambio de `ATTENDED` a `NOT_ATTENDED` o al revés) y el motivo falta, está vacío o solo tiene espacios; tampoco se acepta un motivo de más de 500 caracteres. En ambos casos no se modifica la asistencia ni se crea registro de auditoría.
  - **No hay error `staff.event_not_found`**: un evento no resoluble se devuelve con los campos de evento en `null` (R-ATT-23).

### 7.2 Consultar el historial de un trabajador

- **Método y ruta**: `GET /v1/staff/workers/{worker_id}/attendance`
- **operationId**: `staff_attendance_history`
- **Permiso**: `staff:manage` (solo administrador)
- **Parámetros de consulta**:
  - `from` (fecha, opcional): fecha mínima del evento, inclusiva, en `America/Lima`.
  - `to` (fecha, opcional): fecha máxima del evento, inclusiva, en `America/Lima`.
  - `event_id` (UUID, opcional): solo asignaciones de ese evento.
  - `page` (entero ≥ 1, por defecto 1) y `page_size` (entero 1..100, por defecto 20): paginación estándar del proyecto.
- **Respuesta 200** (`AttendanceHistoryPage`): `{ "items": [...], "total": n, "page": p, "page_size": s }`. Cada ítem contiene los mismos campos de `AttendanceOut`, con `attendance_status`, `attendance_recorded_at` y `attendance_recorded_by` **anulables** (`null` = "sin registrar"). Si `commercial.public_api.event_lookup` no resuelve un evento, el ítem se devuelve igualmente con `event_code`, `event_date` y `event_status` en `null`, sin descartarlo ni responder 404 (R-ATT-23).
- **Orden**: de la asignación más reciente a la más antigua.
- **Filtros y evento huérfano**: las filas con `event_date` nula se excluyen cuando se aplica `from`/`to`, y se incluyen cuando no hay filtro de fecha o cuando el filtro es por `event_id` (R-ATT-23).
- **Errores**:
  - `401` sin sesión.
  - `403` rol sin `staff:manage` (incluye encargado de eventos y compras).
  - `404` `staff.worker_not_found` si el trabajador no existe.
  - `422` `staff.attendance_date_range_invalid` si `from` es posterior a `to`, o si la paginación está fuera de rango.
  - **No hay error `staff.event_not_found`**: un evento no resoluble se devuelve con los campos de evento en `null` (R-ATT-23).

## 8. Fuera de alcance

- **Frontend** (otro repositorio).
- **Nómina, planilla, liquidaciones y pagos reales** al personal (`ledger`). El pago acordado es informativo y no cambia con la asistencia.
- **Horas trabajadas, marcaciones de entrada/salida, justificaciones, adjuntos o evidencias** de la asistencia.
- **Asistencia de personal no asignado** a un evento.
- **Modificar asignaciones (HU17) o disponibilidad (HU16)**: no se tocan sus reglas, su `public_api` ni su comportamiento.
- **Evaluaciones de desempeño, puntuaciones, sanciones o descuentos** derivados de la asistencia.
- **Política de negocio sobre eventos cancelados** más allá de permitir registrar/consultar su asistencia: no se definen devoluciones, compensaciones ni sanciones.
- **Notificaciones** al trabajador (no es usuario) ni al encargado.
- **Reportes agregados de asistencia** por evento o por periodo; esta feature solo expone el historial por trabajador.
- **Multi-tenant**: una sola organización.

## 9. Requisitos no funcionales

- **Autorización en el servidor**: se aplica por permiso en cada ruta; ninguna respuesta entrega pago, documento, teléfono o tarifa a roles sin `staff:manage`. El encargado de eventos y compras nunca acceden.
- **Trazabilidad**: toda alta y corrección de asistencia guarda actor, fecha-hora (UTC), valor anterior y valor nuevo; en la **corrección**, además, el **motivo** obligatorio. El registro es inmutable y no puede existir un cambio sin trazabilidad.
- **Consistencia temporal**: la comparación con `end_at` se hace con el reloj del servidor en UTC; no se acepta una zona horaria del cliente para decidir si el evento terminó.
- **Rendimiento**: el historial debe responder con fluidez para decenas a pocos cientos de asignaciones por trabajador y filtros de rango; la paginación evita consultas masivas.
- **Errores en español y accionables**: "la asignación todavía no termina", "la asignación está anulada", "trabajador no encontrado" y "rango de fechas inválido" se explican sin exponer datos de más.
- **Dinero y fechas**: céntimos enteros de `PEN`; UTC en almacenamiento y comparación, `America/Lima` en la presentación.
- **Contrato OpenAPI**: `operationId` estables y sin cambios incompatibles dentro de `/v1`; `openapi.json` regenerado.
- **Sin dependencias ni servicios nuevos**; el permiso `staff:attendance` se declara en el registro de permisos de `identity` sin migración de datos (precedente de HU16/HU17).
- **Integridad de la consulta**: si `commercial` no resuelve un evento (evento huérfano), **no se inventan datos**: la fila se devuelve con `event_code`, `event_date` y `event_status` en `null`, sin 404 y sin descartarla (R-ATT-23). Las filas con `event_date` nula quedan fuera de los filtros `from`/`to` y dentro de la consulta sin filtro de fecha o filtrada por `event_id`. Existe un test específico de este caso.

## 10. Dependencias e impacto

### 10.1 Dependencias funcionales

- **HU17 (033-staff-assignments) implementada**: existe la asignación con `event_id`, `worker_id`, `function`, `function_description`, `start_at`, `end_at`, `pay_cents` y estado `ACTIVE`/`CANCELLED`. HU18 la **reutiliza por su `public_api`**, sin modificarla.
- **HU16 (034-staff-availability) implementada**: la disponibilidad es planificación, no asistencia (R-DIS-6). HU18 no la usa ni la altera.
- **`commercial.public_api.event_lookup`**: proporciona `id`, `code`, `status`, `event_date`, `start_time` y `end_time` para el historial, sin FK entre módulos. No se modifica.
- **`identity`**: declara el permiso `staff:attendance`; el administrador lo recibe automáticamente. `staff:manage` ya existe y sigue siendo solo del administrador.
- **025 (permisos de ventas)**: el encargado de eventos ya no tiene `staff:manage`; conserva `staff_roster:read` (sin pago). HU18 no cambia esa matriz.

### 10.2 Impacto en API

- Dos rutas nuevas: `PATCH /v1/staff/assignments/{assignment_id}/attendance` y `GET /v1/staff/workers/{worker_id}/attendance`, con los `operationId` indicados en §7.
- No se modifica ninguna ruta existente de HU15, HU16, HU17, HU14 ni de `reporting`.
- Se regenera `openapi.json`.

### 10.3 Impacto en datos y migración

- Se requiere **persistir el estado actual de asistencia por asignación** y un **historial de cambios de solo inserción** con actor, fecha-hora, valor anterior, valor nuevo y, en la corrección, **motivo**.
- El historial de cambios guarda el **motivo** (`reason`) y lleva una **restricción `CHECK`** que garantiza que un **cambio de valor** (valor anterior no nulo y distinto del nuevo) tenga `reason` no vacío: la base de datos **no acepta una corrección sin motivo**, aunque falle la validación de la aplicación. La restricción no aplica al primer registro (valor anterior nulo) ni al mismo valor (que no genera fila).
- Se testea en ambos niveles: corrección **sin motivo** → `422 staff.attendance_reason_required` y **ningún cambio**; corrección **con motivo** → la auditoría guarda ese motivo; e inserción directa en la tabla de auditoría de un cambio de valor sin motivo → **rechazada por la base de datos**.
- **Nueva migración Alembic**. Según la indicación del humano, cuelga de **`b959d55b8430`** (head actual indicado). Antes de crearla se debe verificar con `uv run alembic heads` que hay **un solo head** y que coincide; si no, se para y se avisa (regla de `AGENTS.md` y `docs/sdd/COORDINACION.md`). No se editan migraciones ya aplicadas.
- No se agregan claves foráneas entre módulos: el evento se referencia por ID y se resuelve por `commercial.public_api`. Si la resolución falla (evento huérfano), la asistencia y el historial **se conservan**: la fila se devuelve con los campos de evento en `null`, sin 404 y sin descartar datos (R-ATT-23); el criterio queda cubierto por un test específico.
- No se modifica el esquema ni el `public_api` de HU16/HU17.

### 10.4 Riesgos

- **Evento reprogramado (R-ASG-11)**: la asignación conserva su horario y el evento puede cambiar de fecha/hora. El historial muestra la **fecha del evento** (de `commercial`) y el **horario de la asignación**; si difieren, el usuario debe poder distinguirlo. Mitigación: exponer ambos datos de forma explícita y no recalcular ni mover nada.
- **Evento cancelado**: permitir registrar asistencia es el **supuesto vigente**, pero queda como pregunta al cliente (§12): si responde que un evento cancelado a última hora no debe evaluarse, se ajusta la regla sin tocar el núcleo.
- **Asignaciones anuladas en el historial**: incluirlas con estado `CANCELLED` y asistencia `null` evita perder trazabilidad, pero puede confundir si el frontend no muestra el estado. Mitigación: el estado de la asignación viaja en cada fila.
- **Correcciones concurrentes**: dos administradores podrían corregir a la vez; el valor que prevalece es el último guardado y ambas correcciones quedan auditadas. El plan decidirá si hace falta control de concurrencia optimista.
- **Privacidad del pago**: un error de autorización expondría el pago acordado; la única puerta es `staff:manage` (solo administrador). Se debe probar 403 para encargado de eventos y compras.
- **Reloj y zona horaria**: una comparación incorrecta con `end_at` permitiría registrar antes de tiempo o rechazar un evento ya terminado; se prueba con horas locales y UTC.
- **Conflicto de migraciones**: dos heads rompen el despliegue; se aplica la regla de verificación previa.
- **Evento huérfano**: si `commercial.public_api.event_lookup` no resuelve un `event_id`, la fila del historial y la respuesta del PATCH se devuelven con `event_code`, `event_date` y `event_status` en `null`, sin 404 y sin descartarla (R-ATT-23, mismo criterio que HU16 T-22). Mitigación: no inventar datos del evento, mostrar los campos como no disponibles en el frontend, y cubrirlo con un test específico; las filas con `event_date` nula quedan fuera de los filtros por rango de fechas.

## 11. Supuestos

- **Estados**: solo `ATTENDED` y `NOT_ATTENDED`; no hay estado inicial y una asignación sin registro se muestra como "sin registrar" (`null`). No se registran hora de entrada/salida ni marcaciones.
- **Granularidad**: un registro por **asignación**, no por trabajador-evento; si un trabajador tiene dos asignaciones al mismo evento, cada una tiene su propia asistencia.
- **Ventana**: se registra solo sobre asignaciones `ACTIVE` y cuando el instante actual es igual o posterior al `end_at` (UTC). Las correcciones posteriores siempre se permiten. El estado del evento no es el criterio decisivo.
- **Evento cancelado**: sus asignaciones `ACTIVE` siguen admitiendo registro y consulta una vez terminadas; no se define ninguna consecuencia adicional. Queda como **pregunta al cliente** (§12) si un evento cancelado a última hora debe evaluarse; el supuesto vigente es permitirlo.
- **Historial**: incluye asignaciones `ACTIVE` y `CANCELLED`; las anuladas se identifican por su estado y no admiten asistencia. El orden es del más reciente al más antiguo.
- **Filtros**: rango de fechas del **evento**, inclusivo, en `America/Lima`, y filtro por evento; ambos opcionales y combinables. El historial siempre exige un trabajador.
- **Evento huérfano**: si `commercial.public_api.event_lookup` no resuelve un `event_id`, la fila se devuelve igualmente con `event_code`, `event_date` y `event_status` en `null`, sin 404 y sin descartarla; no se inventan datos. Con filtro `from`/`to` esas filas se excluyen (no tienen `event_date`); sin filtro de fecha o con `event_id` se incluyen (R-ATT-23). **Aprobado el 28/11/2026**.
- **Paginación**: se usa la paginación estándar del proyecto (`page`/`page_size`, por defecto 20, máximo 100) con `total`, coherente con el listado de personal de HU15.
- **Evento sin nombre**: se identifica por su código `EVT-AAAA-NNNN`; el issue menciona "código/nombre", pero el evento no tiene un campo nombre propio.
- **Corrección**: exige **motivo** (`reason`) no vacío, de 1 a 500 caracteres tras recortar; el primer registro no lo exige y reintentar el mismo estado tampoco (R-ATT-22). La trazabilidad guarda actor, fecha-hora, valor anterior, valor nuevo y motivo. **Decisión aprobada el 27/11/2026**; el límite de 500 caracteres es un supuesto de baja criticidad.
- **Idempotencia**: registrar el mismo estado no genera un nuevo cambio de historial.
- **Trabajador inactivo**: conserva y permite consultar su historial; la baja es lógica.
- **Sin efecto contable**: la asistencia no crea ingresos ni egresos y no altera la asignación, la disponibilidad ni el ledger.
- **Una sola organización**; sin multi-tenant.

## 12. Preguntas abiertas

No hay preguntas **bloqueantes**: las decisiones del humano cubren permisos, granularidad, ventana temporal, corrección auditada (con motivo obligatorio, aprobado el 27/11/2026), filtros y alcance. Queda una confirmación de **baja criticidad**, ya resuelta como supuesto en §11, y una pregunta **pendiente para el cliente, no bloqueante para implementar**:

- [ ] ¿El historial debe incluir las asignaciones **anuladas** (con estado `CANCELLED` y asistencia `null`) o solo las `ACTIVE`? *Supuesto actual*: incluirlas para conservar la trazabilidad; se identifican por su estado.
- [ ] **Pendiente para el cliente (no bloqueante):** ¿Debe registrarse/evaluarse la asistencia de un **evento cancelado a última hora**? *Supuesto vigente*: se permite registrar y consultar la asistencia de asignaciones `ACTIVE` ya terminadas de un evento cancelado (R-ATT-8, CA-18.17); si el cliente responde otra cosa, se ajusta la regla.

La decisión sobre el **motivo obligatorio en la corrección** quedó **resuelta el 27/11/2026** (R-ATT-22), por lo que no figura como pregunta abierta. Ninguna de las confirmaciones pendientes cambia el flujo principal.
