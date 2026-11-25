# Plan: Datos del personal (trabajadores)

- **Spec**: ./spec.md
- **Estado**: aprobado (24/11/2026)

## 0. Resumen

- Módulo nuevo **`staff`**; `identity` solo gana el permiso `staff:manage`.
- Un agregado **`Worker`** con baja lógica y una **tabla compacta de auditoría de operaciones** (no historial campo por campo).
- API REST sin `DELETE`; administrador y encargado de eventos gestionan; compras recibe 403.
- Una sola migración Alembic; unicidad por `(document_type, document_number)` garantizada en PostgreSQL.
- `staff.public_api` expone una consulta mínima de solo lectura para que HU17 valide estado y función.

## 1. Módulos y fronteras

### 1.1 `staff` (nuevo)

Estructura prevista:

```
staff/
├─ domain/            worker.py · document.py · money.py · audit.py · errors.py
├─ application/       errors.py · search_text.py
│  ├─ ports/          worker_repository.py · clock.py
│  └─ use_cases/      register_worker.py · update_worker.py · get_worker.py
│                     search_workers.py · change_worker_status.py · get_worker_ref.py
├─ infrastructure/    orm_models.py · worker_repository.py · clock.py
├─ presentation/      worker_router.py · worker_schemas.py · errors.py · dependencies.py
├─ composition.py
└─ public_api.py
```

- Sin tablas de asignaciones, disponibilidad ni cruces de horario: eso es HU17.
- Sin claves foráneas ni JOINs contra tablas de `identity`, `commercial` o `ledger`.
- Los ids de usuario (`changed_by`) se guardan como `UUID` sin FK (regla 3 de AGENTS.md); el `worker_id` de la auditoría sí es FK dentro de `staff`.

### 1.2 `identity` (solo permiso)

- Agregar `Permission.STAFF_MANAGE = "staff:manage"`.
- `Role.ADMIN` lo obtiene por `frozenset(Permission)`.
- `Role.EVENTS_MANAGER` lo recibe explícitamente; “vendedor” es este mismo rol.
- `Role.PURCHASING_MANAGER` **no** lo recibe: sin lectura ni escritura de personal.
- No hay migración: los permisos viven en código (`identity/domain/permissions.py`).
- Actualizar `tests/unit/identity/test_user.py` (conjunto esperado de `EVENTS_MANAGER`).

### 1.3 `staff.public_api` (mínimo para HU17)

```python
@dataclass(frozen=True)
class WorkerRef:
    id: UUID
    name: str
    function: WorkerFunction | None
    function_description: str | None
    status: WorkerStatus


class WorkerLookup(Protocol):
    async def get(self, worker_id: UUID) -> WorkerRef | None: ...


def worker_lookup(session: AsyncSession) -> WorkerLookup: ...
```

- Solo lectura. No expone documento, teléfono, tarifa ni operaciones de escritura.
- HU17 lo usará para rechazar inactivos (RN11) y copiar la función con la que se trabajó.
- Se implementa con una consulta de aplicación (`GetWorkerRef`) sobre el repositorio; `public_api` reexporta el DTO, los enums `WorkerFunction`/`WorkerStatus` y la fábrica.

### 1.4 Fronteras

- `staff` usa de `identity.public_api`: `CurrentUser`, `require_permission`, `Permission`.
- Ningún otro módulo importa `staff` salvo por `public_api`.
- `reporting` y `assistant` no se tocan en HU15; si más adelante consultan personal, lo harán por `staff.public_api` y respetando `staff:manage`.

## 2. Modelo de dominio

### 2.1 Agregado `Worker`

Campos: `id`, `name`, `document`, `phone`, `function`, `function_description`, `worker_type`, `rate`, `overtime_applies`, `overtime_rate`, `status`.

- `Worker.register(...)`: crea siempre en `ACTIVE` (R-STF-10) y valida todo antes de construir.
- `Worker.update(...)`: reemplaza los datos editables; valida todo antes de mutar (mismo criterio que `Client.update_contact`).
- `Worker.deactivate()` / `Worker.activate()`: devuelven `bool` indicando si hubo cambio real.
- No existe `delete()` ni borrado físico (R-STF-2, CA-15.11).
- La unicidad del documento **no** es una invariante del agregado: se comprueba en aplicación y en PostgreSQL.

