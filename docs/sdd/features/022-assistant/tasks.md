# Tasks: Asistente de consulta con IA

- [x] T-01 [adr+deps] ADR 0005 (proveedor Anthropic, SDK `anthropic`), dependencia con `uv add`, STACK.md, README.md, INSTALACION.md, variable ANTHROPIC_API_KEY en `.env.example` (vacía) y config
- [x] T-02 [assistant/domain+app] Puerto `LanguageModel`, registro de herramientas con permiso, caso de uso `AskAssistant` (bucle de herramientas máx. 6, límite R-IA-2, auditoría) + `FakeLanguageModel` + tests
- [x] T-03 [assistant/tools] Las herramientas de CA-35.2 sobre `public_api` (sin la de personal si staff no la expone) + tests con fakes
- [x] T-04 [assistant/infra] Adaptador `AnthropicLanguageModel` (SDK oficial), tabla `assistant_queries` (solo inserción) + migración + integración (sin llamadas reales)
- [ ] T-05 [presentation] `assistant_ask`, `assistant_status`, `assistant_log_list`, permiso `assistant_log:read` + tests de API + `just openapi`; DOMAIN.md §11 (R-IA-1..4)
- [ ] T-06 [frontend] Chat flotante, historial de la sesión, funciones consultadas, historial para el administrador
