# ADR 0005 — `btree_gist` y restricción de exclusión para asignaciones de personal

- **Estado:** aprobado (26/11/2026)
- **Contexto:** RN12 exige que un trabajador **no tenga dos asignaciones vigentes con horarios superpuestos** y que la garantía sea de PostgreSQL, no solo del código (R-ASG-3, HU17). La solución prevista en el plan de `033-staff-assignments` es una restricción de exclusión:

```sql
EXCLUDE USING gist (
  worker_id WITH =,
  tstzrange(start_at, end_at, '[)') WITH &&
) WHERE (occupies)
```

`worker_id` es `uuid`; para combinarlo con el operador de rango `&&` en un índice GiST hace falta el operador de igualdad de `uuid` que aporta la extensión **`btree_gist`** de PostgreSQL. Sin ella, la restricción no se puede crear. La validación en aplicación puede detectar el solape y devolver el 409 con el evento en conflicto, pero no resiste dos peticiones simultáneas (CA-17.11); por eso la restricción es la fuente de verdad.

No consta verificado que la extensión esté habilitada en el PostgreSQL de producción. Es una **condición a confirmar antes de la migración**, no un hecho. Lo que sí se verificó en local (25/11/2026): `postgres:17-alpine` incluye `btree_gist` **1.7** como extensión disponible y `CREATE EXTENSION IF NOT EXISTS btree_gist` funciona con el usuario `postgres` del contenedor.

## Decisión

| Tema | Decisión | Motivo |
|---|---|---|
| Extensión | Usar `btree_gist` y crearla en la migración con `CREATE EXTENSION IF NOT EXISTS btree_gist` | Es la única forma de combinar igualdad por `uuid` y solape de rangos en una restricción de exclusión |
| Garantía | La restricción `staff_assignments_no_overlap` es la fuente de verdad del no-solape | Cumple RN12/R-ASG-3 también ante concurrencia real |
| Validación en aplicación | Se mantiene solo para dar un 409 accionable con el código, la fecha y el horario del evento en conflicto | Mejora la experiencia sin sustituir la garantía de la base |
| Predicado | La restricción es parcial: `WHERE (occupies)` | Permite conservar asignaciones de eventos cancelados sin que ocupen al trabajador (R-ASG-12) |
| Ubicación | La extensión y la restricción las crea la **única migración** de HU17 | El esquema solo cambia por Alembic; no se editan migraciones aplicadas |
| `downgrade` | Elimina tablas, triggers e índices, pero **no** la extensión | `btree_gist` puede usarla otro esquema o una migración posterior; eliminarla podría romperlos |

## Alternativas consideradas y por qué se descartan

| Alternativa | Por qué se descarta |
|---|---|
| **Validación solo en aplicación** | Dos altas simultáneas pueden pasar la comprobación antes de que cualquiera confirme y dejar dos asignaciones solapadas. No cumple R-ASG-3/CA-17.11. |
| **`LOCK TABLE` o advisory lock por trabajador** | Serializa las escrituras, pero no impide solapes introducidos por otra vía (SQL manual, migración de datos, otro proceso). El bloqueo es una medida de concurrencia, no una invariante del dato. Además, un advisory lock mal liberado o una transacción larga bloquea altas legítimas. |
| **Trigger que consulte solapes** | Un trigger `BEFORE INSERT/UPDATE` con `SELECT` sobre la misma tabla puede funcionar, pero es más lento y propenso a errores bajo concurrencia si no se combina con bloqueos; además, concentra lógica de negocio en PL/pgSQL y no expresa la invariante de forma declarativa. La restricción de exclusión es más simple y la evalúa el motor. |
| **Tabla de ocupación separada** | Duplica el estado (asignación y ocupación) y obliga a mantener ambas tablas sincronizadas; una escritura parcial puede dejar la ocupación inconsistente. Añade mantenimiento sin mejorar la garantía. |
| **Delegar en un servicio externo** | Introduce una pieza más que operar y un punto de fallo de red para una regla transaccional que PostgreSQL ya puede garantizar. Contradice el criterio de mínimo mantenimiento. |
| **Solo `EXCLUDE` sin `btree_gist`** | No es posible: el índice GiST necesita el operador de igualdad para `uuid`. Sin la extensión, la restricción no se crea. |

## Consecuencias

- **Privilegios:** `CREATE EXTENSION` puede requerir superusuario o una extensión marcada como *trusted* según la versión y la configuración. En un PostgreSQL gestionado puede necesitar habilitación previa por el administrador. Hay que probarlo en cada entorno (local, CI, staging y producción).
- **Disponibilidad en la imagen:** verificado en local el 25/11/2026 con `docker run postgres:17-alpine`: `btree_gist` aparece en `pg_available_extensions` (versión 1.7) y `CREATE EXTENSION IF NOT EXISTS btree_gist` se ejecuta sin error con el usuario `postgres` del contenedor. `docker-compose.yml` y los tests de integración usan esa misma imagen, así que local y CI no requieren nada adicional. Aun así, el test de integración debe ejecutar `CREATE EXTENSION` de verdad, no asumirlo.
- **Producción:** no consta que `btree_gist` esté habilitada. Si el entorno no permite habilitarla, **se detiene la implementación y se replanifica**; no se degrada silenciosamente a validación solo en aplicación, porque incumpliría RN12/R-ASG-3.
- **`downgrade`:** la migración de bajada no elimina `btree_gist`; se documenta en la migración y en `INSTALACION.md`.
- **Documentación:** `STACK.md` debe mencionar la extensión como requisito de PostgreSQL y `INSTALACION.md`/`README.md` deben explicar qué hacer si `CREATE EXTENSION` falla por privilegios (regla 13 de AGENTS.md).
- **Pruebas:** es obligatoria una prueba de concurrencia con **dos transacciones reales** contra PostgreSQL. Una debe insertar y la otra recibir SQLSTATE `23P01` (`exclusion_violation`), comprobando el nombre `staff_assignments_no_overlap`; además, una prueba directa por SQL debe demostrar que la restricción rechaza el solape aunque no pase por la aplicación.
- **Migración:** una sola, con `down_revision` sobre el head vigente. Antes de crearla: `uv run alembic heads`, confirmar un único head, avisar al humano y esperar confirmación.

## Referencias

- `docs/DOMAIN.md` — RN12 (no solape de asignaciones) y R-ASG-3.
- `docs/sdd/features/033-staff-assignments/spec.md` — R-ASG-3, R-ASG-12, CA-17.7/17.8/17.9/17.11/17.20.
- `docs/sdd/features/033-staff-assignments/plan.md` — §5 (persistencia, restricción y migración) y §8 (riesgos).
- `docs/architecture/STACK.md` — PostgreSQL y `EXCLUDE USING gist` como garantía de no solape.
- `docker-compose.yml` — imagen `postgres:17-alpine` usada en local y en integración.
- `AGENTS.md` — regla 11 (dependencias/decisiones nuevas con ADR), regla 7 (no solape garantizado en PostgreSQL) y reglas de migraciones.
