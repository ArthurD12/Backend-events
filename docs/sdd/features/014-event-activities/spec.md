# Spec: Actividades y observaciones del evento

- **ID**: 014-event-activities
- **Estado**: borrador
- **Módulos afectados**: `commercial` (submódulo `events`), `identity` (nombre del usuario y permisos, por su `public_api`)
- **Historia**: HU13 (#14)

## 1. Problema y objetivo
Entre la firma y el día del evento, el encargado prepara muchas cosas (confirmar la vajilla, llamar al local, probar el menú) y anota indicaciones del cliente. Hoy eso queda en cuadernos o chats y se pierde. El objetivo es que cada evento tenga su **lista de actividades** (pendiente / completada) y su **bitácora de observaciones**, con quién y cuándo registró cada cosa.

## 2. Actores
- **Administrador** y **encargado de eventos** (`events:manage`): registran actividades y observaciones y marcan actividades.
- **Encargado de compras y almacén** (`events:read`): solo consulta (DOMAIN.md §9).

## 3. Historia
- **HU13**: Como encargado de eventos, quiero registrar actividades, indicaciones y observaciones para dar seguimiento a la preparación del servicio.

## 4. Criterios de aceptación
- **CA-13.1**: Un usuario con `events:manage` registra una **actividad o indicación** en un evento: texto obligatorio, hasta 200 caracteres. Nace **pendiente**.
- **CA-13.2**: Cada actividad y cada observación guarda **quién la registró y cuándo** (fecha y hora; se muestra en hora de Lima).
- **CA-13.3**: Una actividad se marca **completada** y se puede volver a **pendiente**. Cada cambio guarda quién y cuándo; la actividad muestra quién la completó y cuándo.
- **CA-13.4**: Un usuario con `events:manage` agrega **observaciones**: texto obligatorio, hasta 1000 caracteres.
- **CA-13.5**: Actividades y observaciones quedan **asociadas a su evento** y se consultan en el detalle del evento: actividades por orden de creación; observaciones de la más reciente a la más antigua.
- **CA-13.6**: Un usuario con solo `events:read` las ve pero no las crea ni las cambia (`auth.forbidden`).
- **CA-13.7**: En un evento **cancelado** o **finalizado** no se agregan actividades ni observaciones ni se cambia su estado; se siguen viendo (ver R-ACT-2).

## 5. Reglas
- **R-ACT-1** *(propuesta del equipo, a validar)*: las **observaciones son una bitácora**: no se editan ni se eliminan. Para corregir, se agrega otra observación (RN03).
- **R-ACT-2** *(propuesta, a validar)*: se registra en estado programado, confirmado y en ejecución. No en finalizado ni cancelado.
- **R-ACT-3** *(propuesta, a validar)*: una actividad **no se elimina** en esta versión. Si sobra, se deja pendiente o se completa con una observación que lo explique.
- **R-ACT-4** *(propuesta, a validar)*: una actividad no tiene responsable ni fecha límite (HU13 no lo pide).
- El usuario se guarda como **ID** del módulo `identity`, sin clave foránea entre módulos (AGENTS.md, regla 3). El issue #14 propone una relación ORM con `Usuario`: no se hace así.

## 6. Fuera de alcance
- Editar el texto de una actividad o una observación.
- Asignar actividades a trabajadores (llegará con HU17) y fechas límite o recordatorios.
- Adjuntar fotos o archivos.
- Mostrar actividades en la ficha consolidada (HU14) o en el dashboard.

## 7. No funcionales
- Auditoría: quién y cuándo en cada registro y en cada cambio de estado (RN03).
- Dos usuarios que marcan la misma actividad a la vez no la dejan inconsistente: gana el último y queda registrado.
- Sin paginación. **[suposición]** Un evento no tendrá cientos de actividades; si ocurre, se agrega.
- Requiere migración nueva: coordinar con Harold (`uv run alembic heads` con un solo head) antes de crearla.

## 8. Preguntas abiertas
- [ ] R-ACT-1: ¿las observaciones son inmutables o se pueden editar o borrar?
- [ ] R-ACT-2: ¿se registran observaciones después de finalizado el evento (cierre, incidencias)?
- [ ] R-ACT-3: ¿se puede eliminar una actividad creada por error mientras está pendiente?
- [ ] R-ACT-4: ¿una actividad necesita responsable o fecha límite?
- [ ] ¿El encargado de compras y almacén puede agregar observaciones (p. ej., faltantes de material)? Hoy DOMAIN.md §9 le da solo lectura.
