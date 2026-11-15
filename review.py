"""
review.py - Stage 6: the reviewer checklist and the Markdown review memo.

Two parts:

1. CHECKLIST: the 9 questions a vendor-risk reviewer answers about a SOC
   report. checklist_hints() adds what the tool found for each one, as a
   hint. The tool never answers the questions itself: every status starts
   as "Not reviewed" and only the reviewer changes it.

2. build_memo(): turns everything - extracted facts, flags, the reviewer's
   checklist answers, and the optional Claude analysis - into one Markdown
   document to save or share.

Markdown is plain text with light formatting (# for headings, | for table
columns), so the memo opens in any text editor and renders nicely on GitHub,
in Confluence, Notion, Obsidian, VS Code, etc.
"""

from datetime import date

from flags import overall_level

STATUSES = ["Not reviewed", "Satisfactory", "Needs follow-up",
            "Not satisfactory", "Not applicable"]

# (key, question). The key is a short ID used to store each answer.
CHECKLIST = [
    ("scope", "Report scope matches the services we use"),
    ("period", "Review period is current"),
    ("opinion", "Auditor's opinion is acceptable"),
    ("criteria", "Trust Services Criteria / control objectives cover our risks"),
    ("exceptions", "Exceptions assessed for impact on us"),
    ("cuecs", "CUECs mapped to owners on our side"),
    ("subservice", "Subservice organization SOC reports obtained"),
    ("bridge", "Bridge letter obtained (if needed)"),
    ("auditor", "Auditor is a licensed CPA firm"),
]


# ----------------------------------------------------------------------------
# Hints: what the tool found, per checklist item
# ----------------------------------------------------------------------------

def _flag_reason(flags, topic):
    """The reason text of the flag with this topic, or '' if there isn't one."""
    for flag in flags:
        if flag.topic == topic:
            return flag.reason
    return ""


def checklist_hints(fields, flags):
    """Return {checklist key: one-line hint} built from the extracted facts."""
    org = fields["service_organization"].value or "the service organization"
    criteria = fields["trust_services_criteria"].value
    days = fields["days_since_period_end"]
    firm = fields["audit_firm"].value

    if days is None:
        bridge = "Period end not found - check whether a bridge letter is needed."
    elif days > 90:
        bridge = f"Needed: the period ended {days} days ago (over 90)."
    else:
        bridge = f"Probably not needed: the period ended {days} days ago."

    return {
        # A semicolon, not a full stop: names like "Acme, Inc." already end in one.
        "scope": f"The report is about {org}; compare its system description "
                 "with the services you actually use.",
        "period": _flag_reason(flags, "Period currency"),
        "opinion": _flag_reason(flags, "Opinion"),
        "criteria": (f"In scope: {', '.join(criteria)}." if criteria else
                     "No Trust Services Criteria found (expected for a SOC 1 - "
                     "review the control objectives instead)."),
        "exceptions": _flag_reason(flags, "Exceptions"),
        "cuecs": _flag_reason(flags, "CUECs"),
        "subservice": _flag_reason(flags, "Subservice orgs"),
        "bridge": bridge,
        "auditor": (f"Signed by {firm}. " if firm else "Audit firm not found. ")
                   + "Check the firm's license, e.g. on cpaverify.org.",
    }


# ----------------------------------------------------------------------------
# Building the memo
# ----------------------------------------------------------------------------

def md_cell(text):
    """Make text safe to put inside a Markdown table cell.

    A "|" would start a new column and a line break would end the row, so
    we escape the first and replace the second with a space.
    """
    text = "" if text is None else str(text)
    return " ".join(text.replace("|", "\\|").split())


def _format_date(d):
    return f"{d:%b} {d.day}, {d.year}" if d else "?"


def _format_period(period):
    if not period:
        return "Not found"
    if period["start"] is None:
        return f"As of {_format_date(period['end'])}"
    return f"{_format_date(period['start'])} to {_format_date(period['end'])}"


def _show(value):
    return "Not found" if value in (None, "", []) else value


