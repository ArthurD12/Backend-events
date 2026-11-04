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
| `hypothesis` | Propiedades (ledger, inventario, solapes) |
| `pre-commit` | Hooks locales |
| `just` | Atajos de comandos |

## Documentación
`mkdocs-material` + `mkdocstrings[python]` (docs desde docstrings), `scalar` o `redoc` para el OpenAPI, `release-please` (changelog/versiones), `oasdiff` (cambios incompatibles del contrato).

## Infraestructura
Docker multi-stage (usuario no root, healthcheck) · docker-compose (API + PostgreSQL en local) · GitHub Actions (CI, CD, docs) · GHCR para imágenes · PostgreSQL con backups automáticos.

## Por qué se eligió cada tecnología

> **se verifica en 000-bootstrap**: estas justificaciones describen la decisión ya tomada en este
> documento; la instalación y configuración reales (pyproject, compose, CI) se verifican en 000-bootstrap.

| Tecnología | Por qué |
|---|---|
| Python 3.12+ | Lenguaje de la API: tipos estrictos, async nativo y ecosistema maduro para FastAPI. |
| FastAPI | API REST tipada; genera OpenAPI/JSON Schema automáticamente, que es el contrato con el frontend (repo aparte). |
| Pydantic v2 (+ pydantic-settings) | Esquemas de borde y configuración validada: una sola fuente de verdad para requests y entorno. |
| SQLAlchemy 2.0 async + asyncpg | ORM async sobre PostgreSQL: permite la restricción de exclusión anti-solape de reservas y los bloqueos de fila que exige el dominio. |
| Alembic | Migraciones: el esquema solo cambia vía migraciones versionadas, nunca editando migraciones aplicadas. |
| PostgreSQL | Persistencia relacional; su restricción de exclusión (`EXCLUDE USING gist`) garantiza que una sala no tenga dos reservas solapadas. |
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
pipx install uv                # entorno, dependencias y lockfile
uv sync                        # instala lo fijado en uv.lock (o: just install)
pipx install just              # atajos de comandos (just check, just test, just dev, ...)
pipx install ruff              # lint y formato (en el repo se ejecuta vía uv run ruff)
docker compose up -d db        # PostgreSQL local (o: just up) — se verifica en 000-bootstrap
```

## Decidido que NO se usa
Redis, Celery/BullMQ, Kafka, GraphQL, tRPC, SQLModel, multi-tenant, pasarela de pagos, facturación electrónica.