### 2.2 Value objects

| VO | Reglas |
|---|---|
| `Document` | `DocumentType` `DNI`/`CE`; normaliza quitando espacios y guiones; DNI `^[0-9]{8}$`; CE `^[0-9]{9,12}$`. |
| `Money` | Entero en céntimos, moneda fija `PEN`; no admite booleanos ni negativos. |
| `WorkerFunction` | Lista fija `COOK`, `WAITER`, `BARTENDER`, `ASSISTANT`, `COORDINATOR`, `OTHER` (cocinero, mozo, bartender, ayudante, coordinador, otro). |
| `WorkerType` | `FIXED` o `EVENTUAL`; opcional. No existe interno/externo. |
| `WorkerStatus` | `ACTIVE` o `INACTIVE`. |
| `WorkerAudit` | `worker_id`, `action`, `reason`, `changed_by`, `changed_at`; solo se inserta, nunca se edita. |

> `Money` y los enums son locales a `staff`; si otro módulo necesita `Money`, se moverá a `shared` con su ADR.

### 2.3 Invariantes

1. `name` obligatorio, sin espacios sobrantes, máximo técnico 150 (igual que clientes).
2. `document` obligatorio y válido; se guarda normalizado.
3. `phone` opcional: si se informa, solo dígitos ASCII (`[0-9]+`), sin longitud fija; vacío se guarda como `None`.
4. `function` opcional. Si es `OTHER`, `function_description` obligatoria y no vacía. Si es otra función o `None`, no admite descripción.
5. `worker_type` opcional; si se informa, solo `FIXED`/`EVENTUAL`.
6. `rate` opcional y `>= 0` céntimos.
7. `overtime_applies = true` exige `overtime_rate > 0`; `false` exige `overtime_rate = None`.
8. Estado inicial `ACTIVE`; activar/desactivar es idempotente y no borra.
9. Dos trabajadores pueden compartir nombre; los distingue el documento (R-STF-9).

### 2.4 Errores de dominio (`code` estable)

`staff.name_required`, `staff.name_too_long`, `staff.document_invalid`, `staff.phone_invalid`,
`staff.function_description_required`, `staff.function_description_not_allowed`,
`staff.rate_invalid`, `staff.overtime_rate_required`, `staff.overtime_rate_not_allowed`,
`staff.overtime_rate_invalid`.

- Los valores fuera de un enum (`document_type`, `function`, `worker_type`) los rechaza Pydantic al validar el esquema; el dominio conserva sus propias comprobaciones para los tests y para cualquier uso interno.
- `DuplicateDocumentError` (`staff.document_duplicated`, 409) y `WorkerNotFoundError` (`staff.not_found`, 404) son errores de aplicación.

## 3. Casos de uso

| Caso de uso | Tipo | Entrada | Salida | Errores de negocio |
|---|---|---|---|---|
| `RegisterWorker` | command | datos de la ficha + `actor_id` + `now` | `Worker` | validación (422), `staff.document_duplicated` (409) |
| `UpdateWorker` | command | `worker_id` + datos editables + `actor_id` + `now` | `Worker` | `staff.not_found` (404), validación (422), `staff.document_duplicated` (409) |
| `GetWorker` | query | `worker_id` | `Worker` | `staff.not_found` (404) |
| `SearchWorkers` | query | `text`, `function?`, `status?`, `page`, `page_size` | `WorkerPage` (items, total, page, page_size) | — |
| `DeactivateWorker` | command | `worker_id`, `reason?`, `actor_id`, `now` | `Worker` | `staff.not_found` (404) |
| `ActivateWorker` | command | `worker_id`, `reason?`, `actor_id`, `now` | `Worker` | `staff.not_found` (404) |
| `GetWorkerRef` | query interna | `worker_id` | `WorkerRef \| None` | — |

- **Idempotencia de estado**: desactivar a alguien ya inactivo, o activar a alguien ya activo, devuelve **200 con la ficha actual** y **no escribe auditoría**, porque no hubo cambio real. Es coherente con `ActivateClient`/`DeactivateClient`, evita filas de auditoría falsas y permite reintentos seguros. Si negocio prefiere un 409, es un cambio localizado en estos dos casos.
- `SearchWorkers` normaliza `page >= 1` y `page_size` entre 1 y 100 (igual que eventos). El texto se recorta y se busca en nombre (sin tildes) o documento normalizado.
- Las escrituras usan `get_for_update` para serializar ediciones y cambios de estado del mismo trabajador.

