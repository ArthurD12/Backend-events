"""PDF de la cotización con ReportLab (HU09, ADR 0004).

Dibuja lo que la aplicación le entrega en `QuoteDocument`: no calcula ni consulta nada. Los
montos salen de la cotización guardada (CA-09.3). Tamaño A4, fuentes estándar de PDF
(Helvetica), que incluyen tildes y la ñ sin instalar fuentes.
"""

from datetime import date
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from local_eventos.modules.commercial.application.quotes.ports.document import QuoteDocument
from local_eventos.modules.commercial.domain.quotes.quote import (
    EventType,
    LineKind,
    LineUnit,
)

_EVENT_TYPES = {
    EventType.WEDDING: "Matrimonio",
    EventType.BIRTHDAY: "Cumpleaños",
    EventType.QUINCEANERA: "Quinceañero",
    EventType.CORPORATE: "Corporativo",
    EventType.GRADUATION: "Promoción",
    EventType.OTHER: "Otro",
}
_MONTHS = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]  # fmt: skip
_PRIMARY = colors.HexColor("#2563EB")
_DARK = colors.HexColor("#0F172A")
_MUTED = colors.HexColor("#64748B")
_LINE = colors.HexColor("#E2E8F0")
_SOFT = colors.HexColor("#F1F5F9")


def soles(cents: int) -> str:
    """4550 → "S/ 45.50"; 545000 → "S/ 5,450.00"."""
    return f"S/ {cents / 100:,.2f}"


def _long_date(value: date) -> str:
    return f"{value.day} de {_MONTHS[value.month - 1]} de {value.year}"


class ReportLabQuoteRenderer:
    def __init__(self, *, compress: bool = True) -> None:
        self._compress = compress  # sin compresión, las pruebas pueden leer el texto del PDF

    def render(self, document: QuoteDocument) -> bytes:
        buffer = BytesIO()
        quote, client, company = document.quote, document.client, document.company
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=f"Cotización {quote.code}",
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
                        f"<font size=16 color='#2563EB'><b>COTIZACIÓN</b></font><br/>"
                        f"<b>{escape(quote.code)}</b><br/>"
                        f"Emitida: {_long_date(document.issued_on)}<br/>"
                        f"Válida hasta: {_long_date(quote.valid_until)}",
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
        document_line = f"{client.document.type.value} {client.document.number}"
        client_rows = [
            ("Cliente", client.name),
            ("Documento", document_line),
            ("Teléfono", client.phone),
        ]
        if client.email:
            client_rows.append(("Correo", client.email))
        event_rows = [
            ("Tipo de evento", _EVENT_TYPES[details.event_type]),
            ("Fecha", _long_date(details.event_date)),
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
                p("<b>Descripción</b>", "th"),
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
        rows.append(
            ["", "", p("<b>TOTAL</b>", "right"), p(f"<b>{soles(quote.total_cents)}</b>", "total")]
        )
        lines = Table(rows, colWidths=["52%", "12%", "18%", "18%"], repeatRows=1)
        lines.setStyle(
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

        story = [
            header,
            Spacer(1, 8 * mm),
            info,
            Spacer(1, 8 * mm),
            lines,
            Spacer(1, 3 * mm),
            p("Precios finales en soles (PEN). No incluye IGV aparte.", "muted"),
        ]
        if quote.notes:
            story += [Spacer(1, 6 * mm), p("<b>NOTAS</b>", "section"), p(escape(quote.notes))]
        story += [
            Spacer(1, 10 * mm),
            p(f"Esta cotización es válida hasta el {_long_date(quote.valid_until)}.", "muted"),
        ]
        pdf.build(story)
        return buffer.getvalue()


def _facts(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [Paragraph(label, styles["label"]), Paragraph(escape(value), styles["body"])]
            for label, value in rows
        ],
        colWidths=[28 * mm, None],
    )
    table.setStyle(
        TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)])
    )
    return table


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    body = ParagraphStyle("body", parent=base, fontName="Helvetica", fontSize=9, leading=12)
    right = ParagraphStyle("right", parent=body, alignment=TA_RIGHT)
    return {
        "body": body,
        "right": right,
        "company": ParagraphStyle("company", parent=body, fontSize=10, leading=14, textColor=_DARK),
        "section": ParagraphStyle("section", parent=body, fontSize=8, textColor=_PRIMARY),
        "label": ParagraphStyle("label", parent=body, textColor=_MUTED),
        "muted": ParagraphStyle("muted", parent=body, fontSize=8, textColor=_MUTED),
        "th": ParagraphStyle("th", parent=body, textColor=colors.white),
        "th_right": ParagraphStyle("th_right", parent=right, textColor=colors.white),
        "total": ParagraphStyle("total", parent=right, fontSize=11, leading=14),
    }
