"""
Tests for extract.py.

Two kinds of test:
  1. Against the fake SOC 2 report (tests/fixtures/fake_soc2_report.txt),
     where we know the right answer for every field.
  2. Tiny made-up snippets for edge cases the fake report doesn't cover,
     e.g. a SOC 1, a Type I, a disclaimer of opinion.
"""

import os
from datetime import date

import pytest

import extract
from pdf_text import Page, load_pages_from_text

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "fake_soc2_report.txt")


@pytest.fixture
def report():
    """The fake report's pages. A pytest "fixture" is set-up code: any test
    that has a parameter called `report` receives this return value."""
    return load_pages_from_text(FIXTURE)


def pages_from(*texts):
    """Build a small fake report: each string becomes one page."""
    return [Page(number=i, text=t) for i, t in enumerate(texts, start=1)]


# --- report type and kind ----------------------------------------------------

def test_report_type_soc2(report):
    found = extract.report_type(report)
    assert found.value == "SOC 2"
    assert found.page == 1


def test_report_type_soc1():
    pages = pages_from("SOC 1 Type 2 Report on controls relevant to user "
                       "entities' internal control over financial reporting")
    assert extract.report_type(pages).value == "SOC 1"


def test_report_type_inferred_when_no_label():
    pages = pages_from("based on the applicable trust services criteria")
    assert extract.report_type(pages).value == "SOC 2"


def test_report_type_unknown():
    assert extract.report_type(pages_from("Nothing useful here.")).value is None


def test_report_kind_type2(report):
    assert extract.report_kind(report).value == "Type II"


@pytest.mark.parametrize("wording, expected", [
    ("SOC 2 Type II Report", "Type II"),
    ("SOC 2 Type 2 Report", "Type II"),
    ("SOC 1 Type I Report", "Type I"),
    ("SOC 1 Type 1 Report", "Type I"),
])
def test_report_kind_spellings(wording, expected):
    # parametrize runs this one test four times, once per row above.
    assert extract.report_kind(pages_from(wording)).value == expected


# --- service organization and audit firm ------------------------------------

def test_service_organization(report):
    assert extract.service_organization(report).value == "Acme Cloud Services, Inc."


def test_service_organization_curly_apostrophe():
    pages = pages_from("We have examined Globex Corporation’s accompanying description")
    assert extract.service_organization(pages).value == "Globex Corporation"


def test_audit_firm(report):
    found = extract.audit_firm(report, "Acme Cloud Services, Inc.")
    assert found.value == "Smith & Patel LLP"
    assert found.page == 3  # the signature on the auditor's report


def test_audit_firm_skips_service_org_that_is_an_llc():
    pages = pages_from("Independent Service Auditor's Report\n"
                       "Initech LLC\n"
                       "In our opinion...\n"
                       "Jones & Wu CPAs\n"
                       "Austin, Texas")
    assert extract.audit_firm(pages, "Initech LLC").value == "Jones & Wu CPAs"


# --- review period -----------------------------------------------------------

def test_review_period(report):
    found = extract.review_period(report)
    assert found.value == {"start": date(2026, 1, 1), "end": date(2026, 6, 30)}


def test_review_period_day_month_year_and_through():
    pages = pages_from("for the period 1 April 2025 through 31 March 2026")
    found = extract.review_period(pages)
    assert found.value == {"start": date(2025, 4, 1), "end": date(2026, 3, 31)}


def test_review_period_type1_as_of():
    pages = pages_from("suitability of the design of controls as of September 30, 2026")
    found = extract.review_period(pages)
    assert found.value == {"start": None, "end": date(2026, 9, 30)}


def test_months_covered():
    six = {"start": date(2026, 1, 1), "end": date(2026, 6, 30)}
    twelve = {"start": date(2025, 10, 1), "end": date(2026, 9, 30)}
    three = {"start": date(2026, 1, 1), "end": date(2026, 3, 31)}
    assert extract.months_covered(six) == 6
    assert extract.months_covered(twelve) == 12
    assert extract.months_covered(three) == 3
    assert extract.months_covered({"start": None, "end": date(2026, 9, 30)}) is None


