# Arquitectura — Monolito modular + Clean Architecture (Python)

## 1. Visión
Un solo despliegue (API FastAPI + PostgreSQL), dividido en **módulos de negocio** con fronteras estrictas. Pensado para una sola organización y para operar con el mínimo de piezas.

## 2. Estructura del repositorio

```
.
├─ AGENTS.md · opencode.json · justfile
├─ pyproject.toml · uv.lock · .importlinter · alembic.ini
├─ Dockerfile · docker-compose.yml · openapi.json
├─ .github/workflows/        # ci.yml · cd.yml · docs.yml · release.yml
├─ .opencode/                # agent/ skill/ command/
├─ docs/
│  ├─ DOMAIN.md              # reglas de negocio
│  ├─ architecture/          # ARCHITECTURE.md · STACK.md · adr/
│  ├─ sdd/                   # flujo, plantillas, features/<NNN-slug>/
│  └─ operations/            # RUNBOOK.md · HANDOVER.md
├─ migrations/               # Alembic (env.py, versions/)
├─ src/local_eventos/
│  ├─ main.py                # create_app(): routers, middlewares, errores
│  ├─ tools/                 # export_openapi.py y utilidades
│  ├─ shared/
│  │  ├─ domain/             # Entity, ValueObject, Money, DomainEvent, Result, Clock (puerto)
│  │  ├─ application/        # UseCase base, UnitOfWork (puerto), EventBus (puerto)
│  │  └─ infrastructure/     # db (engine/session), config, logging, security, outbox
│  └─ modules/
│     ├─ identity/           # usuarios, roles, permisos, auth, historial de accesos
│     ├─ commercial/         # clientes, cotizaciones, contratos y eventos (ADR 0003)
│     ├─ catalog/            # catálogo de servicios y precios referenciales
│     ├─ staff/              # trabajadores (HU15) y asignaciones sin cruces (HU17)
│     ├─ ledger/             # pagos, ingresos, egresos, saldos (append-only)
│     ├─ inventory/          # productos, lotes, movimientos, requerimientos por evento
│     ├─ purchasing/         # proveedores, solicitudes de compra, recepción
│     ├─ reporting/          # dashboard e informes de solo lectura
│     └─ assistant/          # agente de IA de solo consulta, historial de consultas
└─ tests/
   ├─ unit/<modulo>/         # dominio y aplicación, sin DB
   ├─ integration/<modulo>/  # repositorios, API, migraciones (Postgres real)
   └─ architecture/          # reglas de dependencias
```

## 3. Estructura interna de un módulo

```
modules/<modulo>/
├─ public_api.py       # ÚNICA superficie visible para otros módulos (interfaces, DTOs, eventos)
├─ domain/             # entidades, value objects, agregados, eventos, políticas (Python puro)
├─ application/
│  ├─ use_cases/       # un caso de uso por archivo (commands/queries)
│  └─ ports/           # interfaces: repositorios, relojes, servicios externos
├─ infrastructure/     # orm_models.py, repositories.py, mappers.py, adaptadores
├─ presentation/       # router.py, schemas.py (Pydantic), dependencies.py (auth, DI)
└─ composition.py      # ensamblaje: casos de uso + adaptadores
```

### Regla de dependencias
```
presentation ─► application ─► domain
infrastructure ─► application ─► domain     (implementa los puertos)
```
- `domain` no importa FastAPI, SQLAlchemy ni Pydantic.
- Los modelos ORM y los esquemas Pydantic **no son** entidades de dominio: se mapean explícitamente.
- Los routers no contienen lógica de negocio; traducen HTTP ⇄ caso de uso.

## 4. Comunicación entre módulos
1. **Consulta síncrona** por `public_api` (p. ej. `commercial` pide a `catalog` el precio de un servicio; `assistant` consulta a `commercial` o `ledger` mediante funciones de solo lectura). Dentro de `commercial`, los submódulos se usan directamente (ADR 0003).
2. **Eventos de dominio en proceso** (p. ej. `QuoteAccepted`, `ContractSigned`, `EventFinished`) despachados dentro de la misma transacción. Sin broker externo.
3. **Prohibido:** importar capas internas de otro módulo, joins SQL entre tablas de módulos distintos, FKs entre módulos.
4. **Datos:** prefijo de tablas por módulo (`commercial_*`, `inventory_*`, `ledger_*`).
5. **Excepción controlada:** el esquema `reporting` expone **vistas estables** de solo lectura para el dashboard y los reportes; es el único lugar donde se cruzan datos de varios módulos.
6. **`staff` y `commercial`:** `staff` consulta el evento **solo** por `commercial.public_api.event_lookup` (código, estado, fecha y horario) y guarda `event_id` **sin clave foránea**; `commercial` no conoce ni importa `staff`. Las asignaciones viven en `staff` (ADR 0005, HU17).

