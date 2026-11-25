"""Personal del evento para la ficha (019, CA-14.3): nulo hasta que `staff` lo publique."""

from uuid import uuid4

from local_eventos.modules.reporting import composition


async def test_sin_informacion_de_personal_mientras_staff_no_lo_expone() -> None:
    assert await composition.event_staff()(uuid4()) is None
