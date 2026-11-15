# ADR 0003 — Módulo comercial (clientes, cotizaciones, contratos y eventos)

- **Estado:** aceptada por el equipo (15/11/2026)
- **Contexto:** ADR 0002 separó `clients`, `quotes`, `contracts` y `events` en cuatro módulos independientes. En Darze los cuatro forman un solo flujo: el contrato copia la cotización, el evento nace del contrato y el historial del cliente (HU05) muestra cotizaciones y eventos juntos. Con módulos separados, cada paso exige pasar por `public_api` y quedan prohibidos los JOINs y las claves foráneas que ese flujo necesita. El Product Owner indicó que son un mismo módulo comercial con submódulos.

## Decisiones
| Tema | Decisión | Motivo |
|---|---|---|
| Módulo | Se crea `commercial` con cuatro submódulos: `clients`, `quotes`, `contracts` y `events` | Comparten un mismo flujo y cambian juntos |
| Estructura | Las capas siguen en el nivel del módulo y los submódulos van dentro de cada capa: `commercial/domain/clients/`, `commercial/application/quotes/`… | Así los contratos de `import-linter` (`modules.*.domain`, etc.) siguen funcionando sin cambios |
| Comunicación interna | Dentro de `commercial`, un submódulo puede usar a otro directamente | Es un solo módulo: la frontera estricta es hacia afuera |
| Base de datos | Dentro de `commercial` se permiten claves foráneas y JOINs. Tablas con prefijo `commercial_` (`commercial_clients`, `commercial_quotes`…) | Integridad del flujo cotización → contrato → evento |
| Frontera externa | Otros módulos (`ledger`, `staff`, `inventory`, `assistant`, `reporting`) solo usan `commercial/public_api.py` | Se mantiene la regla 3 de AGENTS.md |
| Catálogo | `catalog` sigue siendo un módulo aparte | También lo usará `inventory` (insumos por servicio); cotizaciones lo consulta por su `public_api` |

## Consecuencias
- El código de `modules/clients/` se mueve a `modules/commercial/` en un commit propio, sin cambiar su comportamiento: las pruebas deben seguir pasando.
- Desaparecen los módulos `clients`, `quotes`, `contracts` y `events`; quedan 9 módulos: `identity`, `commercial`, `catalog`, `staff`, `ledger`, `inventory`, `purchasing`, `reporting` y `assistant`.
- Se actualizan `ARCHITECTURE.md` y `README.md`. Las tareas de HU05 y HU10 que piden JOINs o claves foráneas ya no contradicen la arquitectura, porque quedan dentro del mismo módulo.
