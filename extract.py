"""
extract.py - Stage 2: pull the key facts out of a SOC report with regex.

Every function here takes the list of Page objects from pdf_text.py and
looks for one thing (the opinion, the period, the exceptions...). They use
regular expressions ("regex"): small patterns that describe text, such as
"the word Type, a space, then I or II".

Each function returns a Finding (or a list of them). A Finding holds:
    value    - what we found, e.g. "SOC 2" or "Qualified"
    page     - the page number where we found it
    excerpt  - the text around it, so a reviewer can check it

IMPORTANT: this is a FIRST PASS. Auditors don't all use the same wording,
and PDFs scramble table layouts. The UI tells the user to verify every
result in the report itself.

Regex cheat sheet for the patterns below:
    \\b         a word boundary (start or end of a word)
    \\s+        one or more spaces / line breaks
    \\d{4}      exactly four digits
    (...)      a "capture group": the part we want to keep
    (?:...)    a group that is NOT kept, just used for "this OR that"
    a|b        a or b
    ?          the thing before is optional
    .+?        one or more of any character, as FEW as possible
    re.I       ignore upper/lower case
"""

import re
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime


# ----------------------------------------------------------------------------
# The result type
# ----------------------------------------------------------------------------

@dataclass
class Finding:
    value: object          # what we found (None if nothing was found)
    page: int = None       # page number where we found it
    excerpt: str = ""      # surrounding text, for the reviewer to verify


# ----------------------------------------------------------------------------
# Small helpers used by many functions
# ----------------------------------------------------------------------------

def flatten(text):
    """Collapse all line breaks and runs of spaces into single spaces.

    PDFs break sentences across lines in random places. Flattening lets a
    pattern like "for the period January 1" match even when "period" and
    "January" ended up on different lines.
    """
    return " ".join(text.split())


def make_excerpt(text, start, end, padding=150):
    """Return the matched text plus some context on each side."""
    left = max(0, start - padding)
    right = min(len(text), end + padding)
    snippet = text[left:right].strip()
    if left > 0:
        snippet = "..." + snippet
    if right < len(text):
        snippet = snippet + "..."
    return snippet


def find_first(pages, pattern, flags=re.I):
    """Search pages in order. Return (page, flat_text, match) for the first
    hit, or (None, None, None) if the pattern appears nowhere."""
    for page in pages:
        flat = flatten(page.text)
        match = re.search(pattern, flat, flags)
        if match:
            return page, flat, match
    return None, None, None


# Control IDs at the start of a line in the test-results tables, e.g.
# CC6.1, A1.2, C1.1, PI1.3, P4.2 (SOC 2) or CO 1.01, Control 5.2, 3.1 (SOC 1).
CONTROL_ID = re.compile(
    r"^\s*((?:CC|PI|A|C|P)\d{1,2}\.\d{1,2}(?:\.\d+)?"
    r"|(?:CO|Control)\s*\d+(?:\.\d+)*"
    r"|\d{1,2}\.\d{1,2}(?:\.\d+)?)\b"
)


def control_id_above(text_before):
    """Find the nearest control ID at the start of a line, looking upward.

    The text of a test-results row usually starts with the control ID, and
    the result ("Exception noted") is further along the same row or on a
    line below it. So we walk back up the lines until one starts with an ID.
    """
    for line in reversed(text_before.splitlines()):
        match = CONTROL_ID.match(line)
        if match:
            return match.group(1)
    return None


# ----------------------------------------------------------------------------
# 1. Report type: SOC 1 or SOC 2
# ----------------------------------------------------------------------------

