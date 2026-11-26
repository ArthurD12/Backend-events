# Spec: Asistente — cotizaciones, eventos con filtros e historial con valoración

- **ID**: 024-assistant-quotes-feedback
- **Estado**: aprobado por el Product Owner (César Suclupe, 26/11/2026)
- **Módulos afectados**: `assistant` (herramientas, valoración, historial propio), `commercial.public_api` (dos consultas de solo lectura nuevas). **No** se toca `modules/staff`.
- **Historias**: completa HU36 (criterios de eventos y cotizaciones) y HU40 (historial propio y valoración). Amplía [022-assistant](../022-assistant/spec.md).

## 1. Problema y objetivo
El asistente solo ve "próximos eventos" y no puede responder por cotizaciones. Tampoco deja al usuario revisar sus conversaciones ni decir si una respuesta fue buena. Se cierran esos criterios.

## 2. Criterios de aceptación
- **CA-36.5**: El agente consulta **eventos** por rango de fechas, cliente (texto), tipo y estado (`search_events`, permiso `events:read`).
- **CA-36.6**: El agente consulta **cotizaciones** por estado (borrador, enviada, aceptada, rechazada o vencida), cliente (texto) y rango de fechas del evento; devuelve código, cliente, fecha del evento, total y estado (`search_quotes`, permiso `quotes:manage`, el mismo que usa el módulo de cotizaciones).
- **CA-40.3**: Cada usuario revisa **sus** conversaciones anteriores: `GET /v1/assistant/my-queries`, paginado, con pregunta, respuesta, funciones usadas, estado y su última valoración. Solo ve sus filas.
- **CA-40.4**: El usuario marca una respuesta como **correcta o incorrecta** (comentario opcional corto): `POST /v1/assistant/queries/{query_id}/feedback`. Solo el autor de la consulta; si valora de nuevo, vale la última; nada se edita ni se borra (solo inserción).
- **CA-40.5**: `assistant_ask` devuelve `query_id`; el historial del administrador (`assistant_log_list`) incluye la última valoración.
- **CA-38.1/38.2** siguen: solo consulta y permiso verificado dentro de cada herramienta.

## 3. Reglas (provisionales, registradas en DOMAIN.md §11)
- **R-IA-6**: `search_events` filtra por fechas del evento, cliente (texto), tipo y estado; sin ningún filtro devuelve los eventos desde hoy. Respuesta corta (15 filas) con el total.
- **R-IA-7**: `search_quotes`: "vencida" es una cotización en borrador o enviada cuya vigencia ya terminó (CA-08.3, se calcula, no se guarda); "pendiente de respuesta" es enviada y vigente. Permiso `quotes:manage` (administrador y encargado de eventos).
- **R-IA-8**: valoración `correct` / `incorrect`, comentario opcional de hasta 300 caracteres, solo el autor (otro usuario recibe 404, sin revelar que existe), la última valoración es la vigente.
- **R-IA-9**: el historial propio es de cualquier usuario autenticado y solo muestra sus consultas; el administrador ve la valoración en el historial general.

## 4. Fuera de alcance
- Herramienta de personal (depende de `staff`, aún sin API).
- Usar las valoraciones para reentrenar o cambiar el modelo.
