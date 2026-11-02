"""Etiketten und Plakat als PDF.

Der QR-Code auf einem Etikett enthält nur die Inventarnummer – keinen Link –,
damit Etiketten auch nach einem Systemwechsel gültig bleiben.
Etikettenmaße nach den Vorlagen des freien Programms gLabels (Avery Zweckform, A4).
"""

import io
from dataclasses import dataclass

from reportlab.graphics import renderPDF
from reportlab.graphics.barcode.qr import QrCodeWidget
from reportlab.graphics.shapes import Drawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfgen import canvas

PAGE_W, PAGE_H = A4


@dataclass(frozen=True)
class LabelFormat:
    code: str
    width: float  # alle Maße in mm
    height: float
    columns: int
    rows: int
    left: float
    top: float
    pitch_x: float
    pitch_y: float

    @property
    def per_sheet(self):
        return self.columns * self.rows

    @property
    def label(self):
        return (
            f"Avery Zweckform {self.code} – {self.width:g} × {self.height:g} mm, "
            f"{self.per_sheet} je Blatt"
        ).replace(".", ",")


FORMATS = {
    f.code: f
    for f in (
        LabelFormat("4732", 35.6, 16.9, 5, 16, 11.0, 13.0, 38.1, 16.9),
        LabelFormat("6021", 45.7, 16.9, 4, 16, 8.5, 14.0, 48.3, 16.9),
        LabelFormat("4780", 48.5, 25.4, 4, 10, 8.1, 19.0, 48.5, 25.4),
        LabelFormat("3651", 52.5, 29.7, 4, 10, 0.0, 0.0, 52.5, 29.7),
        LabelFormat("3474", 70.0, 37.0, 3, 8, 0.0, 0.5, 70.0, 37.0),
    )
}
DEFAULT_FORMAT = "4780"


def draw_qr(c, value, x, y, size):
    widget = QrCodeWidget(value, barLevel="M", barBorder=1)
    x1, y1, x2, y2 = widget.getBounds()
    drawing = Drawing(size, size, transform=[size / (x2 - x1), 0, 0, size / (y2 - y1), 0, 0])
    drawing.add(widget)
    renderPDF.draw(drawing, c, x, y)


