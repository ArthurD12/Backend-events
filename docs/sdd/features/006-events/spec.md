# Spec: Convertir el contrato en evento

- **ID**: 006-events
- **Estado**: aprobado (César Suclupe, 22/11/2026)
- **Módulos afectados**: `commercial` (submódulo `events`), `identity` (consulta de coordinadores y permisos)
- **Historia**: HU10 (#11), **adaptada a HU42**: el evento nace del contrato firmado con adelanto, no de la cotización (decisión del Product Owner, 22/11/2026).

## 1. Problema y objetivo
Con el contrato firmado y el adelanto pagado, Darze tiene que organizar el evento: fecha, horario, lugar, invitados, servicios y quién lo coordina. Si se registra a mano, se repiten datos y aparecen errores. El objetivo es convertir el contrato en un evento con un clic, copiando lo contratado.

## 2. Actores
- **Encargado de eventos** y **administrador**: convierten el contrato y consultan los eventos.
- **Encargado de compras y almacén**: solo consulta los eventos (DOMAIN.md §9).

## 3. Historia
- **HU10**: Como encargado de eventos, quiero convertir un contrato firmado con adelanto en un evento, para evitar volver a registrar la misma información.

## 4. Criterios de aceptación
El texto de HU10 en GitHub habla de "cotización aceptada"; HU42 (posterior, validada por Darze) exige contrato firmado con adelanto. Quedan así:
- **CA-10.1**: Solo un contrato **firmado y con adelanto pagado** se convierte en evento (CA-42.3).
- **CA-10.2**: La conversión copia el cliente, la fecha, el horario, el lugar, los invitados y los servicios contratados (de la cotización del contrato).
- **CA-10.3**: El sistema genera un código único `EVT-AAAA-NNNN`.
- **CA-10.4**: El contrato y el evento quedan relacionados (y, por el contrato, la cotización).
- **CA-10.5**: Un contrato no se convierte más de una vez.
- **CA-10.6** (RN09): el evento tiene un **responsable de coordinación**: un usuario activo, administrador o encargado de eventos. Por defecto, quien convierte.

## 5. Reglas
- El evento nace en estado **programado** (DOMAIN.md §3). Cambiar su planificación y su estado es HU11.
- **R-EVT-1** *(Product Owner, 22/11/2026)*: el evento se crea con un botón **"Convertir en evento"** en el contrato firmado, no automáticamente.
- **R-EVT-2** *(Product Owner, 22/11/2026)*: el responsable es un **usuario del sistema** (administrador o encargado de eventos) hasta que exista el módulo de personal (HU15).
- **R-EVT-3** *(equipo, provisional)*: un contrato que ya se convirtió en evento **no se anula desde el contrato**: se cancela el evento (HU11). Así no queda un evento sin contrato vigente.
- Varios eventos el mismo día y a la misma hora están permitidos (DOMAIN.md §4, regla 6).

## 6. Fuera de alcance
- HU11 (cambiar planificación y estado), HU12 (calendario), HU13 (actividades), HU14 (ficha consolidada).
- Asignar personal (HU17) y materiales (HU25).

## 7. No funcionales
- Dos conversiones simultáneas del mismo contrato no crean dos eventos (lo garantiza la base de datos).
- Auditoría: quién convirtió y cuándo (RN03).

## 8. Preguntas abiertas
- [x] ¿Desde la cotización o desde el contrato? → Contrato firmado con adelanto (Harold, 22/11/2026).
- [x] ¿Botón o automático? → Botón (César, 22/11/2026).
- [x] ¿Quién es el responsable? → Un usuario del sistema (César, 22/11/2026).
- [ ] Pedir a Harold que actualice el texto del issue #11 (HU10).