def test_days_since_period_end():
    period = {"start": date(2026, 1, 1), "end": date(2026, 6, 30)}
    assert extract.days_since_period_end(period, today=date(2026, 11, 15)) == 138
    assert extract.days_since_period_end(None) is None


# --- opinion -----------------------------------------------------------------

def test_opinion_qualified(report):
    found = extract.opinion(report)
    assert found.value == "Qualified"
    assert found.page == 3


@pytest.mark.parametrize("wording, expected", [
    ("Opinion\nIn our opinion, in all material respects, the description...", "Unmodified"),
    ("Basis for Adverse Opinion ... Adverse Opinion\nIn our opinion, because of...", "Adverse"),
    ("Basis for Disclaimer of Opinion ... Disclaimer of Opinion\nWe do not...", "Disclaimer"),
    # "unqualified" must not be mistaken for "qualified":
    ("We issued an unqualified opinion. In our opinion, in all material respects", "Unmodified"),
])
def test_opinion_types(wording, expected):
    assert extract.opinion(pages_from(wording)).value == expected


def test_basis_for_opinion(report):
    found = extract.basis_for_opinion(report)
    assert found.page == 3
    assert found.value.startswith("Acme states in its description")
    assert found.value.endswith("based on criterion CC6.2.")
    # It must stop before the opinion paragraph itself.
    assert "In our opinion" not in found.value


def test_basis_for_opinion_ignores_paragraph_references():
    # Page 1 only REFERS to the heading; page 2 has the real heading.
    pages = pages_from(
        "except for the matter described in the Basis for Qualified Opinion paragraph",
        "Basis for Qualified Opinion\nBackups were not tested.\nQualified Opinion\nIn our opinion",
    )
    found = extract.basis_for_opinion(pages)
    assert found.page == 2
    assert found.value == "Backups were not tested."


def test_extract_all_skips_basis_when_opinion_is_clean():
    pages = pages_from("In our opinion, in all material respects, the controls...")
    assert extract.extract_all(pages)["basis_for_opinion"].value is None


# --- trust services criteria -------------------------------------------------

def test_trust_services_criteria(report):
    found = extract.trust_services_criteria(report)
    # The fixture also cites the standard's full title, which lists all five
    # categories. Processing Integrity and Privacy must NOT appear.
    assert found.value == ["Security", "Availability", "Confidentiality"]


def test_trust_services_criteria_security_only():
    pages = pages_from(
        "based on the trust services criteria relevant to security (applicable "
        "trust services criteria) set forth in TSP section 100, 2017 Trust "
        "Services Criteria for Security, Availability, Processing Integrity, "
        "Confidentiality, and Privacy")
    assert extract.trust_services_criteria(pages).value == ["Security"]


# --- exceptions --------------------------------------------------------------

def test_exceptions_found_with_pages(report):
    found = extract.exceptions(report)
    assert [(f.value, f.page) for f in found] == [("CC6.2", 7), ("CC8.1", 8)]
    assert "Exception noted" in found[0].excerpt
    assert "Deviation noted" in found[1].excerpt


def test_no_exceptions_noted_does_not_count():
    # THE most important test: the fake report contains "No exceptions
    # noted." five times and none of them may be counted.
    pages = pages_from(
        "CC1.1 Control text  Inspected policy  No exceptions noted.\n"
        "CC1.2 Control text  Inspected log     No exception noted.\n"
        "CC1.3 Control text  Inspected sample  No deviations noted.\n"
        "CC1.4 Control text  Observed process  No relevant exceptions noted.\n"
        "CC1.5 Control text  Inspected tickets no exceptions were noted\n"
    )
    assert extract.exceptions(pages) == []


