# Tasks: Asistente — cotizaciones, eventos con filtros e historial con valoración

- [ ] T-01 [docs] spec, plan, tasks y DOMAIN.md §11 (R-IA-6..9)
- [ ] T-02 [commercial/public_api] `events_find` y `quotes_search` (solo lectura) + tests
- [ ] T-03 [assistant/tools] `search_events`, `search_quotes`, regla del prompt + tests
- [ ] T-04 [assistant] tabla `assistant_feedback` (solo inserción) + migración, `RateQuery`, `SearchQueries` con valoración, `query_id` en `assistant_ask`
- [ ] T-05 [presentation] `assistant_feedback_create`, `assistant_my_queries`, valoración en `assistant_log_list` + tests unit e integración + `just openapi`
- [ ] T-06 [frontend] botones de valoración, "Mis consultas", nombres de herramientas, valoración en `/historial-asistente`
