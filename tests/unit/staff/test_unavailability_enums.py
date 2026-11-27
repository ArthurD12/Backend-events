"""Pruebas de los enums de disponibilidad del personal (HU16, T-01). Sin base de datos."""

from __future__ import annotations

from enum import StrEnum

import pytest

from local_eventos.modules.staff.domain.enums import (
    AvailabilityState,
    UnavailabilityKind,
    UnavailabilityStatus,
)


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (UnavailabilityKind.VACATION, "VACATION"),
        (UnavailabilityKind.LEAVE, "LEAVE"),
        (UnavailabilityKind.REST, "REST"),
        (UnavailabilityKind.OTHER, "OTHER"),
    ],
)
def test_unavailability_kind_values_are_stable(kind: UnavailabilityKind, value: str) -> None:
    assert isinstance(kind, StrEnum)
    assert kind.value == value
    assert str(kind) == value
    assert kind == value


@pytest.mark.parametrize(
    ("status", "value"),
    [
        (UnavailabilityStatus.ACTIVE, "ACTIVE"),
        (UnavailabilityStatus.CANCELLED, "CANCELLED"),
    ],
)
def test_unavailability_status_values_are_stable(
    status: UnavailabilityStatus, value: str
) -> None:
    assert isinstance(status, StrEnum)
    assert status.value == value
    assert str(status) == value
    assert status == value


@pytest.mark.parametrize(
    ("state", "value"),
    [
        (AvailabilityState.FREE, "FREE"),
        (AvailabilityState.BUSY, "BUSY"),
        (AvailabilityState.UNAVAILABLE, "UNAVAILABLE"),
    ],
)
def test_availability_state_values_are_stable(state: AvailabilityState, value: str) -> None:
    assert isinstance(state, StrEnum)
    assert state.value == value
    assert str(state) == value
    assert state == value


def test_enums_have_exactly_the_expected_members() -> None:
    assert {member.value for member in UnavailabilityKind} == {
        "VACATION",
        "LEAVE",
        "REST",
        "OTHER",
    }
    assert {member.value for member in UnavailabilityStatus} == {"ACTIVE", "CANCELLED"}
    assert {member.value for member in AvailabilityState} == {"FREE", "BUSY", "UNAVAILABLE"}
