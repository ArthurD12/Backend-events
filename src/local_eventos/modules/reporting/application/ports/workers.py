"""Puerto de los trabajadores para el reporte de personal (CA-32.5; depende de `staff`).

`staff.public_api` aún no publica esta consulta (pedido en COORDINACION.md §4): mientras tanto,
el ensamblaje entrega `None` y el reporte responde `report.unavailable`. Cuando exista, solo
cambia el adaptador de `infrastructure`.
"""

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WorkerReportItem:
    name: str
    document: str
    function: str
    kind: str  # tipo de trabajador, ya en español
    rate_cents: int | None
    active: bool


class WorkersReportLookup(Protocol):
    async def __call__(
        self, function: str | None = None, active: bool | None = None
    ) -> list[WorkerReportItem]: ...
