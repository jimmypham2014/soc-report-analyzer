"""
Tests for ai_analysis.py.

These NEVER call the real Claude API (no key needed, no cost). Instead,
fake_client() builds a real anthropic client whose network layer is replaced
by a function that returns whatever response we choose. That way the real
SDK code still runs - building the request, parsing and validating the
answer - but nothing leaves the machine.
"""

import json
import os

import anthropic
import httpx2
import pytest

import ai_analysis
from extract import extract_all
from pdf_text import load_pages_from_text

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_soc2_report.txt")

GOOD_ANSWER = {
    "exceptions": [
        {"control_id": "CC6.2", "page": 7, "description": "Late access removal.",
         "severity": "High", "reason": "Ex-staff kept access.",
         "management_response": "Automated HR integration."},
    ],
    "cuecs": [{"cuec": "Remove own users' access", "suggested_owner": "IAM team",
               "reason": "Owns joiner-mover-leaver."}],
    "subservice_organizations": [{"name": "AWS", "services": "Hosting",
                                  "method": "Carve-out"}],
    "overall_risk": {"rating": "High", "reason": "Qualified opinion."},
    "vendor_questions": [f"Question {i}?" for i in range(1, 11)],  # 10: too many
}


def fake_client(answer=GOOD_ANSWER, status=200, stop_reason="end_turn", sent=None):
    """An anthropic client that answers locally instead of over the internet.

    `sent` (a dict) receives the request body, so tests can inspect it.
    """
    def handle(request):
        if sent is not None:
            sent["body"] = json.loads(request.content)
        if status != 200:
            return httpx2.Response(status, json={
                "type": "error", "error": {"type": "error", "message": "fake error"}})
        return httpx2.Response(200, json={
            "id": "msg_test", "type": "message", "role": "assistant",
            "model": ai_analysis.MODEL,
            "content": [{"type": "text", "text": json.dumps(answer)}],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 3000, "output_tokens": 2000},
        })

    return anthropic.Anthropic(
        api_key="test-key-not-real",
        max_retries=0,  # fail fast in tests instead of retrying errors
        http_client=httpx2.Client(transport=httpx2.MockTransport(handle)),
    )


@pytest.fixture
def report():
    pages = load_pages_from_text(FIXTURE)
    return pages, extract_all(pages)


# --- choosing what to send ---------------------------------------------------

def test_pages_to_send_most_important_first(report):
    _, fields = report
    # opinion (3), scope (1), exceptions (7, 8), responses (9),
    # subservice (5, 2), CUECs (6). CSOCs are on 5, already included.
    assert ai_analysis.pages_to_send(fields) == [3, 1, 7, 8, 9, 5, 2, 6]


def test_page_4_management_assertion_is_not_sent(report):
    pages, fields = report
    text, included, left_out = ai_analysis.build_excerpts(pages, fields)
    assert 4 not in included
    assert "Management's Assertion" not in text


def test_excerpts_are_labelled_with_page_numbers(report):
    pages, fields = report
    text, _, _ = ai_analysis.build_excerpts(pages, fields)
    assert "--- PDF page 7 ---" in text
    assert "Exception noted" in text


def test_cap_drops_whole_pages_and_reports_them(report):
    pages, fields = report
    text, included, left_out = ai_analysis.build_excerpts(pages, fields, max_chars=3000)
    assert len(text) <= 3000
    assert included[0] == 3          # the opinion page always goes first
    assert left_out                  # something didn't fit...
    assert sorted(included + left_out) == sorted(ai_analysis.pages_to_send(fields))


# --- calling Claude (faked) --------------------------------------------------

def test_successful_analysis(report):
    pages, fields = report
    analysis, info = ai_analysis.run_analysis(pages, fields, client=fake_client())
    assert analysis.exceptions[0].severity == "High"
    assert analysis.cuecs[0].suggested_owner == "IAM team"
    assert analysis.overall_risk.rating == "High"
    assert len(analysis.vendor_questions) == 8          # capped from 10
    assert info["pages_sent"] == [3, 1, 7, 8, 9, 5, 2, 6]
    # 3000 in x $4/M + 2000 out x $20/M = $0.012 + $0.040
    assert info["estimated_cost_usd"] == pytest.approx(0.052)


def test_request_contents(report):
    pages, fields = report
    sent = {}
    ai_analysis.run_analysis(pages, fields, client=fake_client(sent=sent))
    body = sent["body"]
    assert body["model"] == "claude-opus-5-5"
    message = body["messages"][0]["content"]
    # Report text is wrapped in tags so Claude treats it as data.
    assert "<report_excerpts>" in message and "</report_excerpts>" in message
    assert "instructions" in body["system"]
    # Severity is restricted to exactly three values by the schema.
    schema = body["output_config"]["format"]["schema"]
    severity = schema["$defs"]["ExceptionAssessment"]["properties"]["severity"]
    assert severity["enum"] == ["High", "Medium", "Low"]


def test_answer_with_wrong_severity_is_rejected(report):
    pages, fields = report
    bad = json.loads(json.dumps(GOOD_ANSWER))
    bad["exceptions"][0]["severity"] = "Critical"
    with pytest.raises(ai_analysis.AnalysisError, match="expected format"):
        ai_analysis.run_analysis(pages, fields, client=fake_client(answer=bad))


def test_answer_missing_a_section_is_rejected(report):
    pages, fields = report
    bad = {k: v for k, v in GOOD_ANSWER.items() if k != "overall_risk"}
    with pytest.raises(ai_analysis.AnalysisError, match="expected format"):
        ai_analysis.run_analysis(pages, fields, client=fake_client(answer=bad))


@pytest.mark.parametrize("status, words", [
    (401, "API key was rejected"),
    (429, "Rate limit"),
    (500, "returned an error"),
])
def test_api_errors_become_plain_messages(report, status, words):
    pages, fields = report
    with pytest.raises(ai_analysis.AnalysisError, match=words):
        ai_analysis.run_analysis(pages, fields, client=fake_client(status=status))


@pytest.mark.parametrize("stop_reason, words", [
    ("refusal", "declined"),
    ("max_tokens", "cut off"),
])
def test_incomplete_answers_are_rejected(report, stop_reason, words):
    pages, fields = report
    with pytest.raises(ai_analysis.AnalysisError, match=words):
        ai_analysis.run_analysis(pages, fields,
                                 client=fake_client(stop_reason=stop_reason))


def test_api_key_check(monkeypatch):
    # monkeypatch changes an environment variable just for this test.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ai_analysis.api_key_is_set() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anything")
    assert ai_analysis.api_key_is_set() is True