def report_type(pages):
    """Return Finding("SOC 1" / "SOC 2" / None).

    We count every "SOC 1" and "SOC 2" in the document and pick the most
    common, because a SOC 2 report may mention SOC 1 once in passing.
    """
    counts = Counter()
    first_seen = {}  # where each label first appeared, for the evidence
    for page in pages:
        flat = flatten(page.text)
        for match in re.finditer(r"\bSOC\s*([12])\b", flat, re.I):
            label = "SOC " + match.group(1)
            counts[label] += 1
            if label not in first_seen:
                first_seen[label] = (page.number,
                                     make_excerpt(flat, match.start(), match.end()))

    if counts:
        label = counts.most_common(1)[0][0]
        page_number, excerpt = first_seen[label]
        return Finding(label, page_number, excerpt)

    # No explicit label: fall back on wording only one type uses.
    page, flat, match = find_first(pages, r"trust services criteria")
    if match:
        return Finding("SOC 2", page.number,
                       "(inferred) " + make_excerpt(flat, match.start(), match.end()))
    page, flat, match = find_first(pages, r"internal control over financial reporting")
    if match:
        return Finding("SOC 1", page.number,
                       "(inferred) " + make_excerpt(flat, match.start(), match.end()))
    return Finding(None)


# ----------------------------------------------------------------------------
# 2. Type I or Type II
# ----------------------------------------------------------------------------

# Reports write this as "Type 2", "Type II", "Type 1" or "Type I".
TYPE_NAMES = {"1": "Type I", "I": "Type I", "2": "Type II", "II": "Type II"}


def report_kind(pages):
    """Return Finding("Type I" / "Type II" / None)."""
    counts = Counter()
    first_seen = {}
    for page in pages:
        flat = flatten(page.text)
        # (II|I|2|1): II comes before I so "Type II" isn't read as "Type I".
        for match in re.finditer(r"\bType\s*(II|I|2|1)\b", flat, re.I):
            label = TYPE_NAMES[match.group(1).upper()]
            counts[label] += 1
            if label not in first_seen:
                first_seen[label] = (page.number,
                                     make_excerpt(flat, match.start(), match.end()))

    if counts:
        label = counts.most_common(1)[0][0]
        page_number, excerpt = first_seen[label]
        return Finding(label, page_number, excerpt)

    # Fallback: only a Type II opinion covers "operating effectiveness"
    # "throughout the period". A Type I is "as of" a single date.
    page, flat, match = find_first(pages, r"operat\w+ effectively throughout the period")
    if match:
        return Finding("Type II", page.number,
                       "(inferred) " + make_excerpt(flat, match.start(), match.end()))
    page, flat, match = find_first(pages, r"suitably designed[^.]{0,200}\bas of\b")
    if match:
        return Finding("Type I", page.number,
                       "(inferred) " + make_excerpt(flat, match.start(), match.end()))
    return Finding(None)


# ----------------------------------------------------------------------------
# 3. Service organization name
# ----------------------------------------------------------------------------

# Standard AICPA phrasings that put the service org's name right before 's.
# ['’] matches both a straight and a curly apostrophe (PDFs use both).
SERVICE_ORG_PATTERNS = [
    r"Report on (?:the )?(.{3,100}?)['’]s Description",
    r"We have examined (?:the )?(.{3,100}?)['’]s\b",
    r"description of (.{3,100}?)['’]s\b",
]


def service_organization(pages):
    """Return Finding(name of the company being audited)."""
    for pattern in SERVICE_ORG_PATTERNS:
        page, flat, match = find_first(pages, pattern, flags=0)
        if match:
            name = match.group(1).strip(" ,\"")
            return Finding(name, page.number,
                           make_excerpt(flat, match.start(), match.end()))
    return Finding(None)


# ----------------------------------------------------------------------------
# 4. Audit firm
# ----------------------------------------------------------------------------

# A line that is just a firm name ending in a legal suffix, e.g.
# "Smith & Patel LLP" or "Prepared by: Smith & Patel LLP". This is how the
# auditor signs the report. re.M makes ^ and $ match each line's start/end.
FIRM_LINE = re.compile(
    r"^\s*(?:Prepared by:?|Issued by:?)?\s*"
    r"([A-Z][A-Za-z0-9&.,'’ \-]{1,80}?\b(?:LLP|L\.L\.P\.|LLC|PLLC|P\.C\.|CPAs?|Ltd))"
    r"\.?\s*$",
    re.M,
)


