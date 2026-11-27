# Plan: Permisos de personal para el encargado de eventos

- **Spec**: ./spec.md
- **Estado**: aprobado por el Product Owner (César Suclupe, 27/11/2026) a partir de la aclaración del cliente

## 1. Decisiones
1. **Nuevo permiso `staff_roster:read`** en `identity/domain/permissions.py`, para `ADMIN` (ya lo recibe por `frozenset(Permission)`) y `EVENTS_MANAGER`. Se quita `staff:manage` a `EVENTS_MANAGER`. Compras sin ninguno.
2. **Rutas de `staff` sin cambio de código**: las de trabajadores y la lectura de asignaciones ya exigen `staff:manage`; la escritura, `staff:assign`. Cambian solo los roles que las tienen. Lo autorizado por Harold (dueño de `staff`): tocar `modules/staff` en un PR aparte para esto.
3. **Ficha del evento (HU14)**: el puerto `EventStaffLookup` de `reporting` se implementa con un adaptador sobre `staff.public_api.event_assignments`. El caso de uso `GetEventSheet` recibe `include_staff` (permiso `staff_roster:read`), igual que `include_account` con `payments:record`. Sin permiso, ni siquiera se consulta a `staff`.
4. `SheetStaffOut` agrega `function` y `function_description` (cambio aditivo; `role` se conserva con el nombre legible).
5. La ficha no tiene PDF (el PDF de `reporting` es solo del exportador de reportes tabulares); no hay nada que ajustar ahí.
6. Sin migraciones.

## 2. Pruebas
- `identity`: matriz de roles con `staff_roster:read` y sin `staff:manage` para eventos.
- `staff`: matrices HU15 y HU17, el encargado de eventos recibe 403.
- `reporting`: la ficha con y sin `staff_roster:read`, nunca con pago; adaptador sobre `event_assignments`.
- Integración: ficha del evento con asignaciones reales.