## 4. Auditoría (RN03)

**Decisión: tabla compacta de auditoría de operaciones, no columnas de auditoría ni historial campo por campo.**

| Opción | Veredicto |
|---|---|
| Columnas en `staff_workers` | No: una reactivación pisaría la baja anterior y se perdería quién/cuándo. |
| Tabla solo de cambios de estado | No: no cubre la edición (CA-15.6/CA-15.16). |
| Tabla compacta de operaciones | **Elegida**: una fila por alta, edición, activación o desactivación; sin diff de campos. |

- Tabla `staff_worker_audit`: `worker_id`, `action` (`CREATED`, `UPDATED`, `ACTIVATED`, `DEACTIVATED`), `reason?`, `changed_by`, `changed_at`.
- El alta, la edición y el cambio de estado escriben la fila de auditoría en la **misma transacción** que la ficha; si falla la auditoría, no queda el cambio.
- `reason` solo se admite en `ACTIVATED`/`DEACTIVATED`; es opcional.
- La tabla es **append-only** con trigger `BEFORE UPDATE OR DELETE`, como `identity_access_log` y `ledger_payments`.
- No se expone endpoint de auditoría en HU15: la API devuelve la ficha; el detalle de quién/cuándo queda en la tabla para consulta interna y futuras historias.

## 5. API (OpenAPI)

### 5.1 Endpoints

| Método y ruta | `operationId` | Permiso | Éxito |
|---|---|---|---|
| `POST /v1/staff` | `staff_register` | `staff:manage` | 201 |
| `GET /v1/staff` | `staff_search` | `staff:manage` | 200 |
| `GET /v1/staff/{worker_id}` | `staff_get` | `staff:manage` | 200 |
| `PUT /v1/staff/{worker_id}` | `staff_update` | `staff:manage` | 200 |
| `POST /v1/staff/{worker_id}/deactivate` | `staff_deactivate` | `staff:manage` | 200 |
| `POST /v1/staff/{worker_id}/activate` | `staff_activate` | `staff:manage` | 200 |

- **No existe** `DELETE /v1/staff/{worker_id}` (CA-15.11). Un intento de `DELETE` responde 405.
- `PUT` es reemplazo completo de los campos editables: si se omite un opcional, se limpia. Se documenta en el endpoint.
- `deactivate`/`activate` aceptan cuerpo opcional `{ "reason": "..." }`.
- `GET /v1/staff` acepta `function`, `status` (`ACTIVE` por defecto, `INACTIVE` o `ALL`), `text`, `page`, `page_size` (máx. 100).
- `status=ALL` es la única forma de ver activos e inactivos juntos; sin filtro se muestran solo activos, según CA-15.8 (“los inactivos aparecen cuando el filtro los incluye”).

### 5.2 Esquemas

- `WorkerCreate` / `WorkerUpdate`: `name`, `document_type`, `document_number`, `phone?`, `function?`, `function_description?`, `worker_type?`, `rate_cents?`, `overtime_applies` (por defecto `false`), `overtime_rate_cents?`.
- `WorkerOut`: los mismos datos + `id`, `status`, `currency: "PEN"`.
- `WorkerSummaryOut`: `id`, `name`, `document_type`, `document_number`, `function`, `function_description`, `worker_type`, `status`.
- `WorkerPageOut`: `items`, `total`, `page`, `page_size`.
- Importes siempre enteros en céntimos; nunca decimales.

### 5.3 Errores

| HTTP | `code` | Cuándo |
|---|---|---|
| 401 | `auth.not_authenticated`, `auth.session_expired` | Sin sesión |
| 403 | `auth.forbidden` | Sin `staff:manage` (incluido compras) |
| 404 | `staff.not_found` | `worker_id` inexistente |
| 409 | `staff.document_duplicated` | Misma combinación tipo + número, activo o inactivo |
| 422 | `staff.*` de validación | Nombre, documento, teléfono, función/otro, tipo, tarifa u hora extra |
| 422 | Validación estándar de FastAPI | Enum o forma del cuerpo fuera de contrato |

`openapi.json` se regenera con `just openapi`; la prueba `test_openapi_json_esta_actualizado` debe quedar en verde.

