# Tasks: Permisos de personal para el encargado de eventos

- [x] T-01 [identity] Permiso `staff_roster:read`; quitar `staff:manage` a `EVENTS_MANAGER` — `identity/domain/permissions.py`, `tests/unit/identity/test_user.py`
- [x] T-02 [staff] Actualizar matrices de roles de HU15 y HU17 (el encargado de eventos recibe 403) — `tests/unit/staff/*`
- [x] T-03 [reporting] Adaptador de `EventStaffLookup` sobre `staff.public_api.event_assignments`, `include_staff` por permiso, `function` en el esquema; borrar `NoEventStaff` — `reporting/**`, `tests/unit/reporting/*`
- [x] T-04 [reporting/otros] Revisar otros accesos del encargado de eventos a datos de trabajadores (reporte de personal, asistente) — verificación
- [x] T-05 [docs] DOMAIN.md §5, §9, §11; COORDINACION.md §4; specs 032 y 033 con nota de la decisión
- [x] T-06 [api] `just openapi`, `just check`, `uv run pytest -m integration`
- [x] T-07 [frontend] Sección "Personal" del detalle del evento y personal designado en la ficha
- [x] T-08 [main] Corrección hallada en la prueba en navegador: `GET /v1/staff/assignments` caía en `/v1/staff/{worker_id}` (422) porque el router de trabajadores se registraba antes; se registra primero el de asignaciones — `main.py`, `tests/integration/reporting/test_event_sheet_api_db.py`
