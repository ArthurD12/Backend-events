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
│     ├─ identity/           # usuarios, roles, auth
│     ├─ venues/             # salones (uno por piso), capacidad, tarifa/hora, buffers
│     ├─ clients/            # clientes y contactos
│     ├─ catalog/            # paquetes, servicios, insumos (definiciones y precios)
│     ├─ bookings/           # cotización → reserva → evento; ítems contratados
│     ├─ inventory/          # lotes perecibles, movimientos, consumo por evento
│     ├─ ledger/             # movimientos de caja, cobros, saldos
│     └─ reporting/          # conector opcional hacia el servicio de IA
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
1. **Consulta síncrona** por `public_api` (p. ej. `bookings` pregunta a `venues` por la disponibilidad o tarifa de un salón).
2. **Eventos de dominio en proceso** (p. ej. `ReservationConfirmed`, `EventClosed`) despachados dentro de la misma transacción. Sin broker externo.
3. **Prohibido:** importar capas internas de otro módulo, joins SQL entre tablas de módulos distintos, FKs entre módulos.
4. **Datos:** prefijo de tablas por módulo (`bookings_*`, `inventory_*`, `ledger_*`).
5. **Excepción controlada:** el esquema `reporting` expone **vistas estables** de solo lectura para el conector de IA; es el único lugar donde se cruzan datos de varios módulos.

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
    local_eventos.modules.venues
    local_eventos.modules.clients
    local_eventos.modules.catalog
    local_eventos.modules.bookings
    local_eventos.modules.inventory
    local_eventos.modules.ledger
    local_eventos.modules.reporting
```
> Es un punto de partida: el agente `architect` debe ajustar los contratos (`ignore_imports` para `public_api`) al crear el primer módulo y dejar `just arch` en verde en CI.

## 6. Transversales
- **Errores:** excepciones de dominio tipadas → manejador global → Problem Details (RFC 9457) con `code` de negocio estable.
- **Transacciones:** `UnitOfWork` abierto en el caso de uso, nunca en el router.
- **Concurrencia:** restricción de exclusión para reservas; bloqueo de filas (`FOR UPDATE`) al descontar lotes de inventario.
- **Idempotencia:** `Idempotency-Key` al registrar movimientos y crear reservas.
- **Auditoría:** cada cambio sensible guarda quién, cuándo y qué (ledger, reservas, ajustes de inventario).
- **Observabilidad:** logs JSON con `request_id` (structlog), errores a Sentry, `/health` y `/ready`.
- **Seguridad:** authn/authz en `presentation` por permiso; reglas de negocio de autorización en `application`.

## 7. Contrato con el frontend y con el servicio de IA
- **Frontend (repo aparte):** consume `openapi.json`. CI falla ante cambios incompatibles (oasdiff).
- **Servicio de IA:** el módulo `reporting` envía datos incrementales e idempotentes (push) con una clave de integración rotable. Es **opcional** y se activa por configuración. Nunca recibe acceso de escritura.

## 8. Decisiones
Cada decisión relevante se registra en `docs/architecture/adr/NNNN-titulo.md`. Ver `0001-decisiones-iniciales.md`.