def audit_firm(pages, service_org_name=None):
    """Return Finding(name of the CPA firm that signed the report).

    We prefer a match on the auditor's report pages and take the LAST one,
    because the signature comes at the end of the report. If the service
    org is itself an LLC, we skip lines that are just its name.
    """
    candidates = []  # (is_auditor_page, page, line text)
    for page in pages:
        is_auditor_page = "service auditor" in page.text.lower()
        for match in FIRM_LINE.finditer(page.text):
            name = match.group(1).strip()
            if service_org_name and name.lower() in service_org_name.lower():
                continue
            candidates.append((is_auditor_page, page, name))

    if not candidates:
        return Finding(None)

    on_auditor_pages = [c for c in candidates if c[0]]
    _, page, name = on_auditor_pages[-1] if on_auditor_pages else candidates[0]
    flat = flatten(page.text)
    position = flat.find(name)
    return Finding(name, page.number,
                   make_excerpt(flat, position, position + len(name)))


# ----------------------------------------------------------------------------
# 5. Review period, months covered, days since the period ended
# ----------------------------------------------------------------------------

MONTHS = ("January|February|March|April|May|June|July|August|"
          "September|October|November|December")
# Matches "January 1, 2026", "January 1 2026" and "1 January 2026".
# The doubled {{ }} are needed inside an f-string to mean a literal { }.
DATE = rf"(?:(?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}\s+(?:{MONTHS})\s+\d{{4}})"

PERIOD_PATTERN = (
    rf"period\s+(?:from\s+|of\s+|beginning\s+)?({DATE})\s*"
    rf"(?:to|through|thru|and ending(?: on)?|[-–—])\s*({DATE})"
)
AS_OF_PATTERN = rf"\bas of\s+({DATE})"


def parse_date(text):
    """Turn "January 1, 2026" or "1 January 2026" into a date object."""
    cleaned = text.replace(",", "")
    for fmt in ("%B %d %Y", "%d %B %Y"):
        try:
            return datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass  # wrong format, try the next one
    return None


def review_period(pages):
    """Return Finding({"start": date or None, "end": date}).

    Type II: "for the period January 1, 2026 to June 30, 2026".
    Type I:  "as of June 30, 2026", so start is None.
    The same period is repeated many times in a report, so we take the most
    common one in case a stray date range appears somewhere.
    """
    counts = Counter()
    first_seen = {}
    for page in pages:
        flat = flatten(page.text)
        for match in re.finditer(PERIOD_PATTERN, flat, re.I):
            pair = (match.group(1), match.group(2))
            counts[pair] += 1
            if pair not in first_seen:
                first_seen[pair] = (page.number,
                                    make_excerpt(flat, match.start(), match.end()))

    if counts:
        start_text, end_text = counts.most_common(1)[0][0]
        page_number, excerpt = first_seen[(start_text, end_text)]
        period = {"start": parse_date(start_text), "end": parse_date(end_text)}
        return Finding(period, page_number, excerpt)

    page, flat, match = find_first(pages, AS_OF_PATTERN)
    if match:
        period = {"start": None, "end": parse_date(match.group(1))}
        return Finding(period, page.number,
                       make_excerpt(flat, match.start(), match.end()))
    return Finding(None)


def months_covered(period):
    """How many months a Type II period covers, rounded. None for Type I.

    Jan 1 to Jun 30 is 181 days; 181 / 30.44 (average days in a month)
    rounds to 6.
    """
    if not period or not period.get("start") or not period.get("end"):
        return None
    days = (period["end"] - period["start"]).days + 1  # +1: count both ends
    return round(days / 30.44)


def days_since_period_end(period, today=None):
    """Days between the period end date and today.

    `today` can be passed in so tests always get the same answer.
    """
    if not period or not period.get("end"):
        return None
    today = today or date.today()
    return (today - period["end"]).days


