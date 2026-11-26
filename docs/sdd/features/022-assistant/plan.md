# Plan: Asistente de consulta con IA

- **Spec**: ./spec.md
- **Estado**: aprobado (César Suclupe, 26/11/2026)

## 1. Módulos y fronteras
- `assistant` orquesta: recibe la pregunta, llama al modelo con **herramientas** (una por función de consulta), ejecuta las herramientas en el backend leyendo **solo `public_api`** de otros módulos, y devuelve la respuesta final. Sin acceso directo a tablas ajenas (RN29).
- Puerto `LanguageModel` en `assistant.application`; adaptador `AnthropicLanguageModel` en `assistant.infrastructure` con el SDK oficial `anthropic` (Messages API + uso de herramientas; el bucle lo controla el backend, ya que las herramientas leen la base de datos). Un adaptador `FakeLanguageModel` para tests.
- `identity.public_api`: permisos del usuario actual (ya existe en `CurrentUser`).

## 2. Diseño
- Cada herramienta: nombre, descripción, `input_schema` estricto (`strict: true`), permiso requerido y una función que llama un `public_api` y devuelve JSON compacto. Si falta el permiso, devuelve `{"error": "sin_permiso"}` y el modelo lo explica.
- Llamada al modelo: `claude-opus-5-5`, `output_config.effort: "low"` (consultas simples), `max_tokens` 16000, sistema en español con las reglas RN30–RN32, `tool_choice: auto`, máximo 6 rondas de herramientas por pregunta. Fallback del servidor ante rechazo (`fallbacks: "default"`, beta `server-side-fallback-2026-07-01`).
- Caché de prompt en el sistema + herramientas (prefijo estable) para abaratar.
- Conversación: el frontend envía el historial de la sesión de chat (texto de turnos previos); el backend no guarda estado conversacional (R-IA-3).
- Límite R-IA-2 contando registros de auditoría de la última hora.

## 3. API
| Ruta | `operationId` | Permiso |
|---|---|---|
| `POST /v1/assistant/ask` (pregunta + historial corto) → respuesta + funciones usadas | `assistant_ask` | cualquier usuario autenticado |
| `GET /v1/assistant/status` → disponible o no | `assistant_status` | autenticado |
| `GET /v1/assistant/log` (filtros: usuario, fechas) | `assistant_log_list` | `assistant_log:read` (solo administrador, permiso nuevo) |

Errores: `assistant.unavailable` (503), `assistant.rate_limited` (429), `assistant.provider_error` (502).

## 4. Persistencia
- `assistant_queries` (solo inserción): usuario, fecha, pregunta, funciones (JSONB con nombre y parámetros), respuesta, tokens usados, duración, estado (ok/error/rechazo).

## 5. Dependencias y configuración
- Nueva dependencia `anthropic` (SDK oficial) → **ADR 0005** y actualizar `STACK.md`, `README.md`, `INSTALACION.md` (regla 13).
- Variable `ANTHROPIC_API_KEY` en Render (nunca en el repo). Sin ella, `assistant_status` = no disponible.

## 6. Tests
- Unit (sin red): con `FakeLanguageModel` que pide herramientas concretas → se ejecutan con permisos, se registra la auditoría, se respeta el límite, sin permiso devuelve el error controlado; cada herramienta con fakes de los `public_api`.
- Integración: herramientas contra la base real (evento, pagos, stock).
- Sin llamadas reales al proveedor en CI.

## 7. Frontend
- Botón flotante **Asistente** en todas las pantallas: panel de chat con historial de la sesión, sugerencias de preguntas, indicador "pensando", y debajo de cada respuesta las funciones consultadas (transparencia).
- Si no está disponible: botón deshabilitado con aviso.
- Administración → **Historial del asistente** (solo administrador).

## 8. Riesgos
- Calidad de la respuesta en la demo: se prueban 10 preguntas fijas antes de presentar.
- Costo: acotado por R-IA-2 y respuestas cortas; centavos por demo.
