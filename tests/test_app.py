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


# --- Stage 5: the optional Claude analysis section ---------------------------

def test_claude_section_without_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.checkbox[0].check().run()
    assert not at.exception
    text = all_text(at)
    assert "set the **ANTHROPIC_API_KEY** environment variable" in text
    assert "Sends" in text and "PDF pages 3, 1, 7, 8, 9, 5, 2, 6" in text
    assert len(at.button) == 0  # no button without a key


def test_claude_button_runs_once_and_result_survives_reruns(monkeypatch):
    import ai_analysis
    from test_ai_analysis import GOOD_ANSWER

    calls = []

    def stand_in(pages, fields):
        # Pretend to be Claude: return a validated answer, count the calls.
        calls.append(1)
        analysis = ai_analysis.SocAnalysis.model_validate(GOOD_ANSWER)
        info = {"model": "claude-opus-5-5", "input_tokens": 3000,
                "output_tokens": 2000, "estimated_cost_usd": 0.052,
                "pages_sent": [], "pages_left_out": [], "characters_sent": 0}
        return analysis, info

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(ai_analysis, "run_analysis", stand_in)

    at = AppTest.from_file(APP, default_timeout=30).run()
    at.checkbox[0].check().run()
    assert calls == []                      # nothing sent before the click

    at.button[0].click().run()
    assert not at.exception
    assert calls == [1]
    text = all_text(at)
    assert "Overall risk: High" in text
    assert "AI-generated - verify in the report." in text
    assert len(at.dataframe) == 3           # exceptions, CUECs, subservice orgs

    # Interacting again re-runs the script, but must NOT call Claude again.
    at.checkbox[0].uncheck().run()
    at.checkbox[0].check().run()
    assert calls == [1]
    assert "Overall risk: High" in all_text(at)


# --- Stage 6: checklist and memo ---------------------------------------------

def test_checklist_and_memo(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=30).run()
    at.checkbox[0].check().run()
    assert not at.exception

    # Nine status dropdowns, all starting at "Not reviewed".
    assert len(at.selectbox) == 9
    assert all(box.value == "Not reviewed" for box in at.selectbox)
    assert "Tool says: Needed: the period ended" in all_text(at)
    assert "9 of 9 checklist items not yet reviewed" in all_text(at)

    # Answer one item; the memo preview must reflect it.
    at.selectbox[2].set_value("Not satisfactory").run()
    at.text_input[2].input("Qualified on CC6.2").run()
    at.text_input(key="reviewer").input("J. Pham").run()
    text = all_text(at)
    assert "8 of 9 checklist items not yet reviewed" in text
    assert "| 3 | Auditor's opinion is acceptable | Not satisfactory | Qualified on CC6.2 |" in text
    assert "**Reviewer:** J. Pham" in text

    # The answer survives an unrelated re-run.
    at.checkbox[0].uncheck().run()
    at.checkbox[0].check().run()
    assert at.selectbox[2].value == "Not satisfactory"