def _fit_lines(text, font, size, width, max_lines):
    lines = simpleSplit(text, font, size, width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and simpleSplit(last + "…", font, size, width) != [last + "…"]:
            last = last[:-1].rstrip()
        lines[-1] = last + "…"
    return lines


def _positions(fmt, offset_x, offset_y):
    """Linke untere Ecke jedes Etiketts auf dem Blatt (in Punkt), zeilenweise."""
    for row in range(fmt.rows):
        for col in range(fmt.columns):
            left = (fmt.left + col * fmt.pitch_x + offset_x) * mm
            top = (fmt.top + row * fmt.pitch_y + offset_y) * mm
            yield left, PAGE_H - top - fmt.height * mm


def draw_label(c, fmt, x, y, number, title):
    w, h = fmt.width * mm, fmt.height * mm
    pad = 1.5 * mm
    qr = min(h - 2 * pad, w * 0.45, 25 * mm)
    draw_qr(c, number, x + pad, y + (h - qr) / 2, qr)

    text_x = x + pad + qr + 1.5 * mm
    text_w = x + w - pad - text_x
    number_size = max(6.0, min(11.0, h / mm * 0.42))
    title_size = max(5.0, number_size * 0.72)
    number_lines = _fit_lines(number, "Helvetica-Bold", number_size, text_w, 1)
    max_title_lines = max(1, int((h - 2 * pad - number_size * 1.3) // (title_size * 1.15)))
    title_lines = _fit_lines(title, "Helvetica", title_size, text_w, min(max_title_lines, 4))

    block = number_size * 1.2 + len(title_lines) * title_size * 1.15
    cursor = y + (h + block) / 2 - number_size
    c.setFont("Helvetica-Bold", number_size)
    c.drawString(text_x, cursor, number_lines[0])
    c.setFont("Helvetica", title_size)
    for line in title_lines:
        cursor -= title_size * 1.15
        c.drawString(text_x, cursor, line)


def labels_pdf(copies, fmt, start=1, offset_x=0.0, offset_y=0.0):
    """PDF mit je einem Etikett pro Exemplar. `start` überspringt bereits
    benutzte Etiketten auf dem ersten (angebrochenen) Bogen."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Fundus – Etiketten")
    positions = list(_positions(fmt, float(offset_x), float(offset_y)))
    index = max(0, min(start - 1, fmt.per_sheet - 1))
    for copy in copies:
        if index == fmt.per_sheet:
            c.showPage()
            index = 0
        x, y = positions[index]
        draw_label(c, fmt, x, y, copy.inventory_number, copy.title.title)
        index += 1
    c.showPage()
    c.save()
    return buffer.getvalue()


def test_page_pdf(fmt, offset_x=0.0, offset_y=0.0):
    """Rahmen aller Etiketten zum Ausrichten des Druckers."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Fundus – Testseite Etiketten")
    c.setLineWidth(0.3)
    for number, (x, y) in enumerate(_positions(fmt, float(offset_x), float(offset_y)), 1):
        c.rect(x, y, fmt.width * mm, fmt.height * mm)
        c.setFont("Helvetica", 6)
        c.drawCentredString(x + fmt.width * mm / 2, y + fmt.height * mm / 2 - 2, str(number))
    c.setFont("Helvetica", 8)
    c.drawString(
        12 * mm,
        5 * mm,
        f"Testseite {fmt.label} · Versatz waagerecht {offset_x} mm, senkrecht {offset_y} mm",
    )
    c.showPage()
    c.save()
    return buffer.getvalue()


def poster_pdf(url, school_name=""):
    """A4-Plakat mit QR-Code zur Fundus-Adresse, zum Aufhängen im Lehrerzimmer."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Fundus – Plakat")
    centre = PAGE_W / 2
    c.setFont("Helvetica-Bold", 40)
    c.drawCentredString(centre, PAGE_H - 45 * mm, "Fundus")
    c.setFont("Helvetica", 18)
    subtitle = "Bücher, Tests, Fördermaterial und Technik"
    if school_name:
        subtitle += f" – {school_name}"
    for i, line in enumerate(simpleSplit(subtitle, "Helvetica", 18, PAGE_W - 40 * mm)):
        c.drawCentredString(centre, PAGE_H - 60 * mm - i * 22, line)

    size = 110 * mm
    draw_qr(c, url, centre - size / 2, PAGE_H - 80 * mm - size, size)
    c.setFont("Helvetica", 14)
    c.drawCentredString(centre, PAGE_H - 88 * mm - size, url)

    steps = [
        "1. QR-Code mit der Handykamera scannen.",
        "2. Mit der Schul-E-Mail-Adresse anmelden.",
        "3. Suchen, nachsehen, wo etwas steht – und ob es frei ist.",
    ]
    c.setFont("Helvetica", 16)
    y = PAGE_H - 108 * mm - size
    for step in steps:
        c.drawString(35 * mm, y, step)
        y -= 26
    c.showPage()
    c.save()
    return buffer.getvalue()


def reorder_cards_pdf(items):
    """Nachbestellkarten im Format A6, vier je A4-Blatt (mit Schnittlinien).

    Der QR-Code enthält nur die Kennung des Materials (z. B. NB-0001)."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Fundus – Nachbestellkarten")
    w, h = PAGE_W / 2, PAGE_H / 2
    slots = [(0, h), (w, h), (0, 0), (w, 0)]
    for index, item in enumerate(items):
        if index and index % 4 == 0:
            c.showPage()
        if index % 4 == 0:
            c.setDash(3, 3)
            c.setLineWidth(0.3)
            c.line(w, 0, w, PAGE_H)
            c.line(0, h, PAGE_W, h)
            c.setDash()
        x, y = slots[index % 4]
        pad = 10 * mm
        c.setFont("Helvetica-Bold", 16)
        c.drawString(x + pad, y + h - pad - 6 * mm, "Nachbestellkarte")
        c.setFont("Helvetica", 9)
        c.drawString(
            x + pad,
            y + h - pad - 12 * mm,
            "Diese Karte erreicht? Bitte scannen – dann wird nachbestellt.",
        )
        size = 55 * mm
        draw_qr(c, item.code, x + (w - size) / 2, y + h - pad - 18 * mm - size, size)
        c.setFont("Helvetica-Bold", 13)
        cursor = y + h - pad - 26 * mm - size
        for line in _fit_lines(item.name, "Helvetica-Bold", 13, w - 2 * pad, 2):
            c.drawCentredString(x + w / 2, cursor, line)
            cursor -= 16
        c.setFont("Helvetica", 10)
        c.drawCentredString(x + w / 2, cursor, item.code)
        cursor -= 18
        if item.order_info:
            c.setFont("Helvetica", 8)
            for line in _fit_lines(
                item.order_info.replace("\n", " · "), "Helvetica", 8, w - 2 * pad, 3
            ):
                c.drawString(x + pad, cursor, line)
                cursor -= 10
    c.showPage()
    c.save()
    return buffer.getvalue()