## 6. Persistencia y migración

### 6.1 Tablas

**`staff_workers`**

| Columna | Tipo | Nulo | Nota |
|---|---|---|---|
| `id` | `uuid` | no | PK |
| `name` | `varchar(150)` | no | CHECK no vacío |
| `document_type` | `varchar(3)` | no | `DNI`/`CE` |
| `document_number` | `varchar(12)` | no | CHECK por tipo |
| `phone` | `text` | sí | CHECK solo dígitos |
| `worker_function` | `varchar(15)` | sí | CHECK lista fija |
| `function_description` | `text` | sí | CHECK condicional a `OTHER` |
| `worker_type` | `varchar(8)` | sí | `FIXED`/`EVENTUAL` |
| `rate_cents` | `integer` | sí | `>= 0` |
| `overtime_applies` | `boolean` | no | por defecto `false` |
| `overtime_rate_cents` | `integer` | sí | CHECK condicional |
| `status` | `varchar(8)` | no | `ACTIVE` por defecto |
| `created_at` / `updated_at` | `timestamptz` | no | metadatos técnicos, no auditoría |

**`staff_worker_audit`** (append-only)

`id bigint identity`, `worker_id uuid` FK a `staff_workers` (`ON DELETE RESTRICT`), `action varchar(12)`, `reason text` nulo, `changed_by uuid` (sin FK), `changed_at timestamptz`.

### 6.2 Constraints e índices

- `UNIQUE (document_type, document_number)` → `uq_staff_workers_document`; incluye inactivos automáticamente.
- CHECK de documento:
  `(document_type = 'DNI' AND document_number ~ '^[0-9]{8}$') OR (document_type = 'CE' AND document_number ~ '^[0-9]{9,12}$')`.
- CHECK de teléfono: `phone IS NULL OR phone ~ '^[0-9]+$'`.
- CHECK de función/descripción:
  `(worker_function = 'OTHER' AND function_description IS NOT NULL AND btrim(function_description) <> '') OR (worker_function IS DISTINCT FROM 'OTHER' AND function_description IS NULL)`.
- CHECK de hora extra:
  `(overtime_applies AND overtime_rate_cents IS NOT NULL AND overtime_rate_cents > 0) OR (NOT overtime_applies AND overtime_rate_cents IS NULL)`.
- CHECK de importes: `rate_cents IS NULL OR rate_cents >= 0`.
- CHECK de estados y enums (`status`, `worker_type`, `worker_function`).
- CHECK de auditoría: `action` válida; `reason` solo en `ACTIVATED`/`DEACTIVATED`.
- Índices: `(status, worker_function)`, `(worker_function)`, `(document_number)`, `lower(name)` y `(worker_id, changed_at)` en auditoría.
- Para el volumen esperado (decenas a pocos cientos) no se agrega `pg_trgm`; si crece, se evalúa con ADR.

### 6.3 Migración

- **Una sola migración** `crear_tablas_de_personal`, con `down_revision = d0f713f5dc65` (head actual).
- Antes de crearla: avisar al humano y ejecutar `uv run alembic heads` para confirmar un único head. Si otra feature creó una migración, se rebasa el `down_revision`.
- Incluye tablas, constraints, índices y el trigger `staff_worker_audit_append_only`.
- No modifica tablas existentes ni datos; `identity` no requiere migración.
- `downgrade` elimina trigger, función, índices y tablas.

### 6.4 Concurrencia del documento

1. La aplicación consulta `get_by_document` para dar un 409 amable.
2. La restricción UNIQUE es la garantía real: si dos altas simultáneas pasan la consulta, una falla al hacer flush.
3. El repositorio captura `IntegrityError`, comprueba el nombre `uq_staff_workers_document` y lanza `DuplicateDocumentError`.
4. En edición se excluye el propio `worker_id` de la comprobación; si otro trabajador toma el documento entre la consulta y el flush, la transacción se revierte y la ficha conserva su documento anterior.
5. Prueba de integración con dos sesiones concurrentes: exactamente una alta queda y la otra recibe `staff.document_duplicated`.

## 7. Reglas de negocio aplicadas

