# Flujo SDD (Spec-Driven Development)

La especificación es la fuente de verdad; el código es su consecuencia.

```
/spec  →  spec.md      (QUÉ y POR QUÉ)         ⟶ aprobación humana
/plan  →  plan.md      (CÓMO, técnico)         ⟶ aprobación humana
/tasks →  tasks.md     (pasos atómicos)
/implement → código + tests (un subagente por tarea)
/review → revisión independiente contra spec, dominio y arquitectura
/docs  → documentación de la feature actualizada
```

## Artefactos por feature
`docs/sdd/features/<NNN-slug>/`

| Archivo | Contenido | Dueño |
|---|---|---|
| `spec.md` | Problema, actores, historias, criterios de aceptación (Given/When/Then), fuera de alcance, preguntas abiertas | `spec-writer` |
| `plan.md` | Módulos afectados, modelo de dominio, casos de uso, endpoints, persistencia, riesgos, estrategia de tests | `architect` |
| `tasks.md` | Tareas atómicas ordenadas, con capa, archivos esperados y criterio de hecho | `architect` |

## Reglas
1. Cada criterio de aceptación del spec mapea a al menos un test (con su ID en el nombre).
2. Las preguntas abiertas se resuelven con el humano **antes** de `/plan`. Las reglas de `docs/DOMAIN.md` marcadas "por validar" cuentan como preguntas abiertas.
3. Si algo cambia durante la implementación, se actualiza primero el spec/plan y luego el código.
4. Tareas: una capa y ~5 archivos como máximo; deben caber en una sola sesión de subagente.
5. Orden típico: dominio → aplicación → infraestructura (+ migración) → presentación (API y OpenAPI) → documentación.

## Orden sugerido de features
`000-bootstrap` (proyecto, CI, Docker, import-linter) → `001-identity` (HU01–HU03) → `002-clients` (HU04) → `003-catalog` (HU06) → `004-quotes` (HU07–HU08) → `005-contracts` (HU41–HU42) → `006-events` (HU10–HU11) → `007-staff` → `008-ledger` → `009-inventory` → `010-assistant`. Sigue el cronograma de Sprints del proyecto.