# ----------------------------------------------------------------------------
# 6. Auditor's opinion and the "Basis for..." paragraph
# ----------------------------------------------------------------------------

# Checked in this order: the first one found wins. "Unmodified" is last
# because every opinion, clean or not, contains "In our opinion".
# \bQualified does NOT match inside "Unqualified" (no word boundary there).
OPINION_CHECKS = [
    ("Disclaimer", r"\bDisclaimer of Opinion\b"),
    ("Adverse", r"\bAdverse Opinion\b"),
    ("Qualified", r"\bQualified Opinion\b|\bexcept for the (?:matter|effects?)\b"),
    ("Unmodified", r"\bIn our opinion\b"),
]


def opinion(pages):
    """Return Finding("Unmodified" / "Qualified" / "Adverse" / "Disclaimer")."""
    for label, pattern in OPINION_CHECKS:
        page, flat, match = find_first(pages, pattern)
        if match:
            return Finding(label, page.number,
                           make_excerpt(flat, match.start(), match.end()))
    return Finding(None)


# The heading, e.g. "Basis for Qualified Opinion". The (?!\s+paragraph)
# part skips references like "...described in the Basis for Qualified
# Opinion paragraph", which mention the heading without being it.
BASIS_HEADING = re.compile(
    r"Basis for (?:Qualified |Adverse |Disclaimer of )?Opinion\b(?!\s+paragraph)"
)
# Where the paragraph ends: the next opinion heading. Case-sensitive on
# purpose, so a lower-case "opinion" inside the paragraph doesn't stop it.
BASIS_END = re.compile(
    r"(?:Qualified|Adverse) Opinion\b|Disclaimer of Opinion\b|In our opinion|\bOpinion\b"
)


def basis_for_opinion(pages):
    """Return Finding(text of the "Basis for ... Opinion" paragraph).

    Only modified opinions have this paragraph. The paragraph can run onto
    the next page, so we search the heading's page plus the one after it.
    """
    for index, page in enumerate(pages):
        flat = flatten(page.text)
        heading = BASIS_HEADING.search(flat)
        if not heading:
            continue
        # Text after the heading, continuing onto the next page if any.
        following = flat[heading.end():]
        if index + 1 < len(pages):
            following += " " + flatten(pages[index + 1].text)
        end = BASIS_END.search(following)
        paragraph = following[: end.start() if end else 2000].strip()
        return Finding(paragraph[:2000], page.number, heading.group(0))
    return Finding(None)


# ----------------------------------------------------------------------------
# 7. Trust Services Criteria in scope (SOC 2)
# ----------------------------------------------------------------------------

CATEGORIES = ["Security", "Availability", "Processing Integrity",
              "Confidentiality", "Privacy"]
CATEGORY = r"(?:security|availability|processing integrity|confidentiality|privacy)"
# A list like "Security, Availability, and Confidentiality".
CATEGORY_LIST = rf"{CATEGORY}(?:\s*,\s*(?:and\s+)?{CATEGORY}|\s+and\s+{CATEGORY})*"
TSC_PATTERN = rf"(?:relevant to|criteria for)\s+(?:the\s+)?({CATEGORY_LIST})"


def trust_services_criteria(pages):
    """Return Finding([list of categories in scope]).

    Trap to avoid: every SOC 2 cites the AICPA standard by its full title,
    "2017 Trust Services Criteria for Security, Availability, Processing
    Integrity, Confidentiality, and Privacy". That lists all five even when
    only Security is in scope. So we skip any match that follows "2017" or
    "TSP section 100" (the standard's name).
    """
    found = set()
    first_page, first_excerpt = None, ""
    for page in pages:
        flat = flatten(page.text)
        for match in re.finditer(TSC_PATTERN, flat, re.I):
            before = flat[max(0, match.start() - 40): match.start()]
            if "2017" in before or "TSP" in before:
                continue  # this is the standard's title, not the scope
            for category in CATEGORIES:
                if category.lower() in match.group(1).lower():
                    found.add(category)
            if first_page is None:
                first_page = page.number
                first_excerpt = make_excerpt(flat, match.start(), match.end())

    # Keep the standard order (Security first...) rather than random order.
    in_scope = [c for c in CATEGORIES if c in found]
    return Finding(in_scope, first_page, first_excerpt)


