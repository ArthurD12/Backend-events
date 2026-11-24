# Spec: Calendario de eventos

- **ID**: 012-calendar
- **Estado**: borrador, pendiente de aprobación
- **Módulos afectados**: `commercial` (submódulo `events`, solo lectura)
- **Historia**: HU12 (#13), RF30 y RF31

## 1. Problema y objetivo
La lista de eventos (HU10) sirve para buscar, pero no deja ver de un vistazo qué días están ocupados ni si hay varios eventos el mismo día. El objetivo es un calendario por día, semana o mes, para planificar y evitar desorganización.

## 2. Actores
- **Encargado de eventos**, **administrador** y **encargado de compras y almacén**: los tres consultan el calendario (`events:read`, DOMAIN.md §9).

## 3. Historia
- **HU12**: Como encargado de eventos, quiero visualizar los eventos en un calendario para conocer la programación y evitar desorganización.

## 4. Criterios de aceptación
- **CA-12.1**: El calendario se ve por **mes**, **semana** o **día**, y se avanza o retrocede por periodo, con un botón "Hoy".
- **CA-12.2**: Cada evento muestra al menos su **horario**, **cliente**, **tipo** y **estado**.
- **CA-12.3**: Se filtra por **estado**, **tipo de evento** y **cliente** (por nombre). La fecha se filtra con el periodo que se está viendo.
- **CA-12.4**: Al seleccionar un evento se abre un recuadro con su información principal (código, fecha, horario, cliente, tipo, lugar, invitados, responsable y estado) y un enlace a su detalle.
- **CA-12.5**: Los eventos **cancelados** se distinguen visualmente de los activos (gris y tachados).

## 5. Reglas
- **R-CAL-1** *(equipo, provisional)*: un evento que cruza la medianoche (20:00 → 03:00) se muestra **solo en el día en que empieza**, con la marca "(día siguiente)" en la hora de fin.
- **R-CAL-2** *(equipo, provisional)*: los cancelados se muestran por defecto, diferenciados (CA-12.5), y se pueden ocultar con el filtro de estado.
- Varios eventos el mismo día y a la misma hora están permitidos (DOMAIN.md §4, regla 6): el calendario los muestra todos.
- Las fechas son de Lima (UTC−5); "Hoy" es la fecha de Lima.

## 6. Fuera de alcance
- Crear, mover o editar eventos desde el calendario (arrastrar y soltar): editar la planificación es parte de HU11.
- Alertas de choque de horarios o de personal (HU17).
- Exportar a Google Calendar u otros.

## 7. No funcionales
- Una sola consulta por periodo visible, sin paginación, con un rango máximo de 92 días.
- En celular, el mes se ve como lista por día (no cabe una grilla de 7 columnas legible en 360 px).
