# Tasks: Personal, disponibilidad y asignaciones

Formato: `- [ ] T-NN [capa] descripción — archivos — hecho cuando …`

- [x] T-01 [domain] `Worker`, `Period`, `Unavailability`, `Assignment`, `Availability` + tests — `modules/staff/domain/**` — tests unitarios verdes
- [x] T-02 [application] Casos de uso y puertos (repos, `EventLookup`, reloj) + tests con fakes — `modules/staff/application/**`
- [ ] T-03 [commercial] `commercial.public_api.event_lookup` + puerto `AssignmentReleaser` en `CancelEvent` (R-STF-5) + tests — `modules/commercial/**`
- [x] T-04 [identity] Permisos `staff:manage` y `staff:read` + test de roles — `modules/identity/domain/permissions.py`
- [x] T-05 [infra] ORM, repositorios, migración (btree_gist + EXCLUDE) + tests de integración — `modules/staff/infrastructure/**`, `migrations/versions/**`
- [ ] T-06 [presentation] Routers, esquemas, errores, registro en la app + tests de API — `modules/staff/presentation/**`
- [ ] T-07 [openapi+docs] `just openapi`; DOMAIN.md §5 y §11 (R-STF-1..7); ARCHITECTURE.md — `openapi.json`, `docs/**`
- [ ] T-08 [frontend] Personal, disponibilidad y sección de asignaciones en el evento — repo `Frontend-events`
