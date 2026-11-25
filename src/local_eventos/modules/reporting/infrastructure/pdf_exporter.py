"""Reporte en PDF con ReportLab (CA-34.1, ADR 0004): A4 horizontal, datos de Darze, título,
filtros, fecha de generación (Lima), la tabla y los totales. Dibuja la `ReportTable` tal cual:
no calcula ni consulta nada (CA-34.2)."""

from io import BytesIO
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from local_eventos.modules.commercial.public_api import CompanyProfile
from local_eventos.modules.reporting.application.reports.table import ColumnType, ReportTable
from local_eventos.modules.reporting.infrastructure.formatting import lima, pdf_cell

_PRIMARY = colors.HexColor("#2563EB")
_DARK = colors.HexColor("#0F172A")
_MUTED = colors.HexColor("#64748B")
_LINE = colors.HexColor("#E2E8F0")
_SOFT = colors.HexColor("#F1F5F9")
_RIGHT = (ColumnType.MONEY, ColumnType.QUANTITY, ColumnType.INTEGER)
_WIDE = (ColumnType.TEXT,)


class PdfExporter:
    media_type = "application/pdf"
    extension = "pdf"

    def __init__(self, *, compress: bool = True) -> None:
        self._compress = compress  # sin compresión, las pruebas pueden leer el texto del PDF

    def export(self, table: ReportTable, company: CompanyProfile) -> bytes:
        buffer = BytesIO()
        page = landscape(A4)
        pdf = SimpleDocTemplate(
            buffer,
            pagesize=page,
            leftMargin=12 * mm,
            rightMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=14 * mm,
            title=table.title,
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
        generated = f"Generado: {lima(table.generated_at)}"
        header = Table(
            [
                [
                    p("<br/>".join(company_lines), "company"),
                    p(
                        f"<font size=15 color='#2563EB'><b>{escape(table.title.upper())}</b>"
                        f"</font><br/>{generated}",
                        "right",
                    ),
                ]
            ],
            colWidths=["50%", "50%"],
        )
        header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        filters = "  ·  ".join(
            f"<b>{escape(f.label)}:</b> {escape(f.value)}" for f in table.filters
        )

        right = [c.type in _RIGHT for c in table.columns]
        rows: list[list[Any]] = [
            [p(f"<b>{escape(c.label)}</b>", "th_right" if r else "th")
             for c, r in zip(table.columns, right, strict=True)]
        ]  # fmt: skip
        for row in table.rows:
            rows.append(
                [
                    p(escape(pdf_cell(value, c.type)), "cell_right" if r else "cell")
                    for value, c, r in zip(row, table.columns, right, strict=True)
                ]
            )
        if len(rows) == 1:
            rows.append([p("Sin datos para estos filtros.", "muted")] + [""] * (len(right) - 1))
        weights = [2 if c.type in _WIDE else 1 for c in table.columns]
        width = page[0] - 24 * mm
        grid = Table(rows, colWidths=[width * w / sum(weights) for w in weights], repeatRows=1)
        style: list[Any] = [
            ("BACKGROUND", (0, 0), (-1, 0), _DARK),
            ("LINEBELOW", (0, 1), (-1, -1), 0.5, _LINE),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        if len(table.rows) == 0:
            style.append(("SPAN", (0, 1), (-1, 1)))
        grid.setStyle(TableStyle(style))

        story: list[Any] = [header, Spacer(1, 4 * mm)]
        if filters:
            story += [p(filters, "filters"), Spacer(1, 3 * mm)]
        story.append(grid)
        if table.totals:
            totals = Table(
                [
                    [p(escape(t.label), "label"), p(f"<b>{escape(pdf_cell(t.value, t.type))}</b>",
                                                     "cell_right")]
                    for t in table.totals
                ],
                colWidths=[70 * mm, 40 * mm],
                hAlign="RIGHT",
            )  # fmt: skip
            totals.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), _SOFT),
                        ("BOX", (0, 0), (-1, -1), 0.5, _LINE),
                        ("TOPPADDING", (0, 0), (-1, -1), 2),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                    ]
                )
            )
            story += [Spacer(1, 4 * mm), p("<b>TOTALES</b>", "section"), totals]
        for note in table.notes:
            story += [Spacer(1, 2 * mm), p(escape(note), "muted")]

        def footer(canvas: Any, document: Any) -> None:
            canvas.saveState()
            canvas.setFont("Helvetica", 7)
            canvas.setFillColor(_MUTED)
            canvas.drawString(12 * mm, 7 * mm, f"{company.name} · {table.title} · {generated}")
            canvas.drawRightString(page[0] - 12 * mm, 7 * mm, f"Página {document.page}")
            canvas.restoreState()

        pdf.build(story, onFirstPage=footer, onLaterPages=footer)
        return buffer.getvalue()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["Normal"]
    body = ParagraphStyle("body", parent=base, fontName="Helvetica", fontSize=9, leading=12)
    cell = ParagraphStyle("cell", parent=body, fontSize=8, leading=10)
    return {
        "body": body,
        "right": ParagraphStyle("right", parent=body, alignment=TA_RIGHT),
        "company": ParagraphStyle("company", parent=body, fontSize=10, leading=14, textColor=_DARK),
        "filters": ParagraphStyle("filters", parent=body, textColor=_DARK),
        "section": ParagraphStyle("section", parent=body, fontSize=8, textColor=_PRIMARY),
        "label": ParagraphStyle("label", parent=cell, textColor=_DARK),
        "muted": ParagraphStyle("muted", parent=body, fontSize=8, textColor=_MUTED),
        "cell": cell,
        "cell_right": ParagraphStyle("cell_right", parent=cell, alignment=TA_RIGHT),
        "th": ParagraphStyle("th", parent=cell, textColor=colors.white),
        "th_right": ParagraphStyle(
            "th_right", parent=cell, alignment=TA_RIGHT, textColor=colors.white
        ),
    }