# ----------------------------------------------------------------------------
# 8. Test exceptions / deviations
# ----------------------------------------------------------------------------

# Matches "Exception noted", "exceptions were noted", "Deviation noted",
# "deviations identified", etc. \s+ allows a line break in between.
EXCEPTION_PATTERN = re.compile(
    r"\b(?:exceptions?|deviations?)\s+(?:was\s+|were\s+)?(?:noted|identified|found)\b",
    re.I,
)
# If one of these words comes right before the phrase, it is NOT an
# exception: "No exceptions noted", "no relevant exceptions noted",
# "the exceptions noted in Section 4" (a reference back to one).
NEGATION_BEFORE = re.compile(
    r"\b(?:no|not|without|the|any)\s+(?:relevant\s+|other\s+|further\s+|additional\s+)?$",
    re.I,
)


def is_negated(text_before):
    """True if the words just before the match cancel it out."""
    return bool(NEGATION_BEFORE.search(flatten(text_before[-40:]) + " "))


def exceptions(pages):
    """Return a list of Finding(control ID, page, excerpt), one per exception.

    "No exceptions noted" is the most common phrase in any SOC report and
    must NOT count, so every match is checked with is_negated() first.
    """
    results = []
    for page in pages:
        text = page.text
        for match in EXCEPTION_PATTERN.finditer(text):
            before = text[: match.start()]
            if is_negated(before):
                continue

            # Evidence: from the start of the matched line, plus a few lines
            # after it, stopping at the next control's row.
            line_start = text.rfind("\n", 0, match.start()) + 1
            lines = text[line_start:].splitlines()
            excerpt_lines = [lines[0]]
            for line in lines[1:6]:
                if CONTROL_ID.match(line):
                    break
                excerpt_lines.append(line)

            control = control_id_above(text[: match.end()])
            results.append(Finding(control or "(control not identified)",
                                   page.number,
                                   flatten(" ".join(excerpt_lines))))
    return results


# ----------------------------------------------------------------------------
# 9. Management's responses to exceptions
# ----------------------------------------------------------------------------

RESPONSE_PATTERN = re.compile(r"Management['’]?s?\s+Responses?", re.I)


def management_responses(pages):
    """Return a list of Finding(control ID, page, response text).

    We keep "Management's response: ..." entries and skip the section
    heading ("Management's Response to Exceptions"), which has no colon
    and nothing else on its line.
    """
    results = []
    for page in pages:
        text = page.text
        matches = list(RESPONSE_PATTERN.finditer(text))
        for i, match in enumerate(matches):
            line_end = text.find("\n", match.end())
            rest_of_line = text[match.end(): line_end if line_end != -1 else None]
            if ":" not in rest_of_line and len(rest_of_line.strip()) < 40:
                continue  # a heading, not a response

            # The response runs until the next response or the end of the page.
            stop = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            line_start = text.rfind("\n", 0, match.start()) + 1
            body = flatten(text[line_start:stop])[:1000]

            control = control_id_above(text[: match.end()])
            results.append(Finding(control, page.number, body))
    return results


# ----------------------------------------------------------------------------
# 10. Subservice organizations and carve-out vs inclusive method
# ----------------------------------------------------------------------------

def subservice_method(pages):
    """Return Finding("Carve-out" / "Inclusive" / "Both (verify)" / None).

    Carve-out: the subservice org's controls are EXCLUDED from the report,
    so you need the subservice org's own SOC report.
    Inclusive: they are included and tested in this report.
    """
    carve_page, carve_flat, carve = find_first(pages, r"\bcarve[\s-]*out\b|\bcarved[\s-]*out\b")
    incl_page, incl_flat, incl = find_first(pages, r"\binclusive method\b")

    if carve and incl:
        return Finding("Both (verify)", carve_page.number,
                       make_excerpt(carve_flat, carve.start(), carve.end()))
    if carve:
        return Finding("Carve-out", carve_page.number,
                       make_excerpt(carve_flat, carve.start(), carve.end()))
    if incl:
        return Finding("Inclusive", incl_page.number,
                       make_excerpt(incl_flat, incl.start(), incl.end()))
    return Finding(None)


