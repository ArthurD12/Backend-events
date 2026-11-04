# Plan: <título>

- **Spec**: ./spec.md
- **Estado**: borrador | aprobado

## 1. Módulos y fronteras
<Qué módulos cambian y qué `public_api` se usa o expone.>

## 2. Modelo de dominio
Agregados, entidades, value objects, invariantes, eventos de dominio.

## 3. Casos de uso
| Caso de uso | Tipo (command/query) | Entrada | Salida | Errores de negocio |
|---|---|---|---|---|

## 4. API (OpenAPI)
Endpoints, `operationId`, esquemas de request/response, permisos requeridos, códigos de error (`code` estable).

## 5. Persistencia
Tablas nuevas o cambios, índices, constraints (p. ej. exclusión de solapes), migración Alembic, estrategia de concurrencia.

## 6. Reglas de negocio aplicadas
Referencias a `docs/DOMAIN.md` (y las que se agregan o cambian).

## 7. Estrategia de tests
Unit (dominio/aplicación con fakes), integración (Postgres real), arquitectura. Mapeo CA → test.

## 8. Riesgos y ADRs
...

## 9. Impacto en reporting y documentación
¿Cambia alguna vista de `reporting`? ¿Qué docs se actualizan?
