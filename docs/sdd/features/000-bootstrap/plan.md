# Plan: Proyecto ejecutable (bootstrap)

- **Spec**: ./spec.md
- **Estado**: borrador

## 1. Módulos y fronteras
- No cambia ningún módulo de negocio. Se crea la base compartida:
  - `src/local_eventos/main.py`: `create_app()` registra los routers y expone el OpenAPI.
  - `src/local_eventos/shared/infrastructure/config.py`: configuración validada desde variables de entorno.
  - `src/local_eventos/shared/infrastructure/db.py`: motor async de SQLAlchemy y comprobación de conexión.
  - `src/local_eventos/shared/presentation/health.py`: endpoints `/health` y `/ready`.
- Los routers de negocio se montarán bajo el prefijo `/v1` a partir de `001-identity`.

## 2. Modelo de dominio
No aplica: no hay entidades ni reglas de negocio en esta feature.

## 3. Casos de uso
| Caso de uso | Tipo | Entrada | Salida | Errores |
|---|---|---|---|---|
| Consultar si la API está viva | query | — | `{"status": "ok"}` | — |
| Consultar si la API está lista | query | — | `{"status": "ready"}` o `{"status": "not_ready"}` | Base de datos no disponible → `not_ready` |

## 4. API (OpenAPI)
| Método y ruta | `operationId` | Respuesta | Permiso |
|---|---|---|---|
| `GET /health` | `health_live` | `200 {"status": "ok"}` siempre que el proceso responda (CA-2) | público |
| `GET /ready` | `health_ready` | `200 {"status": "ready"}` si `SELECT 1` funciona (CA-3); `503 {"status": "not_ready"}` si falla, sin detalles del error (CA-4) | público |
| `GET /openapi.json` | — | Contrato con `info.title = "Darze API"` e `info.version = "1.0.0"` (CA-8) | público |

`/health` y `/ready` quedan fuera de `/v1` porque son de operación, no del contrato con el frontend.

## 5. Persistencia
- Sin tablas. PostgreSQL 17 local con `docker-compose.yml` (servicio `db`, volumen persistente y healthcheck).
- Alembic configurado en modo async (`alembic.ini`, `migrations/env.py`) y sin migraciones: `just migrate` debe ejecutarse sin error.
- Conexión: `DATABASE_URL` con el driver `postgresql+asyncpg`.

## 6. Reglas de negocio aplicadas
Ninguna. Se respetan las reglas técnicas de `AGENTS.md`: sin secretos en el repositorio (CA-9), dependencias solo de `STACK.md` (regla 11) y documentación en el mismo commit (regla 13).

## 7. Estrategia de tests
| CA | Test | Tipo |
|---|---|---|
| CA-2 | `test_ca2_health_responde_sin_base_de_datos` | unitario (comprobación de BD falsa que falla) |
| CA-3 | `test_ca3_ready_con_base_de_datos` | integración (PostgreSQL real con Testcontainers) |
| CA-4 | `test_ca4_ready_sin_base_de_datos_no_expone_detalles` | unitario (comprobación falsa que lanza error) |
| CA-5 | `just check` en verde | comando |
| CA-6 | Workflow `ci.yml` ejecuta `just check` en cada pull request a `main` | CI |
| CA-7 | `test_ca7_dominio_que_importa_fastapi_rompe_la_arquitectura` (copia el código a una carpeta temporal, agrega un import prohibido y verifica que `lint-imports` falla) | arquitectura |
| CA-8 | `test_ca8_openapi_tiene_titulo_y_version` | unitario |
| CA-9 | `test_ca9_env_esta_ignorado_y_existe_env_example` | unitario |
| CA-1 | Seguir `docs/INSTALACION.md` en un clon nuevo (Windows y CI en Linux) | manual + CI |

Los tests de integración usan la marca `integration` y necesitan Docker.

## 8. Riesgos y ADRs
| Riesgo | Mitigación |
|---|---|
| `import-linter` con módulos vacíos o comodines (`*`) mal soportados | Verificar los contratos con `just arch` en la tarea correspondiente; listar los módulos explícitamente si hace falta |
| Diferencias Windows/Linux (rutas, fin de línea) | CI en Linux; `.gitattributes` con `eol=lf`; los comandos se ejecutan con `just` |
| Puerto 5432 ocupado en la máquina | Puerto configurable en `.env` (`POSTGRES_PORT`) |
| Dependencias de `STACK.md` que aún no se usan (`structlog`, `sentry-sdk`, `pwdlib`, `pyjwt`) | No se instalan en bootstrap; entran con la feature que las necesita |

Sin ADR nuevo: todas las herramientas ya están en `STACK.md`.

## 9. Impacto en reporting y documentación
- Sin impacto en `reporting`.
- Se actualizan `docs/INSTALACION.md` (quitar las marcas "se verifica en 000-bootstrap", instalación con `winget` en Windows y `rust-just` en PyPI), `README.md` y `STACK.md` (comandos de instalación corregidos).
- `.gitignore`: `.env`, `.venv/`, `.qodo/`.