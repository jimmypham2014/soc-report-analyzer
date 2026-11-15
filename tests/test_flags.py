"""
Tests for flags.py.

Most tests start from clean_fields() - a made-up report where everything is
fine, so every flag is green - and change ONE thing. If that one change
produces the expected flag, we know exactly which rule worked.
"""

import os
from datetime import date

import pytest

import flags
from extract import Finding, extract_all
from pdf_text import load_pages_from_text

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_soc2_report.txt")


def clean_fields(**changes):
    """Fields for a perfect report, with any `changes` applied on top."""
    fields = {
        "opinion": Finding("Unmodified", 3),
        "report_kind": Finding("Type II", 1),
        "review_period": Finding({"start": date(2025, 7, 1), "end": date(2026, 6, 30)}, 1),
        "months_covered": 12,
        "days_since_period_end": 30,
        "exceptions": [],
        "subservice_method": Finding(None),
        "subservice_organizations": [],
        "cuecs": [],
    }
    fields.update(changes)
    return fields


def flag_for(topic, fields):
    """Run all rules and return the one flag about `topic`."""
    matching = [f for f in flags.build_flags(fields) if f.topic == topic]
    assert len(matching) == 1, f"expected exactly one {topic} flag"
    return matching[0]


def test_clean_report_is_all_green():
    result = flags.build_flags(clean_fields())
    assert {f.level for f in result} == {"green"}
    assert flags.overall_level(result) == "green"


# --- opinion -----------------------------------------------------------------

@pytest.mark.parametrize("opinion", ["Qualified", "Adverse", "Disclaimer"])
def test_modified_opinion_is_red(opinion):
    flag = flag_for("Opinion", clean_fields(opinion=Finding(opinion, 3)))
    assert flag.level == "red"
    assert opinion in flag.reason
    assert flag.page == 3


def test_missing_opinion_is_amber_not_green():
    assert flag_for("Opinion", clean_fields(opinion=Finding(None))).level == "amber"


# --- Type I / Type II --------------------------------------------------------

def test_type1_is_amber_and_skips_period_length():
    fields = clean_fields(report_kind=Finding("Type I", 1), months_covered=None)
    assert flag_for("Report type", fields).level == "amber"
    # A Type I has no period length, so that rule must not fire at all.
    assert not [f for f in flags.build_flags(fields) if f.topic == "Period length"]


def test_unknown_kind_is_amber():
    assert flag_for("Report type", clean_fields(report_kind=Finding(None))).level == "amber"


# --- period length (boundary: exactly 6 months is fine) ----------------------

@pytest.mark.parametrize("months, expected", [(5, "amber"), (6, "green"), (12, "green")])
def test_period_length(months, expected):
    assert flag_for("Period length", clean_fields(months_covered=months)).level == expected


def test_unknown_period_length_is_amber():
    assert flag_for("Period length", clean_fields(months_covered=None)).level == "amber"


# --- period age (boundaries: 90 and 365 days are still the lower level) ------

@pytest.mark.parametrize("days, expected, words", [
    (30, "green", "30 days"),
    (90, "green", "90 days"),
    (91, "amber", "bridge letter"),
    (365, "amber", "bridge letter"),
    (366, "red", "stale"),
])
def test_period_age(days, expected, words):
    flag = flag_for("Period currency", clean_fields(days_since_period_end=days))
    assert flag.level == expected
    assert words in flag.reason


def test_unknown_period_age_is_amber():
    flag = flag_for("Period currency", clean_fields(days_since_period_end=None))
    assert flag.level == "amber"


# --- exceptions --------------------------------------------------------------

def test_exceptions_are_amber_with_count_and_pages():
    found = [Finding("CC6.2", 7), Finding("CC7.1", 7), Finding("CC8.1", 8)]
    flag = flag_for("Exceptions", clean_fields(exceptions=found))
    assert flag.level == "amber"
    assert "3 exception(s)" in flag.reason
    assert "page 7, 8" in flag.reason  # each page listed once
    assert flag.page == 7


def test_no_exceptions_is_green_but_says_verify():
    flag = flag_for("Exceptions", clean_fields())
    assert flag.level == "green"
    assert "confirm" in flag.reason


# --- subservice organizations ------------------------------------------------

def test_carve_out_is_amber_and_names_the_org():
    flag = flag_for("Subservice orgs", clean_fields(
        subservice_method=Finding("Carve-out", 5),
        subservice_organizations=[Finding("Amazon Web Services, Inc.", 2)],
    ))
    assert flag.level == "amber"
    assert "Amazon Web Services, Inc." in flag.reason
    assert "get their SOC reports" in flag.reason


def test_inclusive_is_green():
    flag = flag_for("Subservice orgs", clean_fields(
        subservice_method=Finding("Inclusive", 5),
        subservice_organizations=[Finding("Equinix", 5)],
    ))
    assert flag.level == "green"


def test_orgs_without_a_method_is_amber():
    flag = flag_for("Subservice orgs", clean_fields(
        subservice_organizations=[Finding("Equinix", 5)],
    ))
    assert flag.level == "amber"
    assert "unclear" in flag.reason


# --- CUECs -------------------------------------------------------------------

def test_cuecs_are_amber():
    flag = flag_for("CUECs", clean_fields(cuecs=[Finding("CUEC-1 ...", 6)] * 4))
    assert flag.level == "amber"
    assert "4 complementary" in flag.reason
    assert "owner" in flag.reason


# --- ordering and overall ----------------------------------------------------

def test_flags_sorted_worst_first():
    fields = clean_fields(opinion=Finding("Qualified", 3), days_since_period_end=120)
    levels = [f.level for f in flags.build_flags(fields)]
    assert levels == sorted(levels, key=flags.SEVERITY_ORDER.get)
    assert levels[0] == "red"


def test_overall_level():
    red = flags.Flag("red", "x", "y")
    amber = flags.Flag("amber", "x", "y")
    green = flags.Flag("green", "x", "y")
    assert flags.overall_level([green, amber]) == "amber"
    assert flags.overall_level([green, red, amber]) == "red"
    assert flags.overall_level([]) == "amber"  # nothing to judge: not green


# --- end to end on the fake report -------------------------------------------

def test_fake_report_flags():
    fields = extract_all(load_pages_from_text(FIXTURE), today=date(2026, 11, 15))
    result = {f.topic: f.level for f in flags.build_flags(fields)}
    assert result == {
        "Opinion": "red",            # qualified
        "Report type": "green",      # Type II
        "Period length": "green",    # exactly 6 months
        "Period currency": "amber",  # 138 days -> bridge letter
        "Exceptions": "amber",       # 2 exceptions
        "Subservice orgs": "amber",  # AWS carved out
        "CUECs": "amber",            # 4 CUECs
    }
