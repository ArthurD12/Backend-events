"""Ficha consolidada del evento (HU14, CA-14.1 a CA-14.7).

`reporting` junta, en el momento de pedirla, lo que cada módulo sabe del evento, siempre por su
`public_api` (nada copiado). La cuenta del contrato solo se consulta si quien la pide puede ver
los pagos (CA-14.5); el personal llega por un puerto que hoy no tiene datos (CA-14.3).
"""

from dataclasses import dataclass
from uuid import UUID

from local_eventos.modules.commercial.public_api import (
    EventAccount,
    EventAccountLookup,
    EventDetail,
    EventDetailLookup,
    EventFollowUp,
    EventFollowUpLookup,
)
from local_eventos.modules.identity.public_api import UserNamesLookup
from local_eventos.modules.inventory.public_api import EventMaterialInfo, EventMaterialsLookup
from local_eventos.modules.reporting.application.errors import ReportEventNotFoundError
from local_eventos.modules.reporting.application.ports.event_staff import (
    EventStaffLookup,
    StaffAssignment,
)


@dataclass(frozen=True)
class EventSheet:
    event: EventDetail  # con su cliente y servicios
    staff: list[StaffAssignment] | None  # `None`: sin información de personal
    materials: list[EventMaterialInfo]
    account: EventAccount | None  # `None`: quien la pide no ve pagos
    follow_up: EventFollowUp
    user_names: dict[UUID, str]  # responsable, responsables de actividades y autores de notas


class GetEventSheet:
    def __init__(
        self,
        details: EventDetailLookup,
        follow_up: EventFollowUpLookup,
        materials: EventMaterialsLookup,
        accounts: EventAccountLookup,
        staff: EventStaffLookup,
        user_names: UserNamesLookup,
    ) -> None:
        self._details = details
        self._follow_up = follow_up
        self._materials = materials
        self._accounts = accounts
        self._staff = staff
        self._user_names = user_names

    async def __call__(self, event_id: UUID, *, include_account: bool) -> EventSheet:
        """Una sola consulta por bloque, en la misma transacción (sin llamadas en paralelo)."""
        event = await self._details(event_id)
        if event is None:
            raise ReportEventNotFoundError()
        follow_up = await self._follow_up(event.id)
        materials = await self._materials(event.id)
        account = await self._accounts(event.id) if include_account else None
        staff = await self._staff(event.id)
        ids = {event.coordinator_id}
        ids |= {a.responsible_id for a in follow_up.activities}
        ids |= {n.created_by for n in follow_up.recent_notes}
        return EventSheet(
            event=event,
            staff=staff,
            materials=materials,
            account=account,
            follow_up=follow_up,
            user_names=await self._user_names(ids),
        )
