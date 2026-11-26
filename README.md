# Backend de Darze (catering y eventos)

Backend interno de **Darze**, empresa de catering y organización de eventos (San Juan de Lurigancho, Lima).
Centraliza el flujo `cliente → cotización → contrato → evento`, la asignación de personal, el almacén,
los requerimientos y compras, y los pagos. Los cobros se **registran** en un ledger
(sin pasarela de pagos ni facturación electrónica).

Es un **monolito modular** con Clean Architecture en Python: un solo despliegue
(API FastAPI + PostgreSQL), dividido en módulos de negocio con fronteras estrictas
(`presentation → application → domain`; `infrastructure → application/domain`).
Ver `docs/architecture/ARCHITECTURE.md` y `docs/DOMAIN.md`.
Nace para **una sola organización**, con mínimo mantenimiento.

El frontend (Next.js + TypeScript + Tailwind) vive en **otro repositorio** y consume
el OpenAPI de este. El agente de IA es un módulo del backend (`assistant`), solo de consulta,
que usa funciones controladas de los demás módulos (ver ADR 0002).

## Stack

Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async (asyncpg) · Alembic · PostgreSQL ·
uv · ruff · mypy (strict) · pytest (+ Testcontainers) · import-linter · structlog + Sentry ·
ReportLab (PDF de cotizaciones, ADR 0004) · Docker + GitHub Actions. **Sin** Redis, Celery ni Kafka.

Las versiones concretas las fijan `pyproject.toml` y `uv.lock`; este README no fija versiones.

Detalle, justificación y comandos de instalación de cada tecnología: `docs/architecture/STACK.md`.

**Requisito de PostgreSQL:** el esquema de asignaciones de personal usa la extensión `btree_gist` (contrib) para garantizar que un trabajador no tenga horarios solapados. La migración la crea (`CREATE EXTENSION IF NOT EXISTS btree_gist`); `postgres:17-alpine` (local y CI) ya la incluye. En un PostgreSQL gestionado, pide al administrador que la habilite antes de migrar; no se degrada a validación solo en la aplicación (ADR 0005).

## Requisitos previos

- `uv` (instala Python 3.12, el entorno, las dependencias y el lockfile)
- `just` (atajos de comandos)
- Docker + Docker Compose (PostgreSQL local y tests de integración)
- Un clon de este repositorio

Guía paso a paso desde cero: [`docs/INSTALACION.md`](docs/INSTALACION.md).

## Instalación

```bash
cp .env.example .env        # Windows: copy .env.example .env (y cambia la clave)
just install                # uv sync
just up                     # docker compose up -d db
just migrate                # alembic upgrade head
just create-admin           # primer administrador (una sola vez)
```

## Cómo ejecutar

```bash
just dev   # uv run fastapi dev src/local_eventos/main.py
```

Comprueba http://localhost:8000/health (`ok`), http://localhost:8000/ready (`ready`) y http://localhost:8000/docs.

## Cómo correr tests y calidad

```bash
just test     # pruebas unitarias (sin Docker)
just test-all # unitarias + integración con PostgreSQL real (necesita Docker)
just check    # ruff + mypy + lint-imports + pruebas unitarias
just lint     # ruff check + formato
just types    # mypy strict
just arch     # import-linter
```

Ver todos los atajos con `just --list`. Lista completa y significado en el `justfile`.
Comandos adicionales: `just migrate` / `just migration <nombre>` (Alembic),
`just openapi` (exporta `openapi.json`), `just create-admin` (primer administrador),
`just docs` (MkDocs), `just fmt`.

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
│  └─ modules/               # identity, commercial, catalog, staff, ledger, inventory, purchasing, reporting, assistant
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
- [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) — publicación gratuita en Neon, Render y Vercel.
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
Orden sugerido de arranque (según el cronograma de Sprints): `000-bootstrap` → identity → commercial (clientes) →
catalog → commercial (cotizaciones, contratos, eventos) → staff → ledger → inventory → assistant.
