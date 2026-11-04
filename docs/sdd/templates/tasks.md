# Tasks: <título>

Formato: `- [ ] T-NN [capa] descripción — archivos — hecho cuando …`
Una tarea = un subagente = un commit. Marcar `[P]` si puede ir en paralelo.

- [ ] T-01 [domain] Entidades/agregado + invariantes + tests unitarios — `modules/<m>/domain/**` — `pytest tests/unit/<m>` verde
- [ ] T-02 [application] Casos de uso + puertos + tests con fakes — `modules/<m>/application/**`
- [ ] T-03 [infra] Modelos ORM + repositorio + migración Alembic + test de integración — `modules/<m>/infrastructure/**`, `migrations/versions/**`
- [ ] T-04 [presentation] Router + esquemas Pydantic + permisos + test de API — `modules/<m>/presentation/**`
- [ ] T-05 [openapi] Regenerar `openapi.json` y verificar sin cambios incompatibles
- [ ] T-06 [docs] Docstrings, página del módulo y ADR si aplica — `docs/**`
