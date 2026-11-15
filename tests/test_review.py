"""Tests for review.py: the checklist hints and the Markdown memo."""

import os
from datetime import date

import pytest

import review
from ai_analysis import SocAnalysis
from extract import extract_all
from flags import build_flags
from pdf_text import Page, load_pages_from_text
from test_ai_analysis import GOOD_ANSWER

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_soc2_report.txt")
TODAY = date(2026, 11, 15)


@pytest.fixture
def report():
    fields = extract_all(load_pages_from_text(FIXTURE), today=TODAY)
    return fields, build_flags(fields)


def memo_for(report, answers=None, **options):
    fields, flags = report
    return review.build_memo(fields, flags, answers or {}, "fake.pdf",
                             today=TODAY, **options)


# --- checklist ---------------------------------------------------------------

def test_checklist_has_nine_items():
    assert len(review.CHECKLIST) == 9
    keys = [key for key, _ in review.CHECKLIST]
    assert len(set(keys)) == 9  # no duplicate keys


def test_every_item_gets_a_hint(report):
    hints = review.checklist_hints(*report)
    assert set(hints) == {key for key, _ in review.CHECKLIST}
    assert all(hints.values())  # none empty


def test_hints_use_the_findings(report):
    hints = review.checklist_hints(*report)
    assert "bridge letter" in hints["period"]
    assert "Needed" in hints["bridge"] and "138 days" in hints["bridge"]
    assert "Smith & Patel LLP" in hints["auditor"]
    assert "Inc.;" in hints["scope"] and ".." not in hints["scope"]
    assert "Security, Availability, Confidentiality" in hints["criteria"]


def test_bridge_hint_when_period_is_recent():
    pages = [Page(1, "for the period January 1, 2026 to October 31, 2026")]
    fields = extract_all(pages, today=TODAY)
    hints = review.checklist_hints(fields, build_flags(fields))
    assert hints["bridge"].startswith("Probably not needed")


# --- memo --------------------------------------------------------------------

def test_memo_has_all_sections(report):
    memo = memo_for(report)
    for heading in ["# SOC Report Review: Acme Cloud Services, Inc.",
                    "## Report summary", "## Automated flags (overall: RED)",
                    "## Reviewer checklist", "## Basis for opinion (p. 3)",
                    "## Exceptions", "### CC6.2 (p. 7)", "### CC8.1 (p. 8)",
                    "## Subservice organizations",
                    "## Complementary User Entity Controls (CUECs)",
                    "## Complementary Subservice Organization Controls (CSOCs)"]:
        assert heading in memo


def test_memo_summary_values(report):
    memo = memo_for(report)
    assert "| Report | SOC 2 Type II |" in memo
    assert "| Review period | Jan 1, 2026 to Jun 30, 2026 |" in memo
    assert "| Days since period end | 138 |" in memo
    assert "**Review date:** Nov 15, 2026" in memo


def test_unanswered_checklist_is_called_out(report):
    memo = memo_for(report)
    assert "**9 of 9 items not yet reviewed.**" in memo
    assert "| 1 | Report scope matches the services we use | Not reviewed |  |" in memo


def test_answers_and_notes_appear(report):
    answers = {"opinion": {"status": "Not satisfactory",
                           "notes": "Qualified on CC6.2 | raised with vendor\nsee ticket"}}
    memo = memo_for(report, answers=answers, reviewer="J. Pham")
    assert "**Reviewer:** J. Pham" in memo
    assert "**8 of 9 items not yet reviewed.**" in memo
    # The | is escaped and the line break flattened, so the table stays intact.
    assert ("| 3 | Auditor's opinion is acceptable | Not satisfactory "
            "| Qualified on CC6.2 \\| raised with vendor see ticket |") in memo


def test_exception_paired_with_management_response(report):
    memo = memo_for(report)
    cc62 = memo.split("### CC6.2")[1].split("###")[0]
    assert "Management's response (p. 9)" in cc62
    assert "automated integration" in cc62


def test_claude_section_only_when_analysis_given(report):
    assert "Claude analysis" not in memo_for(report)
    memo = memo_for(report, analysis=SocAnalysis.model_validate(GOOD_ANSWER))
    assert "## Claude analysis (AI-generated - verify in the report)" in memo
    assert "**Overall risk: High.**" in memo
    assert "| CC6.2 | 7 | High |" in memo
    assert "| Remove own users' access | IAM team |" in memo


def test_memo_for_a_report_with_nothing_found():
    fields = extract_all([Page(1, "Nothing recognizable here at all, just words.")])
    memo = review.build_memo(fields, build_flags(fields), {}, "odd.pdf", today=TODAY)
    assert "# SOC Report Review: Unknown service organization" in memo
    assert "No exceptions found by text search." in memo
    assert memo.count("None found.") == 3  # subservice, CUECs, CSOCs


def test_md_cell():
    assert review.md_cell("a | b\nc") == "a \\| b c"
    assert review.md_cell(None) == ""


def test_memo_file_name(report):
    fields, _ = report
    assert (review.memo_file_name(fields, today=TODAY)
            == "acme-cloud-services-inc-soc-review-2026-11-15.md")
