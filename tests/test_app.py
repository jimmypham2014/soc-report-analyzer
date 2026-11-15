"""
Tests for app.py, using Streamlit's built-in AppTest.

AppTest runs the Streamlit script without a browser and lets us click things
and read what was drawn. It can't simulate the file-upload button, so these
tests use the "try the sample report" checkbox. (Uploads, including a scanned
PDF, were checked by hand in a real browser - see the README.)
"""

import os

from streamlit.testing.v1 import AppTest

APP = os.path.join(os.path.dirname(__file__), "..", "app.py")


def all_text(at):
    """Every piece of text the app drew, joined together, for easy searching."""
    parts = []
    for kind in ("markdown", "info", "warning", "error", "success", "header",
                 "subheader", "caption", "code"):
        parts += [element.value for element in getattr(at, kind)]
    return "\n".join(str(p) for p in parts)


def test_waits_for_a_file():
    at = AppTest.from_file(APP).run()
    assert not at.exception
    assert "Upload a PDF to begin." in all_text(at)
    assert len(at.metric) == 0  # no results drawn yet


def test_sample_report_shows_results():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.checkbox[0].check().run()
    assert not at.exception

    text = all_text(at)
    assert "Overall: RED" in text
    assert "verify in the report" in text

    tiles = {metric.label: metric.value for metric in at.metric}
    assert tiles["Report"] == "SOC 2 Type II"
    assert tiles["Opinion"] == "Qualified"
    assert tiles["Exceptions found"] == "2"
    assert tiles["Period end"] == "Jun 30, 2026"
    assert "Jan 1, 2026 – Jun 30, 2026" in text
    assert tiles["CUECs"] == "4"

    # One coloured box per flag: 1 red, 4 amber, 2 green.
    assert len(at.error) == 1
    assert len(at.success) == 2
    assert len([w for w in at.warning if "Period currency" in w.value
                or "Exceptions" in w.value or "Subservice" in w.value
                or "CUECs" in w.value]) == 4


def test_exception_is_paired_with_its_management_response():
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.checkbox[0].check().run()
    text = all_text(at)
    assert "Control CC6.2" in text
    assert "automated integration between the HR system" in text
