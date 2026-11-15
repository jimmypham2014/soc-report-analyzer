"""
Tests for pdf_text.py. Run them with:   pytest

Each test_ function checks one behaviour. If an `assert` line is false, pytest
reports that test as failed and shows you the values involved.
"""

import os
import sys

import pytest

from pdf_text import (
    Page,
    PdfReadError,
    extract_pages_from_pdf,
    load_pages_from_text,
    looks_scanned,
)

# Reuse the PDF builders from the helper script.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
from make_sample_pdf import build_scanned_pdf, build_text_pdf  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_soc2_report.txt")


def test_fixture_splits_into_numbered_pages():
    pages = load_pages_from_text(FIXTURE)
    assert len(pages) == 9
    # Page numbers start at 1 and go up by one.
    assert [p.number for p in pages] == list(range(1, 10))
    # Spot-check that content landed on the right page.
    assert "SOC 2 Type 2 Report" in pages[0].text
    assert "Basis for Qualified Opinion" in pages[2].text
    assert "Management's Response to Exceptions" in pages[8].text


def test_pdf_extraction_keeps_page_numbers(tmp_path):
    # tmp_path is a throwaway folder pytest creates for each test.
    pdf_path = tmp_path / "report.pdf"
    build_text_pdf(load_pages_from_text(FIXTURE), str(pdf_path))

    pages = extract_pages_from_pdf(str(pdf_path))

    assert len(pages) == 9
    assert pages[0].number == 1
    assert "Acme Cloud Services" in pages[0].text
    # The CC6.2 exception is on page 7 of the fixture; it must still be there.
    assert "CC6.2" in pages[6].text
    assert "Exception noted" in pages[6].text


def test_pdf_extraction_accepts_a_file_object(tmp_path):
    # Streamlit hands us an open file, not a path - make sure that works too.
    pdf_path = tmp_path / "report.pdf"
    build_text_pdf(load_pages_from_text(FIXTURE), str(pdf_path))
    with open(pdf_path, "rb") as f:
        pages = extract_pages_from_pdf(f)
    assert len(pages) == 9


def test_real_text_is_not_flagged_as_scanned():
    assert looks_scanned(load_pages_from_text(FIXTURE)) is False


def test_scanned_pdf_is_detected(tmp_path):
    pdf_path = tmp_path / "scanned.pdf"
    build_scanned_pdf(str(pdf_path))
    pages = extract_pages_from_pdf(str(pdf_path))
    assert len(pages) == 3
    assert looks_scanned(pages) is True


def test_empty_document_counts_as_scanned():
    assert looks_scanned([]) is True
    assert looks_scanned([Page(number=1, text="   ")]) is True


def test_bad_file_raises_a_clear_error(tmp_path):
    not_a_pdf = tmp_path / "fake.pdf"
    not_a_pdf.write_text("this is not a PDF")
    with pytest.raises(PdfReadError):
        extract_pages_from_pdf(str(not_a_pdf))
