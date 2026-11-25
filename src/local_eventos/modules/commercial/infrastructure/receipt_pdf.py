"""Comprobante interno de un pago en PDF con ReportLab (HU20, ADR 0004).

Dibuja lo que la aplicación le entrega en `PaymentReceipt`: no calcula ni consulta nada. Mismo
estilo que la cotización (`quote_pdf.py`): A4 y fuentes estándar de PDF (Helvetica).
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from local_eventos.modules.commercial.application.contracts.ports.receipt import PaymentReceipt
from local_eventos.modules.commercial.infrastructure.quote_pdf import (
    _LINE,
    _SOFT,
    _facts,
    _long_date,
    _styles,
    soles,
)
from local_eventos.modules.ledger.public_api import PaymentKind, PaymentMethod

_KINDS = {
    PaymentKind.ADVANCE: "Adelanto",
    PaymentKind.INSTALLMENT: "Pago parcial",
    PaymentKind.REFUND: "Devolución",
}
_METHODS = {
    PaymentMethod.CASH: "Efectivo",
    PaymentMethod.TRANSFER: "Transferencia",
    PaymentMethod.CARD: "Tarjeta",
    PaymentMethod.YAPE_PLIN: "Yape/Plin",
}


class ReportLabReceiptRenderer:
    def __init__(self, *, compress: bool = True) -> None:
        self._compress = compress  # sin compresión, las pruebas pueden leer el texto del PDF

    def render(self, receipt: PaymentReceipt) -> bytes:
        buffer = BytesIO()
        payment, void = receipt.entry.payment, receipt.entry.void
        company, client, contract = receipt.company, receipt.client, receipt.contract
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=f"Comprobante {payment.number}",
            author=company.name,
            pageCompression=1 if self._compress else 0,
        )
        styles = _styles()

        def p(text: str, style: str = "body") -> Paragraph:
            return Paragraph(text, styles[style])

        company_lines = [f"<b>{escape(company.name)}</b>"]
        if company.ruc:
            company_lines.append(f"RUC {escape(company.ruc)}")
        for extra in (company.address, company.phone, company.email):
            if extra:
                company_lines.append(escape(extra))
        header = Table(
            [
                [
                    p("<br/>".join(company_lines), "company"),
                    p(
                        f"<font size=14 color='#2563EB'><b>COMPROBANTE DE PAGO</b></font><br/>"
                        f"<b>{escape(payment.number)}</b><br/>"
                        f"Emitido: {_long_date(receipt.issued_on)}",
                        "right",
                    ),
                ]
            ],
            colWidths=["55%", "45%"],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        story: list[Flowable] = [header, Spacer(1, 6 * mm)]
        if void is not None:  # CA-20.3
            story += [
                p("<font size=16 color='#DC2626'><b>ANULADO</b></font>"),
                p(f"Motivo: {escape(void.reason)}"),
                Spacer(1, 4 * mm),
            ]

        client_rows = [
            ("Cliente", client.name),
            ("Documento", f"{client.document.type.value} {client.document.number}"),
            ("Contrato", contract.code),
        ]
        if receipt.event_code:
            client_rows.append(("Evento", receipt.event_code))
        client_rows.append(("Fecha del evento", _long_date(contract.event_date)))
        payment_rows = [
            ("Concepto", _KINDS[payment.kind]),
            ("Fecha de pago", _long_date(payment.paid_on)),
            ("Monto", soles(payment.amount_cents)),
            ("Medio", _METHODS[payment.method]),
        ]
        if payment.reference:
            payment_rows.append(("Referencia", payment.reference))
        payment_rows.append(("Registrado por", receipt.recorded_by_name or "—"))
        info = Table(
            [
                [p("<b>CLIENTE Y CONTRATO</b>", "section"), p("<b>PAGO</b>", "section")],
                [_facts(client_rows, styles), _facts(payment_rows, styles)],
            ],
            colWidths=["50%", "50%"],
        )
        info.setStyle(
            TableStyle(
                [
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("BACKGROUND", (0, 1), (-1, 1), _SOFT),
                    ("BOX", (0, 1), (0, 1), 0.5, _LINE),
                    ("BOX", (1, 1), (1, 1), 0.5, _LINE),
                    ("TOPPADDING", (0, 1), (-1, 1), 6),
                    ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
                ]
            )
        )
        account = Table(
            [
                [p("Total del contrato"), p(soles(contract.total_cents), "right")],
                [p("Pagado"), p(soles(receipt.paid_after_cents), "right")],
                [p("<b>Saldo</b>"), p(f"<b>{soles(receipt.balance_after_cents)}</b>", "total")],
            ],
            colWidths=["70%", "30%"],
        )
        account.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.5, _LINE)]))
        story += [
            info,
            Spacer(1, 8 * mm),
            p("<b>CUENTA DESPUÉS DE ESTE PAGO</b>", "section"),
            account,
            Spacer(1, 10 * mm),
            p("Comprobante interno de pago. No es boleta ni factura.", "muted"),
        ]
        pdf.build(story)
        return buffer.getvalue()