## 5. Reglas verificables (automatizadas con import-linter)
```ini
[importlinter]
root_package = local_eventos

[importlinter:contract:capas]
name = Capas dentro de cada módulo
type = layers
layers =
    local_eventos.modules.*.presentation
    local_eventos.modules.*.application
    local_eventos.modules.*.domain
containers = local_eventos.modules.*
# infrastructure se declara aparte: puede importar application y domain, nadie la importa excepto composition.

[importlinter:contract:dominio-puro]
name = El dominio no depende de frameworks
type = forbidden
source_modules = local_eventos.modules.*.domain
forbidden_modules = fastapi, sqlalchemy, pydantic

[importlinter:contract:modulos-independientes]
name = Los módulos solo se usan por su public_api
type = independence
modules =
    local_eventos.modules.identity
    local_eventos.modules.commercial
    local_eventos.modules.catalog
    local_eventos.modules.staff
    local_eventos.modules.ledger
    local_eventos.modules.inventory
    local_eventos.modules.purchasing
    local_eventos.modules.reporting
    local_eventos.modules.assistant
```
> Es un punto de partida: el agente `architect` debe ajustar los contratos (`ignore_imports` para `public_api`) al crear el primer módulo y dejar `just arch` en verde en CI.

## 6. Transversales
- **Errores:** excepciones de dominio tipadas → manejador global → Problem Details (RFC 9457) con `code` de negocio estable.
- **Transacciones:** `UnitOfWork` abierto en el caso de uso, nunca en el router.
- **Concurrencia:** restricción de exclusión para asignaciones de personal (sin cruces de horario) y bloqueo de filas (`FOR UPDATE`) al descontar lotes de inventario. En `staff`, la restricción `staff_assignments_no_overlap` usa `EXCLUDE USING gist (worker_id WITH =, tstzrange(start_at, end_at, '[)') WITH &&) WHERE (occupies)` y requiere la extensión `btree_gist` (ADR 0005); la aplicación valida el solape solo para devolver un 409 con el evento en conflicto.
- **Idempotencia:** `Idempotency-Key` al registrar pagos y movimientos, y al convertir un contrato en evento.
- **Auditoría:** cada cambio sensible guarda quién, cuándo, qué y el motivo (ledger, contratos, anulaciones, ajustes de inventario, consultas al agente).
- **Tablas append-only:** los historiales que no se corrigen se escriben en tablas de solo inserción protegidas con trigger `BEFORE UPDATE OR DELETE` en PostgreSQL. Ejemplos: `identity_access_log`, `ledger_payments`, `staff_worker_audit` (alta, edición, activación y desactivación de un trabajador con actor y fecha-hora; plan §4 de `032-staff`) y `staff_assignment_audit` (alta, edición y anulación de una asignación con actor, fecha-hora, motivo y, en la edición, valores anteriores y nuevos; HU17).
- **Observabilidad:** logs JSON con `request_id` (structlog), errores a Sentry, `/health` y `/ready`.
- **Seguridad:** authn/authz en `presentation` por permiso; reglas de negocio de autorización en `application`.

## 7. Contrato con el frontend y agente de IA
- **Frontend (repo aparte):** consume `openapi.json`. CI falla ante cambios incompatibles (oasdiff).
- **Agente de IA (`assistant`):** el modelo de lenguaje externo solo elige entre funciones de consulta que el backend expone y autoriza según el rol del usuario. Nunca accede a la base de datos ni tiene acceso de escritura. Cada consulta se registra (ver ADR 0002).

## 8. Decisiones
Cada decisión relevante se registra en `docs/architecture/adr/NNNN-titulo.md`. Ver `0001-decisiones-iniciales.md`.
