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
| HU16–HU18 | Harold | `feat/hu16-...` (desde `developer-b`) | por empezar |
| Lote 6: reportes (HU31 completo, HU32–HU34) | César | `feat/reportes` | backend listo (T-01 a T-06); falta frontend (T-07) |
| Lote 7: HU24, HU25, HU30 (backend y frontend) | César | `feat/materiales-menu` | en desarrollo |

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
| Ficha del evento (HU14, `reporting`) muestra el personal | Harold, `staff.public_api` | `event_assignments(session)(event_id) -> list[...]` con nombre del trabajador, función, inicio y fin (UTC) | **pendiente** (hoy `reporting` usa un adaptador nulo: `NoEventStaff`) |
| Asignar a un evento (HU17) valida estado y horario | César, `commercial.public_api` | `event_lookup` (id, código, estado, fecha, horario) | **listo** |
| Reporte de personal (HU32–HU34, `reporting`) | Harold, `staff.public_api` | `workers_report(session)(function: str \| None, active: bool \| None) -> list[...]` con nombre, documento, función, tipo, tarifa (céntimos o `None`) y estado (solo lectura). `reporting` ya tiene el puerto `WorkersReportLookup` (`reporting/application/ports/workers.py`): al estar lista, César cambia solo el adaptador en `reporting/composition.py` | **pendiente** (`GET /v1/reports/staff` responde 503 `report.unavailable` hasta entonces) |
| Cancelar un evento libera al personal | Harold expone en `staff.public_api` un liberador; César lo conecta en `CancelEvent` por un puerto | **por acordar** |

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