# Common subservice providers. Found by name on pages that talk about
# subservice organizations. Add more as you meet them in real reports.
KNOWN_PROVIDERS = [
    "Amazon Web Services", "Microsoft Azure", "Microsoft Corporation",
    "Google Cloud Platform", "Google LLC", "Oracle Cloud", "IBM Cloud",
    "Equinix", "Digital Realty", "CoreSite", "Rackspace", "Cyxtera",
    "Salesforce", "Snowflake", "Okta", "Cloudflare", "MongoDB",
    "Iron Mountain", "ADP", "Workday", "Twilio", "Stripe",
]

# Prose like "uses a subservice organization, Amazon Web Services, Inc.
# (AWS), to provide...". The name is a run of Capitalised Words. The
# lower-case "subservice" is deliberate: it skips capitalised headings.
NAMED_SUBSERVICE = re.compile(
    r"subservice organizations?,?\s+(?:including\s+|such as\s+)?"
    r"([A-Z][\w&'’.\-]*(?:,?\s+(?:[A-Z][\w&'’.\-]*|of))*)"
)
NOT_A_NAME = {"The", "This", "These", "Section", "Management", "Our"}


def _simplify(name):
    """Lower-case a name and drop punctuation and Inc/LLC, for comparing."""
    name = re.sub(r"[^\w\s]", " ", name.lower())
    name = re.sub(r"\b(?:inc|llc|ltd|corp|corporation|co)\b", " ", name)
    return " ".join(name.split())


def subservice_organizations(pages, service_org_name=None):
    """Return a list of Finding(subservice org name, page, excerpt)."""
    results = []
    seen = []  # simplified names already added, to avoid duplicates

    def add(name, page_number, excerpt):
        name = name.strip(" ,")
        key = _simplify(name)
        if not key or name.split()[0] in NOT_A_NAME:
            return
        if service_org_name and key == _simplify(service_org_name):
            return  # that's the company being audited, not a subservice org
        # Skip "Amazon Web Services" if we already have "Amazon Web Services, Inc."
        if any(key in other or other in key for other in seen):
            return
        seen.append(key)
        results.append(Finding(name, page_number, excerpt))

    for page in pages:
        flat = flatten(page.text)
        for match in NAMED_SUBSERVICE.finditer(flat):
            add(match.group(1), page.number,
                make_excerpt(flat, match.start(), match.end()))
        if "subservice" in flat.lower():
            for provider in KNOWN_PROVIDERS:
                position = flat.find(provider)
                if position != -1:
                    add(provider, page.number,
                        make_excerpt(flat, position, position + len(provider)))
    return results


# ----------------------------------------------------------------------------
# 11. CUECs and CSOCs (numbered lists under a heading)
# ----------------------------------------------------------------------------

CUEC_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:Complementary User Entity Control(?:s| Considerations)"
    r"|User Entity Responsibilities)(?:\s*\(CUECs?\))?\s*:?\s*$",
    re.I,
)
CSOC_HEADING = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?Complementary Subservice Organization Controls"
    r"(?:\s*\(CSOCs?\))?\s*:?\s*$",
    re.I,
)
# A line that starts a new list item: "CUEC-1", "1.", "2)", "a.", or a bullet.
ITEM_START = re.compile(r"^\s*(?:CUEC|CSOC)[\s\-]*\d+|^\s*(?:\d{1,2}[.)]|[a-z][.)]|[•●▪\-–*])\s")
# Lines that mean the list is over: a new section or the other list.
LIST_END = re.compile(
    r"^\s*(?:Section\s+\w+|Complementary (?:User Entity|Subservice)|Subservice Organizations"
    r"|Tests? of Controls|Management['’]s Response)",
    re.I,
)
MAX_LIST_PAGES = 3  # stop looking after this many pages past the heading


