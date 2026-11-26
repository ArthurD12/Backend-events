"""PDF de la orden de compra con ReportLab (HU30, ADR 0004).

Dibuja lo que la aplicación le entrega en `PurchaseDocument`: no calcula ni consulta nada. A4 y
fuentes estándar de PDF (Helvetica), que incluyen tildes y la ñ.
"""

from datetime import datetime
from io import BytesIO
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from local_eventos.modules.purchasing.application.ports.document import PurchaseDocument
from local_eventos.modules.purchasing.domain.purchase import PurchaseStatus

_LIMA = ZoneInfo("America/Lima")
_STATUS = {
    PurchaseStatus.REQUESTED: "Solicitada",
    PurchaseStatus.ORDERED: "Ordenada",
    PurchaseStatus.RECEIVED: "Recibida",
    PurchaseStatus.CANCELLED: "Cancelada",
}
_PRIMARY = colors.HexColor("#2563EB")
_DARK = colors.HexColor("#0F172A")
_MUTED = colors.HexColor("#64748B")
_LINE = colors.HexColor("#E2E8F0")
_SOFT = colors.HexColor("#F1F5F9")


def soles(cents: int) -> str:
    """4550 → "S/ 45.50"; 545000 → "S/ 5,450.00"."""
    return f"S/ {cents / 100:,.2f}"


def _day(value: datetime) -> str:
    return value.astimezone(_LIMA).strftime("%d/%m/%Y")


class ReportLabPurchaseRenderer:
    def __init__(self, *, compress: bool = True) -> None:
        self._compress = compress  # sin compresión, las pruebas pueden leer el texto del PDF

    def render(self, document: PurchaseDocument) -> bytes:
        buffer = BytesIO()
        purchase, supplier = document.purchase, document.supplier
        company = document.company
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            leftMargin=18 * mm,
            rightMargin=18 * mm,
            topMargin=16 * mm,
            bottomMargin=16 * mm,
            title=f"Orden de compra {purchase.code}",
            author=company.name,
            pageCompression=1 if self._compress else 0,
        )
        styles = _styles()

        def p(text: str, style: str = "body") -> Paragraph:
            return Paragraph(text, styles[style])

        company_lines = [f"<b>{escape(company.name)}</b>"]
        if company.ruc:
            company_lines.append(f"RUC {escape(company.ruc)}")
        company_lines += [escape(x) for x in (company.address, company.phone, company.email) if x]
        header = Table(
            [
                [
                    p("<br/>".join(company_lines), "company"),
                    p(
                        f"<font size=16 color='#2563EB'><b>ORDEN DE COMPRA</b></font><br/>"
                        f"<b>{escape(purchase.code)}</b><br/>"
                        f"Estado: {_STATUS[purchase.status]}<br/>"
                        f"Creada: {_day(purchase.created.at)}",
                        "right",
                    ),
                ]
            ],
            colWidths=["55%", "45%"],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))

        supplier_rows = [("Proveedor", supplier.name if supplier else "Sin ordenar aún")]
        if supplier:
            supplier_rows.append(
                ("Documento", f"{supplier.document_type.value} {supplier.document_number}")
            )
            supplier_rows.append(("Teléfono", supplier.phone))
        purchase_rows = []
        if document.event_code:
            purchase_rows.append(("Evento", document.event_code))
        if purchase.invoice_number:
            purchase_rows.append(("Factura", purchase.invoice_number))
        if purchase.received:
            purchase_rows.append(("Recibida", _day(purchase.received.at)))
        if purchase.notes:
            purchase_rows.append(("Nota", purchase.notes))
        info = Table(
            [
                [p("<b>PROVEEDOR</b>", "section"), p("<b>COMPRA</b>", "section")],
                [_facts(supplier_rows, styles), _facts(purchase_rows or [("", "")], styles)],
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

        received = purchase.status is PurchaseStatus.RECEIVED
        rows: list[list[Paragraph]] = [
            [
                p("<b>Código</b>", "th"),
                p("<b>Producto</b>", "th"),
                p("<b>Cantidad</b>", "th_right"),
                p("<b>Costo unit.</b>", "th_right"),
                p("<b>Total</b>", "th_right"),
            ]
        ]
        for line in purchase.lines:
            info_p = document.products.get(line.product_id)
            quantity = (
                line.received_quantity
                if received and line.received_quantity is not None
                else line.quantity
            )
            unit = f" {info_p.unit.value}" if info_p else ""
            rows.append(
                [
                    p(escape(info_p.code) if info_p else "—"),
                    p(escape(info_p.name) if info_p else "Producto no disponible"),
                    p(f"{quantity:.3f}{unit}", "right"),
                    p(
                        "—" if line.unit_cost_cents is None else soles(line.unit_cost_cents),
                        "right",
                    ),
                    p("—" if line.total_cents is None else soles(line.total_cents), "right"),
                ]
            )
        table = Table(rows, colWidths=[24 * mm, None, 34 * mm, 28 * mm, 28 * mm], repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), _PRIMARY),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.5, _LINE),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        total = purchase.total_cents
        story = [
            header,
            Spacer(1, 6 * mm),
            info,
            Spacer(1, 6 * mm),
            table,
            Spacer(1, 4 * mm),
            p(
                f"<b>TOTAL: {'Por definir' if total is None else soles(total)}</b>",
                "total",
            ),
        ]
        if purchase.cancel_reason:
            story += [
                Spacer(1, 3 * mm),
                p(f"Motivo de cancelación: {escape(purchase.cancel_reason)}", "muted"),
            ]
        pdf.build(story)
        return buffer.getvalue()


def _facts(rows: list[tuple[str, str]], styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [Paragraph(escape(label), styles["label"]), Paragraph(escape(value), styles["body"])]
            for label, value in rows
        ],
        colWidths=[22 * mm, None],
    )
    table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
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
