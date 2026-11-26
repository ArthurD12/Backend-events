"""Contrato en PDF con ReportLab (HU43, ADR 0004).

Dibuja lo que la aplicación le entrega en `ContractDocument`: no calcula ni consulta nada. Mismo
estilo que la cotización (`quote_pdf.py`): A4, Helvetica, montos en soles y fechas de Lima.
"""

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from local_eventos.modules.commercial.application.contracts.ports.document import ContractDocument
from local_eventos.modules.commercial.domain.contracts.contract import ContractStatus
from local_eventos.modules.commercial.domain.quotes.quote import LineKind, LineUnit
from local_eventos.modules.commercial.infrastructure.quote_pdf import (
    _DARK,
    _EVENT_TYPES,
    _LINE,
    _MUTED,
    _SOFT,
    _facts,
    _long_date,
    _styles,
    soles,
)

_STATUS = {
    ContractStatus.PENDING_SIGNATURE: "Pendiente de firma",
    ContractStatus.SIGNED: "Firmado",
    ContractStatus.CANCELLED: "Anulado",
}


class ReportLabContractRenderer:
    def __init__(self, *, compress: bool = True) -> None:
        self._compress = compress  # sin compresión, las pruebas pueden leer el texto del PDF

    def render(self, document: ContractDocument) -> bytes:
        buffer = BytesIO()
        contract, quote, client = document.contract, document.quote, document.client
        company = document.company
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=f"Contrato {contract.code}",
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
                        f"<font size=16 color='#2563EB'><b>CONTRATO</b></font><br/>"
                        f"<b>{escape(contract.code)}</b><br/>"
                        f"Emitido: {_long_date(document.issued_on)}<br/>"
                        f"Estado: {_STATUS[contract.status]}",
                        "right",
                    ),
                ]
            ],
            colWidths=["55%", "45%"],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        details = quote.details
        schedule = f"{details.start_time:%H:%M} a {details.end_time:%H:%M}"
        if details.ends_next_day:
            schedule += " (del día siguiente)"
        client_rows = [
            ("Cliente", client.name),
            ("Documento", f"{client.document.type.value} {client.document.number}"),
            ("Teléfono", client.phone),
        ]
        if client.email:
            client_rows.append(("Correo", client.email))
        event_rows = [
            ("Tipo de evento", _EVENT_TYPES[details.event_type]),
            ("Fecha", _long_date(contract.event_date)),
            ("Horario", schedule),
            ("Lugar", details.venue),
            ("Invitados", str(details.guests)),
        ]
        info = Table(
            [
                [p("<b>DATOS DEL CLIENTE</b>", "section"), p("<b>DATOS DEL EVENTO</b>", "section")],
                [_facts(client_rows, styles), _facts(event_rows, styles)],
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

        rows: list[list[Paragraph | str]] = [
            [
                p("<b>Servicio</b>", "th"),
                p("<b>Cant.</b>", "th_right"),
                p("<b>Precio</b>", "th_right"),
                p("<b>Subtotal</b>", "th_right"),
            ]
        ]
        for line in quote.lines:
            if line.kind is LineKind.EXTRA:
                kind = "Concepto adicional"
            elif line.unit is LineUnit.PER_PERSON:
                kind = "Por persona"
            else:
                kind = "Por unidad"
            rows.append(
                [
                    p(f"{escape(line.description)}<br/><font size=7 color='#64748B'>{kind}</font>"),
                    p(str(line.quantity), "right"),
                    p(soles(line.unit_price_cents), "right"),
                    p(soles(line.subtotal_cents), "right"),
                ]
            )
        total = p(f"<b>{soles(contract.total_cents)}</b>", "total")
        rows.append(["", "", p("<b>TOTAL</b>", "right"), total])
        services = Table(rows, colWidths=["52%", "12%", "18%", "18%"], repeatRows=1)
        services.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _DARK),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("LINEBELOW", (0, 1), (-1, -2), 0.5, _LINE),
                    ("LINEABOVE", (2, -1), (-1, -1), 1, _DARK),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )

        amounts = Table(
            [
                [p("Total del contrato"), p(soles(contract.total_cents), "right")],
                [p("Adelanto pactado"), p(soles(contract.advance_cents), "right")],
                [
                    p(f"<b>Saldo</b> (hasta el {_long_date(contract.balance_due_date)})"),
                    p(f"<b>{soles(contract.balance_cents)}</b>", "total"),
                ],
            ],
            colWidths=["70%", "30%"],
        )
        amounts.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -2), 0.5, _LINE)]))

        story: list[Flowable] = [
            header,
            Spacer(1, 5 * mm),
            info,
            Spacer(1, 5 * mm),
            services,
            Spacer(1, 3 * mm),
            p("Precios finales en soles (PEN). No incluye IGV aparte.", "muted"),
            Spacer(1, 4 * mm),
            p("<b>MONTOS Y PLAZOS</b>", "section"),
            amounts,
        ]
        if contract.signature is not None:  # CA-43.4
            signature = contract.signature
            story += [
                Spacer(1, 2 * mm),
                p(
                    f"Firmado el {_long_date(signature.signed_on)} por "
                    f"<b>{escape(signature.signer_name)}</b>."
                ),
            ]
        story += [Spacer(1, 5 * mm), p("<b>CONDICIONES Y POLÍTICA DE CANCELACIÓN</b>", "section")]
        for number, term in enumerate(document.terms, start=1):
            story.append(p(f"{number}. {escape(term)}"))
            story.append(Spacer(1, 1 * mm))

        lines = Table(
            [
                [p("<br/><br/>"), "", p("<br/><br/>"), ""],
                [
                    p(
                        f"<b>Firma del cliente</b><br/>{escape(client.name)}<br/>"
                        f"{client.document.type.value} {escape(client.document.number)}",
                        "muted",
                    ),
                    "",
                    p(
                        f"<b>Por {escape(company.name)}</b>"
                        + (f"<br/>RUC {escape(company.ruc)}" if company.ruc else ""),
                        "muted",
                    ),
                    "",
                ],
            ],
            colWidths=["42%", "8%", "42%", "8%"],
        )
        lines.setStyle(
            TableStyle(
                [
                    ("LINEABOVE", (0, 1), (0, 1), 0.8, _MUTED),
                    ("LINEABOVE", (2, 1), (2, 1), 0.8, _MUTED),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story += [
            Spacer(1, 4 * mm),
            KeepTogether(
                [
                    p("<b>FIRMAS</b>", "section"),
                    Spacer(1, 2 * mm),
                    lines,
                ]
            ),
        ]
        pdf.build(story)
        return buffer.getvalue()
