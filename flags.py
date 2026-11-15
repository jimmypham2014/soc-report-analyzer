"""
flags.py - Stage 3: turn the extracted fields into review flags.

Each rule is a small function that looks at the fields from
extract.extract_all() and returns one Flag:

    red    - a serious problem (e.g. the opinion is not clean)
    amber  - needs follow-up (e.g. request a bridge letter)
    green  - looks fine (but still verify in the report)

Design rule: if the tool could NOT find something, the flag is AMBER, never
green. "Couldn't find the opinion" must not look the same as "the opinion
is clean".

The thresholds live at the top of the file so they're easy to change if
your organization's vendor-risk policy uses different numbers.
"""

from dataclasses import dataclass

# --- Policy thresholds -------------------------------------------------------
MIN_PERIOD_MONTHS = 6       # Type II periods shorter than this -> amber
BRIDGE_LETTER_DAYS = 90     # more than this many days since period end -> amber
STALE_DAYS = 365            # more than this -> red

RED, AMBER, GREEN = "red", "amber", "green"
# Used to sort flags so the worst come first.
SEVERITY_ORDER = {RED: 0, AMBER: 1, GREEN: 2}


@dataclass
class Flag:
    level: str          # "red", "amber" or "green"
    topic: str          # short label, e.g. "Opinion"
    reason: str         # one line explaining why
    page: int = None    # where to look in the report, if known


# ----------------------------------------------------------------------------
# One function per rule. Each takes the `fields` dictionary from
# extract.extract_all() and returns a Flag.
# ----------------------------------------------------------------------------

def flag_opinion(fields):
    found = fields["opinion"]
    if found.value is None:
        return Flag(AMBER, "Opinion",
                    "Could not find the auditor's opinion - check the report manually.")
    if found.value == "Unmodified":
        return Flag(GREEN, "Opinion", "Unmodified (clean) opinion.", found.page)
    return Flag(RED, "Opinion",
                f"{found.value} opinion - read the 'Basis for' paragraph and assess the impact.",
                found.page)


def flag_report_kind(fields):
    found = fields["report_kind"]
    if found.value is None:
        return Flag(AMBER, "Report type",
                    "Could not tell if this is Type I or Type II - check the report.")
    if found.value == "Type I":
        return Flag(AMBER, "Report type",
                    "Type I covers design only - operating effectiveness was not tested.",
                    found.page)
    return Flag(GREEN, "Report type",
                "Type II - operating effectiveness was tested.", found.page)


def flag_period_length(fields):
    """Only applies to Type II reports. A Type I covers a single date."""
    if fields["report_kind"].value == "Type I":
        return None  # no rule to apply; build_flags() skips None
    months = fields["months_covered"]
    page = fields["review_period"].page
    if months is None:
        return Flag(AMBER, "Period length",
                    "Could not find the review period - check the report.")
    if months < MIN_PERIOD_MONTHS:
        return Flag(AMBER, "Period length",
                    f"Period covers only {months} months (under {MIN_PERIOD_MONTHS}) "
                    "- limited evidence of operating effectiveness.", page)
    return Flag(GREEN, "Period length", f"Period covers {months} months.", page)


def flag_period_age(fields):
    days = fields["days_since_period_end"]
    page = fields["review_period"].page
    if days is None:
        return Flag(AMBER, "Period currency",
                    "Could not find the period end date - check the report.")
    if days > STALE_DAYS:
        return Flag(RED, "Period currency",
                    f"Period ended {days} days ago - report is stale; "
                    "request a current report.", page)
    if days > BRIDGE_LETTER_DAYS:
        return Flag(AMBER, "Period currency",
                    f"Period ended {days} days ago - request a bridge letter.", page)
    return Flag(GREEN, "Period currency", f"Period ended {days} days ago.", page)


def flag_exceptions(fields):
    found = fields["exceptions"]
    if not found:
        return Flag(GREEN, "Exceptions",
                    "No exceptions found by text search - skim the test results to confirm.")
    pages = sorted({f.page for f in found})
    page_list = ", ".join(str(p) for p in pages)
    return Flag(AMBER, "Exceptions",
                f"{len(found)} exception(s) noted (page {page_list}) "
                "- assess each one and read management's response.",
                pages[0])


def flag_subservice(fields):
    method = fields["subservice_method"]
    orgs = [f.value for f in fields["subservice_organizations"]]
    names = ", ".join(orgs) if orgs else "names not found"

    if method.value in ("Carve-out", "Both (verify)"):
        return Flag(AMBER, "Subservice orgs",
                    f"Carve-out subservice organization(s) ({names}) "
                    "- get their SOC reports.", method.page)
    if method.value == "Inclusive":
        return Flag(GREEN, "Subservice orgs",
                    f"Inclusive method ({names}) - their controls are tested in this report.",
                    method.page)
    if orgs:
        return Flag(AMBER, "Subservice orgs",
                    f"Subservice organization(s) found ({names}) but the method is unclear "
                    "- check whether they are carved out.", fields["subservice_organizations"][0].page)
    return Flag(GREEN, "Subservice orgs", "No subservice organizations found.")


def flag_cuecs(fields):
    found = fields["cuecs"]
    if not found:
        return Flag(GREEN, "CUECs",
                    "No complementary user entity controls found - confirm in the system description.")
    return Flag(AMBER, "CUECs",
                f"{len(found)} complementary user entity control(s) "
                "- map each one to an owner on our side.", found[0].page)


# The list of rules build_flags() runs, in order. To add a rule, write a
# function like the ones above and add it here.
RULES = [
    flag_opinion,
    flag_report_kind,
    flag_period_length,
    flag_period_age,
    flag_exceptions,
    flag_subservice,
    flag_cuecs,
]


def build_flags(fields):
    """Run every rule and return the flags, worst first (red, amber, green)."""
    flags = []
    for rule in RULES:
        flag = rule(fields)
        if flag is not None:
            flags.append(flag)
    # sorted() keeps the original order among flags of the same level.
    return sorted(flags, key=lambda flag: SEVERITY_ORDER[flag.level])


def overall_level(flags):
    """The worst level among the flags: one red flag makes the whole report red."""
    if not flags:
        return AMBER  # nothing to judge by: don't call it green
    return min((flag.level for flag in flags), key=lambda level: SEVERITY_ORDER[level])


# ----------------------------------------------------------------------------
# Try it:   python flags.py tests/fixtures/fake_soc2_report.pdf
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    from extract import extract_all
    from pdf_text import extract_pages_from_pdf, load_pages_from_text, looks_scanned

    path = sys.argv[1]
    report_pages = (load_pages_from_text(path) if path.endswith(".txt")
                    else extract_pages_from_pdf(path))
    if looks_scanned(report_pages):
        print("This looks like a scanned PDF. Run OCR on it first.")
        sys.exit(1)

    report_flags = build_flags(extract_all(report_pages))
    print(f"Overall: {overall_level(report_flags).upper()}\n")
    for flag in report_flags:
        where = f" (p.{flag.page})" if flag.page else ""
        print(f"[{flag.level.upper():5}] {flag.topic}: {flag.reason}{where}")
