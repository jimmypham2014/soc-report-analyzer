"""
make_sample_pdf.py - build test PDFs from the fake .txt report.

This is a developer helper, not part of the analyzer. It lets us test the
real PDF-reading code without needing a real (confidential) vendor report.

It creates two files in tests/fixtures/:
    fake_soc2_report.pdf  - one PDF page per page of the .txt fixture
    fake_scanned.pdf      - pages with a drawn box but NO text, to imitate
                            a scanned document

Run it from the project folder:
    python tools/make_sample_pdf.py
"""

import os
import sys

from fpdf import FPDF

# Let this script import pdf_text.py from the project folder one level up.
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_DIR)

from pdf_text import load_pages_from_text  # noqa: E402  (import after path fix)

FIXTURES_DIR = os.path.join(PROJECT_DIR, "tests", "fixtures")


def build_text_pdf(pages, out_path):
    """Write each Page's text onto its own PDF page."""
    pdf = FPDF()
    # A small monospaced font keeps the fixture's column layout readable.
    pdf.set_font("Courier", size=8)
    for page in pages:
        pdf.add_page()
        # multi_cell wraps text inside the page width; w=0 means "full width".
        pdf.multi_cell(w=0, h=4, text=page.text)
    pdf.output(out_path)


def build_scanned_pdf(out_path, page_count=3):
    """Write pages that contain only a drawing, no text - like a scan."""
    pdf = FPDF()
    for _ in range(page_count):
        pdf.add_page()
        pdf.rect(x=20, y=20, w=170, h=250)  # a box standing in for a photo
    pdf.output(out_path)


if __name__ == "__main__":
    fixture = os.path.join(FIXTURES_DIR, "fake_soc2_report.txt")
    text_pdf = os.path.join(FIXTURES_DIR, "fake_soc2_report.pdf")
    scanned_pdf = os.path.join(FIXTURES_DIR, "fake_scanned.pdf")

    build_text_pdf(load_pages_from_text(fixture), text_pdf)
    build_scanned_pdf(scanned_pdf)
    print(f"Wrote {text_pdf}")
    print(f"Wrote {scanned_pdf}")
