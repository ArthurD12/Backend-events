---
name: clean-architecture-modules
description: Reglas de Clean Architecture en monolito modular con Python/FastAPI (capas, fronteras entre módulos, puertos, errores, eventos en proceso). Úsala al diseñar o implementar cualquier código de un módulo.
---

# Clean Architecture en monolito modular (Python)

Referencia completa: `docs/architecture/ARCHITECTURE.md`.

## Dónde va cada cosa
| Pieza | Capa |
|---|---|
| Entidad, agregado, value object (`Money`, `TimeRange`), evento de dominio, política | `domain` (dataclasses, sin frameworks) |
| Caso de uso, puerto (`Protocol`/ABC), mapper de aplicación | `application` |
| Modelo ORM, repositorio SQLAlchemy, adaptador externo | `infrastructure` |
| Router, esquema Pydantic, dependencia de auth | `presentation` |
| Interfaces y DTOs que otros módulos pueden usar | `public_api.py` |
| Ensamblaje de dependencias | `composition.py` |

## Reglas
- `domain` no importa FastAPI, SQLAlchemy ni Pydantic.
- `application` depende solo de `domain` y define los puertos; `infrastructure` los implementa.
- Otro módulo se usa **solo** por su `public_api`.
- Entidades de dominio ≠ modelos ORM ≠ esquemas Pydantic: mapeo explícito entre ellos.
- Un caso de uso = una clase con `async def execute(self, input) -> Output`; el input es un dataclass.
- Errores de negocio = excepciones de dominio tipadas con `code` estable; `presentation` las traduce a Problem Details.
- La transacción la abre el caso de uso con `UnitOfWork`, no el router.
- Eventos de dominio: se recogen en el agregado y se despachan en proceso al confirmar la transacción.
- Reloj (`Clock`) e IDs inyectables; nada de `datetime.now()` en dominio o aplicación.

## Patrones del proyecto
- **Value objects:** `Money(amount_cents, currency)`, `TimeRange(start, end)` (UTC, `end > start`).
- **Agregados:** `Booking` (con sus ítems), `InventoryLot`, `LedgerEntry` (inmutable), `Venue`.
- **Consultas:** las queries de lectura pueden usar SQL directo en `infrastructure` y devolver DTOs, sin pasar por el agregado.

## Checklist antes de terminar
- [ ] ¿Dominio sin imports de frameworks?
- [ ] ¿Algún import a internals de otro módulo? (debe ser cero)
- [ ] ¿Lógica de negocio fuera de routers y repositorios?
- [ ] ¿Caso de uso probado sin base de datos?
- [ ] `just arch` y `just check` en verde.