def build_memo(fields, flags, answers, file_name, analysis=None,
               reviewer="", today=None):
    """Return the review memo as one Markdown string.

    answers  - {checklist key: {"status": ..., "notes": ...}} from the UI
    analysis - the SocAnalysis from stage 5, or None if it wasn't run
    today    - can be passed in so tests always get the same date
    """
    today = today or date.today()
    org = fields["service_organization"].value or "Unknown service organization"
    report = " ".join(p for p in (fields["report_type"].value,
                                  fields["report_kind"].value) if p) or "Not found"
    criteria = fields["trust_services_criteria"].value

    # We build the memo as a list of lines, then join them at the end.
    lines = [
        f"# SOC Report Review: {org}",
        "",
        f"- **Review date:** {_format_date(today)}",
        f"- **Reviewer:** {reviewer or '(not entered)'}",
        f"- **Report file:** {file_name}",
        "",
        "> Prepared with the SOC Report Analyzer. Extracted facts come from "
        "pattern matching and must be verified in the report. Page numbers "
        "are PDF page numbers.",
        "",
        "## Report summary",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| Report | {md_cell(report)} |",
        f"| Service organization | {md_cell(org)} |",
        f"| Audit firm | {md_cell(_show(fields['audit_firm'].value))} |",
        f"| Review period | {_format_period(fields['review_period'].value)} |",
        f"| Months covered | {_show(fields['months_covered'])} |",
        f"| Days since period end | {_show(fields['days_since_period_end'])} |",
        f"| Opinion | {md_cell(_show(fields['opinion'].value))} |",
        f"| Trust Services Criteria | {md_cell(', '.join(criteria) if criteria else 'Not found')} |",
        f"| Exceptions found | {len(fields['exceptions'])} |",
        f"| Subservice method | {md_cell(_show(fields['subservice_method'].value))} |",
        f"| CUECs / CSOCs | {len(fields['cuecs'])} / {len(fields['csocs'])} |",
        "",
        f"## Automated flags (overall: {overall_level(flags).upper()})",
        "",
    ]
    for flag in flags:
        page = f" (p. {flag.page})" if flag.page else ""
        lines.append(f"- **{flag.level.upper()}**, {flag.topic}: {flag.reason}{page}")

    # --- The reviewer's checklist ----------------------------------------
    not_reviewed = sum(1 for key, _ in CHECKLIST
                       if answers.get(key, {}).get("status", STATUSES[0]) == STATUSES[0])
    lines += ["", "## Reviewer checklist", ""]
    if not_reviewed:
        lines += [f"**{not_reviewed} of {len(CHECKLIST)} items not yet reviewed.**", ""]
    lines += ["| # | Item | Status | Notes |", "|---|---|---|---|"]
    for number, (key, question) in enumerate(CHECKLIST, start=1):
        answer = answers.get(key, {})
        lines.append(f"| {number} | {md_cell(question)} "
                     f"| {md_cell(answer.get('status', STATUSES[0]))} "
                     f"| {md_cell(answer.get('notes', ''))} |")

    # --- Evidence ---------------------------------------------------------
    basis = fields["basis_for_opinion"]
    if basis.value:
        lines += ["", f"## Basis for opinion (p. {basis.page})", "", f"> {md_cell(basis.value)}"]

    lines += ["", "## Exceptions", ""]
    if fields["exceptions"]:
        responses = {r.value: r for r in fields["management_responses"] if r.value}
        for item in fields["exceptions"]:
            lines += [f"### {item.value} (p. {item.page})", "",
                      f"> {md_cell(item.excerpt)}", ""]
            response = responses.get(item.value)
            if response:
                lines += [f"**Management's response (p. {response.page}):** "
                          f"{md_cell(response.excerpt)}", ""]
    else:
        lines += ["No exceptions found by text search.", ""]

    lines += ["## Subservice organizations", ""]
    orgs = fields["subservice_organizations"]
    lines += [f"- {o.value} (p. {o.page})" for o in orgs] or ["None found."]
    lines += ["", f"Method: {_show(fields['subservice_method'].value)}", ""]

    lines += ["## Complementary User Entity Controls (CUECs)", ""]
    lines += [f"- {md_cell(c.value)} (p. {c.page})" for c in fields["cuecs"]] or ["None found."]
    lines += ["", "## Complementary Subservice Organization Controls (CSOCs)", ""]
    lines += [f"- {md_cell(c.value)} (p. {c.page})" for c in fields["csocs"]] or ["None found."]

    # --- Optional Claude analysis -------------------------------------------
    if analysis is not None:
        lines += [
            "", "## Claude analysis (AI-generated - verify in the report)", "",
            f"**Overall risk: {analysis.overall_risk.rating}.** "
            f"{md_cell(analysis.overall_risk.reason)}", "",
        ]
        if analysis.exceptions:
            lines += ["| Control | Page | Severity | Description | Reason |",
                      "|---|---|---|---|---|"]
            lines += [f"| {md_cell(e.control_id)} | {e.page} | {e.severity} "
                      f"| {md_cell(e.description)} | {md_cell(e.reason)} |"
                      for e in analysis.exceptions]
            lines.append("")
        if analysis.cuecs:
            lines += ["| CUEC | Suggested owner |", "|---|---|"]
            lines += [f"| {md_cell(c.cuec)} | {md_cell(c.suggested_owner)} |"
                      for c in analysis.cuecs]
            lines.append("")
        if analysis.vendor_questions:
            lines += ["**Questions for the vendor**", ""]
            lines += [f"{n}. {md_cell(q)}"
                      for n, q in enumerate(analysis.vendor_questions, start=1)]

    return "\n".join(lines) + "\n"


def memo_file_name(fields, today=None):
    """e.g. "acme-cloud-services-inc-soc-review-2026-11-15.md"."""
    today = today or date.today()
    org = fields["service_organization"].value or "vendor"
    # Keep letters and digits, turn everything else into single dashes.
    slug = "".join(ch if ch.isalnum() else "-" for ch in org.lower())
    slug = "-".join(part for part in slug.split("-") if part)
    return f"{slug}-soc-review-{today.isoformat()}.md"
