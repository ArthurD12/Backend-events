# Tasks: Consultar la disponibilidad del personal y registrar indisponibilidades

- **Spec**: `docs/sdd/features/034-staff-availability/spec.md`
- **Plan**: `docs/sdd/features/034-staff-availability/plan.md`
- **HU**: HU16 (#17) · **Feature**: 034-staff-availability
- **Estado**: pendiente de aprobación humana

Formato: `- [ ] T-NN [capa] descripción — archivos — hecho cuando …`
Una tarea = un subagente = un commit. `[P]` solo si no comparte archivos con otra tarea abierta.

## Reglas globales para todos los subagentes

1. **Prohibido `git push`** y prohibido abrir PR. Solo commit local.
2. **Sin dependencias nuevas y sin ADR** (plan §8). Si una tarea cree necesitar una, **detenerse y avisar** al orquestador.
3. **No tocar HU17**: ni `AssignmentOverlap`, ni `AssignmentView`, ni el SQL de `list_active_overlaps`, ni el código/tipos/contratos de asignaciones. La lectura por `assignment_id` va en archivos **nuevos** de HU16 (`AssignmentConflictLookup`).
4. **No editar migraciones ya aplicadas** ni crear dos heads. Nada de `DELETE` físico ni `UPDATE/DELETE` sobre auditoría.
5. Todo lo nuevo vive en `staff`; `staff.public_api` **no cambia**; no se toca `commercial` (solo `commercial.public_api`), `reporting`, `assistant`, ledger, inventario ni precios.
6. Fechas: dominio en UTC aware; conversión `America/Lima` (offset fijo `-05:00`) solo en los VO de entrada. Dinero no aplica.
7. Verificación estándar de una tarea de dominio/aplicación: `uv run pytest <tests> -q` + `uv run mypy src/local_eventos/modules/staff` + `uv run ruff check src tests`. De infraestructura/presentación, además, sus tests.

## Tareas

- [ ] **T-00** `[gate/identity]` Sincronizar y habilitar el permiso (enabler mínimo). Ejecutar `git fetch origin` y `git merge origin/developer-a`; **si hay cualquier conflicto, abortar el merge, parar y avisar** (no resolver a mano). Añadir **una única línea** `STAFF_AVAILABILITY = "staff:availability"` dentro de `class Permission`; nada más (ni roles, ni tests nuevos, ni imports). — `src/local_eventos/modules/identity/domain/permissions.py` — `uv run python -c "from local_eventos.modules.identity.domain.permissions import Permission, Role; assert Permission.STAFF_AVAILABILITY in Role.ADMIN and Permission.STAFF_AVAILABILITY not in Role.EVENTS_MANAGER and Permission.STAFF_AVAILABILITY not in Role.PURCHASING_MANAGER"` y `uv run pytest tests/unit/identity -q` verdes. **Commit 1 de la feature; bloquea a T-15/T-16/T-20.**

- [ ] **T-01** `[domain]` Enums de disponibilidad: `UnavailabilityKind {VACATION, LEAVE, REST, OTHER}`, `UnavailabilityStatus {ACTIVE, CANCELLED}`, `AvailabilityState {FREE, BUSY, UNAVAILABLE}`. Sin imports de FastAPI/SQLAlchemy/Pydantic. — `src/local_eventos/modules/staff/domain/enums.py`, `tests/unit/staff/test_unavailability_enums.py` — `uv run pytest tests/unit/staff/test_unavailability_enums.py -q` verde; valores y `StrEnum` estables. `[P]` con T-02/T-03.

- [ ] **T-02** `[domain]` Agregado `Unavailability` (`register`, `update` con retorno de cambio real, `cancel` idempotente, `snapshot`, `worker_id` inmutable, sin `delete`/reactivación; `OTHER` exige `description` no vacía ≤120 y las demás la prohíben; `start_at < end_at`) y `UnavailabilityAudit`/`UnavailabilitySnapshot` (`CREATED` sin motivo/snapshots; `UPDATED` y `CANCELLED` con motivo; `previous_values`/`new_values` solo en `UPDATED`; `reason` ≤500; actor y `occurred_at` UTC). — `src/local_eventos/modules/staff/domain/unavailability.py`, `src/local_eventos/modules/staff/domain/unavailability_audit.py`, `tests/unit/staff/test_unavailability.py` — `uv run pytest tests/unit/staff/test_unavailability.py -q` verde; cubre CA-16.1, CA-16.13, CA-16.14 (agregado) y CA-16.18 (dominio). `[P]` con T-01/T-03.

- [ ] **T-03** `[domain]` Value objects de ventana: `AvailabilityQuery` (`from_date`/`to_date` obligatorias, horas opcionales, día completo, cruce de medianoche, semiabierto, máximo 31 días corridos, una sola hora → inválido, `state` opcional) y `UnavailabilitySchedule` (fecha + horas Lima→UTC con reglas R-ASG-4). Extraer el helper de conversión Lima→UTC a `domain/lima.py` y hacer que `assignment_schedule.py` lo reutilice **sin cambiar comportamiento**. — `src/local_eventos/modules/staff/domain/availability_query.py`, `src/local_eventos/modules/staff/domain/unavailability_schedule.py`, `src/local_eventos/modules/staff/domain/lima.py`, `src/local_eventos/modules/staff/domain/assignment_schedule.py`, `tests/unit/staff/test_availability_query.py` — `uv run pytest tests/unit/staff/test_availability_query.py tests/unit/staff/test_assignment_schedule.py -q` verdes (regresión HU17); cubre CA-16.14, CA-16.20. `[P]` con T-01/T-02.

- [ ] **T-04** `[application]` Puertos y errores: `UnavailabilityRepository` (`save` entidad+auditoría misma transacción, `get`, `get_for_update`, `list_active_overlapping(start,end,worker_ids)`, `list_by_worker`), ampliar `WorkerRepository` con `list_active(function) -> list[WorkerRef]`, crear `AssignmentConflictLookup` (`by_ids(ids) -> dict[UUID, WorkerFunction | None]`, solo lectura) y errores de disponibilidad con `code` estable (`staff.availability_window_invalid`, `staff.availability_range_too_large`, `staff.unavailability_not_found`, `staff.unavailability_cancelled`, `staff.unavailability_schedule_invalid`, `staff.unavailability_kind_required`, `staff.unavailability_description_required/not_allowed`, `staff.unavailability_reason_required`). Sin implementaciones. — `src/local_eventos/modules/staff/application/ports/unavailability_repository.py`, `src/local_eventos/modules/staff/application/ports/worker_repository.py`, `src/local_eventos/modules/staff/application/ports/assignment_conflict_lookup.py`, `src/local_eventos/modules/staff/application/errors.py` — `uv run mypy src/local_eventos/modules/staff` verde y `uv run python -c "import local_eventos.modules.staff.application.ports.assignment_conflict_lookup"`; ningún `code` duplicado. Depende de T-01..T-03.

- [ ] **T-05** `[application]` Casos de uso de alta y listado: `RegisterUnavailability` (trabajador inexistente → 404, inactivo → 409 CA-16.2, ventana válida, `kind`/`description`, auditoría `CREATED`) y `ListUnavailability` (filtros trabajador/ventana, incluye `CANCELLED`, solo lectura). — `src/local_eventos/modules/staff/application/use_cases/register_unavailability.py`, `src/local_eventos/modules/staff/application/use_cases/list_unavailability.py`, `tests/unit/staff/test_unavailability_use_cases.py` — `uv run pytest tests/unit/staff/test_unavailability_use_cases.py -q` verde con fakes; cubre CA-16.1 y CA-16.2. Depende de T-04. No `[P]` (comparte el archivo de tests con T-06).

- [ ] **T-06** `[application]` Casos de uso de edición y anulación: `UpdateUnavailability` (`get_for_update`, `CANCELLED` → 409, motivo obligatorio, no-op sin auditoría, `UPDATED` con snapshots) y `CancelUnavailability` (idempotente si ya anulada, motivo obligatorio, `CANCELLED` sin borrado). — `src/local_eventos/modules/staff/application/use_cases/update_unavailability.py`, `src/local_eventos/modules/staff/application/use_cases/cancel_unavailability.py`, `tests/unit/staff/test_unavailability_use_cases.py` — `uv run pytest tests/unit/staff/test_unavailability_use_cases.py -q` verde; cubre CA-16.18 (aplicación). Depende de T-05.

- [ ] **T-07** `[infra]` ORM y mapeo: `StaffUnavailabilityRow` y `StaffUnavailabilityAuditRow` (tablas `staff_unavailabilities` y `staff_unavailabilities_audit`, columnas del plan §5.1–5.2) y mapeo explícito entidad ⇄ fila ⇄ snapshot JSONB. No crear tablas aquí. — `src/local_eventos/modules/staff/infrastructure/orm_models.py`, `src/local_eventos/modules/staff/infrastructure/mappers.py`, `tests/unit/staff/test_orm_mapping.py` — `uv run pytest tests/unit/staff/test_orm_mapping.py -q` verde sin base de datos. Depende de T-02. No `[P]` (comparte `test_orm_mapping.py` con tareas previas).

- [ ] **T-08** `[infra]` Adaptadores: `SqlAlchemyUnavailabilityRepository` (save transaccional entidad+auditoría, `get`/`get_for_update`, solape semiabierto solo `ACTIVE`, listado), `SqlAlchemyWorkerRepository.list_active` (`status=ACTIVE`, filtro función), `SqlAlchemyAssignmentConflictLookup.by_ids` (**una** consulta `WHERE id IN (...)` sobre `StaffAssignmentRow`, solo lectura de `worker_function`/`function_description`, ids ausentes → `None`, **sin** predicados de solape) y fábricas en `composition.py`. No modificar `AssignmentOverlap` ni el repositorio de asignaciones. — `src/local_eventos/modules/staff/infrastructure/unavailability_repository.py`, `src/local_eventos/modules/staff/infrastructure/worker_repository.py`, `src/local_eventos/modules/staff/infrastructure/assignment_conflict_lookup.py`, `src/local_eventos/modules/staff/composition.py` — `uv run pytest tests/unit/staff/test_assignment_conflict_lookup.py -q` verde con sesión fake (1 sola consulta, sin `AssignmentView`, sin pago); `uv run mypy` verde. Depende de T-04 y T-07.

- [ ] **T-09** `[infra/migración]` **Gate de migración — no paralelizar.** Antes de crearla: `git fetch origin` + `git merge origin/developer-a` **sin conflictos** y `uv run alembic heads` con **un único head `8df99a56ff18`**. Si hay conflictos o ≠1 head: **parar y avisar** (no crear, no merge de heads, no editar migraciones). Si se cumple: una sola migración con las dos tablas, CHECKs (ventana, tipo/descripción, estado, auditoría), FKs (`worker_id → staff_workers ON DELETE RESTRICT`, auditoría → indisponibilidad), índices (`(worker_id,start_at)`, `(start_at,end_at)`, `(unavailability_id,occurred_at)`) y triggers (`append_only`, `no_delete`, `immutable_keys`); `down_revision="8df99a56ff18"`. En el **mismo commit**, añadir `staff_unavailabilities_audit, staff_unavailabilities` a **todas** las listas de `TRUNCATE` de integración de staff (workers, constraints, concurrency, audit, assignments repo/constraints/concurrency/audit) y a los tests nuevos que limpien esas tablas. — `migrations/versions/<rev>_crear_tablas_de_disponibilidad.py`, `tests/integration/staff/test_worker_repository.py`, `tests/integration/staff/test_worker_constraints.py`, `tests/integration/staff/test_worker_concurrency.py`, `tests/integration/staff/test_worker_audit_append_only.py`, `tests/integration/staff/test_assignment_repository.py`, `tests/integration/staff/test_assignment_constraints.py`, `tests/integration/staff/test_assignment_concurrency.py`, `tests/integration/staff/test_assignment_audit_append_only.py` — `uv run alembic heads` = 1 head; `uv run alembic upgrade head` y `uv run alembic downgrade 8df99a56ff18` sin residuos; `uv run pytest tests/integration/staff -q -k "worker or assignment"` verde. Ninguna otra tarea puede tocar migraciones.

- [ ] **T-10** `[test-first]` **CA-16.21 antes de la consulta.** Escribir `test_availability_equivalence.py`: sembrar trabajador y asignaciones con eventos `SCHEDULED`/`CONFIRMED`/`IN_PROGRESS`/`FINISHED`/`CANCELLED`; comparar `BUSY` de `GetStaffAvailability` contra el 409 de `RegisterAssignment` sobre un evento candidato `SCHEDULED`; el evento `CANCELLED` no bloquea en ninguno; verificar que HU16 no cambia `occupies` ni escribe filas (snapshot antes/después). Como `GetStaffAvailability` aún no existe, el test se deja **explícitamente en `xfail(strict=False)`** (o `skip`) con import perezoso y `reason="pendiente T-11: GetStaffAvailability"`. — `tests/integration/staff/test_availability_equivalence.py` — el archivo se colecta sin `ImportError`; `uv run pytest tests/integration/staff/test_availability_equivalence.py -q` reporta `xfail`/`skip` (0 errores de colección). Depende de T-09 y T-08.

- [ ] **T-11** `[application]` `GetStaffAvailability` (solo lectura): validar ventana; `list_active(function)`; `list_active_overlapping` en una consulta; por trabajador `list_active_overlaps` (puerto HU17), resolver `event_lookup` con caché por `event_id`, descartar `CANCELLED` **sin** llamar a `release_cancelled`, evento huérfano → omitir con warning; obtener función vía `AssignmentConflictLookup.by_ids`; precedencia `UNAVAILABLE > BUSY > FREE`; filtros `state`/`function`; lista plana con ambos detalles. **Activar CA-16.21**: quitar `xfail`/`skip` de T-10. Fábrica en `composition.py`. — `src/local_eventos/modules/staff/application/use_cases/get_staff_availability.py`, `src/local_eventos/modules/staff/composition.py`, `tests/unit/staff/test_availability_use_case.py`, `tests/integration/staff/test_availability_equivalence.py` — `uv run pytest tests/unit/staff/test_availability_use_case.py tests/integration/staff/test_availability_equivalence.py -q` verde; espía confirma que `release` **no** se invoca y que `list_active_overlaps` sí; cubre CA-16.3, 16.4, 16.5, 16.7, 16.8, 16.9, 16.10, 16.11, 16.12, 16.15, 16.16, 16.21.

- [ ] **T-12** `[test/integration]` Repositorio y constraints con PostgreSQL real: guardar/leer/listar, solape semiabierto (CA-16.13), contiguos no solapan y cruce de medianoche (CA-16.14), CHECKs, FK, triggers de inmutabilidad/no borrado, auditoría en la misma transacción y rollback. — `tests/integration/staff/test_unavailability_repository.py`, `tests/integration/staff/test_unavailability_constraints.py` — `uv run pytest tests/integration/staff/test_unavailability_repository.py tests/integration/staff/test_unavailability_constraints.py -q` verde (Testcontainers; requiere T-09). `[P]` con T-13.

- [ ] **T-13** `[test/integration]` Auditoría append-only y solo lectura: `UPDATE`/`DELETE` sobre auditoría rechazados, anulación sin borrado (CA-16.18), consulta repetida idéntica, `occupies` sin cambios, sin filas de auditoría nuevas, excluye cancelados no liberados y cuenta finalizados (CA-16.3/16.5/16.6/16.15/16.16/16.19). — `tests/integration/staff/test_unavailability_audit_append_only.py`, `tests/integration/staff/test_availability_read_only.py` — ambos archivos verdes (Testcontainers; requiere T-09 y T-11). `[P]` con T-12.

- [ ] **T-14** `[presentation]` Esquemas Pydantic: `AvailabilityOut`/`AvailabilityItem`/`AvailabilityConflict` (solo `event_code`, `event_date`, `start_time`, `end_time`, `function`, `function_description`; **nunca** pago/tarifa/documento/teléfono), `UnavailabilityCreate`/`Update`/`Cancel`/`Out`/`ListOut`, horas locales, `extra="forbid"`, `reason` obligatorio. — `src/local_eventos/modules/staff/presentation/availability_schemas.py`, `tests/unit/staff/test_availability_schemas.py` — `uv run pytest tests/unit/staff/test_availability_schemas.py -q` verde; test que prohíbe las claves sensibles. Depende de T-01/T-03.

- [ ] **T-15** `[presentation]` Router `/v1/staff`: `availability_router` con `operationId` `staff_availability_get`, `staff_unavailability_list`, `staff_unavailability_register`, `staff_unavailability_update`, `staff_unavailability_cancel`; permiso `staff:availability` en todas; sin `DELETE` (405); mapeo de errores a Problem Details en `errors.py`; dependencia en `dependencies.py`. Registrar en `main.py` **antes de `worker_router`**: en el bloque de `assignment_router`, añadir solo `app.include_router(availability_router.router)` con el comentario de colisión; **ningún otro cambio en `main.py`**. Tests de API por ruta (201/200/404/409/422, 401, 403, sin claves sensibles). — `src/local_eventos/modules/staff/presentation/availability_router.py`, `src/local_eventos/modules/staff/presentation/errors.py`, `src/local_eventos/modules/staff/presentation/dependencies.py`, `src/local_eventos/main.py`, `tests/unit/staff/test_availability_api.py` — `uv run pytest tests/unit/staff/test_availability_api.py -q` verde; cubre CA-16.1, 16.2, 16.4, 16.8, 16.9, 16.20. Depende de T-00, T-05, T-06, T-11, T-14.

- [ ] **T-16** `[presentation/test]` Colisión de router y matriz por ruta: cada ruta literal no devuelve 422 de path param, `GET /v1/staff/availability` se enruta a disponibilidad y no a `staff_get`; sin sesión 401, `EVENTS_MANAGER` 403, `PURCHASING_MANAGER` 403 en las cinco rutas. — `tests/unit/staff/test_availability_router_order.py`, `tests/unit/staff/test_availability_api_roles.py` — ambos verdes; cubre CA-16.17 (provisional; el cierre formal es T-20). Depende de T-15.

- [ ] **T-17** `[openapi/architecture]` Regenerar `openapi.json` (`just openapi`) y verificar las cinco operaciones, esquemas y ausencia de cambios incompatibles en `/v1`; ejecutar `just arch` y añadir el caso de import prohibido si el linter lo requiere (`staff` → `commercial` solo por `public_api`; sin imports internos ni tablas). — `openapi.json`, `tests/unit/shared/test_openapi_contract.py`, `.importlinter`, `tests/architecture/test_import_rules.py` — `just openapi` y `uv run pytest tests/unit/shared/test_openapi_contract.py -q` verdes; `just arch` verde. Depende de T-15.

- [ ] **T-18** `[docs]` Documentación de la feature: `DOMAIN.md` §5 con R-DIS-1..10, §11 con las decisiones del 27/11/2026 (Q1–Q10); `ARCHITECTURE.md` con la tabla de indisponibilidad y `staff_unavailabilities_audit` en append-only; docstrings de `composition.py`, router, casos de uso, repositorio y VO. — `docs/DOMAIN.md`, `docs/architecture/ARCHITECTURE.md`, `src/local_eventos/modules/staff/composition.py`, `src/local_eventos/modules/staff/presentation/availability_router.py` — `just docs` y `uv run ruff check` verdes; sin contradicciones con spec/plan. `[P]` con T-17. No toca §9 de la matriz de permisos (lo cierra T-20).

- [ ] **T-19** `[verify]` Verificación intermedia: `just check` completo (ruff + mypy + lint-imports + suite), integración real de disponibilidad (repo, constraints, auditoría, solo lectura, equivalencia), `uv run alembic heads` con un único head y `openapi.json` regenerado. — todo el repo — `just check` en verde y checklist CA-16.1..16.21 con al menos un test por CA (informe breve). Depende de T-10..T-18.

- [ ] **T-20** `[identity/cierre]` **Cierre de permisos (ÚLTIMA tarea; NO añade la constante).** Verificar y fijar la matriz: `ADMIN` sí; `EVENTS_MANAGER` y `PURCHASING_MANAGER` **no**; `staff:manage`, `staff:roster:read` y `staff:assign` no abren disponibilidad. Test de matriz en `tests/unit/identity/test_user.py` y 403 por ruta en `tests/unit/staff/test_availability_api_roles.py` (quitar cualquier excepción temporal). Actualizar `DOMAIN.md` §9 con la fila `staff:availability` y la aclaración. — `tests/unit/identity/test_user.py`, `tests/unit/staff/test_availability_api_roles.py`, `docs/DOMAIN.md` — `uv run pytest tests/unit/identity/test_user.py tests/unit/staff/test_availability_api_roles.py -q` verde y `just check` verde; cubre CA-16.17. Depende de T-19.

## Mapeo CA → tareas

| CA | Tareas |
|---|---|
| CA-16.1 | T-02, T-05, T-12, T-15 |
| CA-16.2 | T-05, T-15 |
| CA-16.3 | T-11, T-13 |
| CA-16.4 | T-11, T-15 |
| CA-16.5 | T-11, T-13 |
| CA-16.6 | T-13 |
| CA-16.7 | T-10, T-11 |
| CA-16.8 | T-11, T-15 |
| CA-16.9 | T-11, T-15 |
| CA-16.10 | T-11 |
| CA-16.11 | T-11 |
| CA-16.12 | T-11 |
| CA-16.13 | T-02, T-12 |
| CA-16.14 | T-02, T-03, T-12 |
| CA-16.15 | T-11, T-13 |
| CA-16.16 | T-11, T-13 |
| CA-16.17 | T-16, T-20 |
| CA-16.18 | T-02, T-06, T-13 |
| CA-16.19 | T-13 |
| CA-16.20 | T-03, T-15 |
| CA-16.21 | T-10 (test-first), T-11 (activación) |

## Gates y bloqueos

- **T-00**: si `git merge origin/developer-a` da conflicto → parar; no continuar la feature.
- **T-09**: crear la migración **solo** si `git fetch origin` + `git merge origin/developer-a` no dan conflictos y `uv run alembic heads` = un único head `8df99a56ff18`. Si hay dos heads o conflictos → parar y avisar. **Nunca** en paralelo.
- **T-10 → T-11**: CA-16.21 debe existir (aunque sea `xfail`/`skip`) antes de implementar `GetStaffAvailability`; T-11 la activa.
- **T-15**: `main.py` solo gana el `include_router` de disponibilidad antes de `worker_router`; nada más.
- **T-20**: última; no declara la constante (ya en T-00), solo verifica matriz, 403 y documentación.

## Prohibiciones explícitas (para todos)

- No `git push`, no PR, no reescribir archivos completos para cambios pequeños.
- No ampliar `AssignmentOverlap`, no modificar `list_active_overlaps`/`AssignmentView`/`release_cancelled` ni ningún código de HU17.
- No `DELETE` físico, no `UPDATE`/`DELETE` en auditoría, no reactivar `CANCELLED`.
- No exponer pago, tarifa, documento ni teléfono; no usar `AssignmentView` en la consulta.
- No tocar `staff.public_api`, `commercial` interno, `reporting`, `assistant`, ledger, inventario ni precios.
- No dependencias nuevas ni ADR; si aparecen, detener la tarea y avisar.
- No tocar `tests/integration/staff/test_staff_api_e2e.py` salvo que falle por el nuevo router (entonces, mínimo cambio y justificado).
