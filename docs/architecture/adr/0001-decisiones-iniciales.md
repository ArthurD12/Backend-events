# ADR 0001 — Decisiones iniciales

- **Estado:** aceptada
- **Contexto:** sistema interno para un local de eventos (una organización, ~5 usuarios), que se entrega al cliente y debe operar con mínimo mantenimiento. El frontend está en otro repositorio. Un servicio de IA independiente consumirá datos de forma opcional.

## Decisiones
| Tema | Decisión | Motivo |
|---|---|---|
| Lenguaje y API | Python + FastAPI, REST `/v1` + OpenAPI | El OpenAPI generado es el contrato con el frontend |
| Persistencia | PostgreSQL, SQLAlchemy 2.0 async, Alembic | Dominio separable del ORM; migraciones versionadas |
| Repositorio | Solo backend, sin monorepo; uv + justfile | El frontend vive aparte |
| Infraestructura | Solo PostgreSQL | Menos piezas que operar; sin Redis ni Kafka |
| Eventos internos | En proceso, misma transacción | Un solo despliegue; sin broker |
| Autenticación | JWT corto + refresh rotado (hash en Postgres), Argon2, RBAC por permisos | Revocable sin Redis |
| Multi-tenant | No | Una sola organización |
| Pagos | Sin pasarela; ledger append-only | Los cobros se registran manualmente |
| Facturación electrónica | No | Fuera de alcance |
| Pruebas | pytest, fakes, Testcontainers (Postgres real), import-linter | Detecta errores de concurrencia y de arquitectura |
| Despliegue | Docker + GitHub Actions, VPS pequeño con Compose, backups | Portable y simple |
| Observabilidad | structlog + Sentry | Suficiente para este tamaño |
| i18n, emails, storage, QR/PDF | No | No requeridos |
| Integración con IA | Módulo `reporting` opcional, push incremental e idempotente | Servicio de IA desacoplado y multi-cliente |

## Consecuencias
- El contrato con el frontend se vigila en CI (oasdiff).
- Cualquier dependencia o servicio nuevo requiere un ADR propio.
- Si el sistema se vendiera a más organizaciones, habría que reabrir la decisión de multi-tenant.
