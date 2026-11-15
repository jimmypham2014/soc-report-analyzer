"""
pdf_text.py - Stage 1: get the text out of a SOC report, one page at a time.

Why page by page?
    A reviewer needs to say "the exception is on page 7", so every piece of
    text we pull out has to remember which page it came from. Everything
    else in this project (extraction, flags, the UI) works on the list of
    pages this module returns.

There are two ways to load a report:
    1. extract_pages_from_pdf()  - a real PDF, read with pdfplumber.
    2. load_pages_from_text()    - a plain .txt test fixture, where pages are
                                   separated by a line "=== PAGE BREAK ===".
Both return the same thing: a list of Page objects. That way the rest of the
code doesn't care whether the report came from a PDF or a test file.
"""

from dataclasses import dataclass

import pdfplumber


# The line that separates pages in our .txt test fixtures.
PAGE_BREAK_MARKER = "=== PAGE BREAK ==="

# If a PDF averages fewer than this many characters of text per page, we
# assume it's a scanned image (a photo of paper) rather than real text.
# A normal page of a SOC report has 2,000+ characters, so 50 is very safe.
MIN_CHARS_PER_PAGE = 50


@dataclass
class Page:
    """One page of the report.

    A dataclass is just a tidy way to bundle two values together so we can
    write page.number and page.text instead of page[0] and page[1].
    """

    number: int  # 1-based, matching the page numbers a human would see
    text: str


class PdfReadError(Exception):
    """Raised when a PDF can't be opened (corrupt, encrypted, not a PDF)."""


def extract_pages_from_pdf(source):
    """Read a PDF and return a list of Page objects, one per page.

    `source` can be a file path (a string) or an open file object. Streamlit's
    file uploader gives us a file object, so supporting both now saves work
    in stage 4.
    """
    pages = []
    try:
        with pdfplumber.open(source) as pdf:
            # enumerate(..., start=1) counts 1, 2, 3... instead of 0, 1, 2...
            for number, pdf_page in enumerate(pdf.pages, start=1):
                # extract_text() returns None for a page with no text layer,
                # so "or ''" turns that into an empty string.
                text = pdf_page.extract_text() or ""
                pages.append(Page(number=number, text=text))
    except Exception as error:
        # pdfplumber raises several different error types for bad files.
        # We catch them all and raise ONE clear error the UI can show.
        raise PdfReadError(
            f"Could not read this PDF. It may be corrupt or password-protected. "
            f"(Details: {error})"
        ) from error
    return pages


def load_pages_from_text(path):
    """Load a .txt test fixture and split it into pages on the marker line."""
    with open(path, encoding="utf-8") as f:
        whole_file = f.read()

    chunks = whole_file.split(PAGE_BREAK_MARKER)
    return [
        Page(number=number, text=chunk.strip())
        for number, chunk in enumerate(chunks, start=1)
    ]


def looks_scanned(pages):
    """Return True if the document seems to be scanned images with no text.

    We can't analyze a scanned PDF with text search, so the UI will catch
    this and tell the user to run OCR first, instead of showing a page of
    empty results (which could be misread as "no exceptions found").
    """
    if not pages:
        return True
    total_chars = sum(len(page.text.strip()) for page in pages)
    average = total_chars / len(pages)
    return average < MIN_CHARS_PER_PAGE


# ----------------------------------------------------------------------------
# Run this file directly to try it on a report:
#     python pdf_text.py path/to/report.pdf
# It prints how many pages it found and the first few lines of each page.
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python pdf_text.py <report.pdf or fixture.txt>")
        sys.exit(1)

    path = sys.argv[1]
    if path.lower().endswith(".txt"):
        report_pages = load_pages_from_text(path)
    else:
        report_pages = extract_pages_from_pdf(path)

    print(f"Found {len(report_pages)} pages.")
    if looks_scanned(report_pages):
        print("WARNING: this looks like a scanned PDF with no text layer. "
              "Run it through OCR first.")

    for page in report_pages:
        first_lines = page.text.splitlines()[:2]
        print(f"\n--- Page {page.number} ({len(page.text)} characters) ---")
        for line in first_lines:
            print(f"    {line}")
