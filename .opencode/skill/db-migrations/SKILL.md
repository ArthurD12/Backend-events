---
name: db-migrations
description: Reglas de esquema PostgreSQL y migraciones Alembic para este proyecto: tablas por módulo, restricción anti-solape de reservas, ledger e inventario append-only, lotes con FEFO, vistas de reporting.
---

# Esquema y migraciones (PostgreSQL + Alembic)

## Propiedad de datos
- Prefijo por módulo: `venues_*`, `bookings_*`, `inventory_*`, `ledger_*`. Sin FKs entre módulos; se guardan IDs (uuid).
- Cada módulo posee sus modelos ORM; nadie más los importa.

## Migraciones
- Una migración por cambio lógico: `uv run alembic revision --autogenerate -m "..."` y **revisarla a mano** (autogenerate no detecta constraints de exclusión ni vistas).
- Nunca editar una migración aplicada. Debe poder revertirse o documentar por qué no.
- Con datos existentes: expand → migrate → contract.
- Se aplican antes de levantar la nueva versión, no al arrancar la app.
- Test de integración que aplica todas las migraciones sobre una base vacía.

## Convenciones
- PK `uuid`; `created_at`/`updated_at` como `timestamptz` en UTC; columna `version` para bloqueo optimista en agregados editables.
- Dinero: `amount_cents BIGINT` + `currency CHAR(3)` (`PEN`), con `CHECK` según la regla.
- Constraints que expresan invariantes: `CHECK (quantity >= 0)`, `UNIQUE (idempotency_key)`.

## Reservas sin solapes
```sql
CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE bookings_bookings
  ADD CONSTRAINT bookings_no_overlap
  EXCLUDE USING gist (venue_id WITH =, blocked_range WITH &&)
  WHERE (status <> 'cancelada');
```
`blocked_range` es un `tstzrange` que ya incluye montaje y limpieza. El caso de uso traduce la violación a un error de negocio `booking.overlap`. Se escribe con `op.execute` en la migración.

## Ledger append-only
- Tabla `ledger_entries`: solo `INSERT`. Reversión = nueva fila con `reverses_entry_id` y signo opuesto.
- Impedir `UPDATE`/`DELETE` con un trigger o permisos del rol de la aplicación.
- Saldos y totales siempre se calculan (o se materializan) a partir de las filas.

## Inventario
- `inventory_lots` (insumo, cantidad inicial, costo unitario, vencimiento) y `inventory_movements` (entrada, consumo de evento, merma, ajuste; solo inserción).
- Salida por **FEFO**: seleccionar lotes por vencimiento ascendente con `SELECT ... FOR UPDATE`; el stock nunca queda negativo (`CHECK` + validación).
- Costo congelado en cada salida.

## Reporting
- Esquema `reporting` con **vistas** versionadas (`reporting.v1_bookings`, `reporting.v1_ledger_entries`, …) y un rol de solo lectura limitado a ese esquema.
- Cambiar una vista requiere subir de versión si rompe columnas existentes.
