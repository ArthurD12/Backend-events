# Plan: Asistente — cotizaciones, eventos con filtros e historial con valoración

- **Spec**: ./spec.md
- **Estado**: aprobado por el Product Owner (César Suclupe, 26/11/2026)

## 1. Fronteras
- `commercial.public_api` agrega dos consultas de solo lectura: `events_find` (eventos por fecha, texto, tipo y estado, con total) y `quotes_search` (cotizaciones con la vigencia ya existente). `assistant` no toca capas internas ni tablas de `commercial`.
- `assistant` agrega las herramientas `search_events` y `search_quotes` (13 en total, `strict: true`, permiso verificado por el `ToolRegistry`) y los casos de uso `RateQuery` y `SearchQueries` ampliado.

## 2. API
| Ruta | `operationId` | Permiso |
|---|---|---|
| `POST /v1/assistant/queries/{query_id}/feedback` (valor + comentario) → 201 | `assistant_feedback_create` | autenticado; solo el autor de la consulta (otro: 404 `assistant.query_not_found`) |
| `GET /v1/assistant/my-queries` (paginado) | `assistant_my_queries` | autenticado; solo sus filas |
| `POST /v1/assistant/ask` devuelve además `query_id` | `assistant_ask` | sin cambio |
| `GET /v1/assistant/log` incluye `feedback` (la última) | `assistant_log_list` | sin cambio |

## 3. Persistencia
- `assistant_feedback` (solo inserción, trigger como `assistant_queries`): `id` (identidad), `query_id` (FK a `assistant_queries`), `user_id`, `value` (`correct`/`incorrect`), `comment` (≤ 300, opcional), `created_at`. La vigente es la de mayor `id` por consulta.
- Migración encadenada a `c3a9e5d7f1b2` (head actual de `developer-b`).

## 4. Prompt
Una regla breve: "pendiente de respuesta" = enviada y vigente; "vencida" = vigencia terminada.

## 5. Tests
- Unit con `FakeLanguageModel` y fakes: herramientas (permisos, filtros, validación), `RateQuery` (autor, reemplazo), `SearchQueries` con valoración, API.
- Integración (PostgreSQL real): trigger de solo inserción, solo tus filas, permisos, herramientas contra datos reales.

## 6. Frontend
Botones "Correcta"/"Incorrecta" bajo cada respuesta, vista "Mis consultas" en el panel, nombres legibles de las herramientas nuevas, valoración en `/historial-asistente`.
