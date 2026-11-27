# Spec: Permisos de personal para el encargado de eventos (ventas)

- **ID**: 025-sales-staff-permissions
- **Estado**: aprobado por el Product Owner (César Suclupe, 27/11/2026) a partir de la aclaración del cliente
- **Módulos afectados**: `identity` (permisos), `staff` (rutas y lectura pública), `reporting` (ficha del evento, HU14), frontend (menú y detalle del evento)
- **Historias**: modifica HU15 (#16), HU17 (#18) y HU14 (#15); completa el punto de conexión HU14 ↔ `staff.public_api`

## 1. Problema y objetivo
Aclaración del cliente: *"El encargado de eventos es de ventas. NO puede ver datos de trabajadores ni cuánto se les paga; solo puede ver quién está designado en un evento."* Hoy el encargado de eventos tiene `staff:manage` (HU15, ficha completa del trabajador con documento, teléfono y tarifa) y, en la rama de HU17, lee asignaciones con el pago acordado. Eso contradice al cliente.

El objetivo es que el personal (trabajadores, tarifas, pagos y asignaciones con pago) sea **solo del administrador**, y que el encargado de eventos vea únicamente **quién está designado en un evento y con qué función**.

## 2. Actores
- **Administrador**: gestiona personal, registra/edita/anula asignaciones y ve el pago acordado; ve también el personal designado.
- **Encargado de eventos** (ventas): ve el personal designado de un evento (nombre del trabajador y función). Nada más del personal.
- **Encargado de compras y almacén**: sin acceso a personal; ve la ficha del evento **sin** la sección de personal.

## 3. Criterios de aceptación
- **CA-25.1**: Existe el permiso `staff_roster:read` ("personal designado por evento, solo lectura"), concedido a administrador y encargado de eventos; compras no lo tiene.
- **CA-25.2**: `staff:manage` queda solo para el administrador. El encargado de eventos recibe **403** en todas las rutas de trabajadores (HU15) y en las de lectura de asignaciones (HU17, que incluyen el pago). La escritura sigue en `staff:assign` (solo administrador).
- **CA-25.3**: La ficha consolidada del evento (`GET /v1/reports/events/{id}/sheet`) incluye el bloque `staff` (trabajador, función, horario; **nunca pago, documento, teléfono ni tarifa**) solo si el usuario tiene `staff_roster:read`. Sin el permiso (compras), `staff` es `null` y el frontend no muestra la sección.
- **CA-25.4**: El bloque `staff` se arma con `staff.public_api.event_assignments` (solo asignaciones vigentes); se elimina el adaptador nulo `NoEventStaff`. Un evento sin asignaciones devuelve lista vacía para quien tiene el permiso.
- **CA-25.5**: El reporte de personal (`GET /v1/reports/staff`, HU32) exige `staff:manage` y por tanto queda solo para el administrador. El asistente de IA no tiene herramientas de personal y no se agregan.
- **CA-25.6**: Frontend: el menú "Personal" y la pantalla `/personal` solo con `staff:manage`; en el detalle del evento, la sección "Personal" muestra al administrador la lista con pago y las acciones Asignar/Editar/Anular, y al encargado de eventos solo nombre y función, sin pagos ni botones.

## 4. Fuera de alcance
- Cambios de datos o migraciones (no se requieren: los permisos son una tabla en código).
- Historial laboral por trabajador (HU18) y disponibilidad (HU16): quedan solo para el administrador (`staff:manage`).
