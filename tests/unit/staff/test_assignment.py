"""Asignación (HU17) y disponibilidad (CA-16.4) en el dominio."""

from datetime import UTC, date, datetime, time
from uuid import uuid4

import pytest

from local_eventos.modules.staff.domain.assignment import Assignment, AssignmentStatus
from local_eventos.modules.staff.domain.availability import Availability, AvailabilityStatus
from local_eventos.modules.staff.domain.errors import StaffRuleError, StaffValidationError
from local_eventos.modules.staff.domain.period import Period
from local_eventos.modules.staff.domain.unavailability import Unavailability
from local_eventos.modules.staff.domain.worker import (
    DocumentType,
    Worker,
    WorkerData,
    WorkerFunction,
    WorkerType,
)

NOW = datetime(2026, 11, 25, 15, tzinfo=UTC)
DAY = date(2026, 12, 19)


def _worker() -> Worker:
    return Worker.register(
        WorkerData(
            name="Luis Quispe", document_type=DocumentType.DNI, document_number="40000001",
            phone="987654321", function=WorkerFunction.COOK, worker_type=WorkerType.FIXED,
            reference_rate_cents=15_000,
        ),
        created_by=uuid4(), now=NOW,
    )  # fmt: skip


def _assignment(worker: Worker, period: Period, code: str = "EVT-2026-0001") -> Assignment:
    return Assignment.create(
        worker_id=worker.id, event_id=uuid4(), event_code=code, function=WorkerFunction.COOK,
        period=period, agreed_pay_cents=15_000, created_by=uuid4(), now=NOW,
    )  # fmt: skip


def test_ca17_2_asignacion_vigente_con_pago_acordado() -> None:
    assignment = _assignment(_worker(), Period.on(DAY, time(20), time(3)))

    assert assignment.status is AssignmentStatus.ACTIVE
    assert assignment.agreed_pay_cents == 15_000
    assert assignment.withdrawal is None


def test_r_stf_3_pago_cero_si_negativo_no() -> None:
    worker = _worker()
    common = {
        "worker_id": worker.id, "event_id": uuid4(), "event_code": "EVT-2026-0001",
        "function": WorkerFunction.OTHER, "period": Period.on(DAY, time(9), time(10)),
        "created_by": uuid4(), "now": NOW,
    }  # fmt: skip

    assert Assignment.create(agreed_pay_cents=0, **common).agreed_pay_cents == 0  # type: ignore[arg-type]
    with pytest.raises(StaffValidationError):
        Assignment.create(agreed_pay_cents=-100, **common)  # type: ignore[arg-type]


def test_ca17_7_retirar_deja_quien_cuando_y_motivo() -> None:
    assignment = _assignment(_worker(), Period.on(DAY, time(20), time(3)))
    by = uuid4()

    assignment.withdraw(reason="  Se enfermó ", withdrawn_by=by, now=NOW)

    assert assignment.status is AssignmentStatus.WITHDRAWN
    assert assignment.withdrawal is not None
    assert (assignment.withdrawal.reason, assignment.withdrawal.withdrawn_by) == ("Se enfermó", by)
    with pytest.raises(StaffRuleError) as error:
        assignment.withdraw(reason=None, withdrawn_by=by, now=NOW)
    assert error.value.code == "staff.assignment_already_withdrawn"


def test_motivo_de_retiro_demasiado_largo() -> None:
    assignment = _assignment(_worker(), Period.on(DAY, time(20), time(3)))

    with pytest.raises(StaffValidationError):
        assignment.withdraw(reason="x" * 201, withdrawn_by=uuid4(), now=NOW)
    assert assignment.is_active


def test_ca16_4_libre_ocupado_y_no_disponible() -> None:
    worker = _worker()
    night = Period.on(DAY, time(20), time(3))
    busy = _assignment(worker, Period.on(DAY, time(18), time(23)), code="EVT-2026-0007")
    away = Unavailability.create(
        worker_id=worker.id, period=Period.on(DAY, time(0), time(23)), reason=None,
        created_by=uuid4(), now=NOW,
    )  # fmt: skip
    withdrawn = _assignment(worker, Period.on(DAY, time(21), time(22)))
    withdrawn.withdraw(reason=None, withdrawn_by=uuid4(), now=NOW)

    both = Availability.of(worker, night, [withdrawn, busy], [away])
    only_away = Availability.of(worker, night, [withdrawn], [away])
    free = Availability.of(worker, Period.on(DAY, time(8), time(10)), [busy], [])

    assert (both.status, both.event_code, both.period) == (
        AvailabilityStatus.BUSY,
        "EVT-2026-0007",
        busy.period,
    )
    assert (only_away.status, only_away.period) == (AvailabilityStatus.UNAVAILABLE, away.period)
    assert free.status is AvailabilityStatus.FREE
