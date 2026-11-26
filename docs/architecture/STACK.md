# Stack y dependencias

> Las versiones las fija `uv.lock`. Al crear el proyecto, instalar las versiones vigentes y verificarlas (no copiar números de este documento).
> Regla: no añadir dependencias sin un ADR. Menos piezas = menos mantenimiento.

## Runtime
| Paquete | Para qué |
|---|---|
| `fastapi` + `uvicorn[standard]` | API y servidor ASGI |
| `pydantic` v2 + `pydantic-settings` | Esquemas de borde y configuración validada |
| `sqlalchemy[asyncio]` 2.0 + `asyncpg` | ORM async y driver PostgreSQL |
| `alembic` | Migraciones |
| `pwdlib[argon2]` (o `argon2-cffi`) | Hash de contraseñas |
| `pyjwt` | Tokens de acceso |
| `reportlab` | PDF de cotizaciones (ADR 0004). Sin librerías del sistema: funciona igual en Windows y Docker |
| `structlog` | Logs estructurados |
| `sentry-sdk[fastapi]` | Errores en producción |
| `httpx` | Cliente HTTP del conector `reporting` |

## Desarrollo y calidad
| Herramienta | Para qué |
|---|---|
| `uv` | Entorno, dependencias y lockfile |
| `ruff` | Lint y formato |
| `mypy` (strict) | Tipos |
| `import-linter` | Reglas de arquitectura |
| `pytest`, `pytest-asyncio`, `pytest-cov` | Tests |
| `testcontainers[postgres]` | PostgreSQL real en integración |
| `types-reportlab` | Tipos de ReportLab para que mypy (strict) revise el código del PDF |
| `hypothesis` | Propiedades (ledger, inventario, solapes) |
| `pre-commit` | Hooks locales |
| `just` | Atajos de comandos |

## Documentación
`mkdocs-material` + `mkdocstrings[python]` (docs desde docstrings), `scalar` o `redoc` para el OpenAPI, `release-please` (changelog/versiones), `oasdiff` (cambios incompatibles del contrato).

## Infraestructura
Docker multi-stage (usuario no root, healthcheck) · docker-compose (API + PostgreSQL en local) · GitHub Actions (CI, CD, docs) · GHCR para imágenes · PostgreSQL con backups automáticos.

**Extensión PostgreSQL `btree_gist` (contrib):** el esquema de asignaciones de personal (HU17) la requiere para la restricción de exclusión `staff_assignments_no_overlap`, que garantiza el no solape de horarios (ADR 0005). La migración la crea con `CREATE EXTENSION IF NOT EXISTS btree_gist` y su `downgrade` **no** la elimina (puede usarla otro esquema). No añade una dependencia de Python ni un servicio: es una extensión del motor. `postgres:17-alpine` (local y CI) la incluye; en un PostgreSQL gestionado el administrador puede tener que habilitarla antes del despliegue.

## Por qué se eligió cada tecnología

| Tecnología | Por qué |
|---|---|
| Python 3.12+ | Lenguaje de la API: tipos estrictos, async nativo y ecosistema maduro para FastAPI. |
| FastAPI | API REST tipada; genera OpenAPI/JSON Schema automáticamente, que es el contrato con el frontend (repo aparte). |
| Pydantic v2 (+ pydantic-settings) | Esquemas de borde y configuración validada: una sola fuente de verdad para requests y entorno. |
| SQLAlchemy 2.0 async + asyncpg | ORM async sobre PostgreSQL: permite la restricción de exclusión anti-solape de reservas y los bloqueos de fila que exige el dominio. |
| Alembic | Migraciones: el esquema solo cambia vía migraciones versionadas, nunca editando migraciones aplicadas. |
| PostgreSQL | Persistencia relacional; su restricción de exclusión (`EXCLUDE USING gist` + `btree_gist`) garantiza que un trabajador no tenga dos asignaciones con horarios solapados (RN12, ADR 0005). |
| uv | Entorno, dependencias y `uv.lock`: un solo comando reproducible, mínimo mantenimiento. |
| ruff | Lint y formato en un solo binario: rápido y sin piezas extra. |
| mypy (strict) | Tipos estrictos en todo `src/`: detecta errores sin ejecutar el código. |
| import-linter | Verifica las reglas de arquitectura (capas y módulos independientes) automáticamente en CI. |
| pytest + Testcontainers (+ Hypothesis) | Pirámide de tests: casos de uso sin DB, integración contra PostgreSQL real, propiedades para ledger/inventario. |
| structlog + Sentry | Logs JSON con `request_id` y errores en producción, sin servicios extra. |
| Docker + GitHub Actions | Despliegue reproducible y CI/CD: imagen multi-stage, compose para local, GHCR para imágenes. |
| MkDocs + mkdocstrings | Documentación desde docstrings, sin mantener dos fuentes. |

**Comandos de instalación** (oficiales, una línea cada uno):

```bash
winget install --id=astral-sh.uv -e   # uv en Windows (Linux/macOS: instalador oficial de astral.sh)
winget install --id=Casey.Just -e     # just en Windows (Linux/macOS: uv tool install rust-just)
uv sync                               # instala lo fijado en uv.lock (o: just install)
docker compose up -d db               # PostgreSQL local (o: just up)
uv run pytest -m ""                   # pruebas con integración (o: just test-all)
uv run python -m local_eventos.tools.create_admin  # primer administrador (o: just create-admin)
```

## Decidido que NO se usa
Redis, Celery/BullMQ, Kafka, GraphQL, tRPC, SQLModel, multi-tenant, pasarela de pagos, facturación electrónica.
