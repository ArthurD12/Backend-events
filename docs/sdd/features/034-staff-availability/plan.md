# Plan: Consultar la disponibilidad del personal y registrar indisponibilidades

- **Spec**: `docs/sdd/features/034-staff-availability/spec.md`
- **Estado**: borrador (pendiente de aprobación humana)
- **HU**: HU16 (#17)
- **Feature**: 034-staff-availability
- **Depende de**: HU15 (032-staff) y HU17 (033-staff-assignments) implementadas.
- **Sin dependencias nuevas ni ADR**: ver §8.

## 0. Resumen

- Todo vive **dentro del módulo `staff`**: no se añade un módulo nuevo ni se exponen datos a otros módulos. `staff.public_api` no cambia.
- `identity` solo gana el permiso `staff:availability`; `Role.ADMIN` lo recibe automáticamente (`frozenset(Permission)`) y ningún otro rol. `staff:manage` y `staff:roster:read` **no** dan acceso.
- La consulta de disponibilidad es de **solo lectura**. Reutiliza el mismo puerto de HU17 (`AssignmentRepository.list_active_overlaps`) y el mismo criterio efectivo (semiabierto `[inicio, fin)`, cruce de medianoche, eventos finalizados ocupan, cancelados no), **sin reimplementar el SQL del solape ni disparar `release_cancelled`**.
- Las indisponibilidades se editan y anulan **sin borrado físico**, con auditoría append-only, siguiendo el patrón de HU17.
- La tabla nueva `staff_unavailabilities` (más su auditoría) requiere **una migración** encadenada a `8df99a56ff18`; la migración es un **gate humano** y no se crea en esta fase.
- El router de disponibilidad se registra en `main.py` **antes** de `worker_router` para evitar la colisión con `/v1/staff/{worker_id}`.

## 1. Módulos y fronteras

### 1.1 `staff` (se amplía)

Nuevo o modificado (rutas relativas a `src/local_eventos/modules/staff/`):

```
staff/
├─ domain/
│  ├─ unavailability.py              # agregado Unavailability
│  ├─ unavailability_audit.py        # auditoría + snapshot
│  ├─ availability_query.py          # VO de ventana de consulta (Lima → UTC)
│  ├─ unavailability_schedule.py     # entrada local del alta (Lima → UTC)
│  └─ enums.py                       # + UnavailabilityKind, UnavailabilityStatus
├─ application/
│  ├─ errors.py                      # + errores de disponibilidad
│  ├─ ports/unavailability_repository.py
│  ├─ ports/worker_repository.py     # + list_active(function) -> list[WorkerRef]
│  ├─ ports/assignment_conflict_lookup.py  # nuevo: función por assignment_id (solo lectura)
│  └─ use_cases/
│     ├─ get_staff_availability.py
│     ├─ register_unavailability.py
│     ├─ update_unavailability.py
│     ├─ cancel_unavailability.py
│     └─ list_unavailability.py
├─ infrastructure/
│  ├─ orm_models.py                  # + staff_unavailabilities, staff_unavailabilities_audit
│  ├─ mappers.py                     # + mapeo entidad ⇄ fila ⇄ snapshot
│  ├─ unavailability_repository.py
│  ├─ worker_repository.py           # + list_active
│  ├─ assignment_conflict_lookup.py  # nuevo: WHERE id IN (...) sobre StaffAssignmentRow
├─ presentation/
│  ├─ availability_router.py         # prefijo /v1/staff
│  ├─ availability_schemas.py
│  ├─ errors.py                      # + mapeo a Problem Details
│  └─ dependencies.py                # + require STAFF_AVAILABILITY
├─ composition.py                    # + fábricas de casos de uso, repositorio y AssignmentConflictLookup
└─ public_api.py                     # SIN cambios
```

- `worker_id` de la indisponibilidad es FK **dentro de `staff`** (`staff_workers.id`, `ON DELETE RESTRICT`). No hay FK entre módulos.
- La consulta usa `commercial.public_api.event_lookup` y `EventInfo`/`EventStatus` solo para **leer** código, fecha y estado del evento en conflicto. Cero imports a capas internas o tablas de `commercial`.
- Usa `identity.public_api` (`CurrentUser`, `Permission`, `require_permission`), como el resto de `staff`.
- `reporting`, `assistant`, ledger, inventario y precios **no se tocan**.

### 1.2 `identity` (solo permiso — enabler temprano + verificación final)

- **Enabler temprano (T-00)**: declarar `Permission.STAFF_AVAILABILITY = "staff:availability"` en `src/local_eventos/modules/identity/domain/permissions.py` en el **primer** commit de `identity`, antes de presentación: es una dependencia de import del router (1 línea). `Role.ADMIN` lo hereda automáticamente (`frozenset(Permission)`) y ningún otro rol cambia.
- `EVENTS_MANAGER` y `PURCHASING_MANAGER` **no** lo reciben; no se toca su conjunto actual (025 ya les quitó `staff:manage`/lectura de asignaciones).
- Sin migración (los permisos viven en código).
- **Cierre de permisos (T-20, última)**: verificación, **no** añade la constante. Test de matriz (ADMIN sí; `EVENTS_MANAGER` y `PURCHASING_MANAGER` no), 403 por ruta y documentación (`DOMAIN.md` §9). Actualizar `tests/unit/identity/test_user.py` si la matriz lo requiere.

### 1.3 `commercial` (sin cambios)

- Solo se consume `event_lookup(session)` y `EventInfo(id, code, status, event_date, start_time, end_time)`.
- No se consultan contratos, cotizaciones ni pagos. No se añaden FK ni JOINs.

## 2. Modelo de dominio

### 2.1 Agregado `Unavailability`

Campos: `id`, `worker_id`, `kind`, `description`, `start_at`, `end_at`, `status`.

- `Unavailability.register(...)`: valida antes de construir; nace `ACTIVE`.
- `update(kind, description, start_at, end_at) -> bool`: reemplaza campos editables y devuelve si hubo cambio real. No cambia `worker_id`.
- `cancel() -> bool`: pasa a `CANCELLED`; idempotente.
- No existe `delete()`. `worker_id` es inmutable.
- Una indisponibilidad `CANCELLED` no se reactiva; se registra otra.

Invariantes:

1. `worker_id` obligatorio (UUID).
2. `start_at`/`end_at` en UTC aware; `end_at > start_at`.
3. `kind` obligatorio (`VACATION`, `LEAVE`, `REST`, `OTHER`; etiquetas en español en presentación).
4. Si `kind = OTHER`, `description` obligatoria y no vacía (máx. 120); en las demás, `description` debe ser `None`. Reusa el patrón de `function_description` de HU15/HU17.
5. `status ∈ {ACTIVE, CANCELLED}`; `CANCELLED` es terminal.
6. Sin borrado físico ni reactivación.

### 2.2 Value object `AvailabilityQuery`

Traduce la entrada local (`America/Lima`, offset fijo `-05:00`) a una ventana UTC semiabierta `[start_at, end_at)`.

- Entrada: `from_date`, `to_date` (obligatorias), `start_time?`, `end_time?`, `function?`, `state?`.
- Con horas: `start_at = from_date start_time` y `end_at = to_date end_time`, interpretados en Lima; si `end_time < start_time` en la **misma** fecha, termina al día siguiente (R-ASG-4). Para rangos multi-día la hora de fin se aplica al `to_date`; si `end_time <= start_time` en un rango de un solo día con igualdad, inválido.
- Sin horas: día completo; `start_at = from_date 00:00` y `end_at = to_date + 1 día 00:00` (Lima).
- Si se envía solo una de las dos horas → 422 (`staff.availability_window_invalid`).
- `end_at > start_at`; ventana máxima de **31 días corridos** (`(to_date - from_date).days <= 30`, ambas fechas incluidas) → si se excede, 422 `staff.availability_range_too_large`.
- `state` filtra el resultado (`FREE`, `BUSY`, `UNAVAILABLE`).

**`UnavailabilitySchedule` (alta/edición)**: recibe `date` + `start_time` + `end_time` obligatorios, los interpreta en Lima (`-05:00`) y devuelve `start_at`/`end_at` UTC. Mismas reglas que `AssignmentSchedule` de HU17 (R-ASG-4): `end_time == start_time` es inválido; `end_time < start_time` termina al día siguiente; `end_time > start_time` termina el mismo día. Se recomienda extraer un helper común de conversión Lima→UTC y hacer que ambos VO lo usen, sin cambiar el comportamiento de HU17 (test de regresión).

### 2.3 `UnavailabilityAudit`

Tabla lógica append-only con una fila por `CREATED`, `UPDATED` o `CANCELLED`.

- `UnavailabilitySnapshot`: `kind`, `description`, `start_at`, `end_at`.
- `CREATED`: `reason = None`, sin snapshots.
- `UPDATED`: `reason` obligatorio; `previous_values` y `new_values` obligatorios (JSONB).
- `CANCELLED`: `reason` obligatorio; sin snapshots.
- `actor_id` (usuario de `identity`, sin FK) y `occurred_at` (UTC) siempre.
- Se escribe en la **misma transacción** que la indisponibilidad.
- La entidad expone `snapshot()` para no duplicar la serialización.

### 2.4 Cálculo del estado (reutilización de HU17)

Para cada trabajador **activo** del filtro y la ventana consultada:

1. **Ocupación**: `AssignmentRepository.list_active_overlaps(worker_id, start_at, end_at)` — el mismo método y la misma composición que usa HU17. Devuelve asignaciones `ACTIVE` con `occupies=true` que comparten algún instante.
2. **Filtro efectivo de cancelados, solo lectura**: para cada solape se consulta `event_lookup(event_id)`; si el evento está `CANCELLED`, se descarta. No se escribe, no se modifica `occupies` y **no se llama** a `AssignmentOccupancy.release_cancelled`. Así la consulta aplica el mismo criterio efectivo que HU17 aunque la liberación perezosa aún no haya ocurrido (CA-16.15).
3. **Indisponibilidad**: `UnavailabilityRepository.list_active_overlapping(start_at, end_at, worker_ids)` en una sola consulta; solo `status='ACTIVE'`, con el mismo criterio semiabierto.
4. **Estado**: `UNAVAILABLE` si hay indisponibilidad (prevalece, Q5); si no, `BUSY` si quedan conflictos de asignación; si no, `FREE`.
5. Se devuelven los detalles de **ambos** conflictos cuando existan (Q5), pero el estado principal es uno.

No se duplica el SQL de solape de asignaciones: se invoca el puerto existente. El solape de indisponibilidades es una consulta distinta sobre otra tabla, con el mismo predicado `start_at < fin AND end_at > inicio`.

### 2.5 Enums nuevos

En `staff/domain/enums.py`:

- `UnavailabilityKind {VACATION, LEAVE, REST, OTHER}`.
- `UnavailabilityStatus {ACTIVE, CANCELLED}`.
- `AvailabilityState {FREE, BUSY, UNAVAILABLE}` (puede vivir en el dominio de disponibilidad).

## 3. Casos de uso

| Caso de uso | Tipo | Entrada | Salida | Errores de negocio |
|---|---|---|---|---|
| `GetStaffAvailability` | query | `AvailabilityQuery` | `AvailabilityReport` (lista plana) | `staff.availability_window_invalid`, `staff.availability_range_too_large` |
| `RegisterUnavailability` | command | `worker_id`, `date`, `start_time`, `end_time`, `kind`, `description?`, `actor_id` | `UnavailabilityView` | `staff.not_found`, `staff.worker_inactive`, `staff.unavailability_schedule_invalid`, `staff.unavailability_kind_required`, `staff.unavailability_description_required/not_allowed` |
| `UpdateUnavailability` | command | `unavailability_id`, campos editables, `reason`, `actor_id` | `UnavailabilityView` | `staff.unavailability_not_found`, `staff.unavailability_cancelled`, `staff.unavailability_reason_required`, validaciones de alta |
| `CancelUnavailability` | command | `unavailability_id`, `reason`, `actor_id` | `UnavailabilityView` | `staff.unavailability_not_found`, `staff.unavailability_reason_required` |
| `ListUnavailability` | query | `worker_id?`, `from_date?`, `to_date?` | lista de vistas | `staff.not_found`, `staff.availability_range_too_large` |

### 3.1 `GetStaffAvailability` (solo lectura)

1. Validar `AvailabilityQuery` (ventana, máximo 31 días, horas).
2. `worker_repository.list_active(function=query.function)` → una sola consulta de trabajadores `ACTIVE` (`WorkerRef`, sin datos sensibles).
3. `unavailability_repository.list_active_overlapping(start, end, worker_ids)` → una sola consulta; agrupar por `worker_id`.
4. Para cada trabajador: `list_active_overlaps(...)` (puerto de HU17); resolver eventos con `event_lookup`, **cacheando por `event_id` en la petición**, y descartar `CANCELLED`.
5. Calcular estado con precedencia `UNAVAILABLE > BUSY > FREE`.
6. Aplicar filtro `state` si viene; devolver lista plana (sin paginación).
7. **No escribe**: no hay `save`, ni `release`, ni auditoría. Repetir la consulta con los mismos datos da el mismo resultado.

Detalle del conflicto de asignación: `event_code`, `event_date`, `start_time`/`end_time` **de la asignación** (convertidos a Lima) y la función de la asignación vía **lectura aparte de HU16**. `list_active_overlaps` devuelve los `assignment_id`; después `AssignmentConflictLookup.by_ids(assignment_ids)` — puerto nuevo `application/ports/assignment_conflict_lookup.py` y adaptador nuevo `infrastructure/assignment_conflict_lookup.py` — lee `worker_function` y `function_description` de `staff_assignments` en **una sola consulta** (`WHERE id IN (...)`), importando el ORM existente `StaffAssignmentRow` **solo para lectura** (sin modificarlo). **No** se amplía `AssignmentOverlap`, **no** se toca ningún tipo/contrato/código de HU17 y **no** se duplica el predicado de solape: los ids provienen siempre del puerto de HU17. Si un id no aparece en la lectura (inconsistencia), la función se devuelve `None` y la consulta no falla.

Si `event_lookup` no encuentra el evento de un solape (dato huérfano), se omite ese conflicto y se registra un warning; la consulta no falla.

### 3.2 `RegisterUnavailability`

1. `worker_lookup.get(worker_id)` (o `worker_repository.get`): si no existe → 404 `staff.not_found`; si `INACTIVE` → 409 `staff.worker_inactive` (CA-16.2).
2. Construir `UnavailabilitySchedule` (Lima → UTC, cruce de medianoche); validar `end_at > start_at`.
3. Validar `kind`/`description`.
4. Crear el agregado y la auditoría `CREATED`; guardar en la misma transacción.
5. Devolver la vista con id y auditoría (usuario y fecha-hora).

### 3.3 `UpdateUnavailability`

1. `get_for_update(id)`; si no existe → 404.
2. Si está `CANCELLED` → 409 `staff.unavailability_cancelled`.
3. `reason` obligatorio y no vacío.
4. Validar los nuevos datos como en el alta.
5. Si no hay cambios reales, devolver 200 sin auditar (idempotente).
6. Escribir `UPDATED` con `reason`, `previous_values` y `new_values`.

### 3.4 `CancelUnavailability`

1. `get_for_update(id)`; si no existe → 404.
2. Si ya está `CANCELLED`, devolver 200 sin nueva auditoría (idempotente).
3. `reason` obligatorio y no vacío.
4. `cancel()` + auditoría `CANCELLED` con motivo; sin borrado físico.

### 3.5 `ListUnavailability`

- Filtra por trabajador y, opcionalmente, por ventana. Devuelve vistas (incluye estado). Solo lectura.
- Sirve para que el administrador recupere ids para editar/anular; no es la consulta de disponibilidad.

## 4. API (OpenAPI)

### 4.1 Colisión de router (diseño obligatorio)

Hecho verificado: `main.py:135-137` registra `assignment_router` antes de `worker_router` porque `/v1/staff/{worker_id}` (UUID) captura rutas literales y responde 422.

Diseño:

- `availability_router` usa `APIRouter(prefix="/v1/staff", tags=["staff"])` y define rutas literales `/availability` y `/unavailability...`.
- Se registra en `main.py` **antes** de `worker_router`, junto a `assignment_router`:

```python
# Primero las rutas literales: `/v1/staff/availability` y `/v1/staff/unavailability`
# no deben caer en `/v1/staff/{worker_id}` (UUID) y devolver 422.
app.include_router(assignment_router.router)
app.include_router(availability_router.router)
app.include_router(worker_router.router)
```

- **Regla permanente** (documentar en `main.py` y en `staff/presentation/availability_router.py`): toda ruta **literal** bajo `/v1/staff/*` se registra antes de `GET /v1/staff/{worker_id}`.

Tests obligatorios por **cada** ruta nueva:

1. Petición con sesión de administrador y parámetros/cuerpo válidos → **no 422**; se espera `200`/`201`/`404` según el caso, nunca un 422 de path param.
2. Sin sesión → `401`.
3. `EVENTS_MANAGER` → `403`.
4. `PURCHASING_MANAGER` → `403`.

Tests de humo de OpenAPI: para cada ruta, el `openapi.json` contiene el path y el `operationId` esperado. Añadir un test que documente la colisión: `GET /v1/staff/availability` no debe interpretarse como `worker_id`.

### 4.2 Endpoints

| Método y ruta | `operationId` | Permiso | Éxito |
|---|---|---|---|
| `GET /v1/staff/availability?from_date=&to_date=&start_time=&end_time=&function=&state=` | `staff_availability_get` | `staff:availability` | 200 |
| `GET /v1/staff/unavailability?worker_id=&from_date=&to_date=` | `staff_unavailability_list` | `staff:availability` | 200 |
| `POST /v1/staff/unavailability` | `staff_unavailability_register` | `staff:availability` | 201 |
| `PUT /v1/staff/unavailability/{unavailability_id}` | `staff_unavailability_update` | `staff:availability` | 200 |
| `POST /v1/staff/unavailability/{unavailability_id}/cancel` | `staff_unavailability_cancel` | `staff:availability` | 200 |

- No hay `DELETE`; un intento responde 405.
- `PUT` es reemplazo completo de los campos editables (`kind`, `description`, fecha/horas) y exige `reason`.
- El listado y la consulta no escriben nada.

### 4.3 Esquemas

**`AvailabilityOut`**

```
{
  "from": "2026-12-01T05:00:00Z",
  "to": "2026-12-02T05:00:00Z",
  "items": [
    {
      "worker_id": "uuid",
      "name": "...",
      "function": "WAITER|...|OTHER",
      "function_description": null,
      "state": "FREE|BUSY|UNAVAILABLE",
      "conflicts": [
        {"event_code": "EVT-2026-0012", "event_date": "2026-12-01",
         "start_time": "18:00:00", "end_time": "23:00:00",
         "function": "WAITER", "function_description": null}
      ],
      "unavailabilities": [
        {"id": "uuid", "kind": "VACATION", "description": null,
         "start_at": "...Z", "end_at": "...Z"}
      ]
    }
  ]
}
```

- **Nunca** incluye pago, tarifa, documento ni teléfono (R-DIS-9). Se verifica con un test que recorre las claves de la respuesta.

**`UnavailabilityCreate`**: `worker_id`, `date`, `start_time`, `end_time`, `kind`, `description?`.
**`UnavailabilityUpdate`**: `kind`, `description`, `date`, `start_time`, `end_time`, `reason` (obligatorio).
**`UnavailabilityCancel`**: `reason` (obligatorio).
**`UnavailabilityOut`**: `id`, `worker_id`, `kind`, `description`, `date`, `start_time`, `end_time`, `start_at`, `end_at`, `status`, `created_at`, `updated_at`.
**`UnavailabilityListOut`**: `{ "items": [UnavailabilityOut, ...] }`.

### 4.4 Errores (Problem Details)

| HTTP | `code` | Cuándo |
|---|---|---|
| 401 | `auth.not_authenticated`, `auth.session_expired` | Sin sesión |
| 403 | `auth.forbidden` | Sin `staff:availability` (incluye encargado de eventos y compras) |
| 404 | `staff.not_found` | `worker_id` inexistente |
| 404 | `staff.unavailability_not_found` | `unavailability_id` inexistente |
| 409 | `staff.worker_inactive` | Alta para trabajador inactivo (CA-16.2) |
| 409 | `staff.unavailability_cancelled` | Editar una indisponibilidad anulada |
| 422 | `staff.availability_window_invalid` | Horas incompletas, fin ≤ inicio o fechas inválidas |
| 422 | `staff.availability_range_too_large` | Ventana > 31 días (CA-16.20) |
| 422 | `staff.unavailability_schedule_invalid` | Fin ≤ inicio |
| 422 | `staff.unavailability_kind_required` | Tipo ausente |
| 422 | `staff.unavailability_description_required` / `not_allowed` | Reglas de `OTHER` |
| 422 | `staff.unavailability_reason_required` | Edición/anulación sin motivo |
| 422 | Validación estándar de FastAPI | Formato de fecha/hora, UUID, campos faltantes |

- Se añaden al mapeo local de `staff/presentation/errors.py`; `shared/presentation/problems.py` no se modifica.
- `openapi.json` se regenera con `just openapi`.

## 5. Persistencia y migración

### 5.1 Tabla `staff_unavailabilities`

| Columna | Tipo | Nulo | Nota |
|---|---|---|---|
| `id` | `uuid` | no | PK |
| `worker_id` | `uuid` | no | FK `staff_workers.id`, `ON DELETE RESTRICT` |
| `kind` | `varchar(10)` | no | `VACATION`/`LEAVE`/`REST`/`OTHER` |
| `description` | `text` | sí | Obligatoria solo con `OTHER` |
| `start_at` / `end_at` | `timestamptz` | no | UTC; `end_at > start_at` |
| `status` | `varchar(9)` | no | `ACTIVE`/`CANCELLED` |
| `created_at` / `updated_at` | `timestamptz` | no | Metadatos técnicos, no auditoría |

### 5.2 Tabla `staff_unavailabilities_audit` (append-only)

| Columna | Tipo | Nulo | Nota |
|---|---|---|---|
| `id` | `bigint identity` | no | PK |
| `unavailability_id` | `uuid` | no | FK `staff_unavailabilities.id`, `ON DELETE RESTRICT` |
| `action` | `varchar(9)` | no | `CREATED`/`UPDATED`/`CANCELLED` |
| `reason` | `text` | sí | Obligatorio en `UPDATED`/`CANCELLED` (máx. 500) |
| `actor_id` | `uuid` | no | Usuario de `identity`, sin FK |
| `occurred_at` | `timestamptz` | no | UTC |
| `previous_values` | `jsonb` | sí | Obligatorio en `UPDATED` |
| `new_values` | `jsonb` | sí | Obligatorio en `UPDATED` |

### 5.3 Constraints, índices y triggers

- CHECK de ventana: `end_at > start_at`.
- CHECK de tipo: `kind IN (...)`, `description` obligatoria/no vacía solo con `OTHER` y nula en las demás.
- CHECK de estado: `status IN ('ACTIVE','CANCELLED')`.
- CHECK de auditoría: acción válida; motivo obligatorio en `UPDATED`/`CANCELLED`; snapshots obligatorios solo en `UPDATED`.
- Índices:
  - `(worker_id, start_at)` — consultas por trabajador y por solape.
  - `(start_at, end_at)` — consulta de disponibilidad por ventana.
  - Índice parcial `WHERE status = 'ACTIVE'` si el plan lo justifica; mínimo, el de `(start_at, end_at)`.
  - `(unavailability_id, occurred_at)` en auditoría.
- Triggers:
  - `staff_unavailabilities_audit_append_only` (`BEFORE UPDATE OR DELETE`): rechaza toda modificación.
  - `staff_unavailabilities_no_delete` (`BEFORE DELETE`): rechaza el borrado físico.
  - `staff_unavailabilities_immutable_keys` (`BEFORE UPDATE`): rechaza cambiar `worker_id` y reactivar una `CANCELLED`.
- **No** hay restricción de exclusión: las indisponibilidades solapadas entre sí están permitidas (son informativas).
- No hay `UNIQUE` por trabajador/fecha: se admiten varios intervalos por día (Q2).

### 5.4 Migración (BLOQUEADA hasta confirmación humana)

- Una sola migración con las dos tablas, constraints, índices y triggers.
- `down_revision = "8df99a56ff18"` (head de HU17 según `docs/sdd/COORDINACION.md` §5).
- Verificado en `docs/sdd/COORDINACION.md:47`: el head esperado es `8df99a56ff18`; se re-confirmará con `uv run alembic heads` antes de crear la migración.
- **No se crea ahora.** Antes de crearla:
  1. `git fetch origin developer-b` y unir `developer-b` en la rama.
  2. `uv run alembic heads` debe devolver **un solo head**; si cambió, ajustar `down_revision` o hacer `alembic merge` (nunca editar una migración ya unida).
  3. Avisar al humano y esperar confirmación (regla del repo).
- `downgrade`: elimina triggers, funciones, índices y tablas.
- Test de integración: `upgrade head` sobre base vacía y `downgrade` de la migración, verificando que no quedan tablas ni triggers.

### 5.5 Concurrencia y auditoría

- Edición/anulación usan `get_for_update` para evitar actualizaciones perdidas.
- No hay validación de solape en la base; el alta no compite con la exclusión de asignaciones (no la consulta ni la modifica).
- La indisponibilidad y su auditoría se escriben en la misma transacción; si falla la auditoría, no queda el cambio.
- La consulta de disponibilidad no abre escritura ni auditoría.

### 5.6 Listas de `TRUNCATE` en integración (obligatorio)

Al añadir la tabla, actualizar **todas** las listas de `TRUNCATE` de `tests/integration/**` que ya limpian `staff_assignment_audit`/`staff_assignments`/`staff_workers`, incluyendo `staff_unavailabilities_audit, staff_unavailabilities` (por la FK a `staff_workers`). Ver `docs/sdd/COORDINACION.md:33`. Archivos afectados al redactar este plan:

- `tests/integration/staff/test_worker_repository.py`
- `tests/integration/staff/test_worker_constraints.py`
- `tests/integration/staff/test_worker_concurrency.py`
- `tests/integration/staff/test_worker_audit_append_only.py`
- `tests/integration/staff/test_assignment_repository.py`
- `tests/integration/staff/test_assignment_constraints.py`
- `tests/integration/staff/test_assignment_concurrency.py`
- `tests/integration/staff/test_assignment_audit_append_only.py`

Si un test nuevo trunca solo sus tablas, incluir también `staff_workers` y las tablas de asignaciones.

## 6. Reglas de negocio aplicadas

| Regla | Cómo se cumple |
|---|---|
| R-DIS-1 | `GetStaffAvailability` no tiene `save`/`release`; test de solo lectura. |
| R-DIS-2 (RN11, R-STF-4) | `list_active` filtra `status = ACTIVE`; la reactivación vuelve a incluir al trabajador. |
| R-DIS-3 | Un `state` por trabajador; detalles de ambos conflictos. |
| R-DIS-4 (R-ASG-3/4/12) | Reutiliza `list_active_overlaps`; filtra `CANCELLED` solo en lectura; `FINISHED` cuenta; sin reimplementar el SQL. |
| R-DIS-5 | Indisponibilidad informativa; no bloquea HU17; no genera pago. |
| R-DIS-6 | No se registra asistencia. |
| R-DIS-7 (R-COT-1) | VO Lima→UTC, semiabierto `[inicio, fin)`. |
| R-DIS-8 (R-STF-5/16, R-ASG-14) | Permiso `staff:availability` solo para administrador; `staff:manage`/`staff_roster:read` no abren nada. |
| R-DIS-9 (Q9) | Respuesta limitada a nombre, función, estado y conflicto (código/fecha/horario/función); test de claves prohibidas. |
| R-DIS-10 | No se borra ni archiva por fecha; se conserva al desactivar. |

## 7. Estrategia de tests

### 7.1 Unitarios (sin base de datos)

- **Dominio**:
  - `test_unavailability.py`: alta, `update`, `cancel`, inmutabilidad de `worker_id`, `OTHER`, `end > start`, sin `delete`, snapshots.
  - `test_availability_query.py`: día completo, horas, cruce de medianoche, ventana > 31 días, horas incompletas, semiabierto.
- **Aplicación con fakes**:
  - `test_availability_use_case.py`: estado `FREE/BUSY/UNAVAILABLE`, precedencia Q5, filtros función/estado, trabajador inactivo excluido, conflicto cancelado descartado sin escribir, cache de evento, lista vacía.
  - `test_unavailability_use_cases.py`: alta (trabajador inexistente/inactivo, tipo, descripción, horario), edición (motivo, no-op, anulada), anulación (idempotencia), listado.
  - Espía sobre `AssignmentRepository` que verifica que `release` **no** se invoca y que `list_active_overlaps` sí (CA-16.15/16.16).
  - `test_assignment_conflict_lookup.py` (adaptador nuevo, sesión/fake): la consulta es **un único** `WHERE id IN (...)` sobre `StaffAssignmentRow`, devuelve `worker_function`/`function_description` y `None` para ids ausentes; asserta que **no** se usa `AssignmentView` (que trae pago) y que el adaptador **no** añade ni reemplaza el criterio de solape (sin predicados de `start_at`/`end_at` propios; los ids proceden de `list_active_overlaps`).
- **API con fakes** (`test_availability_api.py`, `test_availability_api_roles.py`):
  - 401/403 por ruta y por rol.
  - 404/409/422.
  - Respuesta sin claves prohibidas.
  - No `DELETE` (405).
  - `operationId` y rutas en OpenAPI.
- **Router/colisión** (`test_availability_router_order.py`): cada ruta nueva no devuelve 422; `GET /v1/staff/availability` se enruta a disponibilidad y no a `staff_get`.

### 7.2 Integración (PostgreSQL real + Alembic)

- `test_unavailability_repository.py`: guardar/leer/listar, estados, auditoría, edición/anulación.
- `test_unavailability_constraints.py`: CHECKs, FK, índices, triggers de no borrado e inmutabilidad.
- `test_unavailability_audit_append_only.py`: trigger rechaza `UPDATE`/`DELETE`; auditoría en la misma transacción.
- `test_availability_equivalence.py` (CA-16.21):
  1. Sembrar un trabajador y asignaciones que ocupen con eventos `SCHEDULED`, `CONFIRMED`, `IN_PROGRESS`, `FINISHED` y `CANCELLED`.
  2. Para varias ventanas, calcular el conjunto `BUSY` con `GetStaffAvailability`.
  3. Por cada asignación existente, intentar `RegisterAssignment` de una asignación equivalente sobre un **evento candidato `SCHEDULED`** que se solape con esa ventana (el evento candidato debe ser asignable para aislar el solape). HU17 responderá `409 staff.assignment_overlap` si y solo si HU16 marcó `BUSY`; para el evento `CANCELLED`, ambos deben permitir el alta (sin 409 de solape). Repetir con un trabajador limpio o anulando la candidata entre casos.
  4. Verificar de forma explícita que HU16 no cambia `occupies` ni crea/edita/anula asignaciones (snapshot antes/después).
- `test_availability_read_only.py`: consulta repetida, `occupies` sin cambios, sin filas nuevas de auditoría, excluye cancelados no liberados y cuenta finalizados.

### 7.3 Arquitectura

- `just arch` en verde: `staff` no importa capas internas ni tablas de `commercial`; usa `commercial.public_api` e `identity.public_api`.
- Caso nuevo en `tests/architecture/test_import_rules.py` si el linter necesita declarar el nuevo router.
- `just check` completo.

### 7.4 Mapeo CA-16.x → tests

| CA | Test(s) |
|---|---|
| CA-16.1 | `unit/staff/test_unavailability_use_cases.py::test_ca16_1_alta_auditada`; `unit/staff/test_availability_api.py::test_ca16_1_post_201`; `integration/staff/test_unavailability_repository.py::test_ca16_1_guarda_y_lee` |
| CA-16.2 | `unit/staff/test_unavailability_use_cases.py::test_ca16_2_validaciones`; `unit/staff/test_availability_api.py::test_ca16_2_404_409_422` |
| CA-16.3 | `unit/staff/test_availability_use_case.py::test_ca16_3_estado_por_intervalo`; `integration/staff/test_availability_read_only.py::test_ca16_3_tiempo_real` |
| CA-16.4 | `unit/staff/test_availability_use_case.py::test_ca16_4_filtro_funcion`; `unit/staff/test_availability_api.py::test_ca16_4_query_function` |
| CA-16.5 | `unit/staff/test_availability_use_case.py::test_ca16_5_inactivo_excluido`; `integration/staff/test_availability_read_only.py::test_ca16_5` |
| CA-16.6 | `integration/staff/test_availability_read_only.py::test_ca16_6_reactivacion_conserva_historial` |
| CA-16.7 | `unit/staff/test_availability_use_case.py::test_ca16_7_usa_list_active_overlaps`; `integration/staff/test_availability_equivalence.py::test_ca16_7_finalizado_ocupa` |
| CA-16.8 | `unit/staff/test_availability_api.py::test_ca16_8_detalle_conflicto_sin_datos_sensibles` |
| CA-16.9 | `unit/staff/test_availability_use_case.py::test_ca16_9_no_disponible_con_motivo`; `unit/staff/test_availability_api.py::test_ca16_9` |
| CA-16.10 | `unit/staff/test_availability_use_case.py::test_ca16_10_precedencia_y_ambos_detalles` |
| CA-16.11 | `unit/staff/test_availability_use_case.py::test_ca16_11_filtros_combinados_vacio` |
| CA-16.12 | `unit/staff/test_availability_use_case.py::test_ca16_12_libre` |
| CA-16.13 | `unit/staff/test_availability_use_case.py::test_ca16_13_indisponibilidad_fuera_de_ventana`; `integration/staff/test_unavailability_repository.py::test_ca16_13_semiabierto` |
| CA-16.14 | `unit/staff/test_unavailability.py::test_ca16_14_cruce_medianoche`; `integration/staff/test_unavailability_constraints.py::test_ca16_14_contiguos_no_solapan` |
| CA-16.15 | `unit/staff/test_availability_use_case.py::test_ca16_15_cancelado_no_ocupa_sin_escribir`; `integration/staff/test_availability_read_only.py::test_ca16_15_sin_release` |
| CA-16.16 | `unit/staff/test_availability_use_case.py::test_ca16_16_idempotente_sin_escritura`; `integration/staff/test_availability_read_only.py::test_ca16_16` |
| CA-16.17 | `unit/staff/test_availability_api_roles.py::test_ca16_17_401_403_matriz` |
| CA-16.18 | `unit/staff/test_unavailability_use_cases.py::test_ca16_18_edita_y_anula_con_motivo`; `integration/staff/test_unavailability_audit_append_only.py::test_ca16_18_sin_borrado` |
| CA-16.19 | `integration/staff/test_availability_read_only.py::test_ca16_19_refleja_cambios` |
| CA-16.20 | `unit/staff/test_availability_query.py::test_ca16_20_max_31_dias`; `unit/staff/test_availability_api.py::test_ca16_20_422` |
| CA-16.21 | `integration/staff/test_availability_equivalence.py::test_ca16_21_equivalencia_hu16_hu17` |

## 8. Riesgos y ADRs

- **Colisión de router (alto)**: `/v1/staff/availability` y `/v1/staff/unavailability` caen en `/v1/staff/{worker_id}` si se registran después. Mitigación: orden en `main.py`, regla permanente y test por ruta + OpenAPI.
- **Reutilización del criterio de HU17 (alto valor)**: se usa `list_active_overlaps`; el filtro de `CANCELLED` es de solo lectura y no llama a `release_cancelled`. Riesgo de divergencia si HU17 cambia el criterio: la prueba CA-16.21 lo detecta. No se duplica SQL.
- **N+1 en la consulta (medio)**: `list_active_overlaps` por trabajador. Volumen de decenas a pocos cientos y ventana ≤ 31 días; índice `(worker_id, start_at)`. Si el rendimiento no basta, evolucionar a una variante *bulk* en el mismo repositorio reutilizando el predicado (fuera de esta entrega).
- **Filtro de eventos cancelados no liberados (medio)**: se resuelve con `event_lookup` por solape y cache; no se escribe. Si el evento no existe, se omite el conflicto con warning.
- **Zona horaria y día completo (medio)**: VO con offset fijo `-05:00`, ventana semiabierta y máximo 31 días; tests de borde.
- **Privacidad (alto)**: la respuesta se construye con DTOs propios; test que prohíbe `pay`, `tariff`, `document`, `phone`. La consulta no reutiliza `AssignmentView` (que incluye pago).
- **Migración (alto)**: gate humano; `uv run alembic heads` con un solo head; no editar migraciones aplicadas; actualizar listas de `TRUNCATE`.
- **Permisos y orden de tareas (medio)**: el router importa `Permission.STAFF_AVAILABILITY`; si se implementan rutas antes de la tarea final de `permissions.py`, el módulo no importa. Ver §10 y §12.
- **Cruces de horario en asignaciones (alto, cubierto)**: HU16 no crea ni mueve asignaciones; solo lee `list_active_overlaps`. La restricción de exclusión de HU17 sigue siendo la única fuente de verdad y no se modifica.
- **Cotización, contrato, evento y precios congelados (ninguno)**: no se tocan transiciones de estado ni precios; solo se lee `EventInfo` (código, fecha, estado) por `commercial.public_api`.
- **Ledger, inventario, append-only y pagos (ninguno)**: no se escriben movimientos ni pagos; la indisponibilidad no genera egreso.
- **`reporting` / `assistant` (ninguno)**: no se añaden vistas ni funciones; no se expone disponibilidad a otros módulos y el agente de IA no gana acceso.
- **ADR**: **no se requiere**. No hay dependencias nuevas ni servicios; se reutiliza un puerto existente y se sigue el patrón de auditoría/triggers de HU17. Si el humano quiere registrar formalmente "reutilizar `list_active_overlaps` en lugar de un adaptador nuevo", sería un ADR informativo, no bloqueante.

## 9. Impacto en reporting y documentación

- **`reporting`**: sin cambios. No hay vista ni reporte de disponibilidad en esta entrega.
- **`assistant`**: sin cambios; no se exponen datos de disponibilidad a roles sin permiso.
- **`docs/DOMAIN.md`**:
  - §5: añadir reglas R-DIS-1..10 (o remitir al spec).
  - §9: añadir `staff:availability` a la matriz (solo administrador); aclarar que `staff:manage`, `staff:roster:read` y `staff:assign` no abren disponibilidad.
  - §11: registrar la decisión del 27/11/2026 (Q1–Q10).
- **`docs/architecture/ARCHITECTURE.md`**: añadir `staff_unavailabilities_audit` a las tablas append-only y la tabla de indisponibilidad al mapa del módulo `staff`.
- **Docstrings**: `composition.py`, `availability_router.py`, casos de uso, repositorio y VO.
- **`openapi.json`**: regenerar con `just openapi`.
- **`README.md` / `STACK.md` / `INSTALACION.md`**: sin dependencias nuevas; solo si se documenta el endpoint.

## 10. Orden de implementación (tareas)

El orden es domain → application → infrastructure (+ migración) → presentation → openapi → docs. `permissions.py` se toca en **dos momentos** (decisión: enabler temprano + verificación final): la constante se declara antes de presentación y el **cierre de permisos** queda como último trabajo relevante.

0. **Enabler de permisos** (`T-00`, antes de presentación): declarar `Permission.STAFF_AVAILABILITY` en `identity/domain/permissions.py` como dependencia de import del router (1 línea; `Role.ADMIN` lo hereda, los demás roles no cambian).
1. **Dominio** (`T-01`..`T-03`): enums, `Unavailability`, auditoría, `AvailabilityQuery` y schedule, con tests puros.
2. **Aplicación** (`T-04`..`T-08`): puertos (`UnavailabilityRepository`, `list_active` en `WorkerRepository`, **`AssignmentConflictLookup` nuevo en archivo propio**), casos de uso y errores, con fakes.
3. **Infraestructura** (`T-09`..`T-11`): ORM, mappers, repositorio SQLAlchemy y **adaptador `assignment_conflict_lookup`** (una consulta `WHERE id IN (...)` sobre `StaffAssignmentRow`, solo lectura, sin tocar HU17) + fábrica en `composition.py`; luego **migración** (`T-12`, gate humano) y tests de constraints/auditoría.
4. **Presentación** (`T-13`..`T-15`): esquemas, router, mapeo de errores, dependencia de permiso y registro en `main.py` **antes de `worker_router`**.
5. **Tests de contrato y colisión** (`T-16`..`T-17`): 401/403 por ruta, ausencia de datos sensibles, OpenAPI, CA-16.21.
6. **OpenAPI y arquitectura** (`T-18`): `just openapi`, `just arch`.
7. **Documentación** (`T-19`): `DOMAIN.md`, `ARCHITECTURE.md`, docstrings.
8. **Cierre de permisos (`T-20`, ÚLTIMA)**: **verificar**, no añadir la constante (ya está en T-00). Test de matriz (`ADMIN` sí; `EVENTS_MANAGER` y `PURCHASING_MANAGER` no), 403 por ruta y documentación de la matriz de permisos.

Paralelizable: T-01..T-03 entre sí; T-04..T-08 tras el dominio; T-19 con T-20. **T-00 va antes de presentación (T-13); T-20 no añade la constante, solo verifica.** **La migración (T-12) nunca va en paralelo.**

## 11. Supuestos del plan

1. **Rutas y operationId**: las de §4.2 (`/v1/staff/availability`, `/v1/staff/unavailability...`; `staff_availability_get`, `staff_unavailability_*`). Ajustables sin cambiar el diseño.
2. **Consulta por GET con query params**: no se usa POST de búsqueda; es una lectura y encaja con el resto de listados.
3. **Sin paginación**: lista plana para decenas a pocos cientos de trabajadores. Si el volumen crece, se añade paginación en otra entrega.
4. **Indisponibilidades solapadas permitidas**: son informativas; no hay restricción de exclusión.
5. **`worker_id` inmutable** en la indisponibilidad; para otro trabajador se registra otro intervalo.
6. **Anulada es terminal**: no se edita ni reactiva; se crea otra. Editar una `CANCELLED` → 409.
7. **Sin horas = día completo**; con una sola hora → 422. Rango máximo: 31 días corridos inclusive (`(to_date - from_date).days <= 30`).
8. **Tipo de indisponibilidad**: `VACATION`, `LEAVE`, `REST`, `OTHER`; etiquetas en español en la UI.
9. **Motivo**: máximo 500 caracteres; descripción `OTHER`: máximo 120.
10. **Función en el conflicto**: **Decidido (humano, 27/11/2026)**: la función del conflicto se obtiene con una lectura aparte de HU16 por `assignment_id` (`AssignmentConflictLookup`, archivos nuevos, solo lectura del ORM `StaffAssignmentRow`); `AssignmentOverlap` y el código de HU17 no se modifican.
11. **Evento huérfano**: si `event_lookup` no lo encuentra, se omite el conflicto con warning; no se falla la consulta.
12. **Estados internos** `FREE/BUSY/UNAVAILABLE`; la UI los traduce.

## 12. Pendientes de confirmación humana

1. **Migración**: confirmar el head vigente con `uv run alembic heads` (hoy `8df99a56ff18`, según `docs/sdd/COORDINACION.md` §5) y autorizar su creación.
2. **Función en el conflicto: decidido (27/11/2026)** — lectura aparte de HU16 por `assignment_id` (`AssignmentConflictLookup`, archivos nuevos); `AssignmentOverlap` y el código de HU17 no se modifican (ver §3.1 y §11.10).

**Decisión tomada (27/11/2026) — orden de `permissions.py`:** *enabler temprano + verificación final*. La constante `Permission.STAFF_AVAILABILITY` se declara en el primer commit de `identity` (T-00, dependencia de import del router; `Role.ADMIN` la hereda y los demás roles no cambian). El commit final de permisos (T-20) es el **cierre/verificación**: test de matriz (ADMIN sí; `EVENTS_MANAGER` y `PURCHASING_MANAGER` no), 403 por ruta y documentación; **no** añade la constante.
