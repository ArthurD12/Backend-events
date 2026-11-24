# Plan: Calendario de eventos

- **Spec**: ./spec.md
- **Estado**: borrador, pendiente de aprobación

## 1. Módulos y fronteras
- Solo `commercial` (eventos). Sin tablas nuevas ni migraciones: se lee `commercial_events` con su cliente.
- El nombre del responsable sale de `identity.public_api` (`coordinator_lookup`), igual que en la lista.

## 2. Caso de uso
| Caso de uso | Entrada | Errores (`code`) |
|---|---|---|
| `EventCalendar` | `date_from`, `date_to` (obligatorias), `status?`, `event_type?`, `text?` (cliente o código) | `event.range_invalid` (422): fin antes del inicio o más de 92 días |

Devuelve todos los eventos del rango, ordenados por fecha y hora de inicio, sin paginar.

## 3. API
| Método y ruta | `operationId` | Permiso |
|---|---|---|
| `GET /v1/events/calendar` | `events_calendar` | `events:read` |

Cada elemento: `id`, `code`, `client_name`, `event_type`, `event_date`, `start_time`, `end_time`, `venue`, `guests`, `coordinator_name`, `status`. El repositorio actual ya filtra por texto, estado y fechas; se agrega el filtro por **tipo de evento**.

## 4. Frontend
- Página `/eventos/calendario`, con un enlace desde `/eventos` ("Ver calendario") y viceversa.
- **Componente propio con Tailwind, sin librería**:
  - **Mes**: grilla de 7 columnas (lunes a domingo) con hasta 3 eventos por día y un "+N más".
  - **Semana**: 7 columnas con los eventos de cada día, ordenados por hora.
  - **Día**: lista del día con más detalle.
  - **Celular**: mes y semana se muestran como lista por día.
- Cancelados: gris y tachados (CA-12.5). Los demás estados, con los colores de la etiqueta de estado.
- Clic en un evento → recuadro (`Modal`) con la información principal y "Ver evento".
- El periodo y la vista quedan en la URL (`?vista=mes&fecha=2026-12-01`): al volver desde el detalle, el calendario sigue donde estaba.

**Por qué sin FullCalendar** (el issue lo propone solo como ejemplo):
- Darze tiene pocos eventos por día y no se arrastran (fuera de alcance), así que la grilla horaria de FullCalendar no aporta.
- Agregarlo suma una dependencia que hay que adaptar a React 19 y Next 16, y a los estilos del diseño aprobado, a menos de 3 semanas de la presentación.

## 5. Tests
- **Unit**: rango inválido o mayor a 92 días; filtros por estado, tipo y cliente; orden por fecha y hora; API con los tres roles.
- **Integración**: la consulta con filtros en PostgreSQL real (eventos dentro y fuera del rango, cancelados incluidos).
- **Frontend (navegador)**: mes, semana y día; navegación y "Hoy"; filtros; recuadro; cancelado tachado; celular sin scroll horizontal.

## 6. Riesgos
- Sin datos sensibles nuevos ni cambios en la base de datos. Riesgo bajo.