def test_no_exceptions_noted_split_across_lines():
    # PDF tables often wrap "No exceptions" and "noted." onto two lines.
    pages = pages_from("CC2.1 Control text  Inspected policy  No exceptions\nnoted.")
    assert extract.exceptions(pages) == []


def test_reference_to_exceptions_does_not_count():
    pages = pages_from("Management's responses to the exceptions noted in Section 4")
    assert extract.exceptions(pages) == []


def test_exception_wording_variants():
    pages = pages_from(
        "1.1 Control  Test  Exceptions noted: 2 of 25 samples lacked approval.\n"
        "1.2 Control  Test  The following deviations were identified: ...\n"
    )
    found = extract.exceptions(pages)
    assert [f.value for f in found] == ["1.1", "1.2"]


# --- management responses ----------------------------------------------------

def test_management_responses(report):
    found = extract.management_responses(report)
    assert [(f.value, f.page) for f in found] == [("CC6.2", 9), ("CC8.1", 9)]
    assert "automated integration" in found[0].excerpt
    # Each response stops where the next one starts.
    assert "emergency fixes" not in found[0].excerpt


# --- subservice organizations ------------------------------------------------

def test_subservice_method_carve_out(report):
    found = extract.subservice_method(report)
    assert found.value == "Carve-out"
    assert found.page == 5


def test_subservice_method_inclusive():
    pages = pages_from("The description includes the subservice organization "
                       "using the inclusive method.")
    assert extract.subservice_method(pages).value == "Inclusive"


def test_subservice_method_none():
    assert extract.subservice_method(pages_from("No subservice orgs.")).value is None


def test_subservice_organizations(report):
    found = extract.subservice_organizations(report, "Acme Cloud Services, Inc.")
    # Found once by wording and once as a known provider; must appear once.
    assert [f.value for f in found] == ["Amazon Web Services, Inc."]


def test_subservice_organizations_known_provider():
    pages = pages_from("Data center services are provided by subservice "
                       "organizations. Equinix hosts the primary data center.")
    assert [f.value for f in extract.subservice_organizations(pages)] == ["Equinix"]


# --- CUECs and CSOCs ---------------------------------------------------------

def test_cuecs(report):
    found = extract.cuecs(report)
    assert len(found) == 4
    assert all(f.page == 6 for f in found)
    assert found[0].value.startswith("CUEC-1 User entities are responsible")
    # The wrapped second line must be joined onto the item.
    assert found[0].value.endswith("access to the Acme customer portal.")


def test_csocs(report):
    found = extract.csocs(report)
    assert len(found) == 3
    assert found[2].value.startswith("CSOC-3 AWS is responsible")


def test_cuecs_numbered_list_spanning_pages():
    pages = pages_from(
        "Complementary User Entity Controls\n"
        "1. Users review access quarterly.\n"
        "2. Users protect their passwords.",
        "Section 3 (continued)\n"
        "3. Users report incidents.\n"
        "Section 4: Tests of Controls",
    )
    found = extract.cuecs(pages)
    assert [(f.page, f.value) for f in found] == [
        (1, "1. Users review access quarterly."),
        (1, "2. Users protect their passwords."),
        (2, "3. Users report incidents."),
    ]


def test_no_cuec_section():
    assert extract.cuecs(pages_from("Nothing here.")) == []


# --- everything together -----------------------------------------------------

def test_extract_all_on_pdf(tmp_path):
    """End to end: build a real PDF and check the main fields come through."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "tools"))
    from make_sample_pdf import build_text_pdf
    from pdf_text import extract_pages_from_pdf

    pdf_path = tmp_path / "report.pdf"
    build_text_pdf(load_pages_from_text(FIXTURE), str(pdf_path))
    fields = extract.extract_all(extract_pages_from_pdf(str(pdf_path)),
                                 today=date(2026, 11, 15))

    assert fields["report_type"].value == "SOC 2"
    assert fields["opinion"].value == "Qualified"
    assert fields["days_since_period_end"] == 138
    assert len(fields["exceptions"]) == 2
    assert len(fields["cuecs"]) == 4
