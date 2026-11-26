# Plan: Asignación de trabajadores a eventos

- **Spec**: ./spec.md
- **Estado**: aprobado (PO, 25/11/2026); Q1–Q8 y la función elegible aprobadas
- **HU**: HU17 (#18)
- **Decisiones del PO**: 25/11/2026, Q1–Q8 aprobadas

## 0. Resumen

- Las asignaciones viven en **`staff`**. `identity` solo gana el permiso `staff:assign` (solo administrador); la lectura usa `staff:manage` (administrador y encargado de eventos). Compras no accede.
- El evento se referencia por `event_id` UUID **sin FK** a `commercial`; código, estado, fecha y horario se leen por `commercial.public_api.event_lookup` (`EventInfo`), nunca por tablas.
- El no-solape se garantiza con **restricción de exclusión PostgreSQL** sobre `(worker_id, tstzrange(start_at, end_at, '[)'))`, con `btree_gist` y predicado parcial `WHERE occupies`.
- Se agregan edición y anulación lógica; **nunca borrado físico**. Trabajador y evento son inmutables. Toda operación deja auditoría append-only con actor, fecha-hora, motivo y, en edición, valores anteriores/nuevos.
- Una sola migración Alembic; el uso de `btree_gist` se decide en un ADR (regla 11) antes de crearla.
- `staff.public_api` expone una consulta de solo lectura por evento para HU14 (nombre, función, descripción y horario; **sin pago**).

## 1. Módulos y fronteras

### 1.1 `staff` (se amplía)

Estructura prevista (lo nuevo o modificado):

```
staff/
├─ domain/
│  ├─ assignment.py              # agregado Assignment
│  ├─ assignment_schedule.py     # VO de fecha/horas Lima → UTC
│  ├─ assignment_audit.py        # VO de auditoría + snapshot
│  └─ enums.py                   # + AssignmentStatus
├─ application/
│  ├─ errors.py                  # + errores de asignación
│  ├─ assignment_occupancy.py    # servicio interno de ocupación
│  ├─ ports/assignment_repository.py
│  └─ use_cases/
│     register_assignment.py · update_assignment.py · cancel_assignment.py
│     list_event_assignments.py · get_assignment.py · list_event_assignments_for_sheet.py
│     change_worker_status.py    # modifica DeactivateWorker
├─ infrastructure/
│  ├─ orm_models.py              # + staff_assignments, staff_assignment_audit
│  ├─ mappers.py                 # + mapeo Assignment ⇄ fila y snapshot JSONB
│  └─ assignment_repository.py
├─ presentation/
│  ├─ assignment_router.py
│  ├─ assignment_schemas.py
│  ├─ errors.py                  # + 409 de asignación
│  └─ dependencies.py            # + staff:assign y AssignmentRepository
├─ composition.py
└─ public_api.py                 # + EventAssignmentLookup / event_assignments (HU14)
```

- `worker_id` es FK dentro de `staff` (`staff_workers`, `ON DELETE RESTRICT`).
- `event_id` es un UUID sin FK; **cero** imports a capas internas o tablas de `commercial`.
- `staff` usa de `commercial.public_api`: `event_lookup`, `EventInfo` y `EventStatus` (solo lectura).
- `staff` usa de `identity.public_api`: `CurrentUser`, `Permission`, `require_permission`.
- No se crea ningún endpoint `DELETE`: la anulación es un cambio de estado (`CANCELLED`).

### 1.2 `identity` (solo permiso)

- Agregar `Permission.STAFF_ASSIGN = "staff:assign"` en `identity/domain/permissions.py`.
- `Role.ADMIN` lo recibe automáticamente por `frozenset(Permission)`.
- `Role.EVENTS_MANAGER` **no** lo recibe (conserva `staff:manage` para lectura).
- `Role.PURCHASING_MANAGER` no recibe ninguno de los dos.
- No hay migración: los permisos viven en código. Actualizar el test del conjunto de permisos.

### 1.3 `commercial` (sin cambios de código)

- Ya expone `event_lookup(session)` y `EventInfo(id, code, status, event_date, start_time, end_time)`.
- HU17 no modifica eventos, contratos ni cotizaciones. Tampoco reacciona automáticamente a cambios del evento (R-EVT-9).
- No se agregan FK ni JOINs entre módulos.

### 1.4 `staff.public_api` (nuevo para HU14)

```python
@dataclass(frozen=True)
class EventAssignment:
    worker_id: UUID
    worker_name: str
    function: WorkerFunction
    function_description: str | None
    starts_at: datetime  # UTC, aware
    ends_at: datetime  # UTC, aware


class EventAssignmentLookup(Protocol):
    async def __call__(self, event_id: UUID) -> list[EventAssignment]: ...


def event_assignments(session: AsyncSession) -> EventAssignmentLookup: ...
```

- Solo asignaciones con `status = 'ACTIVE'`; si no hay, lista vacía.
- **No** expone pago, documento, teléfono ni tarifa.
- `reporting` (HU14, implementada en el PR #64) la consumirá sustituyendo su adaptador nulo `NoEventStaff`; el nombre y los campos se acuerdan en `docs/sdd/COORDINACION.md` §4: `event_assignments(session)(event_id)` devuelve nombre, función, inicio y fin en UTC. En esta feature no se modifica `reporting`, solo se deja el `public_api` listo.

## 2. Modelo de dominio

### 2.1 Agregado `Assignment`

Campos: `id`, `event_id`, `worker_id`, `function`, `function_description`, `start_at`, `end_at`, `pay`, `status`, `occupies`.

- `Assignment.register(...)`: valida todo antes de construir; nace `ACTIVE` y `occupies=True`.
- `update(function, description, start_at, end_at, pay) -> bool`: reemplaza los campos editables y devuelve si hubo cambio real.
- `cancel() -> bool`: pasa a `CANCELLED` y `occupies=False`.
- `release() -> bool`: solo para eventos cancelados; `occupies=False` sin cambiar el estado.
- No existe `delete()`. `worker_id` y `event_id` no tienen setter: son inmutables.
- Estados: `ACTIVE` y `CANCELLED`. No hay reactivación de una asignación anulada (se crea otra).

Invariantes:

1. `event_id` y `worker_id` son UUID; obligatorios.
2. `function` siempre está presente (se copia o se elige al crear; ver §10).
3. Si `function = OTHER`, `function_description` es obligatoria y no vacía; en las demás, debe ser `None` (reusa las reglas de `WorkerFunction`).
4. `start_at` y `end_at` son `datetime` con zona, en UTC; `end_at > start_at`.
5. `pay` es `Money` en céntimos `PEN`, entero y `>= 0` (R-ASG-7).
6. `status = CANCELLED` implica `occupies = False`.
7. No hay borrado físico ni reactivación.

### 2.2 Value object `AssignmentSchedule`

Representa la entrada local del administrador y su traducción a UTC.

- Entrada: `date` (fecha de la asignación) + `start_time` + `end_time`.
- Se interpreta en `America/Lima` con offset fijo `-05:00`, como el resto del proyecto (Perú no aplica DST).
- Si `end_time == start_time`: inválido (`staff.assignment_schedule_invalid`), duración cero.
- Si `end_time < start_time`: termina al **día siguiente** (R-COT-1); por ejemplo, `22:00 → 02:00`.
- Si `end_time > start_time`: termina el mismo día.
- `start_at`/`end_at` se guardan en UTC; la presentación vuelve a `America/Lima`.
- **Regla de fecha (Q5, supuesto §10.2)**: la fecha de la asignación debe ser la fecha del evento o, si el evento cruza la medianoche (`end_time < start_time`), también la fecha siguiente. No se limita el horario al del evento (Q5 permite montaje/desmontaje).
- La comparación con la fecha del evento es una regla del caso de uso, no del VO (el VO no conoce eventos).

### 2.3 Auditoría `AssignmentAudit` y snapshot

Tabla lógica append-only con una fila por `CREATED`, `UPDATED` o `CANCELLED`.

- `AssignmentSnapshot`: función, descripción, `start_at`, `end_at`, `pay_cents`, `currency`.
- `CREATED`: `reason = None`, sin snapshot anterior/nuevo.
- `UPDATED`: `reason` obligatorio y no vacío; `previous_values` y `new_values` obligatorios (JSONB).
- `CANCELLED`: `reason` obligatorio y no vacío; sin snapshots.
- `actor_id` (usuario de `identity`, sin FK) y `occurred_at` (UTC, aware) siempre.
- Se escribe en la **misma transacción** que la asignación; si falla, no queda el cambio.
- El agregado expone `snapshot()` para que el caso de uso arme la auditoría sin duplicar la serialización.

### 2.4 Ocupación y eventos cancelados

El no-solape debe ignorar las asignaciones de eventos cancelados (R-ASG-12/CA-17.20), pero la base no conoce el estado del evento (sin FK ni JOIN entre módulos). Decisión del plan:

- `staff_assignments.occupies` es `true` mientras la asignación ocupa al trabajador.
- La restricción de exclusión es **parcial**: `WHERE (occupies)`.
- Al anular una asignación, `occupies = false` de inmediato.
- Al cancelarse un evento, `staff` **libera perezosamente** sus asignaciones antes de la siguiente escritura del trabajador:
  1. `AssignmentOccupancy.release_cancelled(worker_id)` lee las asignaciones activas que ocupan.
  2. Consulta `commercial.public_api.event_lookup` para cada `event_id`.
  3. Si el evento está `CANCELLED`, marca `occupies = false` (no cambia el estado de la asignación ni escribe auditoría: es un dato derivado).
- La lista del evento sigue devolviendo esas asignaciones (estado `ACTIVE`) con `event_status = CANCELLED`; así se conserva el historial y se indica el evento cancelado.
- Es una decisión de implementación, no una regla nueva: el resultado observable es el del spec (dejan de ocupar, no se borran). Se registra como riesgo en §8.

## 3. Casos de uso

| Caso de uso | Tipo | Entrada | Salida | Errores de negocio |
|---|---|---|---|---|
| `RegisterAssignment` | command | `event_id`, `worker_id`, `function?`, `function_description?`, `date`, `start_time`, `end_time`, `pay_cents`, `actor_id` | `Assignment` + datos del evento | 404 evento/trabajador; 409 inactivo/estado/cruce; 422 validación |
| `UpdateAssignment` | command | `assignment_id`, campos editables, `reason`, `actor_id` | `Assignment` | 404; 409 estado/cruce/inmutabilidad; 422 validación |
| `CancelAssignment` | command | `assignment_id`, `reason`, `actor_id` | `Assignment` | 404; 409 estado; 422 motivo |
| `ListEventAssignments` | query | `event_id` | lista de vistas activas ordenadas por `start_at` | 404 evento |
| `GetAssignment` | query | `assignment_id` | vista (incluye anuladas) | 404 |
| `ListEventAssignmentsForSheet` | query pública | `event_id` | `list[EventAssignment]` sin pago | — |
| `AssignmentOccupancy` | servicio interno | `worker_id` | libera cancelados / detecta futuros | — |
| `DeactivateWorker` (modificado) | command | `worker_id`, `reason?`, `actor_id` | `Worker` | 409 `staff.worker_has_future_assignments` |

### 3.1 `RegisterAssignment`

1. `event = event_lookup(event_id)`; si no existe → `staff.event_not_found` (404).
2. Si el estado del evento no es `SCHEDULED`, `CONFIRMED` o `IN_PROGRESS` → `staff.event_not_assignable` (409; el detalle indica el estado).
3. `worker = worker_lookup.get(worker_id)`; si no existe → `staff.not_found` (404); si `status != ACTIVE` → `staff.worker_inactive` (409).
4. Construir `AssignmentSchedule`; validar fecha contra el evento (§2.2).
5. Función: si el cuerpo la trae, se usa (puede ser distinta a la de la ficha); si se omite, se copia la de la ficha; si ninguna existe → `staff.assignment_function_required` (422). La ficha **no** se modifica. Decisión del PO del 25/11/2026.
6. Pago: `Money(pay_cents)`; validación de céntimos enteros y `>= 0`.
7. Bloquear la fila del trabajador (`lock_worker`) para serializar altas/ediciones/bajas del mismo trabajador.
8. `AssignmentOccupancy.release_cancelled(worker_id)`.
9. Buscar solapes activos (`list_active_overlaps`). Si hay, obtener código, fecha y horario de cada evento con `event_lookup` y lanzar `staff.assignment_overlap` (409) con la lista de conflictos. No se expone documento, teléfono ni tarifa.
10. Crear el agregado y la auditoría `CREATED`; `save` en la misma transacción.
11. Si la base rechaza por la restricción de exclusión (carrera), traducir a `staff.assignment_overlap` sin detalle de eventos (ver §5.4).

### 3.2 `UpdateAssignment`

1. Leer la asignación sin bloqueo para conocer `worker_id`.
2. Bloquear la fila del trabajador y luego la asignación (`FOR UPDATE`); orden fijo para evitar deadlocks.
3. Releer y validar que sigue existiendo.
4. `event = event_lookup(assignment.event_id)`; si `FINISHED` o `CANCELLED` → 409 `staff.event_not_assignable` (solo lectura).
5. Validar los nuevos datos como en el alta. Si el trabajador está `INACTIVE` y el nuevo `end_at` es futuro, rechazar con `staff.worker_inactive`; las correcciones de asignaciones ya pasadas se permiten (supuesto §10.9).
6. `release_cancelled(worker_id)` y comprobar solapes **excluyendo la propia asignación**.
7. Si no hay cambios reales, devolver la asignación sin escribir auditoría (supuesto §10.4).
8. Aplicar cambios y escribir `UPDATED` con `reason`, `previous_values` y `new_values`.

### 3.3 `CancelAssignment`

1. Bloquear trabajador y asignación (mismo orden).
2. `event_lookup`; si `FINISHED` o `CANCELLED` → 409 (solo lectura).
3. `reason` obligatorio y no vacío.
4. `assignment.cancel()` y auditoría `CANCELLED` con motivo; `save` en la misma transacción.
5. Si ya estaba anulada, devolver 200 sin nueva auditoría (idempotente).

### 3.4 `ListEventAssignments` / `GetAssignment`

- `ListEventAssignments`: `event_lookup` (404 si no existe), luego asignaciones `status = ACTIVE` ordenadas por `start_at`; cada ítem incluye `event_code`, `event_status`, nombre del trabajador, función/descripción, fecha/horas locales, instantes UTC y pago. Sin paginación (volumen bajo, supuesto §10.8).
- `GetAssignment`: devuelve la asignación por id, incluso anulada, para consulta/detalle. La lista vigente no incluye anuladas (CA-17.16).
- `ListEventAssignmentsForSheet`: solo `status = ACTIVE`; no incluye pago.

### 3.5 `DeactivateWorker` (modificación de HU15)

- Se inyecta `AssignmentOccupancy`.
- Tras bloquear la ficha y antes de cambiar el estado: `release_cancelled(worker_id)` y, si existe alguna asignación `ACTIVE` con `occupies = true` y `end_at > now`, lanzar `staff.worker_has_future_assignments` (409). Las pasadas o anuladas no bloquean (CA-17.25).
- Si no hay bloqueo, el cambio de estado y su auditoría siguen como en HU15.
- La comprobación y el alta de asignación bloquean la misma fila de `staff_workers`, por lo que no hay carrera entre ambas.

## 4. API (OpenAPI)

### 4.1 Endpoints

| Método y ruta | `operationId` | Permiso | Éxito |
|---|---|---|---|
| `POST /v1/staff/assignments` | `staff_assignment_register` | `staff:assign` | 201 |
| `GET /v1/staff/assignments?event_id={uuid}` | `staff_assignment_list` | `staff:manage` | 200 |
| `GET /v1/staff/assignments/{assignment_id}` | `staff_assignment_get` | `staff:manage` | 200 |
| `PUT /v1/staff/assignments/{assignment_id}` | `staff_assignment_update` | `staff:assign` | 200 |
| `POST /v1/staff/assignments/{assignment_id}/cancel` | `staff_assignment_cancel` | `staff:assign` | 200 |

- No existe `DELETE`; un intento responde 405.
- `PUT` es reemplazo completo de los campos editables (función, descripción, fecha, horas, pago) y exige `reason`.
- La lectura incluye el pago acordado (decisión del PO, 25/11/2026); solo para `staff:manage`.

### 4.2 Esquemas

**`AssignmentCreate`**
- `event_id: UUID`, `worker_id: UUID`
- `function: WorkerFunction | None` (si se omite, se copia de la ficha)
- `function_description: str | None` (máx. 120; solo con `OTHER`)
- `date: date`, `start_time: time`, `end_time: time` (hora local `America/Lima`)
- `pay_cents: int` estricto, `>= 0` (S/ 45.00 = 4500)

**`AssignmentUpdate`**
- `function`, `function_description`, `date`, `start_time`, `end_time`, `pay_cents`
- `reason: str` obligatorio y no vacío (máx. 500 técnico, supuesto §10.7)
- `worker_id` y `event_id` **no** forman parte del cuerpo; si se envían, se rechazan con `staff.assignment_immutable` (409).

**`AssignmentOut`**
- `id`, `event_id`, `event_code`, `event_status`, `worker_id`, `worker_name`
- `function`, `function_description`
- `date`, `start_time`, `end_time` (Lima) y `start_at`, `end_at` (UTC)
- `pay_cents`, `currency: "PEN"`, `status` (`ACTIVE`/`CANCELLED`)

**`AssignmentListOut`**: `{ "items": [AssignmentOut, ...] }`.

**`AssignmentCancel`**: `{ "reason": "..." }` obligatorio.

### 4.3 Permisos por rol

| Acción | Permiso | ADMIN | EVENTS_MANAGER | PURCHASING_MANAGER |
|---|---|:-:|:-:|:-:|
| Crear, editar, anular | `staff:assign` | ✔ | – | – |
| Listar y ver detalle | `staff:manage` | ✔ | ✔ | – |
| Consulta pública para HU14 | la aplica `reporting`; `staff.public_api` no autoriza | ✔ | ✔ | – |

- Compras conserva `events:read`, pero no puede llamar a ninguna ruta de asignaciones (403).
- El frontend debe ocultar el bloque «Personal asignado» a compras y los botones de escritura al encargado de eventos.

### 4.4 Errores (Problem Details)

| HTTP | `code` | Cuándo |
|---|---|---|
| 401 | `auth.not_authenticated`, `auth.session_expired` | Sin sesión |
| 403 | `auth.forbidden` | Sin el permiso de la ruta |
| 404 | `staff.not_found` | `worker_id` inexistente |
| 404 | `staff.event_not_found` | `event_id` inexistente |
| 404 | `staff.assignment_not_found` | `assignment_id` inexistente |
| 409 | `staff.worker_inactive` | Trabajador inactivo (CA-17.2) |
| 409 | `staff.event_not_assignable` | Evento `FINISHED`/`CANCELLED` (CA-17.3/17.24) |
| 409 | `staff.assignment_overlap` | Cruce de horario (CA-17.7/17.9/17.10) |
| 409 | `staff.assignment_immutable` | Intento de cambiar trabajador o evento (CA-17.15) |
| 409 | `staff.worker_has_future_assignments` | Baja con asignaciones futuras vigentes (CA-17.25) |
| 422 | `staff.assignment_schedule_invalid` | Fin igual a inicio o ventana inválida |
| 422 | `staff.assignment_date_invalid` | Fecha fuera de la fecha del evento (Q5) |
| 422 | `staff.assignment_function_required` | Sin función en el cuerpo y sin función en la ficha |
| 422 | `staff.function_description_required` / `staff.function_description_not_allowed` | Reglas de `OTHER` |
| 422 | `staff.assignment_pay_invalid` | Pago negativo o no entero |
| 422 | `staff.assignment_reason_required` | Edición/anulación sin motivo |
| 422 | Validación estándar de FastAPI | Formato de fecha/hora, UUID, campos faltantes |

- Los 409 de cruce devuelven, además del `detail`, una extensión `conflicts` con `event_code`, `event_date`, `start_time` y `end_time` (nunca datos del trabajador). Ejemplo:

```json
{
  "type": "about:blank",
  "title": "Conflicto de horario",
  "status": 409,
  "code": "staff.assignment_overlap",
  "detail": "El trabajador ya tiene asignaciones que se superponen: EVT-2026-0012 del 01/12/2026 de 18:00 a 23:00.",
  "conflicts": [
    {"event_code": "EVT-2026-0012", "event_date": "2026-12-01", "start_time": "18:00:00", "end_time": "23:00:00"}
  ]
}
```

- Se define un `AssignmentProblem` local a `staff` (extiende `Problem` con `conflicts` opcional) para documentar el 409 en OpenAPI; `shared/presentation/problems.py` no se modifica.
- `openapi.json` se regenera con `just openapi`; el test de contrato debe quedar en verde.

## 5. Persistencia y migración

### 5.1 Tabla `staff_assignments`

| Columna | Tipo | Nulo | Nota |
|---|---|---|---|
| `id` | `uuid` | no | PK |
| `event_id` | `uuid` | no | Referencia a `commercial`, **sin FK** |
| `worker_id` | `uuid` | no | FK `staff_workers.id`, `ON DELETE RESTRICT` |
| `worker_function` | `varchar(15)` | no | Copiada al crear; lista fija + `OTHER` |
| `function_description` | `text` | sí | Obligatoria solo con `OTHER` |
| `start_at` / `end_at` | `timestamptz` | no | UTC; `end_at > start_at` |
| `pay_cents` | `integer` | no | `>= 0` |
| `currency` | `char(3)` | no | `PEN` |
| `status` | `varchar(9)` | no | `ACTIVE`/`CANCELLED` |
| `occupies` | `boolean` | no | `true` por defecto; `false` si anulada o evento cancelado |
| `created_at` / `updated_at` | `timestamptz` | no | Metadatos técnicos, no auditoría |

### 5.2 Tabla `staff_assignment_audit` (append-only)

| Columna | Tipo | Nulo | Nota |
|---|---|---|---|
| `id` | `bigint identity` | no | PK |
| `assignment_id` | `uuid` | no | FK `staff_assignments.id`, `ON DELETE RESTRICT` |
| `action` | `varchar(9)` | no | `CREATED`/`UPDATED`/`CANCELLED` |
| `reason` | `text` | sí | Obligatorio en `UPDATED`/`CANCELLED` |
| `actor_id` | `uuid` | no | Usuario de `identity`, sin FK |
| `occurred_at` | `timestamptz` | no | UTC |
| `previous_values` | `jsonb` | sí | Obligatorio en `UPDATED` |
| `new_values` | `jsonb` | sí | Obligatorio en `UPDATED` |

### 5.3 Constraints, índices y triggers

- `CREATE EXTENSION IF NOT EXISTS btree_gist` (lo crea la migración).
- Restricción de exclusión:

```sql
ALTER TABLE staff_assignments
  ADD CONSTRAINT staff_assignments_no_overlap
  EXCLUDE USING gist (
    worker_id WITH =,
    tstzrange(start_at, end_at, '[)') WITH &&
  ) WHERE (occupies);
```

- CHECK de ventana: `end_at > start_at`.
- CHECK de pago: `pay_cents >= 0` y `currency = 'PEN'`.
- CHECK de función: lista fija + `OTHER`; `function_description` obligatoria/no vacía solo con `OTHER` y nula en las demás.
- CHECK de estado: `status IN ('ACTIVE','CANCELLED')`.
- CHECK de ocupación: `(status = 'CANCELLED' AND NOT occupies) OR (status = 'ACTIVE')` (permite `ACTIVE` con `occupies=false` por evento cancelado).
- CHECK de auditoría: `action` válida; motivo obligatorio en `UPDATED`/`CANCELLED`; `previous_values`/`new_values` obligatorios solo en `UPDATED`.
- Índices: `(event_id, start_at)`, `(worker_id, start_at)`, `(assignment_id, occurred_at)` en auditoría.
- Trigger `staff_assignment_audit_append_only` (`BEFORE UPDATE OR DELETE`): rechaza toda modificación.
- Trigger `staff_assignments_no_delete` (`BEFORE DELETE`): rechaza el borrado físico.
- Trigger `staff_assignments_immutable_keys` (`BEFORE UPDATE`): rechaza cambiar `worker_id` o `event_id`, y reactivar una asignación `CANCELLED`.
- No hay `UNIQUE` por `(event_id, worker_id)`: se permiten varias asignaciones no superpuestas al mismo evento (CA-17.23).

### 5.4 Migración

- **Una sola migración** para las dos tablas, constraints, índices y triggers.
- `down_revision` = **head vigente** de Alembic. Al redactar este plan la cadena termina en `6900ec1af5f8` (migración de unión de HU15 con eventos, pagos e inventario); **no se hardcodea**: antes de crearla hay que ejecutar `uv run alembic heads`, confirmar que hay un único head, avisar al humano y esperar confirmación (regla del repo). No se marca como tarea paralela.
- `downgrade`: elimina triggers, funciones, índices y tablas. **No** elimina `btree_gist` (puede usarlo otro esquema); se documenta.
- Test de integración: `upgrade head` sobre base vacía y `downgrade` de la migración, verificando que no quedan tablas ni triggers.

### 5.5 Concurrencia y auditoría

- Orden de bloqueo: **primero `staff_workers` (`FOR UPDATE`), después `staff_assignments` (`FOR UPDATE`)**. Así se evitan deadlocks entre alta, edición, anulación y baja del trabajador.
- La aplicación consulta solapes para dar un 409 con detalle; la **garantía real** es la restricción de exclusión.
- Si dos transacciones compiten, una inserta y la otra recibe `IntegrityError`/SQLSTATE `23P01`; el repositorio comprueba el nombre `staff_assignments_no_overlap` y lanza `AssignmentOverlapError` (sin detalle de evento si ya no puede consultar dentro de la transacción abortada). La prueba de concurrencia usa **dos transacciones reales**.
- La asignación y su auditoría se escriben en la misma transacción; si la auditoría falla, la asignación no queda.
- La liberación por evento cancelado (`occupies=false`) es un cambio derivado y no genera auditoría.

### 5.6 Decisiones de arquitectura y por qué

- **Las asignaciones viven en `staff`, no en `commercial`**: el trabajador, su función y su estado son datos de `staff`; `commercial` solo aporta el evento por `public_api`. Así se evita una FK entre módulos y un ciclo de dependencias.
- **El no-solape se garantiza en PostgreSQL, no solo en el caso de uso**: una validación en aplicación no resiste dos peticiones simultáneas (CA-17.11). La restricción de exclusión es la fuente de verdad; la consulta previa solo sirve para dar un 409 con detalle.
- **Predicado parcial `WHERE occupies`**: permite que una asignación de evento cancelado se conserve sin bloquear al trabajador, sin que la base tenga que conocer tablas de `commercial`.
- **Liberación perezosa en `staff`**: mantiene la dirección `staff → commercial.public_api` y evita introducir un evento de dominio entre módulos que hoy no existe. Es la solución de menor mantenimiento; si negocio exige tiempo real, se reevalúa con ADR.
- **Auditoría en la misma transacción y append-only**: cumple RN03 y garantiza que no exista un cambio sin trazabilidad; el trigger impide corregir el historial por SQL.
- **Bloqueo `worker → assignment`**: serializa las operaciones del mismo trabajador y evita deadlocks entre altas, ediciones, anulaciones y la baja del trabajador.
- **Lookup público separado del CRUD**: `EventAssignmentLookup` devuelve solo nombre, función y horario; el pago queda fuera de la superficie que consume `reporting` (Q8/CA-17.21).

## 6. Reglas de negocio aplicadas

| Regla | Cómo se cumple |
|---|---|
| R-ASG-1 | Modelo y esquemas exigen evento, trabajador, función, horario y pago; `worker_id`/`event_id` inmutables. |
| R-ASG-2 | `WorkerLookup` valida `ACTIVE` al crear; las asignaciones existentes se conservan aunque el trabajador se desactive. |
| R-ASG-3 | Restricción de exclusión PostgreSQL + prueba de concurrencia. |
| R-ASG-4 | `AssignmentSchedule` interpreta Lima, cruza medianoche y guarda UTC. |
| R-ASG-5 | 409 `staff.assignment_overlap` con código, fecha y horario del evento en `conflicts`/`detail`. |
| R-ASG-6 | Función copiada al crear y almacenada en la asignación; no se actualiza al cambiar la ficha. |
| R-ASG-7 | `Money` en céntimos `PEN`, `>= 0`; no toca el ledger. |
| R-ASG-8 | Edición y anulación lógica; motivo obligatorio; sin borrado físico. |
| R-ASG-9 | Auditoría append-only con actor, fecha-hora y snapshots en `UPDATED`. |
| R-ASG-10 | Solo `SCHEDULED`, `CONFIRMED`, `IN_PROGRESS`; `FINISHED`/`CANCELLED` de solo lectura. |
| R-ASG-11 | No hay lógica que mueva asignaciones al cambiar el evento; solo se consulta su estado/fecha al escribir. |
| R-ASG-12 | Liberación perezosa de asignaciones de eventos cancelados; no se borran. |
| R-ASG-13 | `event_id` sin FK; datos del evento solo por `commercial.public_api`. |
| R-ASG-14 | `staff:assign` solo admin; `staff:manage` admin + eventos; compras sin acceso. |
| R-ASG-15 | Sin unicidad por evento+trabajador; la exclusión solo impide solapes. |
| R-ASG-16 | `DeactivateWorker` rechaza si hay asignaciones activas con `end_at > now` (incluye las de evento cancelado, ya liberadas). |
| R-ASG-17 | Si la ficha no tiene función, el alta exige elegirla y no modifica la ficha. |
| R-ASG-18 | Edición/corrección permitida en `IN_PROGRESS`; `FINISHED` de solo lectura. |

## 7. Estrategia de tests

### 7.1 Unitarios (sin base de datos)

- **Dominio**: `AssignmentSchedule` (mismo día, medianoche, fin igual a inicio, UTC), `Assignment` (función/descripción, pago, inmutabilidad, anulación, `release`, sin `delete`), `AssignmentAudit` (motivo y snapshots por acción).
- **Aplicación con fakes**: alta (evento/trabajador inexistente, inactivo, estados, fecha, función, pago, conflicto con detalle), edición (motivo, solo lectura, no-op, exclusión de sí misma, snapshots), anulación (idempotencia), listas (orden, solo activas, evento cancelado), lookup público (sin pago), baja de trabajador (bloqueo/liberación).
- **API con fakes**: permisos, 404/409/422, `conflicts`, ausencia de `DELETE`, `operationId` estables.

### 7.2 Integración (PostgreSQL real, Alembic)

- Guardar/leer/listar; evento y trabajador reales por `public_api`/fixtures.
- Restricción de exclusión: solape mismo evento y entre eventos; intervalos contiguos aceptados; cruce de medianoche; múltiples asignaciones al mismo evento.
- Anulación libera ocupación; evento cancelado libera perezosamente.
- Concurrencia con dos transacciones reales: exactamente una fila.
- Auditoría: alta/edición/anulación; trigger rechaza `UPDATE`/`DELETE`; trigger de asignaciones rechaza `DELETE` y cambio de claves; si falla la auditoría, no queda la asignación.
- Migración `upgrade`/`downgrade` sobre base vacía; `btree_gist` disponible; `/ready` en verde.

### 7.3 Arquitectura

- `just arch` en verde: `staff` solo usa `commercial.public_api`, nunca sus capas internas; `commercial` no importa `staff`.
- Caso nuevo en `tests/architecture/test_import_rules.py`.
- `just check` completo.

### 7.4 Mapeo CA-17.x → test

Los nombres son orientativos; la suite real debe cubrir cada CA.

| CA | Test(s) |
|---|---|
| CA-17.1 | `unit/staff/test_assignment_use_cases.py::test_ca17_1_alta_valida`; `unit/staff/test_assignment_api.py::test_ca17_1_post`; `integration/staff/test_assignment_repository.py::test_ca17_1_guarda_y_lee` |
| CA-17.2 | `unit/staff/test_assignment_use_cases.py::test_ca17_2_trabajador_inactivo`; `unit/staff/test_assignment_api.py::test_ca17_2_409` |
| CA-17.3 | `unit/staff/test_assignment_use_cases.py::test_ca17_3_evento_finalizado_o_cancelado` |
| CA-17.4 | `unit/staff/test_assignment.py::test_ca17_4_campos_obligatorios`; `unit/staff/test_assignment_api.py::test_ca17_4_422` |
| CA-17.5 | `unit/staff/test_assignment_use_cases.py::test_ca17_5_copia_funcion_y_la_conserva` |
| CA-17.6 | `unit/staff/test_assignment_use_cases.py::test_ca17_6_pago_independiente_de_tarifa` |
| CA-17.7 | `unit/staff/test_assignment_use_cases.py::test_ca17_7_solape_rechazado`; `integration/staff/test_assignment_constraints.py::test_ca17_7_exclusion` |
| CA-17.8 | `integration/staff/test_assignment_constraints.py::test_ca17_8_intervalos_contiguos` |
| CA-17.9 | `integration/staff/test_assignment_constraints.py::test_ca17_9_cruce_medianoche` |
| CA-17.10 | `unit/staff/test_assignment_use_cases.py::test_ca17_10_detalle_de_conflictos`; `unit/staff/test_assignment_api.py::test_ca17_10_conflicts` |
| CA-17.11 | `integration/staff/test_assignment_concurrency.py::test_ca17_11_dos_transacciones` |
| CA-17.12 | `unit/staff/test_assignment_queries.py::test_ca17_12_lista_ordenada`; `unit/staff/test_assignment_api.py::test_ca17_12_get` |
| CA-17.13 | `unit/staff/test_assignment_use_cases.py::test_ca17_13_edicion_auditada`; `integration/staff/test_assignment_repository.py::test_ca17_13_auditoria_update` |
| CA-17.14 | `unit/staff/test_assignment_use_cases.py::test_ca17_14_edicion_con_solape_conserva_valores` |
| CA-17.15 | `unit/staff/test_assignment.py::test_ca17_15_claves_inmutables`; `unit/staff/test_assignment_api.py::test_ca17_15_409` |
| CA-17.16 | `unit/staff/test_assignment_use_cases.py::test_ca17_16_anula_y_sale_de_vigentes`; `integration/staff/test_assignment_repository.py::test_ca17_16_no_borra` |
| CA-17.17 | `unit/staff/test_assignment_api_roles.py::test_ca17_17_matriz_de_permisos` |
| CA-17.18 | `unit/staff/test_assignment_audit.py::test_ca17_18_acciones_y_snapshots`; `integration/staff/test_assignment_audit_append_only.py::test_ca17_18_append_only` |
| CA-17.19 | `unit/staff/test_assignment_use_cases.py::test_ca17_19_no_mueve_asignaciones` (comportamiento: no hay caso de uso que lo haga) |
| CA-17.20 | `unit/staff/test_assignment_use_cases.py::test_ca17_20_evento_cancelado_libera`; `integration/staff/test_assignment_constraints.py::test_ca17_20_no_ocupa` |
| CA-17.21 | `unit/staff/test_assignment_queries.py::test_ca17_21_lookup_sin_pago`; `integration/staff/test_assignment_repository.py::test_ca17_21_lookup` |
| CA-17.22 | `unit/staff/test_assignment.py::test_ca17_22_matriz_validacion`; `unit/staff/test_assignment_api.py::test_ca17_22_422` |
| CA-17.23 | `unit/staff/test_assignment_use_cases.py::test_ca17_23_mismo_evento_sin_solape`; `integration/staff/test_assignment_constraints.py::test_ca17_23` |
| CA-17.24 | `unit/staff/test_assignment_use_cases.py::test_ca17_24_en_ejecucion_permite_y_finalizado_no` |
| CA-17.25 | `unit/staff/test_worker_deactivation.py::test_ca17_25_bloquea_futuras`; `integration/staff/test_assignment_repository.py::test_ca17_25_pasadas_no_bloquean` |
| CA-17.26 | `unit/staff/test_assignment_use_cases.py::test_ca17_26_funcion_obligatoria_si_ficha_sin_funcion` |

## 8. Riesgos y ADRs

- **`btree_gist` (alto)**: es una extensión de PostgreSQL contrib. En la imagen `postgres:17-alpine` está disponible, pero `CREATE EXTENSION` requiere privilegios; en un PostgreSQL gestionado puede necesitar habilitación previa. Se propone **ADR 0005** (regla 11) antes de la migración; si el equipo lo rechaza, no se cumple R-ASG-3 con garantía de base.
- **Liberación de eventos cancelados (medio, decisión aprobada 25/11/2026)**: no hay eventos de dominio entre módulos implementados; se resuelve con reconciliación perezosa al escribir. Si el PO prefiere una comunicación explícita `commercial → staff`, exige un evento en proceso y un ADR adicional. Mientras no se escriba, una asignación de evento cancelado puede seguir ocupando; la siguiente escritura la libera.
- **Cambio de fecha del evento (medio)**: R-ASG-11 deja la asignación con su horario. Si el administrador edita solo el pago, la regla Q5 puede exigir corregir también la fecha. Se documenta y se valida con `staff.assignment_date_invalid`; si negocio prefiere permitir la edición sin corregir la fecha, es un cambio localizado.
- **Concurrencia y deadlocks (medio)**: orden fijo de bloqueo (trabajador → asignación). La prueba de dos transacciones y la restricción son obligatorias.
- **Permisos (medio)**: el encargado de eventos pierde la escritura; el frontend debe ocultar botones. Compras debe recibir 403 también en lectura. Actualizar el test de permisos de `identity`.
- **Privacidad (medio)**: la lectura incluye pago solo con `staff:manage`; el 409 no expone documento, teléfono, tarifa ni pago. El lookup de HU14 no incluye pago.
- **Contrato OpenAPI (bajo)**: se agregan rutas y esquemas; regenerar `openapi.json`. Sin cambios incompatibles en `/v1`.
- **Migración (alto)**: una sola, con `down_revision` sobre el head vigente. Antes: `uv run alembic heads`, avisar al humano y esperar confirmación. No editar migraciones aplicadas. No marcar como paralela.
- **Trigger append-only (bajo)**: no cubre `TRUNCATE` (igual que en HU15); se documenta como pendiente menor.
- **Ledger, inventario y precios (ninguno)**: el pago acordado no es egreso y no se escribe en el ledger; no se toca el congelado de precios de cotizaciones/contratos ni el append-only de inventario.
- **`assistant` (ninguno)**: no se agregan funciones; no debe exponer asignaciones ni pagos a roles sin `staff:manage`.
- **`reporting` (bajo)**: HU14 no está implementada; esta feature solo deja `staff.public_api` listo. No se cambian vistas ni reportes.

## 9. Impacto en módulos existentes y documentación

- **`identity`**: nuevo permiso `staff:assign`; sin migración. Test de `EVENTS_MANAGER` actualizado.
- **`staff`**: nuevas tablas, dominio, aplicación, infraestructura, presentación y `public_api`. Se modifica `DeactivateWorker` y su composición/tests.
- **`commercial`**: sin cambios; se reutiliza `event_lookup` y `EventStatus`.
- **`reporting`**: sin cambios en esta feature; HU14 ya está implementada con `NoEventStaff`. HU17 publica `event_assignments` y el dueño de `reporting` sustituye el adaptador nulo cuando el punto de conexión pase a “listo” en `docs/sdd/COORDINACION.md` §4.
- **`assistant`**: sin cambios; no se expone información de asignaciones.
- **`docs/DOMAIN.md`**:
  - §5.1: mantener R-STF-1..17.
  - §5.2 (nueva): reglas R-ASG-1..18 (o resumen que remita al spec) y matriz de permisos.
  - §9: dividir «Eventos y asignaciones» en «Eventos» (compras: lectura) y «Asignaciones» (admin: escritura, eventos: lectura, compras: –); nota de `staff:assign` y `staff:manage`.
  - §11: registrar las decisiones del 25/11/2026 (Q1–Q8, permisos, anulación con motivo, evento cancelado, baja bloqueada por asignaciones futuras).
- **`docs/architecture/ARCHITECTURE.md`**:
  - §6: agregar `staff_assignment_audit` a las tablas append-only y la restricción `staff_assignments_no_overlap` como ejemplo de exclusión.
  - §4: `staff` consulta `commercial` solo por `public_api.event_lookup`.
- **Docstrings**: `staff/composition.py`, `staff/public_api.py`, `assignment_router.py`, casos de uso y repositorio.
- **`README.md` / `STACK.md` / `INSTALACION.md`**: documentar que el esquema usa la extensión `btree_gist` (PostgreSQL contrib), que la migración la crea y qué hacer si el usuario de la base no tiene privilegios.
- **`openapi.json`**: regenerar con `just openapi`.
- **ADR 0005**: `docs/architecture/adr/0005-btree-gist-asignaciones.md`.

## 10. Decisiones del plan y supuestos

1. **Función en el alta (decisión del PO, 25/11/2026)**: si el cuerpo la omite, se copia de la ficha; si la ficha no tiene, se exige. Si el cuerpo la envía, se usa tal cual (permite elegir otra función porque un trabajador puede cubrir distintas funciones por evento). La ficha no se modifica.
2. **Fecha de la asignación**: debe ser la fecha del evento o, si el evento cruza la medianoche, también la siguiente (Q5). **Supuesto** de interpretación.
3. **Evento cancelado**: las asignaciones quedan `ACTIVE` con `occupies=false`; no se auto-anulan ni generan auditoría. Se liberan perezosamente al escribir. **Decisión de implementación**.
4. **Edición sin cambios**: devuelve 200 sin escribir auditoría (idempotente, como la baja de HU15). **Supuesto**.
5. **Asignación futura para la baja**: `end_at > now`; incluye la que está en curso. Las pasadas o anuladas no bloquean. **Supuesto**.
6. **Evento cancelado**: no se crea, edita ni anula; se conserva. Se interpreta R-ASG-10 en sentido amplio. **Supuesto**.
7. **Motivo**: máximo técnico de 500 caracteres, como en la cancelación de eventos. **Supuesto**.
8. **Listado**: sin paginación; volumen de decenas. **Supuesto** (el spec lo marca como tal).
9. **Trabajador inactivo en edición**: se permite corregir asignaciones pasadas; si el nuevo `end_at` es futuro, se rechaza. **Supuesto**.
10. **Detalle**: `GET` devuelve también asignaciones anuladas; la lista vigente no las incluye. **Supuesto**.
11. **Reconciliación de eventos cancelados (decisión aprobada 25/11/2026)**: no se notifica a `staff` desde `commercial`; no hay evento de dominio implementado. Se libera perezosamente al escribir.
12. **No se toca** `reporting`, `assistant`, ledger, inventario ni el congelado de precios.
13. **Edición de una asignación anulada (decisión del PO, 26/11/2026)**: se permite editar una asignación `CANCELLED`; el estado no cambia, no se reactiva y el cambio queda auditado como `UPDATED`. No se añade un 409 específico.

## 11. Orden de implementación

1. **Dominio** (T-02..T-04): horario, agregado y auditoría, con tests puros.
2. **Aplicación** (T-05..T-11): puertos, ocupación, casos de uso y baja de trabajador, con fakes.
3. **Infraestructura y ADR** (T-12..T-17): ORM/mappers, ADR 0005, migración, repositorio, constraints/concurrencia, triggers/migración. La migración es un gate humano.
4. **Presentación** (T-18..T-20): esquemas, router, errores y matriz de roles.
5. **Composición, OpenAPI y arquitectura** (T-21..T-23).
6. **Documentación y verificación** (T-24..T-27): `DOMAIN.md`, `ARCHITECTURE.md`, `STACK.md`, docstrings, `just check` e integración real.

Paralelizable: T-01 con T-02; T-07..T-11 entre sí tras T-06; T-16 y T-17 entre sí tras T-15; T-24, T-25 y T-26 entre sí tras T-21. La migración (T-14) **nunca** va en paralelo.
