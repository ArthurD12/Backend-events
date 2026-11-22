"""Arma las líneas de una cotización a partir de lo que pide el encargado (HU07, CA-07.3).

- Servicio del catálogo: se congela su nombre, su unidad y su precio (AGENTS.md, regla 6). Si
  ya estaba en la cotización, conserva lo congelado aunque el catálogo haya cambiado después.
  Solo los servicios nuevos deben estar activos (DOMAIN.md §4, regla 2).
- Por persona: si no se indica cantidad, es la cantidad de invitados (regla 11).
- Concepto adicional: descripción y monto libres (regla 12).
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.catalog.public_api import ServiceLookup
from local_eventos.modules.commercial.application.quotes.errors import (
    QuoteServiceInactiveError,
    QuoteServiceNotFoundError,
)
from local_eventos.modules.commercial.domain.quotes.quote import (
    LineKind,
    LineUnit,
    QuoteLine,
    QuoteValidationError,
)


@dataclass(frozen=True)
class LineInput:
    kind: LineKind
    service_id: UUID | None = None  # solo SERVICE
    description: str | None = None  # solo EXTRA
    quantity: int | None = None
    unit_price_cents: int | None = None  # None = precio del catálogo


async def build_lines(
    inputs: list[LineInput],
    *,
    guests: int,
    services: ServiceLookup,
    previous: tuple[QuoteLine, ...] = (),
) -> list[QuoteLine]:
    frozen = {line.service_id: line for line in previous if line.service_id is not None}
    lines: list[QuoteLine] = []
    for item in inputs:
        if item.kind is LineKind.EXTRA:
            if item.unit_price_cents is None:
                raise QuoteValidationError(
                    "quote.price_invalid", "Cada concepto adicional necesita un monto."
                )
            lines.append(
                QuoteLine(
                    kind=LineKind.EXTRA,
                    description=item.description or "",
                    unit=LineUnit.PER_UNIT,
                    quantity=item.quantity or 1,
                    unit_price_cents=item.unit_price_cents,
                )
            )
            continue

        if item.service_id is None:
            raise QuoteValidationError(
                "quote.line_invalid", "Cada línea de servicio necesita un servicio del catálogo."
            )
        if item.service_id in frozen:
            kept = frozen[item.service_id]
            description, unit, catalog_price = kept.description, kept.unit, kept.catalog_price_cents
        else:
            summary = await services(item.service_id)
            if summary is None:
                raise QuoteServiceNotFoundError()
            if not summary.active:
                raise QuoteServiceInactiveError(summary.name)
            description = summary.name
            unit = LineUnit(summary.price_unit)
            catalog_price = summary.reference_price_cents
        default_quantity = guests if unit is LineUnit.PER_PERSON else 1
        lines.append(
            QuoteLine(
                kind=LineKind.SERVICE,
                description=description,
                unit=unit,
                quantity=item.quantity if item.quantity is not None else default_quantity,
                unit_price_cents=(
                    item.unit_price_cents
                    if item.unit_price_cents is not None
                    else catalog_price or 0
                ),
                service_id=item.service_id,
                catalog_price_cents=catalog_price,
            )
        )
    return lines