def _list_under_heading(pages, heading_pattern):
    """Collect the items listed under a heading, e.g. all the CUECs.

    How it works, line by line:
      - find the heading line
      - a line starting with a marker (CUEC-1, 1., a bullet) starts an item
      - other lines are joined onto the current item (wrapped text)
      - stop at the next section heading, or after MAX_LIST_PAGES pages
    Lines before the first item (an intro sentence) are ignored.
    """
    items = []           # list of [page number, text] while we build them
    collecting = False
    pages_used = 0

    for page in pages:
        if collecting:
            pages_used += 1
            if pages_used > MAX_LIST_PAGES:
                break
        for line in page.text.splitlines():
            if not collecting:
                if heading_pattern.match(line):
                    collecting = True
                continue
            if not line.strip() or line.strip().endswith("(continued)"):
                continue  # skip blank lines and repeated page headers
            if LIST_END.match(line):
                collecting = False
                break
            if ITEM_START.match(line):
                items.append([page.number, line.strip()])
            elif items:
                items[-1][1] += " " + line.strip()  # wrapped onto a new line
        if items and not collecting:
            break  # the list ended on this page

    return [Finding(flatten(text), number, flatten(text)) for number, text in items]


def cuecs(pages):
    """Return a list of Finding(CUEC text, page, excerpt)."""
    return _list_under_heading(pages, CUEC_HEADING)


def csocs(pages):
    """Return a list of Finding(CSOC text, page, excerpt)."""
    return _list_under_heading(pages, CSOC_HEADING)


# ----------------------------------------------------------------------------
# Run everything at once
# ----------------------------------------------------------------------------

def extract_all(pages, today=None):
    """Run every extractor and return the results in one dictionary.

    This is what stage 3 (flags) and stage 4 (the UI) will use.
    """
    org = service_organization(pages)
    period = review_period(pages)
    opinion_found = opinion(pages)

    # The "Basis for..." paragraph only matters if the opinion isn't clean.
    if opinion_found.value in (None, "Unmodified"):
        basis = Finding(None)
    else:
        basis = basis_for_opinion(pages)

    return {
        "report_type": report_type(pages),
        "report_kind": report_kind(pages),
        "service_organization": org,
        "audit_firm": audit_firm(pages, org.value),
        "review_period": period,
        "months_covered": months_covered(period.value),
        "days_since_period_end": days_since_period_end(period.value, today),
        "opinion": opinion_found,
        "basis_for_opinion": basis,
        "trust_services_criteria": trust_services_criteria(pages),
        "exceptions": exceptions(pages),
        "management_responses": management_responses(pages),
        "subservice_method": subservice_method(pages),
        "subservice_organizations": subservice_organizations(pages, org.value),
        "cuecs": cuecs(pages),
        "csocs": csocs(pages),
    }


# ----------------------------------------------------------------------------
# Try it:   python extract.py tests/fixtures/fake_soc2_report.pdf
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    from pdf_text import extract_pages_from_pdf, load_pages_from_text, looks_scanned

    path = sys.argv[1]
    report_pages = (load_pages_from_text(path) if path.endswith(".txt")
                    else extract_pages_from_pdf(path))
    if looks_scanned(report_pages):
        print("This looks like a scanned PDF. Run OCR on it first.")
        sys.exit(1)

    for field_name, result in extract_all(report_pages).items():
        print(f"\n== {field_name} ==")
        if isinstance(result, list):
            print(f"   {len(result)} found")
            for item in result:
                print(f"   - p.{item.page}: {item.value} | {item.excerpt[:90]}")
        elif isinstance(result, Finding):
            print(f"   {result.value}   (page {result.page})")
        else:
            print(f"   {result}")
