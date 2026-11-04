---
name: backend-conventions
description: Convenciones FastAPI/Pydantic del proyecto: routers por módulo, OpenAPI estable, errores Problem Details, auth JWT con refresh rotado, permisos, paginación, idempotencia, logging, configuración y conector reporting.
---

# Convenciones de backend (FastAPI)

## Aplicación
- `create_app()` en `main.py`: monta un router por módulo con prefijo `/v1/<modulo>`, middlewares (request_id, CORS solo al origen del frontend) y manejadores de errores.
- Configuración con `pydantic-settings`, validada al arrancar; ningún `os.environ` suelto.
- Todo `async`; sin llamadas bloqueantes dentro de rutas.
- `/health` (proceso vivo) y `/ready` (con base de datos).

## API y OpenAPI
- Rutas REST en plural. `operationId` **explícito y estable** (`bookings_create`, `ledger_register_entry`): los clientes generados se nombran con él.
- Esquemas Pydantic solo en `presentation`; `response_model` siempre declarado; sin exponer campos internos.
- Errores en Problem Details (RFC 9457): `type`, `title`, `status`, `detail`, `code` de negocio estable (p. ej. `booking.overlap`).
- Paginación por cursor en listados; filtros y orden explícitos.
- `Idempotency-Key` en la creación de reservas y el registro de movimientos.
- `openapi.json` exportado y versionado; cambios incompatibles solo en una versión nueva.

## Autenticación y permisos
- Contraseñas con Argon2. Access JWT corto (~15 min) + refresh opaco con **rotación**, guardado **hasheado** en PostgreSQL y revocable; si se reutiliza un refresh ya rotado, se invalida la familia.
- Autorización por **permiso** (`bookings:create`, `ledger:reverse`, `inventory:adjust`) mediante una dependencia `require_permission(...)`; los roles solo agrupan permisos. Matriz en `docs/DOMAIN.md`.
- Limitar intentos de login (contador en base de datos o memoria; hay una sola instancia).
- Nunca registrar contraseñas, tokens ni datos personales en logs.

## Persistencia
- Una sesión por request mediante `UnitOfWork`; repositorios por agregado.
- Consultas de lectura pueden ser SQL directo a DTOs.
- Ver skill `db-migrations` para esquema y constraints.

## Observabilidad
- `structlog` en JSON con `request_id`; excepciones no controladas a Sentry; sin PII.

## Conector `reporting` (servicio de IA)
- Opcional, activado por configuración. Puerto `AnalyticsExporter` con adaptador HTTP.
- Envío incremental por lotes, idempotente (IDs estables), con reintentos y clave de integración rotable.
- Solo lectura de vistas versionadas del esquema `reporting`; nunca escribe en el sistema.
