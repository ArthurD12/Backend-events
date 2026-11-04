---
name: sdd-workflow
description: Flujo Spec-Driven Development del proyecto: fases, artefactos, plantillas y criterios de calidad de spec, plan y tasks. Úsala al redactar o revisar spec.md, plan.md o tasks.md.
---

# SDD workflow

## Fases y puertas de aprobación
`spec` → (humano aprueba) → `plan` → (humano aprueba) → `tasks` → `implement` → `review`.

## Calidad de un buen spec
- Describe comportamiento observable, no implementación.
- Cada criterio es verificable por un test (Given/When/Then).
- Incluye casos borde y errores, no solo el camino feliz.
- Fuera de alcance explícito. Sin preguntas abiertas al aprobar.

## Calidad de un buen plan
- Cada CA mapea a un caso de uso y a un test.
- Contratos y eventos definidos antes de la implementación.
- Riesgos identificados con mitigación.

## Calidad de buenas tasks
- Atómicas: una capa, ≤ ~5 archivos, ejecutables en una sesión.
- Orden por dependencias; marcar `[P]` las paralelizables.
- Criterio de hecho medible (qué test o comando debe pasar).

## Plantillas
`docs/sdd/templates/{spec,plan,tasks}.md`

## Si algo cambia en implementación
Actualiza primero spec/plan, luego el código. Registra decisiones relevantes como ADR.
