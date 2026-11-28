# Tasks: Registrar asistencia e historial del personal

- **Feature**: 035-staff-attendance (HU18 / issue #19)
- **Spec**: ./spec.md · **Plan**: ./plan.md (aprobado con ajustes 28/11/2026)
- **Regla**: una tarea = un subagente = **un commit**, **sin push**. `[P]` = puede ir en paralelo (no comparte archivos ni commit con otra tarea paralela).

Formato: `- [ ] T-NN [capa] objetivo — archivos — CA/reglas — comando — commit`.

---

## T-00 · Permiso `staff:attendance` (identity)

- [x] **T-00 [identity] [P]** Añadir el permiso nuevo y probar la matriz de roles. **Mínimo: una sola línea** en el registro de permisos; no tocar otros permisos ni roles.
  - **Archivos**: `src/local_eventos/modules/identity/domain/permissions.py` (añadir `STAFF_ATTENDANCE = "staff:attendance"`; ADMIN lo hereda por `frozenset(Permission)`), `tests/unit/identity/test_user.py` (matriz: ADMIN tiene `STAFF_ATTENDANCE`; `EVENTS_MANAGER` y `PURCHASING_MANAGER` no).
  - **Cubre**: R-ATT-14, CA-18.9 (base del permiso).
  - **Depende de**: —
  - **Verificación**: `uv run pytest tests/unit/identity/test_user.py -q`
  - **Commit**: `feat(identity): T-00 agregar permiso staff:attendance`

## T-01 · Dominio de asistencia

- [x] **T-01 [domain] [P]** Implementar `AttendanceStatus`, el agregado `Attendance`, el VO `AttendanceAudit` y los errores de dominio.
  - **Archivos**: `src/local_eventos/modules/staff/domain/attendance.py`, `src/local_eventos/modules/staff/domain/attendance_audit.py`, `src/local_eventos/modules/staff/domain/attendance_errors.py`, `tests/unit/staff/test_attendance_domain.py`.
  - **Reglas**: solo `ATTENDED`/`NOT_ATTENDED`; `record` (primer registro, sin motivo); `correct` (motivo recortado 1..500, cambio de valor); `AttendanceAudit` coherente (`RECORDED` con `previous=None`/`reason=None`; `CORRECTED` con `previous!=new` y motivo no vacío). Errores `staff.attendance_status_invalid` y `staff.attendance_reason_required`.
  - **Cubre**: R-ATT-1/2/3/6/7/17/22; CA-18.1, 18.2, 18.11, 18.12, 18.16.
  - **Depende de**: —
  - **Verificación**: `uv run pytest tests/unit/staff/test_attendance_domain.py -q`
  - **Commit**: `feat(staff): T-01 modelo de dominio de asistencia`

## T-02 · Puertos y errores de aplicación

- [x] **T-02 [application]** Definir el puerto `AttendanceRepository`, sus DTOs de lectura y los errores de aplicación.
  - **Archivos**: `src/local_eventos/modules/staff/application/ports/attendance_repository.py` (Protocol, `AttendanceAssignmentView`, fila de historial, `lock_assignment`, `get`, `save`, `list_history`), `src/local_eventos/modules/staff/application/attendance_errors.py` (`AttendanceWorkerNotFoundError`, `AttendanceNotDueError`, `AttendanceAssignmentCancelledError`, `AttendanceDateRangeInvalidError`). Reutiliza `AssignmentNotFoundError` y `WorkerLookup` existentes.
  - **Reglas**: sin frameworks; el evento se resuelve por `commercial.public_api.event_lookup` (no se define `staff.event_not_found`).
  - **Cubre**: R-ATT-4/5/19/23 (contratos).
  - **Depende de**: T-01.
  - **Verificación**: `uv run mypy src/local_eventos/modules/staff/application -q`
  - **Commit**: `feat(staff): T-02 puerto y errores de aplicación de asistencia`

## T-03 · Caso de uso `UpdateAttendance`

- [x] **T-03 [application] [P]** Implementar el command de registro/corrección de asistencia.
  - **Archivos**: `src/local_eventos/modules/staff/application/use_cases/update_attendance.py`, `tests/unit/staff/test_attendance_update.py`. **No editar** `application/use_cases/__init__.py` (lo comparte con T-04).
  - **Comportamiento**: lock → 404; `CANCELLED` → 409 antes de ventana; `now < end_at` → 409 (`now == end_at` permitido); validar `status`; `event_lookup` **tolerante** (no resuelto → campos de evento `null`, sin 404); primer registro sin motivo; mismo estado idempotente sin auditoría; cambio exige motivo 1..500. El actor guardado se usa para la respuesta.
  - **Cubre**: R-ATT-4/5/6/7/17/22/23; CA-18.1, 18.2, 18.3, 18.4, 18.11, 18.12, 18.16, 18.17, **18.22 (evento huérfano PATCH)**.
  - **Depende de**: T-02.
  - **Verificación**: `uv run pytest tests/unit/staff/test_attendance_update.py -q`
  - **Commit**: `feat(staff): T-03 caso de uso registrar y corregir asistencia`

## T-04 · Caso de uso `GetAttendanceHistory`

- [x] **T-04 [application] [P]** Implementar la query del historial por trabajador.
  - **Archivos**: `src/local_eventos/modules/staff/application/use_cases/get_attendance_history.py`, `tests/unit/staff/test_attendance_history.py`. **No editar** `application/use_cases/__init__.py`.
  - **Comportamiento**: validar paginación y `from <= to`; 404 trabajador; `list_history` (ACTIVE y CANCELLED, una fila por asignación, orden `start_at DESC`, filtro `event_id` en SQL); resolver eventos **deduplicados y tolerantes** (`null` si no resuelve, sin 404); filtrar `event_date` en memoria (huérfanas excluidas con `from`/`to`, incluidas sin filtro de fecha o con `event_id`); `total` coherente tras filtro; paginar.
  - **Cubre**: R-ATT-3/9/10/11/12/13/16/18/21/23; CA-18.5, 18.6, 18.7, 18.8, 18.13, 18.14, 18.18, 18.20, 18.21, **18.22 (historial huérfano y `total`)**.
  - **Depende de**: T-02.
  - **Verificación**: `uv run pytest tests/unit/staff/test_attendance_history.py -q`
  - **Commit**: `feat(staff): T-04 caso de uso historial de asistencia`

## T-05 · Modelos ORM y mappers

- [x] **T-05 [infrastructure] [P]** Crear los modelos ORM de estado y auditoría, sus mappers y registrarlos en Alembic.
  - **Archivos**: `src/local_eventos/modules/staff/infrastructure/attendance_orm_models.py` (`staff_attendance`, `staff_attendance_audit` con CHECK, índice y triggers en la migración), `src/local_eventos/modules/staff/infrastructure/attendance_mappers.py`, `migrations/env.py` (importar `attendance_orm_models`). **No editar** `staff/infrastructure/orm_models.py`.
  - **Reglas**: PK por `assignment_id`; sin FK a `identity`/`commercial`.
  - **Cubre**: R-ATT-1/7/22 (persistencia).
  - **Depende de**: T-01.
  - **Verificación**: `uv run pytest tests/unit/staff/test_orm_mapping.py -q`
  - **Commit**: `feat(staff): T-05 modelos ORM y mappers de asistencia`

## T-06 · Repositorio de asistencia

- [x] **T-06 [infrastructure]** Implementar el adaptador SQLAlchemy (lock, lectura, escritura, historial).
  - **Archivos**: `src/local_eventos/modules/staff/infrastructure/attendance_repository.py`.
  - **Comportamiento**: `lock_assignment` con `SELECT ... FOR UPDATE`; `get` del estado vigente; `save` estado + auditoría en la misma transacción; `list_history` con `LEFT JOIN` a la asistencia y datos del trabajador.
  - **Cubre**: R-ATT-1/7/15/19/21.
  - **Depende de**: T-02, T-05.
  - **Verificación**: `uv run mypy src/local_eventos/modules/staff/infrastructure/attendance_repository.py -q`
  - **Commit**: `feat(staff): T-06 repositorio de asistencia`

## T-07 · Migración Alembic (ÚNICA que crea migración)

- [x] **T-07 [infra/migración]** Crear la migración de `staff_attendance` y `staff_attendance_audit` tras repetir la puerta de head único.
  - **Puerta obligatoria (repetir)**, parando y avisando si falla:
    ```bash
    git fetch origin
    git merge origin/developer-a
    uv run alembic heads   # debe imprimir UN único head == b959d55b8430
    ```
  - **Archivos**: `migrations/versions/<nueva>_staff_attendance.py` (`down_revision = "b959d55b8430"`; tablas, CHECKs, índice `(assignment_id, occurred_at)`, triggers `BEFORE DELETE` en estado y `BEFORE UPDATE OR DELETE` en auditoría; `downgrade` inverso), `tests/integration/staff/test_attendance_constraints.py`, `tests/integration/staff/test_attendance_audit_append_only.py`, `tests/integration/staff/test_attendance_migration.py`.
  - **Cubre**: R-ATT-7/22; CA-18.11 (CHECK del motivo a nivel DB).
  - **Depende de**: T-05, T-06.
  - **Verificación**: `uv run alembic heads` (un solo head nuevo encadenado) · `uv run pytest tests/integration/staff/test_attendance_constraints.py tests/integration/staff/test_attendance_audit_append_only.py tests/integration/staff/test_attendance_migration.py -q`
  - **Commit**: `chore(staff): T-07 migración de asistencia y auditoría`

## T-08 · Integración: repositorio y concurrencia

- [x] **T-08 [integration]** Probar el repositorio y el bloqueo pesimista contra PostgreSQL real.
  - **Archivos**: `tests/integration/staff/test_attendance_repository.py` (roundtrip estado/auditoría, activas y anuladas, pago en céntimos, trabajador inactivo, **evento huérfano devuelto sin descartarse**), `tests/integration/staff/test_attendance_concurrency.py` (dos correcciones simultáneas serializadas y auditadas).
  - **Cubre**: CA-18.6, 18.13, 18.19, 18.21, **18.22**; R-ATT-7/8.
  - **Depende de**: T-06, T-07.
  - **Verificación**: `uv run pytest tests/integration/staff/test_attendance_repository.py tests/integration/staff/test_attendance_concurrency.py -q` (requiere Docker)
  - **Commit**: `test(staff): T-08 integración de repositorio y concurrencia`

## T-09 · Composición y dependencias de presentación

- [x] **T-09 [composition/presentation]** Ensamblar casos de uso y definir DI, permisos y Problem Details.
  - **Archivos**: `src/local_eventos/modules/staff/attendance_composition.py`, `src/local_eventos/modules/staff/presentation/attendance_dependencies.py` (DI, permiso `staff:attendance` para PATCH y `staff:manage` para GET, `user_names`), `src/local_eventos/modules/staff/presentation/attendance_errors.py`.
  - **Reglas**: no editar `composition.py`; 403 para roles sin permiso; errores con `code` estable.
  - **Cubre**: R-ATT-14; CA-18.9.
  - **Depende de**: T-03, T-04, T-06.
  - **Verificación**: `uv run mypy src/local_eventos/modules/staff/presentation/attendance_dependencies.py -q`
  - **Commit**: `feat(staff): T-09 composición y dependencias de asistencia`

## T-10 · Esquemas, router y orden de inclusión

- [x] **T-10 [presentation]** Crear esquemas Pydantic y router; incluirlo en `main.py` antes de availability y worker.
  - **Archivos**: `src/local_eventos/modules/staff/presentation/attendance_schemas.py` (`AttendanceUpdate`, `AttendanceOut` con `event_code: str | null`, `event_date: date | null`, `event_status: EventStatus | null`, `AttendanceHistoryPage`), `src/local_eventos/modules/staff/presentation/attendance_router.py` (`PATCH /v1/staff/assignments/{assignment_id}/attendance` = `staff_attendance_update`; `GET /v1/staff/workers/{worker_id}/attendance` = `staff_attendance_history`; `from`/`to` con alias), `src/local_eventos/main.py` (registrar router y errores; orden: assignment → **attendance** → availability → worker), `tests/unit/staff/test_attendance_schemas.py` (anulabilidad de campos de evento y alias de query).
  - **Cubre**: R-ATT-23, CA-18.20, 18.22.
  - **Depende de**: T-09.
  - **Verificación**: `uv run pytest tests/unit/staff/test_attendance_schemas.py -q`
  - **Commit**: `feat(staff): T-10 esquemas y rutas de asistencia`

## T-11 · Tests de API y orden de rutas

- [x] **T-11 [tests] [P]** Probar las dos rutas y que el enrutado no colisiona.
  - **Archivos**: `tests/unit/staff/test_attendance_api.py` (PATCH 200/404/409/422; GET 200/404/422; forma de esquemas; **evento huérfano serializado en `null` sin 404**), `tests/unit/staff/test_attendance_router_order.py` (**un test por ruta** sobre `create_app()`, verifica `operationId` enrutado y ausencia de `422` de path param).
  - **Cubre**: CA-18.1/2/3/4/5/7/8/15/16/20/22.
  - **Depende de**: T-10.
  - **Verificación**: `uv run pytest tests/unit/staff/test_attendance_api.py tests/unit/staff/test_attendance_router_order.py -q`
  - **Commit**: `test(staff): T-11 API y orden de rutas de asistencia`

## T-12 · Matriz de permisos por ruta

- [x] **T-12 [tests] [P]** Verificar autorización por rol en ambos endpoints.
  - **Archivos**: `tests/unit/staff/test_attendance_api_roles.py` (ADMIN 200; `EVENTS_MANAGER` y `PURCHASING_MANAGER` → 403 `auth.forbidden`; sin sesión → 401; usuarios con solo `staff_roster:read` o `staff:assign` → 403; `staff_roster:read` no abre ninguna ruta).
  - **Cubre**: R-ATT-14; CA-18.9, 18.10.
  - **Depende de**: T-10.
  - **Verificación**: `uv run pytest tests/unit/staff/test_attendance_api_roles.py -q`
  - **Commit**: `test(staff): T-12 matriz de permisos de asistencia`

## T-13 · OpenAPI y documentación

- [x] **T-13 [openapi/docs]** Regenerar el contrato y documentar la feature.
  - **Archivos**: `openapi.json` (regenerado), `docs/DOMAIN.md` (§5.4 Asistencia HU18 y §9 permiso `staff:attendance`), `docs/sdd/COORDINACION.md` (estado HU18, head de Alembic).
  - **Cubre**: R-ATT-14/23; contrato estable.
  - **Depende de**: T-10.
  - **Verificación**: `just openapi` y revisar `staff_attendance_update`/`staff_attendance_history` en `openapi.json`; `git diff --exit-code openapi.json` tras comitear no aplica (el diff es el commit).
  - **Commit**: `docs(staff): T-13 OpenAPI y documentación de asistencia`

## T-14 · Verificación final

- [ ] **T-14 [verificación]** Comprobar que toda la feature queda en verde.
  - **Archivos**: sin cambios de código (solo correcciones puntuales si la verificación falla).
  - **Comandos**:
    ```bash
    just check
    just arch
    uv run alembic heads
    uv run pytest -m integration
    ```
  - **Regla Docker**: si Docker no responde, la verificación de integración queda **bloqueada** (no "hecha"); se reporta y no se cierra la tarea.
  - **Cubre**: CA-18.1..CA-18.22 (suite completa).
  - **Depende de**: todas (T-00..T-13).
  - **Verificación**: los cuatro comandos en verde / integración bloqueada por Docker reportada.
  - **Commit**: `chore(staff): T-14 verificación final de asistencia`

---

## Dependencias y paralelismo

```
T-00 ───────────────┐
T-01 ──┬── T-02 ──┬── T-03 ──┐
       │          ├── T-04 ──┤
       └── T-05 ──┴── T-06 ──┴── T-09 ── T-10 ──┬── T-11 ──┐
                    T-07 (migración) ── T-08 ───┘           ├── T-14
                                            └── T-12 ──────┤
                                            T-13 ──────────┘
```

- **Paralelizables**: T-00 ∥ T-01; T-03 ∥ T-04 (sin tocar `__init__.py`); T-05 ∥ T-03/T-04; T-11 ∥ T-12; T-13 ∥ T-11/T-12.
- **T-07 es la única que crea migración** y repite la puerta de head.
- Un commit por tarea, **sin push**.

## Mapeo CA-18.x → tareas

| CA | Tareas |
|---|---|
| 18.1 | T-01, T-03, T-11, T-08 |
| 18.2 | T-01, T-03, T-11, T-08 |
| 18.3 | T-03, T-11 |
| 18.4 | T-03, T-11 |
| 18.5 | T-04, T-11 |
| 18.6 | T-04, T-08 |
| 18.7 | T-04, T-11 |
| 18.8 | T-04, T-11 |
| 18.9 | T-00, T-09, T-12 |
| 18.10 | T-12 |
| 18.11 | T-01, T-03, T-07 |
| 18.12 | T-01, T-03 |
| 18.13 | T-04, T-08 |
| 18.14 | T-04 |
| 18.15 | T-03, T-04, T-11 |
| 18.16 | T-01, T-03, T-11 |
| 18.17 | T-03 |
| 18.18 | T-04 |
| 18.19 | T-08 |
| 18.20 | T-04, T-10 |
| 18.21 | T-04, T-08 |
| 18.22 | T-03, T-04, T-08, T-11 |
