"""
Certificate PDFs, drawn with ReportLab.

ReportLab rather than an HTML-to-PDF converter: it is pure Python (pip only),
so it behaves the same on a Mac, AWS and PythonAnywhere — no system libraries
and no browser to install. The price is that the layout is coordinates here
rather than CSS.

THE DESIGN is TestMu AI's Figma certificate. templates/certificates/
certificate.html is the same design in HTML/CSS — the visual reference, and a
quick way to preview it in a browser. Both use the same measurements, taken
from the design on a 1760 × 1320 canvas ("design px"). If the design changes,
change both and compare them side by side.

Assets, all in static/certificates/:
    logo.svg, signature.svg   vectors, from Figma (drawn with svglib)
    seal.png                  cut from Figma's 3× export
    fonts/Rubik-*.ttf         embedded in the PDF, so it never depends on the
                              internet. OFL-licensed (fonts/OFL.txt).

Nothing here is stored: a PDF is generated whenever a certificate is sent.
"""

import io
import re
from pathlib import Path

from django.conf import settings
from reportlab.graphics import renderPDF
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from svglib.svglib import svg2rlg

from .timezones import to_local

ASSETS = Path(settings.BASE_DIR) / "static" / "certificates"

# The page: 11 × 8.25 in, the design's own 4:3 shape. One design px is
# 792 pt / 1760 on it.
PAGE_W, PAGE_H = 792, 594
S = PAGE_W / 1760

FRAME = HexColor("#99a3b3")
BAND = HexColor("#dfe7ef")
GOLD = HexColor("#9f8716")
BLUE = HexColor("#1642df")
TEXT = HexColor("#434343")
INK = HexColor("#000000")
WHITE = HexColor("#ffffff")

#: Content starts on this line, right of the band.
LEFT = 480

_fonts_registered = False


def _register_fonts():
    global _fonts_registered
    if _fonts_registered:
        return
    for name in ("Light", "Regular", "Medium"):
        pdfmetrics.registerFont(TTFont(f"Rubik-{name}", str(ASSETS / "fonts" / f"Rubik-{name}.ttf")))
    _fonts_registered = True


def _pt(px):
    return px * S


def _rect(c, x0, y0, x1, y1, color):
    """A filled rectangle, given in design px from the top-left corner."""
    c.setFillColor(color)
    c.rect(_pt(x0), PAGE_H - _pt(y1), _pt(x1 - x0), _pt(y1 - y0), stroke=0, fill=1)


def _text(c, x, baseline, text, font, size, color):
    """One line of text: x and baseline in design px from the top-left, size in design px."""
    c.setFont(font, _pt(size))
    c.setFillColor(color)
    c.drawString(_pt(x), PAGE_H - _pt(baseline), text)
    return c.stringWidth(text, font, _pt(size)) / S   # its width, in design px


def _load_svg(filename):
    """
    An SVG from static/certificates as a ReportLab drawing.

    Figma writes each colour twice — `fill:#121212;fill:color(display-p3 …)` —
    the hex for older software, the display-p3 form for newer. svglib knows
    only the first, and given the second it drops the colour and the shape
    disappears. So the display-p3 declarations are removed as the file is
    read, leaving the hex; the files themselves stay exactly as exported.
    """
    raw = (ASSETS / filename).read_text()
    return svg2rlg(io.StringIO(re.sub(r"(fill|stroke):color\([^)]*\);?", "", raw)))


def _svg(c, filename, x, top, width):
    """An SVG drawn as vectors, scaled to `width` design px, top-left at (x, top)."""
    drawing = _load_svg(filename)
    scale = _pt(width) / drawing.width
    height = drawing.height * scale
    drawing.scale(scale, scale)
    renderPDF.draw(drawing, c, _pt(x), PAGE_H - _pt(top) - height)
    return height / S


def _lines(text, font, size, max_width):
    """`text` wrapped to `max_width` design px, as the template's CSS wraps it."""
    return simpleSplit(text, font, _pt(size), _pt(max_width)) or [""]


def _date(moment, tz):
    """"October 27, 2026", in the zone the candidate booked in."""
    local = to_local(moment, tz)
    return f"{local:%B} {local.day}, {local.year}"


