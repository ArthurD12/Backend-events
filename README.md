# Backend del Local de Eventos

Backend interno de un local de eventos (matrimonios, cumpleaños, promociones).
Un edificio con varios salones —uno por piso, **no divisibles**— que se alquilan **por horas**,
y un solo punto de venta. Todo lo que se vende está ligado a una reserva; los cobros se **registran**
en un ledger (sin pasarela de pagos ni facturación electrónica).

Es un **monolito modular** con Clean Architecture en Python: un solo despliegue
(API FastAPI + PostgreSQL), dividido en módulos de negocio con fronteras estrictas
(`presentation → application → domain`; `infrastructure → application/domain`).
Ver `docs/architecture/ARCHITECTURE.md` y `docs/DOMAIN.md`.
Nace para **una sola organización**, con mínimo mantenimiento.

El frontend (Next.js + TypeScript + Tailwind) vive en **otro repositorio** y consume
el OpenAPI de este. El módulo de IA es un servicio aparte y opcional:
este backend solo le envía datos mediante el módulo `reporting`.

## Stack

Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async (asyncpg) · Alembic · PostgreSQL ·
uv · ruff · mypy (strict) · pytest (+ Testcontainers) · import-linter · structlog + Sentry ·
Docker + GitHub Actions. **Sin** Redis, Celery ni Kafka.

Las versiones concretas las fija `uv.lock` / `pyproject` cuando exista —se verifica en 000-bootstrap—;
este README no fija versiones.

Detalle, justificación y comandos de instalación de cada tecnología: `docs/architecture/STACK.md`.

## Requisitos previos

- Python 3.12 o superior
- `uv` (entorno, dependencias y lockfile)
- `just` (atajos de comandos)
- Docker + Docker Compose (PostgreSQL local y tests de integración)
- Un clon de este repositorio

Guía paso a paso desde cero: [`docs/INSTALACION.md`](docs/INSTALACION.md).

## Instalación

> **se verifica en 000-bootstrap**: `pyproject.toml`, `docker-compose.yml` y `.env.example` aún no existen;
> los pasos que dependen de ellos se marcan en `docs/INSTALACION.md`.

```bash
cp .env.example .env        # se verifica en 000-bootstrap
docker compose up -d db     # o: just up
just install                # uv sync
just migrate                # alembic upgrade head
```

## Cómo ejecutar

```bash
just dev   # uv run fastapi dev src/local_eventos/main.py
```

> **se verifica en 000-bootstrap**: la app runnable aún no existe.

## Cómo correr tests y calidad

```bash
just test     # pytest
just check    # ruff + mypy + lint-imports + pytest
just lint     # ruff check + formato
just types    # mypy strict
just arch     # import-linter
```

Ver todos los atajos con `just --list`. Lista completa y significado en el `justfile`.
Comandos adicionales: `just migrate` / `just migration <nombre>` (Alembic),
`just openapi` (exporta `openapi.json`), `just docs` (MkDocs), `just fmt`.

## Estructura del repositorio

Resumen de `docs/architecture/ARCHITECTURE.md` §2 (repositorio) y §3 (un módulo).
La versión completa y vigente está en ese documento:

```
.
├─ AGENTS.md · justfile · pyproject.toml · uv.lock · Dockerfile · docker-compose.yml · openapi.json
├─ .github/workflows/        # CI, CD, docs, release
├─ .opencode/                # agentes, skills y comandos (/spec, /plan, ...)
├─ docs/
│  ├─ DOMAIN.md              # reglas de negocio, glosario, roles
│  ├─ architecture/          # ARCHITECTURE.md · STACK.md · adr/
│  ├─ sdd/                   # flujo SDD y features/<NNN-slug>/
│  └─ operations/            # RUNBOOK.md · HANDOVER.md
├─ migrations/               # Alembic (esquema solo vía migraciones)
├─ src/local_eventos/
│  ├─ main.py                # create_app(): routers, middlewares, errores
│  ├─ shared/                # domain / application / infrastructure transversales
│  └─ modules/               # identity, venues, clients, catalog, bookings, inventory, ledger, reporting
└─ tests/                    # unit, integration (Postgres real), architecture
```

Cada módulo tiene la misma estructura (§3 de ARCHITECTURE.md):

```
modules/<modulo>/
├─ public_api.py       # ÚNICA superficie visible para otros módulos
├─ domain/             # entidades y reglas (Python puro, sin FastAPI/SQLAlchemy/Pydantic)
├─ application/        # casos de uso y puertos
├─ infrastructure/     # modelos ORM, repositorios, adaptadores
├─ presentation/       # router, esquemas Pydantic, dependencias (auth, DI)
└─ composition.py      # ensamblaje: casos de uso + adaptadores
```

Un módulo solo usa a otro por su `public_api`: nunca sus capas internas, tablas ni modelos ORM,
y sin claves foráneas entre módulos (los IDs se usan como referencia).

## Documentación

- [`docs/DOMAIN.md`](docs/DOMAIN.md) — reglas de negocio, glosario, roles y permisos.
- [`docs/architecture/ARCHITECTURE.md`](docs/architecture/ARCHITECTURE.md) — arquitectura del monolito modular.
- [`docs/architecture/STACK.md`](docs/architecture/STACK.md) — stack, por qué se eligió y cómo instalarlo.
- [`docs/INSTALACION.md`](docs/INSTALACION.md) — instalación paso a paso desde cero.
- [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) — ramas, commits, versionado y flujo SDD.
- [`docs/operations/RUNBOOK.md`](docs/operations/RUNBOOK.md) — operación y entrega.
- [`docs/architecture/adr/`](docs/architecture/adr/) — decisiones de arquitectura (ADR).

## Flujo SDD (Spec-Driven Development)

Sin `spec.md` y `plan.md` aprobados por el humano **no se implementa** (ver `AGENTS.md`).

```
/spec <feature>     → spec.md (qué y por qué), aprobado por el humano
/plan <NNN-slug>    → plan.md, aprobado por el humano
/tasks <NNN-slug>   → tasks.md (una tarea = un subagente = un commit)
/implement <NNN-slug>
/review <NNN-slug>
/docs <NNN-slug>    → documenta la feature cerrada
```

Cada feature vive en `docs/sdd/features/<NNN-slug>/{spec,plan,tasks}.md`.
Orden sugerido de arranque: `000-bootstrap` → identity → venues → clients → catalog → bookings →
ledger → inventory → reporting.