| Regla | Cómo se cumple |
|---|---|
| R-STF-1 | `Document` normaliza y valida; UNIQUE por tipo + número; incluye inactivos. |
| R-STF-2 / R-STF-3 | Baja lógica (`status`), sin `DELETE`; la fila y la auditoría se conservan. |
| R-STF-4 | `public_api` expone `status`; HU17 rechazará inactivos. HU15 no asigna. |
| R-STF-5 | Permiso `staff:manage` en `identity`; solo admin y encargado de eventos. |
| R-STF-6 | Tabla de auditoría append-only con usuario y fecha-hora. |
| R-STF-7 / R-STF-8 | `rate` y `overtime_rate` son referenciales; no se copian a documentos ni a `ledger`. |
| R-STF-9 | No hay unicidad por nombre. |
| R-STF-10 | Alta siempre `ACTIVE`. |
| R-STF-11 | `WorkerType` solo `FIXED`/`EVENTUAL`; sin interno/externo. |
| R-STF-12 / R-STF-17 | `WorkerFunction` fija + `OTHER` con descripción obligatoria; sin descripción en las demás. |
| R-STF-13 | Obligatorios: nombre y documento; teléfono y tarifa opcionales; teléfono solo dígitos. |
| R-STF-14 | CHECK y validación de dominio para hora extra condicional. |
| R-STF-15 | Activar/desactivar con auditoría y motivo opcional; reactivación permitida. |
| R-STF-16 | Admin y encargado de eventos; compras sin acceso. |

## 8. Estrategia de tests

### 8.1 Unitarios (sin base de datos)

- **Dominio**: `Document` (normalización, DNI, CE, límites), `Money`, `Worker` (nombre, teléfono, función/otro, tipo, tarifa, hora extra, estado inicial, idempotencia de activar/desactivar, sin borrado).
- **Aplicación con fakes**: alta, edición, consulta, listado (filtros, búsqueda, paginación), desactivar/activar, duplicado, no encontrado, auditoría (acción, actor, fecha, motivo), idempotencia sin auditoría.
- **API con fakes**: permisos (admin/eventos 2xx, compras 403, sin sesión 401), errores 404/409/422, filtros y paginación, ausencia de `DELETE`, `operationId` estables.

### 8.2 Integración (PostgreSQL real, migraciones Alembic)

- Guardar/leer/actualizar; búsqueda por nombre sin tildes y por documento; filtros y paginación.
- Duplicado secuencial y **concurrente** (dos sesiones); edición a documento existente conserva el anterior.
- Dos desactivaciones simultáneas: una cambia el estado y la otra es no-op; queda una sola fila de auditoría.
- CHECKs reales con SQL directo: tipo/documento, teléfono, función/otro, hora extra, importes, estado.
- Auditoría: alta, edición, baja y reactivación; trigger rechaza `UPDATE`/`DELETE`; si falla la auditoría, la ficha no queda.
- API de punta a punta con admin; `/ready` sigue en verde.

### 8.3 Arquitectura

- `just arch` en verde con `staff` ya incluido en `.importlinter`.
- Agregar un caso en `tests/architecture/test_import_rules.py`: un import de `staff/domain` a `identity` interna o a FastAPI rompe la regla correspondiente.
- `just check` completo.

### 8.4 Mapeo CA-15.x → test

Los nombres de test son orientativos; la suite real cubre los CA.

