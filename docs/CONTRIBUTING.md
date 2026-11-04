# Contribuir al Backend del Local de Eventos

Guía breve para quien desarrolla en este repositorio. Las reglas permanentes y cortas viven en
[`AGENTS.md`](../AGENTS.md) — este documento no las repite, solo explica cómo trabajar.

## 1. Ramas

Nombra cada rama según el tipo de cambio y el tema, en minúsculas y con guiones:

| Prefijo | Para qué | Ejemplo |
|---|---|---|
| `feat/` | Una feature nueva (o un módulo nuevo) | `feat/bookings-reserva` |
| `fix/` | Corrección de un defecto | `fix/ledger-reversion` |
| `chore/` | Tareas de mantenimiento (dependencias, CI, tooling) | `chore/subir-uv` |
| `docs/` | Solo documentación | `docs/sdd-000-bootstrap` |

Una rama = una feature o un cambio acotado. No mezcles módulos distintos en la misma rama.

## 2. Mensajes de commit (Conventional Commits)

Formato: `tipo(alcance): descripción breve en imperativo`.

Tipos habituales: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `build`, `ci`.

```text
feat(bookings): bloquea rango de horas al reservar
fix(ledger): revierte cobro con movimiento inverso
docs(sdd): agrega spec 000-bootstrap
```

Una tarea de `tasks.md` = un subagente = **un commit**. Mantén las ediciones puntuales:
no reescribas archivos completos para cambios pequeños.

## 3. Versionado semántico con tags

- Se usa **versionado semántico** (SemVer): `v1.2.3` = `MAJOR.MINOR.PATCH`.
  - **PATCH**: corrección compatible (solo `fix/`).
  - **MINOR**: funcionalidad nueva compatible (solo `feat/`).
  - **MAJOR**: cambio incompatible de API o de esquema (viene con migración y ADR).
- Cada release se marca con un **tag** Git (`v1.2.3`). El changelog se genera con `release-please`
  (ver `docs/architecture/STACK.md`).
- Dentro de `/v1` no se hacen cambios incompatibles del contrato OpenAPI (`operationId` estables,
  `openapi.json` versionado; ver `AGENTS.md` regla 9). Un cambio incompatible obliga a major.

## 4. Flujo SDD: `/spec /plan /tasks /implement /review /docs`

El desarrollo es **Spec-Driven**: cada feature pasa por estas fases, en este orden, con la aprobación
del humano antes de escribir código (ver `AGENTS.md` regla 1).

| Comando | Qué produce | Quién aprueba |
|---|---|---|
| `/spec <feature>` | `docs/sdd/features/<NNN-slug>/spec.md` (qué y por qué, sin decisiones técnicas) | Humano |
| `/plan <NNN-slug>` | `plan.md` (diseño técnico) | Humano |
| `/tasks <NNN-slug>` | `tasks.md` (tareas numeradas, una por capa/módulo) | Humano |
| `/implement <NNN-slug>` | Código de **una** tarea (`tasks.md`) por subagente | — |
| `/review <NNN-slug>` | Revisión independiente del diff contra spec, plan y dominio | — |
| `/docs <NNN-slug>` | Documentación de la feature: docstrings, página del módulo, ADR si hubo decisión, `openapi.json` regenerado | — |

Reglas de trabajo con agentes (ver `AGENTS.md`): la sesión principal **orquesta**, no implementa;
cada subagente lee solo su tarea, las secciones del plan que aplican, su módulo y la skill relevante.

**Definición de hecho**: `just check` en verde, criterios de aceptación cubiertos por tests,
`openapi.json` regenerado si cambió la API, y documentación de la feature actualizada.

## 5. Dependencias nuevas

Toda dependencia, herramienta o comando nuevo se documenta en `STACK.md`, `README.md` e
`INSTALACION.md` en el mismo commit (ver `AGENTS.md` regla 13). Sin un ADR no se añaden servicios
ni dependencias (ver `AGENTS.md` regla 11).