def certificate_values(certificate):
    """What is printed on a certificate — the same values the HTML template takes."""
    booking = certificate.booking
    candidate = booking.candidate
    return {
        "holder_name": (candidate.display_name or candidate.email) if candidate else "",
        "exam_name": booking.exam.exam_name,
        "issued_on": _date(certificate.issued_at, booking.booked_timezone),
        "valid_until": _date(certificate.expires_at, booking.booked_timezone),
        "certificate_id": str(certificate.certificate_id),
    }


def render_certificate_pdf(values):
    """
    The certificate as PDF bytes. `values` is certificate_values() — or any
    dict of the same five strings, for a sample.
    """
    _register_fonts()
    from io import BytesIO

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Certificate · {values['holder_name']} · {values['exam_name']}")
    c.setAuthor("TestMu AI Certifications")

    # ---- Frame: thick outer rule, white gap, thin inner rule --------------
    _rect(c, 0, 0, 1760, 1320, WHITE)
    _rect(c, 28, 28, 1732, 1292, FRAME)
    _rect(c, 50, 50, 1710, 1270, WHITE)
    _rect(c, 58, 58, 1702, 1262, FRAME)
    _rect(c, 64, 64, 1696, 1256, WHITE)

    # ---- Band: gold stripe, pale blue, gold stripe ------------------------
    _rect(c, 152, 64, 336, 1256, GOLD)
    _rect(c, 164, 64, 324, 1256, BAND)

    # ---- Seal, over the band ----------------------------------------------
    c.drawImage(str(ASSETS / "seal.png"), _pt(116), PAGE_H - _pt(296 + 252), _pt(252), _pt(252), mask="auto")

    # ---- Heading: logo, then the exam title in blue capitals ---------------
    _svg(c, "logo.svg", LEFT, 222, 192)
    _text(c, LEFT + 192 + 30, 250, values["exam_name"].upper(), "Rubik-Medium", 38, BLUE)

    # ---- From "Presented to" down, lines stack: a name or exam that wraps
    # pushes everything below it down, as in the template. `shift` is how far.
    _text(c, LEFT, 345, "Presented to", "Rubik-Light", 36, TEXT)

    shift = 0
    name_lines = _lines(values["holder_name"].upper(), "Rubik-Medium", 54, 1150)
    for i, line in enumerate(name_lines):
        _text(c, LEFT - 6, 432 + i * 59, line, "Rubik-Medium", 54, INK)
    shift += (len(name_lines) - 1) * 59

    reason = f"for successfully completing {values['exam_name']} certification"
    reason_lines = _lines(reason, "Rubik-Light", 36, 760)
    for i, line in enumerate(reason_lines):
        _text(c, LEFT, 514 + shift + i * 50, line, "Rubik-Light", 36, TEXT)
    shift += (len(reason_lines) - 2) * 50   # the design has two lines here

    x = LEFT + _text(c, LEFT, 648 + shift, f"Issued {values['issued_on']}", "Rubik-Light", 36, TEXT)
    x += 14 + _text(c, x + 14, 648 + shift, "·", "Rubik-Light", 36, FRAME) + 14
    _text(c, x, 648 + shift, f"Valid until {values['valid_until']}", "Rubik-Light", 36, TEXT)

    _svg(c, "signature.svg", LEFT, 695 + shift, 384)
    _text(c, LEFT, 847 + shift, "Co-Founder and CEO", "Rubik-Regular", 27, INK)

    # ---- Certificate ID, fixed at the foot ---------------------------------
    x = 493 + _text(c, 493, 1197, "Certificate ID: ", "Rubik-Regular", 27, INK)
    _text(c, x, 1197, values["certificate_id"], "Rubik-Medium", 27, INK)

    c.showPage()
    c.save()
    return buffer.getvalue()


def certificate_pdf_attachment(booking):
    """(filename, bytes, mimetype) for the email attachment, or None without a certificate."""
    certificate = getattr(booking, "certificate", None)
    if certificate is None:
        return None
    return (
        f"TestMu-AI-certificate-{certificate.certificate_id}.pdf",
        render_certificate_pdf(certificate_values(certificate)),
        "application/pdf",
    )