| CA | Test(s) |
|---|---|
| CA-15.1 | `unit/staff/test_worker.py::test_ca15_1_alta_activa_con_obligatorios`; `unit/staff/test_worker_api.py::test_ca15_1_registra`; `integration/staff/test_worker_repository.py::test_ca15_1_guarda_y_lee` |
| CA-15.2 | `unit/staff/test_worker.py::test_ca15_2_nombre_y_documento_obligatorios`; `unit/staff/test_worker_api.py::test_ca15_2_422` |
| CA-15.3 | `unit/staff/test_worker_use_cases.py::test_ca15_3_duplicado_incluye_inactivos`; `integration/staff/test_worker_repository.py::test_ca15_3_unique`; `unit/staff/test_worker_api.py::test_ca15_3_409` |
| CA-15.4 | `unit/staff/test_worker_use_cases.py::test_ca15_4_edicion_a_documento_ajeno`; `integration/staff/test_worker_repository.py::test_ca15_4_conserva_documento_anterior` |
| CA-15.5 | `integration/staff/test_worker_concurrency.py::test_ca15_5_dos_altas_simultaneas` |
| CA-15.6 | `unit/staff/test_worker_use_cases.py::test_ca15_6_edicion_auditada`; `integration/staff/test_worker_repository.py::test_ca15_6_auditoria_update`; `unit/staff/test_worker_api.py::test_ca15_6_put` |
| CA-15.7 | `unit/staff/test_worker_use_cases.py::test_ca15_7_consulta_inactivo`; `unit/staff/test_worker_api.py::test_ca15_7_get_inactivo` |
| CA-15.8 | `unit/staff/test_worker_use_cases.py::test_ca15_8_filtros_y_paginacion`; `integration/staff/test_worker_repository.py::test_ca15_8_busqueda`; `unit/staff/test_worker_api.py::test_ca15_8_query` |
| CA-15.9 | `unit/staff/test_worker_use_cases.py::test_ca15_9_desactiva_con_motivo_opcional`; `integration/staff/test_worker_repository.py::test_ca15_9_auditoria_baja` |
| CA-15.10 | `unit/staff/test_worker_use_cases.py::test_ca15_10_reactiva`; `unit/staff/test_worker_api.py::test_ca15_10_activate` |
| CA-15.11 | `unit/staff/test_worker_api.py::test_ca15_11_no_existe_delete`; `unit/staff/test_worker.py::test_ca15_11_sin_metodo_delete` |
| CA-15.12 | `unit/staff/test_worker_use_cases.py::test_ca15_12_worker_lookup_estado_y_funcion`; `integration/staff/test_worker_repository.py::test_ca15_12_lookup_inactivo` |
| CA-15.13 | `integration/staff/test_worker_repository.py::test_ca15_13_baja_logica_conserva_fila_y_auditoria` (el historial de eventos se probará en HU17) |
| CA-15.14 | `unit/staff/test_worker_api.py::test_ca15_14_permisos_por_rol` (admin/eventos 2xx, compras 403, sin sesión 401) |
| CA-15.15 | `unit/staff/test_worker.py::test_ca15_15_matriz_validacion`; `unit/staff/test_worker_api.py::test_ca15_15_422`; `integration/staff/test_worker_repository.py::test_ca15_15_checks` |
| CA-15.16 | `unit/staff/test_worker_use_cases.py::test_ca15_16_auditoria_en_las_cuatro_operaciones`; `integration/staff/test_worker_repository.py::test_ca15_16_filas_auditoria` |
| CA-15.17 | `unit/staff/test_worker.py::test_ca15_17_tipo_fijo_o_eventual`; `unit/staff/test_worker_api.py::test_ca15_17_enum` |
| CA-15.18 | `unit/staff/test_worker.py::test_ca15_18_funcion_fija_y_otro`; `unit/staff/test_worker_api.py::test_ca15_18_funcion` |
| CA-15.19 | `unit/staff/test_document.py::test_ca15_19_normaliza_y_valida`; `integration/staff/test_worker_repository.py::test_ca15_19_unique_incluye_inactivos` |
| CA-15.20 | `unit/staff/test_worker.py::test_ca15_20_tarifa_centimos_opcional`; `unit/staff/test_worker_api.py::test_ca15_20_rate_cents` |
| CA-15.21 | `unit/staff/test_worker.py::test_ca15_21_hora_extra_condicional`; `integration/staff/test_worker_repository.py::test_ca15_21_check_hora_extra` |
| CA-15.22 | `unit/staff/test_worker.py::test_ca15_22_telefono_solo_digitos_sin_longitud`; `integration/staff/test_worker_repository.py::test_ca15_22_check_telefono` |
| CA-15.23 | `unit/staff/test_worker_api.py::test_ca15_23_compras_403_en_todas_las_rutas` |
| CA-15.24 | `unit/staff/test_worker_use_cases.py::test_ca15_24_reactivacion_auditada`; `integration/staff/test_worker_repository.py::test_ca15_24_auditoria_activacion` |
| CA-15.25 | `unit/staff/test_worker.py::test_ca15_25_otro_exige_descripcion`; `unit/staff/test_worker_api.py::test_ca15_25_422`; `integration/staff/test_worker_repository.py::test_ca15_25_check_funcion` |

## 9. Riesgos y ADRs

