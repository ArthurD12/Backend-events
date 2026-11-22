"""Entidad Contrato (HU41–HU42): adelanto, saldo, firma y anulación."""

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

import pytest

from local_eventos.modules.commercial.domain.contracts.contract import (
    Contract,
    ContractRuleError,
    ContractStatus,
    ContractValidationError,
    default_advance,
    format_contract_code,
)
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventDetails,
    EventType,
    LineKind,
    LineUnit,
    Quote,
    QuoteLine,
    QuoteStatus,
)

TODAY = date(2026, 11, 22)
NOW = datetime(2026, 11, 22, 15, tzinfo=UTC)


def _quote(total: int = 545_001, status: QuoteStatus | None = QuoteStatus.ACCEPTED) -> Quote:
    quote = Quote.create(
        code="COT-2026-0001",
        client_id=uuid4(),
        details=EventDetails(
            event_type=EventType.WEDDING,
            event_date=date(2026, 12, 19),
            start_time=time(20),
            end_time=time(3),
            venue="Local Los Jardines",
            guests=100,
        ),
        lines=[
            QuoteLine(
                kind=LineKind.EXTRA,
                description="Paquete",
                unit=LineUnit.PER_UNIT,
                quantity=1,
                unit_price_cents=total,
            )
        ],
        created_by=uuid4(),
        now=NOW,
        today=TODAY,
    )
    if status:
        quote.change_status(status, TODAY)
    return quote


def _contract(**changes: object) -> Contract:
    data: dict[str, object] = {
        "code": "CON-2026-0001",
        "quote": _quote(),
        "today": TODAY,
        "created_by": uuid4(),
        "now": NOW,
        **changes,
    }
    return Contract.generate(**data)  # type: ignore[arg-type]


def _sign(contract: Contract, **changes: object) -> None:
    data: dict[str, object] = {
        "signed_on": TODAY,
        "signer_name": "  José   Ramírez ",
        "advance_payment_id": uuid4(),
        "recorded_by": uuid4(),
        "now": NOW,
        "today": TODAY,
        **changes,
    }
    contract.sign(**data)  # type: ignore[arg-type]


def test_ca41_genera_pendiente_con_50_por_ciento_y_saldo_a_7_dias() -> None:
    quote = _quote()
    contract = _contract(quote=quote)

    assert contract.status is ContractStatus.PENDING_SIGNATURE
    assert (contract.quote_id, contract.client_id) == (quote.id, quote.client_id)
    assert contract.total_cents == 545_001
    assert contract.advance_cents == 272_501  # 50 %, medio céntimo hacia arriba
    assert contract.balance_cents == 272_500
    assert contract.balance_due_date == date(2026, 12, 12)
    assert contract.can_become_event is False


def test_ca41_3_el_adelanto_se_puede_ajustar() -> None:
    assert _contract(advance_cents=100_000).advance_cents == 100_000
    assert _contract(advance_cents=545_001).balance_cents == 0


@pytest.mark.parametrize("advance", [0, -1, 545_002])
def test_r_con_2_adelanto_mayor_que_cero_y_no_mayor_que_el_total(advance: int) -> None:
    with pytest.raises(ContractValidationError) as error:
        _contract(advance_cents=advance)
    assert error.value.code == "contract.advance_invalid"


@pytest.mark.parametrize("status", [None, QuoteStatus.SENT, QuoteStatus.REJECTED])
def test_ca41_1_solo_desde_cotizacion_aceptada(status: QuoteStatus | None) -> None:
    with pytest.raises(ContractRuleError) as error:
        _contract(quote=_quote(status=status))
    assert error.value.code == "contract.quote_not_accepted"


def test_ca42_1_firma_con_fecha_y_firmante_y_queda_listo_para_evento() -> None:
    contract = _contract()

    _sign(contract)

    assert contract.status is ContractStatus.SIGNED
    assert contract.signature is not None
    assert (contract.signature.signed_on, contract.signature.signer_name) == (TODAY, "José Ramírez")
    assert contract.can_become_event is True


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"signer_name": "  "}, "contract.signer_required"),
        ({"signed_on": TODAY + timedelta(days=1)}, "contract.signed_on_future"),
    ],
)
def test_ca42_1_datos_de_firma_validos(changes: dict[str, object], code: str) -> None:
    contract = _contract()
    with pytest.raises(ContractValidationError) as error:
        _sign(contract, **changes)
    assert error.value.code == code
    assert contract.status is ContractStatus.PENDING_SIGNATURE


def test_ca42_2_firmado_no_se_vuelve_a_firmar() -> None:
    contract = _contract()
    _sign(contract)

    with pytest.raises(ContractRuleError) as error:
        _sign(contract)
    assert error.value.code == "contract.not_pending"


def test_ca42_4_anular_exige_motivo() -> None:
    contract = _contract()
    with pytest.raises(ContractValidationError) as error:
        contract.cancel(
            reason="  ", refund_cents=None, refund_payment_id=None, note=None,
            cancelled_by=uuid4(), now=NOW,
        )  # fmt: skip
    assert error.value.code == "contract.reason_required"


def test_r_con_3_anular_firmado_con_devolucion_registrada() -> None:
    contract = _contract()
    _sign(contract)
    refund_id = uuid4()

    contract.cancel(
        reason="El cliente canceló la boda",
        refund_cents=100_000,
        refund_payment_id=refund_id,
        note="Acuerdo de palabra",
        cancelled_by=uuid4(),
        now=NOW,
    )

    assert contract.status is ContractStatus.CANCELLED
    assert contract.cancellation is not None
    assert (contract.cancellation.refund_cents, contract.cancellation.refund_payment_id) == (
        100_000,
        refund_id,
    )
    assert contract.can_become_event is False


@pytest.mark.parametrize(("signed", "refund"), [(True, 272_502), (False, 1), (True, 0)])
def test_r_con_3_devolucion_no_supera_lo_pagado(signed: bool, refund: int) -> None:
    contract = _contract()
    if signed:
        _sign(contract)

    with pytest.raises(ContractValidationError) as error:
        contract.check_cancellation("Motivo", refund)
    assert error.value.code == "contract.refund_invalid"


def test_anulado_no_se_anula_otra_vez() -> None:
    contract = _contract()
    contract.cancel(
        reason="Motivo", refund_cents=None, refund_payment_id=None, note=None,
        cancelled_by=uuid4(), now=NOW,
    )  # fmt: skip

    with pytest.raises(ContractRuleError) as error:
        contract.check_cancellation("Otra vez", None)
    assert error.value.code == "contract.already_cancelled"


def test_codigo_y_redondeo() -> None:
    assert format_contract_code(2026, 3) == "CON-2026-0003"
    assert (default_advance(1), default_advance(2), default_advance(545_000)) == (1, 1, 272_500)
