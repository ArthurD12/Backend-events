---
name: testing-strategy
description: Estrategia de pruebas con pytest para el backend: pirámide, fakes vs mocks, PostgreSQL real con Testcontainers, tests de API con httpx, propiedades con hypothesis, tests de arquitectura y mapeo criterios de aceptación → tests.
---

# Estrategia de tests (pytest)

## Pirámide
| Nivel | Qué | Herramienta | Notas |
|---|---|---|---|
| Unit de dominio | Invariantes, políticas, value objects | pytest | Sin mocks, puro |
| Unit de aplicación | Casos de uso | pytest + fakes en memoria | Sin DB ni HTTP |
| Integración | Repositorios, migraciones, restricciones | pytest + Testcontainers (PostgreSQL) | Base real |
| API | Rutas, permisos, errores, OpenAPI | `httpx.AsyncClient` sobre la app | Con DB real |
| Propiedades | Ledger, inventario, solapes | hypothesis | Invariantes con muchos casos |
| Arquitectura | Capas y fronteras | `import-linter` (`just arch`) | Falla el CI |

## Reglas
- **Fakes** para los puertos del dominio; mockea solo bordes externos (el servicio de IA).
- Reloj e IDs inyectables; tests deterministas e independientes entre sí.
- Una instancia de PostgreSQL por sesión de tests; aislamiento por transacción con rollback, o por base por worker si se usa `pytest-xdist`.
- Builders/factories para los datos; sin fixtures gigantes.
- Cada **CA-n** del spec tiene un test con su ID en el nombre.
- `pytest-asyncio` en modo `auto`.

## Casos críticos obligatorios
- Doble reserva simultánea del mismo salón (solo una gana; la otra recibe `booking.overlap`).
- Solape que ocurre solo por los tiempos de montaje/limpieza.
- Precios congelados: cambiar el catálogo no altera una reserva.
- Saldo = total contratado − cobros + reversiones; la reversión no modifica el movimiento original.
- Salida de inventario por FEFO; stock nunca negativo; costo congelado en la salida.
- Permisos: cada rol solo hace lo que dice la matriz de `docs/DOMAIN.md`.
- Idempotencia: repetir con la misma `Idempotency-Key` no duplica efectos.

## Comandos
`just test` · `uv run pytest tests/unit -q` · `just check`
