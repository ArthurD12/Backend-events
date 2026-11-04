---
description: Implementa tareas de tasks.md con subagentes (fase 4 SDD)
agent: orchestrator
---

Implementa la feature: $ARGUMENTS

1. Lee solo `tasks.md` de la feature (no leas código).
2. Toma la siguiente tarea pendiente (o las `[P]` independientes en paralelo) y delégala al subagente de la capa correspondiente con un brief corto: ID de tarea, rutas de spec/plan, restricciones.
3. Exige resumen ≤ 15 líneas con comandos de verificación ejecutados y resultado.
4. Marca la tarea completada y continúa. Detente y consúltame ante cualquier ambigüedad o desviación del plan.
5. Al terminar todas las tareas, ejecuta `/review`.