- **Migración con dos heads**: alto. Antes de crear la migración, avisar al humano y confirmar un único head con `uv run alembic heads`. No editar migraciones aplicadas.
- **Datos personales**: documento y teléfono solo se devuelven con `staff:manage`; compras recibe 403. No registrar cuerpos de petición con datos personales en logs. `assistant` no recibe funciones de personal en HU15.
- **Contrato OpenAPI**: se agregan endpoints y esquemas; regenerar `openapi.json`. No hay cambios incompatibles en `/v1`; el frontend debe mapear los nuevos `staff.*`.
- **Concurrencia**: UNIQUE para documento y `FOR UPDATE` para edición/estado. Probar dos altas simultáneas y dos cambios de estado simultáneos.
- **Auditoría**: tabla append-only con trigger; si se degrada el trigger, RN03 queda solo en código. Probar `UPDATE`/`DELETE` rechazados.
- **Volumen y búsqueda**: sin `pg_trgm`; el filtro por nombre con `contains` puede escanear. Aceptable para decenas/cientos; si crece, evaluar extensión con ADR.
- **Identidad**: actualizar el test de permisos de `EVENTS_MANAGER`; compras debe seguir sin `staff:manage`.
- **Sin asignaciones ni cruces**: HU15 no crea `staff_assignments` ni la restricción de exclusión; eso queda para HU17. No hay impacto en el congelado de precios ni en estados comerciales.
- **Sin dependencias nuevas**: no se requiere ADR por la regla 11. Si la tabla de auditoría se adopta como patrón transversal, proponer ADR 0005 en la fase de docs.

## 10. Impacto en `reporting` y documentación

- **`reporting`**: sin cambios en HU15. Cuando exista un panel de personal, `reporting` pedirá los números por `staff.public_api`; nunca leerá `staff_*` directamente.
- **`assistant`**: sin funciones nuevas; no debe exponer personal a roles sin `staff:manage`.
- **`docs/DOMAIN.md`**:
  - §2: precisar el glosario de **Trabajador** (documento, función, tipo, estado, tarifa referencial).
  - §5: agregar las reglas R-STF-1..17 (o un resumen que remita a la spec).
  - §9: **dividir** la fila `Eventos, personal y asignaciones` en `Eventos y asignaciones` (compras: lectura, como hoy) y `Personal (trabajadores)` (admin/eventos: ✔; compras: –), con la nota de `staff:manage` (24/11/2026).
  - §11: registrar las decisiones del 24/11/2026 (tipo, función/otro, tarifa y hora extra, documento, obligatorios, baja/reactivación, listado, permisos, unicidad, formato).
- **`docs/architecture/ARCHITECTURE.md`**: agregar personal a los ejemplos de auditoría (§6); opcionalmente aclarar en el mapa que HU15 solo trabajadores y HU17 asignaciones.
- **`openapi.json`**: regenerar con `just openapi`.
- **`README.md` / `STACK.md` / `INSTALACION.md`**: sin cambios (no hay dependencias, herramientas ni comandos nuevos).
- **`docs/sdd/README.md`**: revisar el roadmap si se quiere alinear `007-staff` con la feature `032-staff`.
- **ADR**: no se crea ninguno en esta fase; no hay dependencias nuevas. La decisión de auditoría queda en este plan.

## 11. Decisiones del plan

1. **Mensaje de documento duplicado**: ¿solo tipo + número o también el nombre del trabajador existente?
   - Opciones: (A) “Ya existe un trabajador con DNI 44125896.”; (B) incluir también el nombre.
   - **Decidido (24/11/2026): opción A**, solo tipo + número, porque el documento ya identifica al trabajador y evita exponer datos de más (§7 de la spec). Si negocio quiere el nombre, se agrega en el `detail`.
2. **Longitud de la “descripción breve” de la función `OTRO`**: la spec no fija un máximo.
   - Opciones: (A) `text` sin máximo, solo no vacío; (B) máximo técnico de 120 caracteres.
   - **Decidido (24/11/2026): opción B (máximo 120 caracteres)**, como límite técnico, no como regla de negocio; se valida en dominio y en el esquema.
3. **Visibilidad de la auditoría en la API**: la spec exige guardar quién/cuándo, no mostrarlo.
   - **Decidido (24/11/2026): no exponer endpoint de auditoría en HU15**; la tabla queda para consulta interna. Si el frontend necesita “última baja por X”, se agrega una consulta de solo lectura en otra historia.
