# AGENTS.md — Backend de Darze (catering y eventos)

> Se carga en TODAS las sesiones. Mantenerlo corto (<120 líneas). El detalle vive en `docs/` y en las skills (bajo demanda).

## Contexto
Sistema interno de **Darze**, empresa de catering y organización de eventos que atiende en el lugar que indica el cliente. Flujo central: `cliente → cotización → contrato → evento → personal, materiales y compras → pagos`. Usuarios: administrador, encargado de eventos, encargado de compras y almacén.
- **Una sola organización.** Instalación única que se entrega al cliente y debe funcionar con **mínimo mantenimiento**.
- El frontend (Next.js + TypeScript + Tailwind) vive en **otro repositorio** y consume el OpenAPI de este.
- El agente de IA es un **módulo del backend** (`assistant`) **solo de consulta**: usa funciones controladas de otros módulos (nunca la base de datos directa), respeta el rol del usuario y registra cada consulta. El modelo de lenguaje es un proveedor externo detrás de un puerto. Ver ADR 0002.
- Sin pasarela de pagos ni facturación electrónica: los cobros se **registran** en el ledger.

## Stack
Python 3.12+ · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async (asyncpg) · Alembic · PostgreSQL · uv · ruff · mypy (strict) · pytest (+ Testcontainers) · import-linter · structlog + Sentry · Docker + GitHub Actions.
Sin Redis, Celery ni Kafka. Detalle y dependencias: `docs/architecture/STACK.md`.

## Mapa del repo
- `src/local_eventos/` → código (`shared/` + `modules/<modulo>/`). Estructura: `docs/architecture/ARCHITECTURE.md`
- `docs/DOMAIN.md` → reglas de negocio, glosario, roles y permisos
- `docs/sdd/` → flujo SDD; cada feature en `docs/sdd/features/<NNN-slug>/{spec,plan,tasks}.md`
- `docs/operations/` → runbook y checklist de entrega
- `.opencode/{agent,skill,command}/` → agentes, skills y comandos (`/spec /plan /tasks /implement /review /docs`)

## Reglas no negociables
1. Sin `spec.md` y `plan.md` aprobados por el humano **no se implementa**.
2. Dependencias: `presentation → application → domain`; `infrastructure → application/domain`. El dominio no importa FastAPI, SQLAlchemy ni Pydantic.
3. Un módulo solo usa a otro por su `public_api`. Nunca sus capas internas, tablas ni modelos ORM. Sin FKs entre módulos (IDs como referencia).
4. Dinero en enteros (céntimos) + moneda (`PEN`). Fechas `timestamptz` en UTC; la zona `America/Lima` solo en presentación.
5. **Ledger e inventario son append-only**: se corrige con reversión o ajuste, nunca con UPDATE/DELETE.
6. Los precios se **congelan en la cotización**: cambiar el catálogo no altera cotizaciones, contratos ni eventos existentes.
7. Un trabajador no puede tener dos asignaciones con horarios superpuestos: lo garantiza una restricción en PostgreSQL, no solo el código.
8. Esquema solo vía Alembic; nunca editar migraciones aplicadas.
9. El OpenAPI es el contrato con el frontend: `operationId` estables, `openapi.json` versionado, sin cambios incompatibles dentro de `/v1`.
10. Todo cambio de comportamiento lleva test. Los casos de uso se testean sin base de datos.
11. Mínimo mantenimiento: no añadir dependencias ni servicios sin un ADR.
12. Ediciones puntuales; no reescribir archivos completos para cambios pequeños.
13. Toda dependencia, herramienta o comando nuevo se documenta en `STACK.md`, `README.md` e `INSTALACION.md` en el mismo commit.

## Trabajo con agentes (ahorro de contexto)
- La sesión principal **orquesta**, no implementa. Delega con un brief corto y exige un **resumen ≤ 15 líneas** (qué cambió, archivos, comandos ejecutados, riesgos).
- Los subagentes leen solo: su tarea en `tasks.md`, las secciones del plan que aplican, su módulo y la skill relevante.
- Una tarea de `tasks.md` = un subagente = un commit.
- No pegar archivos grandes en el chat; referenciar por ruta.
- **Pregunta antes de asumir** cuando falte una regla de negocio; no inventes políticas (cancelaciones, descuentos, costos).

## Comandos (justfile)
`just check` (ruff + mypy + lint-imports + pytest) · `just test` · `just lint` · `just types` · `just arch` · `just migrate` · `just openapi` (exporta openapi.json) · `just docs`

## Definición de hecho
`just check` en verde, criterios de aceptación cubiertos por tests, `openapi.json` regenerado si cambió la API, documentación de la feature actualizada (`docs-writer`), resumen entregado al orquestador.
