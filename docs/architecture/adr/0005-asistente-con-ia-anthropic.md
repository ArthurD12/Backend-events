# ADR 0005 — Asistente de consulta con Claude (SDK `anthropic`)

- **Estado:** aceptada por el equipo (26/11/2026)
- **Contexto:** HU35–HU40 piden un chat que responda con datos reales del sistema. El documento del proyecto mencionaba OpenAI; el equipo decidió usar Claude (R-IA-1). La regla 11 de AGENTS.md pide un ADR para cualquier dependencia nueva.

## Decisiones
| Tema | Decisión | Motivo |
|---|---|---|
| Proveedor y librería | Anthropic, paquete oficial `anthropic` (`AsyncAnthropic`) | SDK oficial, con tipos y reintentos incluidos; evita escribir el cliente HTTP a mano |
| Modelo | `claude-opus-5-5`, `output_config.effort: "low"`, `max_tokens` 16000, sin `thinking` ni `temperature`, `tool_choice` automático | Consultas simples: poco esfuerzo, menor costo y latencia |
| Dónde | Puerto `LanguageModel` en `assistant/application`; adaptador `AnthropicLanguageModel` en `assistant/infrastructure` | Cambiar de proveedor no toca el dominio ni las herramientas |
| Herramientas | Una por función de consulta, con `strict: true`. El bucle (máx. 6 rondas) corre en el backend; cada herramienta verifica el permiso y lee solo `public_api` | RN28–RN30: solo consulta y con el rol del usuario |
| Respaldo | `client.beta.messages.create` con la beta `server-side-fallback-2026-07-01` y `fallbacks="default"` | Si el modelo rechaza la petición, el servidor la reintenta con el modelo de respaldo |
| Caché | `cache_control` efímero; sistema y herramientas estables. La fecha de hoy va en el mensaje del usuario | Prefijo estable = menor costo |
| Clave | `ANTHROPIC_API_KEY` en el entorno (nunca en el repo). Sin ella: `assistant_status` no disponible y `assistant_ask` responde 503 | El resto del sistema funciona igual (CA-40.2) |
| Pruebas | `FakeLanguageModel`; nunca se llama al proveedor real en tests ni en CI | Sin costo ni dependencia de red |

## Consecuencias
- Una dependencia más (`anthropic`) en `pyproject.toml`, documentada en `STACK.md`, `README.md` e `INSTALACION.md` (regla 13).
- Costo acotado por R-IA-2 (30 preguntas por usuario por hora) y respuestas cortas.
- Los datos que la herramienta devuelve viajan al proveedor para redactar la respuesta: solo los que el rol del usuario puede ver.
