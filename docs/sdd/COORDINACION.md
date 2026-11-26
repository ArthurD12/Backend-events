# Coordinación del equipo (backend)

> Lo leen las personas y sus agentes antes de empezar una tarea. Actualizar al tomar o terminar trabajo.
> Última actualización: 25/11/2026.

## 1. Dueños por módulo
| Módulo / área | Dueño | Historias |
|---|---|---|
| `staff` (personal, disponibilidad, asignaciones, asistencia) | **Harold** | HU15 ✓, HU16, HU17, HU18 |
| `commercial`, `ledger`, `inventory`, `purchasing`, `reporting` | **César** | HU11, HU13, HU14, HU19–HU30, HU31–HU34 |
| Frontend (repo `Frontend-events`), todas las pantallas | **César** | — |
| `assistant` (IA) | sin asignar | HU35–HU40 (al final) |

Un agente **no modifica** un módulo de otro dueño. Si necesita algo de él, lo pide aquí (sección 4) y usa su `public_api` cuando exista.

## 2. En curso
| Trabajo | Dueño | Rama | Estado |
|---|---|---|---|
| HU17 (asignaciones) | Harold | `feat/hu17-asignaciones` (desde `developer-b`) | T-01..T-12; gate ADR 0005 y migración |
| HU16 (disponibilidad) | Harold | `feat/hu16-disponibilidad` (solo docs, otra sesión) | spec/plan en paralelo; implementación bloqueada por HU17 (necesita asignaciones) |
| HU18 (asistencia) | Harold | — | después de HU17 |
| Lote 6: reportes (HU31 completo, HU32–HU34) | César | `feat/reportes` | spec |
| Lote 7: HU24, HU25, HU30 | César | — | después del lote 6 |

## 3. Archivos compartidos (conflictos frecuentes)
Al resolver un conflicto en estos archivos **se conservan las dos partes**, nunca solo una:
- `src/local_eventos/main.py` (routers y manejadores de errores de cada módulo).
- `src/local_eventos/modules/identity/domain/permissions.py` y `tests/unit/identity/test_user.py`.
- `docs/DOMAIN.md` (§9 tabla de permisos y §11 registro de decisiones: se agregan filas).
- Listas de `TRUNCATE` en `tests/integration/**`.
- `openapi.json`: no se edita a mano; después del merge se regenera con `just openapi`.

## 4. Puntos de conexión entre dueños
| Necesita | Quién lo expone | Qué | Estado |
|---|---|---|---|
| Ficha del evento (HU14, `reporting`) muestra el personal | Harold, `staff.public_api` | `event_assignments(session)(event_id) -> list[...]` con nombre del trabajador, función, inicio y fin (UTC), **sin pago** | **en curso** (HU17); `reporting` cambiará su adaptador nulo `NoEventStaff` cuando pase a listo |
| Asignar a un evento (HU17) valida estado y horario | César, `commercial.public_api` | `event_lookup` (id, código, estado, fecha, horario) | **listo** |
| Cancelar un evento libera al personal | — | No se requiere hook: la liberación es **perezosa** al escribir sobre el trabajador (decisión 25/11/2026); si se quiere inmediata, reevaluar con un evento de dominio | **acordado** |

Cuando un punto pase a "listo", avisar al otro dueño para que lo conecte.

## 5. Migraciones (Alembic)
- Head actual de `developer-b`: **`6900ec1af5f8`**.
- Antes de crear una migración: `git fetch origin developer-b`, unir `developer-b` en tu rama y `uv run alembic heads` = **un solo head**; la tuya va encadenada a ese.
- Si mientras tanto entró otra migración a `developer-b`: cambia el `down_revision` de **tu** migración (si nunca se unió) o agrega una migración de unión (`alembic merge`). **Nunca** se edita una migración ya unida (regla 8).

## 6. Reglas de PR
1. Antes de abrir el PR: unir `origin/developer-b` en tu rama y correr `just check` y `uv run pytest -m integration`.
2. **No se une un PR con el CI en rojo**, aunque GitHub lo permita.
3. Después de resolver conflictos, volver a correr todo: un merge puede romper lo que antes pasaba.
4. Un PR por historia o lote; `developer-b` → `main` solo después de una prueba de punta a punta.
5. Dos features del **mismo módulo** no se implementan en paralelo: comparten dominio, ORM, composición y migraciones. El spec/plan sí puede ir en paralelo; el código espera a que la primera tenga su migración mergeada y `alembic heads` con un solo head.
