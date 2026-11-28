# Plan: Registrar asistencia e historial del personal

- **Spec**: ./spec.md
- **Estado**: aprobado con ajustes (28/11/2026)
- **HU**: HU18 (#19)
- **Feature**: 035-staff-attendance
- **Depende de**: HU15 (032-staff), HU16 (034-staff-availability) y HU17 (033-staff-assignments) implementadas.
- **Sin dependencias nuevas**. Sin ADR: las decisiones de diseño (estado vigente + auditoría append-only + `CHECK` del motivo + lock pesimista `FOR UPDATE`) quedan documentadas **en este plan** (§2, §5 y §8); no se crea ningún archivo en `docs/architecture/adr/`.

## 0. Resumen

- Todo vive **dentro del módulo `staff`**. `commercial` se usa **solo** por `public_api.event_lookup`; `identity` solo por `public_api` y por un permiso nuevo.
- La asistencia tiene **estado vigente por asignación** (`staff_attendance`) y **auditoría append-only** (`staff_attendance_audit`) con actor, occurred_at, valor anterior, valor nuevo y motivo.
- El permiso nuevo `staff:attendance` (solo ADMIN) protege el `PATCH`; `staff:manage` (solo ADMIN) protege el `GET` del historial. Encargado de eventos y compras reciben **403** en ambas rutas.
- No se tocan entidades, puertos, adaptadores ni routers de HU16/HU17. La lectura de asignación, trabajador y pago se hace con **puertos/adaptadores nuevos de solo lectura** dentro de `staff`.
- **Evento huérfano (R-ATT-23/CA-18.22)**: si `commercial.public_api.event_lookup` no resuelve el `event_id`, `PATCH` y `GET` devuelven la fila igualmente con `event_code`, `event_date` y `event_status` en `null`; **no hay 404 por evento** ni se descarta la fila. En el historial, esas filas se excluyen cuando hay filtro `from`/`to` (no tienen `event_date`) y se incluyen sin filtro de fecha o con `event_id`, reflejándose en el `total`.
- Una migración nueva, **no creada en esta fase**, con `down_revision = "b959d55b8430"`. Antes de crearla se exige la puerta de migración de §5.4.
- Los `operationId` son estables: `staff_attendance_update` y `staff_attendance_history`. `openapi.json` se regenera.
- Sin dependencias ni logging nuevos: se usa el logging estándar del proyecto (structlog no está en el repo) y Problem Details con los `code` del spec.

## 1. Módulos y fronteras

### 1.1 `staff` (se amplía)

Archivos nuevos (rutas relativas a `src/local_eventos/modules/staff/`):

```
staff/
├─ domain/
│  ├─ attendance.py                 # AttendanceStatus, agregado Attendance
│  ├─ attendance_audit.py           # AttendanceAction, AttendanceAudit
│  └─ attendance_errors.py          # errores de dominio (422 con code staff.attendance_*)
├─ application/
│  ├─ ports/attendance_repository.py # Protocol + DTOs de lectura (sin frameworks)
│  ├─ attendance_errors.py          # errores de aplicación (404/409)
│  └─ use_cases/
│     ├─ update_attendance.py       # command
│     └─ get_attendance_history.py  # query
├─ infrastructure/
│  ├─ attendance_orm_models.py      # staff_attendance, staff_attendance_audit
│  ├─ attendance_mappers.py         # entidad ⇄ fila
│  └─ attendance_repository.py      # adaptador de solo lectura/escritura de asistencia
├─ presentation/
│  ├─ attendance_schemas.py
│  ├─ attendance_router.py
│  ├─ attendance_dependencies.py    # DI, permisos y user_names
│  └─ attendance_errors.py          # Problem Details de asistencia
└─ attendance_composition.py        # ensamblaje propio; no se edita composition.py
```

Modificaciones mínimas y justificadas:

- `identity/domain/permissions.py`: **una línea**, `STAFF_ATTENDANCE = "staff:attendance"` (patrón T-00 de HU16).
- `main.py`: importar y registrar `attendance_router` y `register_attendance_errors`.
- `migrations/env.py`: importar `attendance_orm_models` para que Alembic vea las tablas nuevas (no se edita `orm_models.py` de HU15/HU16/HU17).
- `openapi.json` y documentación (§9).

Fronteras:

- `staff` importa `commercial.public_api.EventLookup/EventInfo/EventStatus` y `identity.public_api.Permission/CurrentUser/user_names`. Nada más de esos módulos.
- Sin FK entre módulos: `event_id` sigue viviendo solo en `staff_assignments`; `recorded_by`/`actor_id` son UUID de `identity` sin FK.
- `reporting`, `assistant`, `ledger`, `inventory` y `purchasing` no se tocan.
- `staff.public_api` **no cambia**: no se expone asistencia a otros módulos en esta feature.

### 1.2 `identity` (solo permiso)

- `Permission.STAFF_ATTENDANCE = "staff:attendance"` en `identity/domain/permissions.py`.
- `Role.ADMIN` lo hereda por `frozenset(Permission)`; `EVENTS_MANAGER` y `PURCHASING_MANAGER` no lo reciben.
- `staff:manage` ya existe y sigue siendo solo del administrador.
- Sin migración: los permisos viven en código.
- Cierre al final: test de matriz (ADMIN sí; encargado de eventos 403; compras 403) en `tests/unit/identity/test_user.py` y en las rutas.

### 1.3 `commercial` (sin cambios)

Verificado en el código real (`commercial/public_api.py` y `application/events/use_cases/event_lookup.py`):

```python
@dataclass(frozen=True)
class EventInfo:
    id: UUID
    code: str
    status: EventStatus
    event_date: date
    start_time: time
    end_time: time


class EventLookup(Protocol):
    async def __call__(self, event_id: UUID) -> EventInfo | None: ...
```

`EventStatus` real: `SCHEDULED | CONFIRMED | IN_PROGRESS | FINISHED | CANCELLED`. **Coincide exactamente con el spec**. No se modifica `commercial` ni se añaden FK/JOIN.

## 2. Modelo de dominio

### 2.1 `AttendanceStatus`

`StrEnum` nuevo en `domain/attendance.py` (no se edita `enums.py` de HU15/HU17):

- `ATTENDED = "ATTENDED"` ("cumplió").
- `NOT_ATTENDED = "NOT_ATTENDED"` ("no cumplió").
- No hay tercer estado. "Sin registrar" se representa por **ausencia de fila** (`None`).

### 2.2 Agregado `Attendance`

Campos: `assignment_id: UUID`, `status: AttendanceStatus`, `recorded_by: UUID`, `recorded_at: datetime` (UTC aware).

- `Attendance.record(assignment_id, status, actor_id, recorded_at)`: primer registro; valida UUID, estado y fecha aware; normaliza `recorded_at` a UTC.
- `Attendance.correct(new_status, reason, actor_id, occurred_at) -> AttendanceAudit`:
  - si `new_status` no es `AttendanceStatus` → `staff.attendance_status_invalid`;
  - si `new_status == status` → no-op idempotente (lo decide el caso de uso antes de llamar);
  - exige `reason` recortado de 1..500 → `staff.attendance_reason_required`;
  - muta el estado actual y devuelve la auditoría `CORRECTED` con anterior/nuevo, actor y fecha.
- `Attendance.record(...)` genera la auditoría `RECORDED` (motivo nulo; el spec lo permite).
- Invariantes: un solo estado vigente por asignación; nunca `DELETE`; toda mutación va acompañada de auditoría en la misma transacción.

### 2.3 `AttendanceAudit`

VO inmutable:

- `action ∈ {RECORDED, CORRECTED}`.
- `previous_status: AttendanceStatus | None`; `new_status: AttendanceStatus`.
- `reason: str | None`; `actor_id: UUID`; `occurred_at: datetime` UTC.
- Reglas:
  - `RECORDED`: `previous_status is None`, `reason is None`.
  - `CORRECTED`: `previous_status is not None`, `previous_status != new_status`, `reason` recortado 1..500.
  - `previous_status`/`new_status` solo `ATTENDED`/`NOT_ATTENDED`.
- La base de datos replica estas reglas con `CHECK` (§5), incluida la corrección sin motivo.

### 2.4 Errores de dominio/aplicación

Dominio (subclase de `StaffValidationError` → 422 con `code`):

- `staff.attendance_status_invalid` (estado ausente o distinto de `ATTENDED`/`NOT_ATTENDED`).
- `staff.attendance_reason_required` (corrección sin motivo, vacío, solo espacios o >500).

Aplicación (404/409, con handler propio):

- `staff.assignment_not_found` (reutiliza `AssignmentNotFoundError` existente) → 404.
- `staff.worker_not_found` (nuevo `AttendanceWorkerNotFoundError`) → 404.
- `staff.attendance_not_due` (`AttendanceNotDueError`) → 409.
- `staff.attendance_assignment_cancelled` (`AttendanceAssignmentCancelledError`) → 409.
- `staff.attendance_date_range_invalid` (`AttendanceDateRangeInvalidError`) → 422.

> **No existe `staff.event_not_found` en esta feature** (R-ATT-23): un evento no resoluble por `commercial` no es un error; la fila se devuelve con los campos de evento en `null`. Las decisiones de modelo (estado vigente + auditoría append-only + `CHECK` del motivo + lock pesimista `FOR UPDATE`) se documentan aquí y en §5/§8; **no se crea ADR**.

## 3. Casos de uso

| Caso de uso | Tipo | Entrada | Salida | Errores de negocio |
|---|---|---|---|---|
| `UpdateAttendance` | command | `assignment_id`, `status` (str/enum), `reason?`, `actor_id` | vista de asignación + asistencia vigente y evento (anulable) | 404 asignación; 409 anulada/no terminada; 422 estado/motivo |
| `GetAttendanceHistory` | query | `worker_id`, `from?`, `to?`, `event_id?`, `page`, `page_size` | página de filas + total | 404 trabajador; 422 rango/paginación |

### 3.1 `UpdateAttendance`

1. `attendance_repository.lock_assignment(assignment_id)` → `SELECT ... FOR UPDATE` de `staff_assignments` y su trabajador. Si no existe → 404 `staff.assignment_not_found`.
2. Si `assignment_status == CANCELLED` → 409 `staff.attendance_assignment_cancelled` (se evalúa antes que la ventana temporal).
3. `now = clock.now()` (inyectado, UTC). Si `now < end_at` → 409 `staff.attendance_not_due`. `now == end_at` **sí** se acepta (CA-18.1/R-ATT-5).
4. Validar `status`; si falta o no es `ATTENDED`/`NOT_ATTENDED` → 422 `staff.attendance_status_invalid`.
5. `event_lookup(assignment.event_id)` para completar `event_code`, `event_status` y `event_date`; **resolución tolerante**: si no se resuelve (evento huérfano) se devuelven `event_code`, `event_date` y `event_status` en `null`, **sin 404** y sin descartar la asignación (R-ATT-23/CA-18.22).
6. Leer estado vigente (`attendance_repository.get`).
   - **Sin registro**: crear `Attendance.record(...)` y auditoría `RECORDED`; `reason` se ignora (no se persiste). Guardar estado + auditoría.
   - **Mismo estado**: idempotente; no se valida motivo, no se escribe auditoría y se devuelve el estado actual (CA-18.12).
   - **Estado distinto**: exigir motivo recortado 1..500 (si no → 422 `staff.attendance_reason_required`); `Attendance.correct(...)` + auditoría `CORRECTED`; guardar.
7. Devolver `AttendanceAssignment` + `Attendance` + `EventInfo` ya resueltos; presentación resuelve el nombre del actor con `identity.public_api.user_names` y mapea a `AttendanceOut`. Se usa el actor **guardado** (`recorded_by`), no el usuario de la petición, para que una repetición idempotente muestre a quien registró originalmente.

No modifica función, horario, pago, estado de la asignación, disponibilidad ni ledger (CA-18.19).

### 3.2 `GetAttendanceHistory`

1. Validar `page >= 1`, `1 <= page_size <= 100` y, si vienen ambas, `from <= to`; cualquier fallo → 422 `staff.attendance_date_range_invalid`.
2. `worker_lookup.get(worker_id)` (puerto existente `WorkerLookup`, el mismo que expone `staff.public_api`) → si `None`, 404 `staff.worker_not_found`. Incluye trabajadores inactivos (CA-18.14).
3. `attendance_repository.list_history(worker_id, event_id?)`: **una fila por asignación**, `ACTIVE` y `CANCELLED`, con nombre de trabajador y asistencia vigente (`LEFT JOIN`). Orden por `start_at DESC`; `event_id` se filtra en SQL.
4. Resolver el evento de cada fila con `commercial.public_api.event_lookup`, **deduplicando por `event_id`** (una llamada por evento distinto). **Resolución tolerante**: si un evento no se resuelve, la fila se conserva con `event_code`, `event_date` y `event_status` en `null`; **no se responde 404 por evento** ni se descarta la fila (R-ATT-23/CA-18.22).
5. Aplicar el filtro de **fecha del evento** (`EventInfo.event_date`, ya es fecha local de Lima) inclusivo `[from, to]` en memoria. Esto es necesario porque `staff` no puede hacer JOIN con `commercial`; el volumen es de decenas a pocos cientos de asignaciones por trabajador. Las filas con `event_date` **nula** (evento huérfano) **no coinciden** con `from`/`to` (se excluyen cuando hay filtro de fecha) y **sí** se incluyen cuando no hay filtro de fecha o cuando el filtro es por `event_id`.
6. Calcular `total` sobre las filas filtradas (incluidas las huérfanas que apliquen según el paso 5); recortar la página `[(page-1)*page_size : page*page_size]`. Página fuera de rango → lista vacía con el total correcto (CA-18.8).
7. Devolver `items` (con `recorded_by` UUID), `total`, `page`, `page_size`. La presentación resuelve los nombres de la página con `identity.public_api.user_names` en una sola llamada.

## 4. API (OpenAPI)

### 4.1 Endpoints

| Método y ruta | `operationId` | Permiso | Éxito |
|---|---|---|---|
| `PATCH /v1/staff/assignments/{assignment_id}/attendance` | `staff_attendance_update` | `staff:attendance` (solo ADMIN) | 200 |
| `GET /v1/staff/workers/{worker_id}/attendance` | `staff_attendance_history` | `staff:manage` (solo ADMIN) | 200 |

- No hay `DELETE`; la asistencia se corrige con `PATCH`.
- Ambos routers van bajo `tags=["staff"]` y documentan 401/403.

### 4.2 Esquemas

**`AttendanceUpdate`** (`extra="forbid"`):

- `status: str | None` con `default=None`. Se documenta con `json_schema_extra={"enum": ["ATTENDED","NOT_ATTENDED"]}` para conservar el contrato OpenAPI; la validación real la hace el caso de uso para devolver `staff.attendance_status_invalid` (incluido el caso de estado ausente) en vez del 422 genérico de Pydantic. Semánticamente es obligatorio.
- `reason: str | None` opcional. Se recorta y valida (1..500) **solo cuando es una corrección**. El primer registro y el mismo estado lo ignoran.

**`AttendanceOut`**:

- `assignment_id`, `worker_id`, `worker_name`
- `event_id`
- `event_code: str | null`, `event_status: EventStatus | null` (**anulables**: `null` si el evento no se resuelve, R-ATT-23)
- `function`, `function_description`
- `event_date: date | null` (**anulable**: `null` si el evento no se resuelve, R-ATT-23)
- `start_time`, `end_time` (horas locales de la asignación), `start_at`, `end_at` (UTC ISO 8601)
- `pay_cents` (entero), `currency` (`"PEN"`)
- `assignment_status` (`ACTIVE`/`CANCELLED`)
- `attendance_status` (`ATTENDED`/`NOT_ATTENDED`; `null` = "sin registrar")
- `attendance_recorded_at` (UTC), `attendance_recorded_by` (nombre del usuario) y `attendance_recorded_by_id` (UUID; extensión compatible para trazabilidad, ver §11)

**`AttendanceHistoryPage`**: `{ "items": [AttendanceOut], "total": int, "page": int, "page_size": int }`.

**Query de historial**: `from` y `to` (alias de `from_`/`to_` en Python), `event_id`, `page`, `page_size`. Se usa `Query(alias="from")` y `Query(alias="to")` para respetar el contrato.

### 4.3 Errores

| HTTP | `code` | Cuándo |
|---|---|---|
| 401 | `auth.not_authenticated` / `auth.session_expired` | sin sesión |
| 403 | `auth.forbidden` | rol sin el permiso de la ruta |
| 404 | `staff.assignment_not_found` | PATCH con asignación inexistente |
| 409 | `staff.attendance_not_due` | asignación aún no terminada (`now < end_at`) |
| 409 | `staff.attendance_assignment_cancelled` | asignación `CANCELLED` |
| 422 | `staff.attendance_status_invalid` | `status` ausente o fuera de `ATTENDED`/`NOT_ATTENDED` |
| 422 | `staff.attendance_reason_required` | corrección sin motivo/vacío/solo espacios/>500 |
| 404 | `staff.worker_not_found` | GET con trabajador inexistente |
| 422 | `staff.attendance_date_range_invalid` | `from > to` o paginación fuera de rango |

**No hay `staff.event_not_found`**: un evento no resoluble se devuelve con `event_code`, `event_date` y `event_status` en `null` (R-ATT-23/CA-18.22), tanto en `PATCH` como en `GET`.

### 4.4 Permisos por rol

| Acción | Permiso | ADMIN | EVENTS_MANAGER | PURCHASING_MANAGER |
|---|---|:-:|:-:|:-:|
| Registrar/corregir asistencia | `staff:attendance` | ✔ | – | – |
| Consultar historial (con pago) | `staff:manage` | ✔ | – | – |
| Personal designado del evento (existente) | `staff_roster:read` | ✔ | ✔ | – |

`staff_roster:read` **no** abre ninguna de las dos rutas (CA-18.10 se mantiene sin cambios).

### 4.5 Orden de rutas (obligatorio)

En `main.py`, el orden será:

```python
app.include_router(assignment_router.router)
app.include_router(attendance_router.router)  # ANTES de availability y worker
app.include_router(availability_router.router)
app.include_router(worker_router.router)
```

Motivo: las rutas literales `/v1/staff/assignments/...` y `/v1/staff/workers/...` deben declararse antes de `GET /v1/staff/{worker_id}` (misma lección que HU16/HU17). Aunque hoy no colisionan por número de segmentos, se fija el orden y se prueba con **un test por ruta** que verifica el `operationId` realmente enrutado y que no hay `422` de path param.

## 5. Persistencia

### 5.1 Tablas nuevas

**`staff_attendance`** (estado vigente, una fila por asignación):

| Columna | Tipo | Regla |
|---|---|---|
| `assignment_id` | `UUID` PK | `REFERENCES staff_assignments(id) ON DELETE RESTRICT` |
| `status` | `VARCHAR(12)` | `NOT NULL`, `CHECK status IN ('ATTENDED','NOT_ATTENDED')` |
| `recorded_by` | `UUID` | `NOT NULL`; usuario de `identity`, sin FK |
| `recorded_at` | `TIMESTAMPTZ` | `NOT NULL` |

- La PK garantiza un solo estado vigente por asignación.
- Trigger `BEFORE DELETE` que rechaza el borrado físico (la asistencia no se elimina).

**`staff_attendance_audit`** (append-only):

| Columna | Tipo | Regla |
|---|---|---|
| `id` | `BIGINT IDENTITY` PK | |
| `assignment_id` | `UUID` | `NOT NULL`, `REFERENCES staff_assignments(id) ON DELETE RESTRICT` |
| `action` | `VARCHAR(9)` | `CHECK action IN ('RECORDED','CORRECTED')` |
| `previous_status` | `VARCHAR(12)` | `NULL` o `ATTENDED`/`NOT_ATTENDED` |
| `new_status` | `VARCHAR(12)` | `NOT NULL`, `ATTENDED`/`NOT_ATTENDED` |
| `reason` | `TEXT` | `NULL` solo en `RECORDED` |
| `actor_id` | `UUID` | `NOT NULL`, sin FK |
| `occurred_at` | `TIMESTAMPTZ` | `NOT NULL` |

`CHECK` compuesto (réplica de R-ATT-7/R-ATT-22):

```sql
(action = 'RECORDED' AND previous_status IS NULL AND reason IS NULL)
OR
(action = 'CORRECTED'
 AND previous_status IS NOT NULL
 AND previous_status <> new_status
 AND reason IS NOT NULL
 AND btrim(reason) <> ''
 AND char_length(btrim(reason)) <= 500)
```

- Índice `(assignment_id, occurred_at)`.
- Trigger `BEFORE UPDATE OR DELETE` que rechaza la modificación (append-only).
- Sin FK a `identity` ni a `commercial`.

### 5.2 Migración Alembic

- Una sola migración nueva; **no se crea en esta fase**.
- `down_revision = "b959d55b8430"` (head actual indicado).
- Crea ambas tablas, `CHECK`s, índice y triggers. `downgrade` elimina triggers y tablas en orden inverso.
- `migrations/env.py` importa `attendance_orm_models`; no se edita `staff/infrastructure/orm_models.py`.

### 5.3 Transacción y concurrencia

- La transacción la abre `get_session` (`async with sessions.begin()`); el caso de uso no hace commit. Estado vigente + auditoría se guardan en la **misma transacción**: si falla la auditoría, no queda el cambio (R-ATT-7).
- **Correcciones simultáneas**: `UpdateAttendance` bloquea la fila de `staff_assignments` con `SELECT ... FOR UPDATE`. La segunda transacción espera, relee el estado vigente y decide:
  - si coincide con el nuevo estado → idempotente, sin auditoría;
  - si difiere → exige motivo y audita el cambio real.
  Ambas correcciones quedan auditadas y prevalece la última guardada. No se añade columna de versión ni bloqueo optimista.
- El lock es por asignación; no se bloquea al trabajador ni otras asignaciones.

### 5.4 Puerta previa obligatoria a crear la migración

Antes de generar el archivo de migración, en este orden y **parando si algo falla**:

```bash
git fetch origin
git merge origin/developer-a
uv run alembic heads
```

`uv run alembic heads` debe imprimir **un único head igual a `b959d55b8430`**. Si hay dos heads o no coincide, **no se crea la migración** y se avisa al humano (AGENTS.md y COORDINACION.md). Tras crear la migración, repetir `uv run alembic heads` y confirmar un solo head nuevo encadenado.

**Estado de la puerta**: ya fue **ejecutada y pasó** (28/11/2026): `git merge origin/developer-a` limpio, `uv run alembic heads` con **head único `b959d55b8430`** y **Docker disponible** para los tests de integración. **Debe repetirse antes de crear la migración** (T-07): si el fetch/merge deja dos heads o un head distinto de `b959d55b8430`, se **para** y se avisa al humano (AGENTS.md y COORDINACION.md). Tras crear la migración, repetir `uv run alembic heads` y confirmar un solo head nuevo encadenado.

## 6. Reglas de negocio aplicadas

- **R-ATT-1/R-ATT-2/R-ATT-3**: una asistencia vigente por asignación; solo `ATTENDED`/`NOT_ATTENDED`; ausencia = "sin registrar".
- **R-ATT-4/R-ATT-5**: solo asignaciones `ACTIVE` y con `now >= end_at`.
- **R-ATT-6/R-ATT-7/R-ATT-22**: corrección en cualquier momento con motivo 1..500; auditoría append-only con actor, fecha, anterior, nuevo y motivo; sin trazabilidad no hay cambio.
- **R-ATT-8/CA-18.17**: evento cancelado no impide registrar si la asignación terminó; el historial muestra el estado real del evento.
- **R-ATT-9/R-ATT-11/R-ATT-18/R-ATT-21**: historial por trabajador, una fila por asignación, incluidas `CANCELLED` con asistencia `null`, orden descendente por inicio.
- **R-ATT-10/R-ATT-12/R-ATT-13**: filtros por fecha de evento y evento; `commercial.public_api`; UTC en almacenamiento, Lima en presentación; céntimos `PEN`.
- **R-ATT-14**: `staff:attendance` y `staff:manage`, solo ADMIN; 403 para los otros roles.
- **R-ATT-15/R-ATT-19/R-ATT-20**: no altera asignación, disponibilidad ni ledger; 404 para asignación/trabajador inexistente; sin marcaciones.
- **R-ATT-16/R-ATT-17**: trabajador inactivo conserva historial; mismo estado es idempotente.

No se modifica `DOMAIN.md` en este plan; en la tarea de docs se añade §5.4 "Asistencia (HU18)" y la fila de permisos en §9.

## 7. Estrategia de tests

### 7.1 Unitarios (sin base de datos)

Usan fakes en memoria (`FakeAttendanceRepository`, `FakeClock`, `FakeEventLookup`, `FakeWorkerLookup`, `FakeUserNames`).

- `tests/unit/staff/test_attendance_domain.py`: estados, primer registro, corrección con motivo, motivo recortado/límites, mismo estado, invariantes de `AttendanceAudit`.
- `tests/unit/staff/test_attendance_update.py`: 404, 409 anulada, 409 no terminada, `now == end_at` permitido, primer registro sin motivo, corrección sin/con motivo, idempotencia sin auditoría, campos de auditoría, **evento huérfano (event_lookup → `None`) devuelve 200 con `event_code`/`event_date`/`event_status` en `null`, sin 404**.
- `tests/unit/staff/test_attendance_history.py`: 404 trabajador, trabajador inactivo, filtros `from`/`to`/`event_id`, rango inválido, paginación y total, página fuera de rango, orden descendente, varias asignaciones al mismo evento, `CANCELLED` con `null`, **evento huérfano: fila devuelta con campos de evento en `null`; excluida con `from`/`to`; incluida sin filtro de fecha y con `event_id`; `total` coherente en cada caso**, conversión Lima/UTC y céntimos.
- `tests/unit/staff/test_attendance_api.py`: `PATCH` 200/404/409/422 con `code`; `GET` 200/404/422 con `code`; forma de `AttendanceOut`/`AttendanceHistoryPage`; **evento huérfano serializado con `event_code`/`event_date`/`event_status` en `null` (PATCH y GET), sin 404**.
- `tests/unit/staff/test_attendance_router_order.py`: **un test para `PATCH` y otro para `GET`** sobre `create_app()` real, con dependencias en memoria: la petición se enruta con su `operationId`, no devuelve el `422` de path param, y las rutas de asistencia se declaran antes de `/v1/staff/{worker_id}`.
- `tests/unit/staff/test_attendance_api_roles.py`: ADMIN pasa; `EVENTS_MANAGER` y `PURCHASING_MANAGER` → 403 `auth.forbidden` en ambas rutas; sin sesión → 401; usuarios con solo `staff_roster:read` o `staff:assign` → 403.
- `tests/unit/identity/test_user.py`: `STAFF_ATTENDANCE` en ADMIN y no en los otros roles.

### 7.2 Integración (PostgreSQL real)

- `tests/integration/staff/test_attendance_repository.py`: roundtrip estado/auditoría, historial con activas y anuladas, pago en céntimos, trabajador inactivo, **evento huérfano (asignación cuyo `event_id` no existe en `commercial`) devuelto por el historial sin descartarse**.
- `tests/integration/staff/test_attendance_constraints.py`: PK única; `CHECK` de estados; **inserción directa de una corrección sin motivo rechazada por la base**; primer registro sin motivo aceptado; motivo >500 rechazado.
- `tests/integration/staff/test_attendance_audit_append_only.py`: `UPDATE`/`DELETE` sobre auditoría rechazados por trigger; `DELETE` sobre `staff_attendance` rechazado.
- `tests/integration/staff/test_attendance_concurrency.py`: dos correcciones simultáneas sobre la misma asignación se serializan; ambas quedan auditadas y el estado final es el último guardado.
- `tests/integration/staff/test_attendance_migration.py`: `upgrade head` crea tablas/constraints/triggers; `downgrade` limpio.
- `tests/integration/staff/test_attendance_api_db.py` (opcional, e2e): dos rutas contra la app real y PostgreSQL; 401/403/404/409/422.

### 7.3 Mapeo CA → test

| CA | Test principal |
|---|---|
| 18.1, 18.2 | `test_attendance_update` (primer registro) + `test_attendance_api` + `test_attendance_repository` |
| 18.3 | `test_attendance_update` (no terminada) + API 409 |
| 18.4 | `test_attendance_update` (anulada) + API 409 |
| 18.5 | `test_attendance_history` (sin registro → `null`) |
| 18.6 | `test_attendance_history` (campos y orden) |
| 18.7 | `test_attendance_history` (filtros y rango inválido) |
| 18.8 | `test_attendance_history` (paginación/total/página fuera de rango) |
| 18.9 | `test_attendance_api_roles` (401/403) |
| 18.10 | `test_attendance_api_roles` + `test_user` (roster intacto) |
| 18.11 | `test_attendance_update` + `test_attendance_constraints` (CHECK sin motivo) |
| 18.12 | `test_attendance_update` (idempotencia, sin auditoría) |
| 18.13 | `test_attendance_history` (céntimos) + ausencia de escritura en ledger (no hay repositorio de ledger en el caso de uso) |
| 18.14 | `test_attendance_history` (inactivo) |
| 18.15 | `test_attendance_update`/`test_attendance_history` (404) |
| 18.16 | `test_attendance_api`/`test_attendance_update` (422 status) |
| 18.17 | `test_attendance_update` (evento cancelado permitido) |
| 18.18 | `test_attendance_history` (varias asignaciones al mismo evento) |
| 18.19 | `test_attendance_repository` (asignación no cambia) + revisión de imports (sin ledger/disponibilidad) |
| 18.20 | `test_attendance_history`/`test_attendance_api` (Lima y UTC) |
| 18.21 | `test_attendance_history` (anuladas con `null`) |
| 18.22 | `test_attendance_update` + `test_attendance_history` + `test_attendance_api` + `test_attendance_repository` (evento huérfano: campos `null`, sin 404, filtros y `total`) |

## 8. Riesgos y decisiones de diseño

- **Reprogramación del evento**: se muestran por separado `event_date` (de `commercial`) y el horario de la asignación; no se recalcula nada (R-ASG-11).
- **Evento cancelado**: se permite registrar si la asignación terminó; el supuesto del cliente sigue abierto y no bloquea.
- **Correcciones concurrentes**: resueltas con `FOR UPDATE` por asignación; última escritura prevalece y todas se auditan.
- **Privacidad del pago**: la única puerta es `staff:manage`; se prueba 403 para encargado de eventos y compras.
- **Reloj/zona**: comparación con `clock.now()` UTC; presentación en Lima; tests con `end_at` exacto.
- **Evento huérfano**: si `commercial` no resuelve un `event_id`, la fila se devuelve igualmente con `event_code`, `event_date` y `event_status` en `null`, **sin 404** y sin descartarla (R-ATT-23/CA-18.22); no se inventan datos. En el historial se excluye con `from`/`to` y se incluye sin filtro de fecha o con `event_id`, reflejándose en el `total`. Se cubre con un test específico (unit + API + integración).
- **Migraciones**: puerta de head único antes de crear la migración (§5.4).
- **Decisiones sin ADR**: estado vigente + auditoría append-only + `CHECK` del motivo + lock pesimista `FOR UPDATE` documentados en §2 y §5; **no se crea** `docs/architecture/adr/0008-*` (decisión del 28/11/2026). Sin dependencia nueva.

## 9. Impacto en `reporting` y documentación

- **`reporting`**: sin cambios. No consume asistencia; su reporte de personal sigue con `staff:manage`. No hay vistas nuevas ni cambios de contrato.
- **`assistant`**: sin cambios; no se expone asistencia al agente.
- **Documentación**:
  - `docs/DOMAIN.md`: §5.4 (reglas de asistencia) y §9 (permiso `staff:attendance`).
  - `docs/sdd/COORDINACION.md`: estado de HU18 y head de Alembic.
  - `openapi.json`: regenerado con `just openapi`; `operationId` estables.
  - `docs/sdd/features/035-staff-attendance/tasks.md`: tareas atómicas T-00..T-14 con archivos, CA y comando de verificación.

## 10. Orden de implementación (tareas atómicas, detalladas en `tasks.md`)

| # | Tarea | Capa | Depende de |
|---|---|---|---|
| T-00 | `staff:attendance` en `identity/domain/permissions.py` + test de matriz | identity | — |
| T-01 | `AttendanceStatus`, `Attendance`, `AttendanceAudit`, errores de dominio + tests | domain | — |
| T-02 | Puerto `AttendanceRepository`, DTOs de lectura y errores de aplicación | application | T-01 |
| T-03 | `UpdateAttendance` + tests unitarios | application | T-02 |
| T-04 | `GetAttendanceHistory` + tests unitarios | application | T-02 |
| T-05 | ORM `attendance_orm_models.py`, mappers e import en `migrations/env.py` | infrastructure | T-01 |
| T-06 | `attendance_repository.py` (lock, get, save, historial) | infrastructure | T-02, T-05 |
| T-07 | Migración (puerta §5.4) + tests de constraints/append-only/migración | infra/migración | T-05, T-06 |
| T-08 | Tests de repositorio y concurrencia contra PostgreSQL | integration | T-06, T-07 |
| T-09 | `attendance_composition.py`, `attendance_dependencies.py`, `attendance_errors.py` | composition/presentation | T-03, T-04, T-06 |
| T-10 | `attendance_schemas.py`, `attendance_router.py` e inclusión ordenada en `main.py` | presentation | T-09 |
| T-11 | Tests de API y de orden de rutas (uno por ruta) | tests | T-10 |
| T-12 | Matriz de permisos por ruta (401/403/ADMIN) y cierre de permisos | tests/identity | T-10 |
| T-13 | `openapi.json` + docs (`DOMAIN`, `COORDINACION`, feature) | docs | T-10 |
| T-14 | Verificación final: `just check`, `just arch`, `uv run alembic heads` | verificación | todas |

Paralelizables: T-03 y T-04 (casos de uso independientes); T-05/T-06 pueden avanzar en paralelo con T-03/T-04; T-11/T-12 en paralelo tras T-10. T-00 puede ir primero y en paralelo con T-01.

## 11. Discrepancias y decisiones entre spec y código real

1. **Estados del evento**: el spec enumera `SCHEDULED | CONFIRMED | IN_PROGRESS | FINISHED | CANCELLED`; el `EventStatus` real coincide **exactamente**. No hay discrepancia. `EventInfo` real tiene `id`, `code`, `status`, `event_date`, `start_time`, `end_time`; el plan usa esos campos.
2. **Query params `from`/`to`**: el spec los nombra así; en Python se implementan como `from_`/`to_` con `Query(alias="from")`/`Query(alias="to")`. El contrato HTTP no cambia.
3. **`attendance_recorded_by`**: el spec no fija si es UUID o nombre. El plan devuelve el **nombre** (resuelto con `identity.public_api.user_names`) y añade `attendance_recorded_by_id` (UUID) como campo extra compatible. La auditoría guarda el UUID.
4. **Evento huérfano (decisión 28/11/2026)**: si `commercial.public_api.event_lookup` no resuelve un `event_id`, **no** se responde 404 ni se descarta la fila; `PATCH` y `GET` devuelven `event_code`, `event_date` y `event_status` en `null` (R-ATT-23/CA-18.22, mismo criterio que HU16 T-22). Se elimina el error `staff.event_not_found` de esta feature. En el historial, las filas con `event_date` nula se excluyen con `from`/`to` y se incluyen sin filtro de fecha o con `event_id`; el `total` lo refleja.
5. **Validación exacta de `status` y `reason`**: para devolver `staff.attendance_status_invalid` y `staff.attendance_reason_required` (y no el 422 genérico de Pydantic), el esquema acepta `status`/`reason` como texto (con `status=None` por defecto para capturar también el estado ausente) y el caso de uso valida. OpenAPI documenta el enum de `status`.
6. **Filtro por fecha del evento**: no puede hacerse en SQL sin cruzar módulos (sin FK/JOIN). El repositorio trae las asignaciones del trabajador y el caso de uso resuelve eventos por `public_api`, filtra por `event_date` y pagina en memoria. Es correcto para el volumen esperado (decenas a pocos cientos); si el volumen crece, se evaluará en otra feature.
7. **`end_at` igual a `now`**: se acepta (`now >= end_at`), tal como R-ATT-5.
8. **Asignación `CANCELLED`**: se comprueba antes que la ventana temporal; una asignación anulada responde siempre 409 `staff.attendance_assignment_cancelled`, aunque su `end_at` ya haya pasado.

## 12. Verificación final

- `just check` (ruff + mypy + lint-imports + pytest) en verde.
- `just arch` en verde: sin imports a capas internas de `commercial`/`identity` ni a `staff` desde otros módulos.
- `uv run alembic heads` con **un solo head**; tras aplicar la migración, el head nuevo encadena desde `b959d55b8430`.
- `openapi.json` regenerado y revisado (`staff_attendance_update`, `staff_attendance_history`).
- Criterios de aceptación CA-18.1..CA-18.22 cubiertos por los tests mapeados en §7.3.
