"""
app.py - Stage 4: a local web page for the analyzer, built with Streamlit.

Run it with:
    streamlit run app.py
then open the address it prints (usually http://localhost:8501).

How Streamlit works, in one paragraph:
    Streamlit runs this whole file from top to bottom every time you
    interact with the page (upload a file, tick a box...). Each st.something()
    call draws one thing on the page. There are no callbacks to wire up: the
    script just runs again and redraws. That's why the slow part - reading
    the PDF - is cached (see analyze() below), so it only happens once per
    file instead of on every click.

Privacy: everything here runs on your machine. Nothing is uploaded anywhere;
the "upload" button just hands the file from your browser to this script.
The one exception is the optional "Run Claude analysis" button (stage 5),
which sends selected pages to the Claude API - only when clicked.
"""

import hashlib
import io
import os

import streamlit as st

from ai_analysis import (MAX_CHARS, MODEL, AnalysisError, api_key_is_set,
                         build_excerpts, run_analysis)
from extract import extract_all
from flags import build_flags, overall_level
from pdf_text import PdfReadError, extract_pages_from_pdf, load_pages_from_text, looks_scanned
from review import CHECKLIST, STATUSES, build_memo, checklist_hints, memo_file_name

SAMPLE_REPORT = os.path.join(os.path.dirname(__file__),
                             "tests", "fixtures", "fake_soc2_report.pdf")

# How each flag level is drawn: an icon, and which Streamlit box to use.
LEVEL_ICONS = {"red": "🔴", "amber": "🟠", "green": "🟢"}
LEVEL_BOXES = {"red": st.error, "amber": st.warning, "green": st.success}


# ----------------------------------------------------------------------------
# The analysis (cached)
# ----------------------------------------------------------------------------

@st.cache_data(show_spinner="Reading the report...")
def analyze(file_bytes):
    """Read the PDF and run extraction and flags.

    @st.cache_data remembers the result for each different file_bytes. Same
    file again -> Streamlit returns the saved result instantly instead of
    re-reading every page.

    Returns (pages, fields, flags). If the PDF looks scanned, fields and
    flags are None so the page can show an OCR message instead.
    """
    # io.BytesIO wraps the raw bytes so pdfplumber can treat them as a file.
    pages = extract_pages_from_pdf(io.BytesIO(file_bytes))
    if looks_scanned(pages):
        return pages, None, None
    fields = extract_all(pages)
    return pages, fields, build_flags(fields)


# ----------------------------------------------------------------------------
# Small display helpers
# ----------------------------------------------------------------------------

def show_or_missing(value):
    """Turn None / empty values into a visible 'Not found'."""
    if value is None or value == "" or value == []:
        return "Not found"
    return value


def format_date(d):
    """date(2026, 1, 1) -> "Jan 1, 2026"."""
    return f"{d:%b} {d.day}, {d.year}" if d else "?"


def format_period(period):
    if not period:
        return "Not found"
    if period["start"] is None:  # Type I
        return f"As of {format_date(period['end'])}"
    return f"{format_date(period['start'])} – {format_date(period['end'])}"


def show_excerpt(page, text):
    """Show one piece of evidence: its page number and the text around it.

    st.code shows the text exactly as-is in a grey box. We avoid st.markdown
    here because report text can contain characters like * or $ that
    markdown would turn into formatting.
    """
    st.markdown(f"**PDF page {page if page else '?'}**")
    st.code(text or "(no excerpt)", language=None, wrap_lines=True)


def as_table(items):
    """Turn Claude's results into table rows with readable column names.

    model_dump() turns each Pydantic object into a plain dictionary; we then
    rename keys like "control_id" to "Control id" for the column headers.
    """
    return [
        {key.replace("_", " ").capitalize(): value
         for key, value in item.model_dump().items()}
        for item in items
    ]


def show_finding_list(findings, empty_message):
    """Show every item in a list of Findings (CUECs, CSOCs, ...)."""
    if not findings:
        st.write(empty_message)
    for finding in findings:
        show_excerpt(finding.page, finding.value)


# ----------------------------------------------------------------------------
# The page
# ----------------------------------------------------------------------------

st.set_page_config(page_title="SOC Report Analyzer", page_icon="📄", layout="wide")
st.title("📄 SOC Report Analyzer")
st.caption("Upload a SOC 1 or SOC 2 report. It is processed on this computer only, "
           "unless you choose to run the optional Claude analysis.")

uploaded = st.file_uploader("SOC report (PDF)", type=["pdf"])
use_sample = st.checkbox("Or try the built-in fake sample report")

# Decide which file to analyze. An upload wins over the sample.
if uploaded is not None:
    file_bytes = uploaded.getvalue()
    file_name = uploaded.name
elif use_sample:
    with open(SAMPLE_REPORT, "rb") as f:
        file_bytes = f.read()
    file_name = "fake_soc2_report.pdf (sample)"
else:
    st.info("Upload a PDF to begin.")
    st.stop()  # stop drawing the rest of the page until there's a file

# --- Read the report, handling bad and scanned files gracefully -------------
try:
    pages, fields, flags = analyze(file_bytes)
except PdfReadError as error:
    st.error(str(error))
    st.stop()

if fields is None:
    st.error(
        f"**{file_name}** has {len(pages)} pages but almost no text. It is "
        "probably a scanned document (images of pages).\n\n"
        "Run it through OCR first to add a text layer - for example "
        "`ocrmypdf input.pdf output.pdf`, or the OCR feature in Adobe "
        "Acrobat - then upload the OCR'd file."
    )
    st.stop()

st.warning(
    "**First pass only - verify in the report.** These results come from "
    "pattern matching. Wording varies between audit firms, so check every "
    "finding against the page shown. Page numbers are PDF pages, which may "
    "differ from the numbers printed in the report.",
    icon="⚠️",
)

# --- Overall result ---------------------------------------------------------
overall = overall_level(flags)
st.header(f"{LEVEL_ICONS[overall]} Overall: {overall.upper()}")
st.caption(f"{file_name} · {len(pages)} pages")

# --- At-a-glance tiles ------------------------------------------------------
report_label = " ".join(
    part for part in (fields["report_type"].value, fields["report_kind"].value) if part
)
period = fields["review_period"].value
tsc = fields["trust_services_criteria"].value

row1 = st.columns(3)
row1[0].metric("Report", show_or_missing(report_label))
row1[1].metric("Opinion", show_or_missing(fields["opinion"].value))
row1[2].metric("Exceptions found", len(fields["exceptions"]))

row2 = st.columns(3)
row2[0].metric("Period end", format_date(period["end"]) if period else "Not found")
row2[1].metric("Months covered", show_or_missing(fields["months_covered"]))
row2[2].metric("Days since period end", show_or_missing(fields["days_since_period_end"]))

row3 = st.columns(3)
row3[0].metric("Subservice method", show_or_missing(fields["subservice_method"].value))
row3[1].metric("CUECs", len(fields["cuecs"]))
row3[2].metric("CSOCs", len(fields["csocs"]))

st.markdown(
    f"**Service organization:** {show_or_missing(fields['service_organization'].value)}  \n"
    f"**Audit firm:** {show_or_missing(fields['audit_firm'].value)}  \n"
    f"**Review period:** {format_period(period)}  \n"
    f"**Trust Services Criteria:** "
    f"{', '.join(tsc) if tsc else 'Not found (expected for a SOC 1)'}"
)

# --- Flags ------------------------------------------------------------------
st.subheader("Review flags")
for flag in flags:
    where = f" (PDF page {flag.page})" if flag.page else ""
    box = LEVEL_BOXES[flag.level]
    box(f"**{flag.topic}:** {flag.reason}{where}", icon=LEVEL_ICONS[flag.level])

# --- Evidence ---------------------------------------------------------------
st.subheader("Evidence")
st.caption("Open a section to see the text each result came from.")

with st.expander("Opinion and Basis for Opinion"):
    show_excerpt(fields["opinion"].page, fields["opinion"].excerpt)
    basis = fields["basis_for_opinion"]
    if basis.value:
        st.markdown("**Basis for opinion paragraph**")
        show_excerpt(basis.page, basis.value)

with st.expander(f"Exceptions ({len(fields['exceptions'])}) with management responses"):
    # Match each exception to its response using the control ID (e.g. CC6.2).
    responses = {r.value: r for r in fields["management_responses"] if r.value}
    if not fields["exceptions"]:
        st.write("No exceptions found by text search. Skim the test results "
                 "section to confirm.")
    for item in fields["exceptions"]:
        st.markdown(f"#### Control {item.value}")
        show_excerpt(item.page, item.excerpt)
        response = responses.get(item.value)
        if response:
            st.markdown("Management's response:")
            show_excerpt(response.page, response.excerpt)
        else:
            st.caption("No matching management response found.")

with st.expander(f"All management responses ({len(fields['management_responses'])})"):
    if not fields["management_responses"]:
        st.write("No management responses found.")
    for response in fields["management_responses"]:
        show_excerpt(response.page, response.excerpt)

with st.expander("Report type, service organization, audit firm"):
    for label in ("report_type", "report_kind", "service_organization", "audit_firm"):
        finding = fields[label]
        st.markdown(f"**{label.replace('_', ' ').capitalize()}:** "
                    f"{show_or_missing(finding.value)}")
        if finding.excerpt:
            show_excerpt(finding.page, finding.excerpt)

with st.expander("Review period"):
    show_excerpt(fields["review_period"].page, fields["review_period"].excerpt)

with st.expander("Trust Services Criteria"):
    criteria = fields["trust_services_criteria"]
    show_excerpt(criteria.page, criteria.excerpt)

with st.expander(f"Subservice organizations ({len(fields['subservice_organizations'])})"):
    method = fields["subservice_method"]
    st.markdown(f"**Method:** {show_or_missing(method.value)}")
    if method.excerpt:
        show_excerpt(method.page, method.excerpt)
    for org in fields["subservice_organizations"]:
        st.markdown(f"**{org.value}**")
        show_excerpt(org.page, org.excerpt)

with st.expander(f"Complementary User Entity Controls ({len(fields['cuecs'])})"):
    show_finding_list(fields["cuecs"], "No CUECs found.")

with st.expander(f"Complementary Subservice Organization Controls ({len(fields['csocs'])})"):
    show_finding_list(fields["csocs"], "No CSOCs found.")


# --- Claude analysis (optional, stage 5) ------------------------------------
st.subheader("🤖 Claude analysis (optional)")

excerpt_text, pages_included, pages_left_out = build_excerpts(pages, fields)
st.caption(
    f"Sends {len(excerpt_text):,} characters from PDF pages "
    f"{', '.join(str(n) for n in pages_included)} to the Claude API ({MODEL}). "
    "Nothing is sent until you click the button; the rest of the report "
    "stays on this computer."
)
if pages_left_out:
    st.caption(f"Over the {MAX_CHARS:,}-character limit, so these pages are NOT sent: "
               f"{', '.join(str(n) for n in pages_left_out)}.")

# Streamlit forgets everything between re-runs, except st.session_state.
# We keep each result there, keyed by a fingerprint of the file, so clicking
# anything else on the page doesn't lose the result - or pay for it again.
if "claude_results" not in st.session_state:
    st.session_state["claude_results"] = {}
file_id = hashlib.sha256(file_bytes).hexdigest()

if not api_key_is_set():
    st.info(
        "To use this, set the **ANTHROPIC_API_KEY** environment variable, then "
        "restart the app. Everything else on this page works without it.\n\n"
        "PowerShell: `$env:ANTHROPIC_API_KEY = \"your-key\"`  \n"
        "Mac/Linux: `export ANTHROPIC_API_KEY=\"your-key\"`"
    )
elif st.button("Run Claude analysis", type="primary"):
    with st.spinner("Asking Claude... this usually takes under a minute."):
        try:
            st.session_state["claude_results"][file_id] = run_analysis(pages, fields)
        except AnalysisError as error:
            st.error(str(error))

result = st.session_state["claude_results"].get(file_id)
if result:
    analysis, info = result
    st.warning(
        "**AI-generated - verify in the report.** Severity ratings and owners "
        "are suggestions to start your review, not conclusions.",
        icon="⚠️",
    )
    st.markdown(f"### Overall risk: {analysis.overall_risk.rating}")
    st.write(analysis.overall_risk.reason)

    st.markdown("**Exceptions**")
    if analysis.exceptions:
        st.dataframe(as_table(analysis.exceptions), hide_index=True)
    else:
        st.write("Claude found no exceptions in the excerpts.")

    st.markdown("**CUECs and suggested owners**")
    if analysis.cuecs:
        st.dataframe(as_table(analysis.cuecs), hide_index=True)
    else:
        st.write("No CUECs in the excerpts.")

    st.markdown("**Subservice organizations**")
    if analysis.subservice_organizations:
        st.dataframe(as_table(analysis.subservice_organizations), hide_index=True)
    else:
        st.write("No subservice organizations in the excerpts.")

    st.markdown("**Questions for the vendor**")
    st.markdown("\n".join(f"{number}. {question}" for number, question
                           in enumerate(analysis.vendor_questions, start=1)))

    st.caption(
        f"{info['model']} · {info['input_tokens']:,} input / "
        f"{info['output_tokens']:,} output tokens · "
        f"estimated cost ${info['estimated_cost_usd']:.3f}"
    )


# --- Reviewer checklist (stage 6) -------------------------------------------
st.subheader("✅ Reviewer checklist")
st.caption("Each item shows what the tool found. Only you set the status: "
           "everything starts as \"Not reviewed\".")

hints = checklist_hints(fields, flags)
answers = {}
for number, (key, question) in enumerate(CHECKLIST, start=1):
    with st.container(border=True):
        left, middle, right = st.columns([3, 2, 3])
        left.markdown(f"**{number}. {question}**")
        left.caption(f"Tool says: {hints[key]}")
        # A widget with a `key` keeps its value when Streamlit re-runs the
        # script. Putting file_id in the key keeps each report's answers
        # separate if you switch files.
        status = middle.selectbox("Status", STATUSES, key=f"{file_id}-{key}-status")
        notes = right.text_input("Notes", key=f"{file_id}-{key}-notes")
        answers[key] = {"status": status, "notes": notes}

# --- Review memo (stage 6) --------------------------------------------------
st.subheader("📝 Review memo")
reviewer = st.text_input("Reviewer name (optional)", key="reviewer")

claude_result = st.session_state["claude_results"].get(file_id)
memo = build_memo(
    fields, flags, answers, file_name,
    analysis=claude_result[0] if claude_result else None,
    reviewer=reviewer,
)

remaining = sum(1 for answer in answers.values() if answer["status"] == STATUSES[0])
if remaining:
    st.caption(f"{remaining} of {len(CHECKLIST)} checklist items not yet reviewed. "
               "You can still download; the memo will say so.")
st.caption("Includes the summary, flags, your checklist, the evidence"
           + (", and the Claude analysis." if claude_result else
              ". Run the Claude analysis above first if you want it included."))

st.download_button(
    "Download review memo (.md)",
    data=memo,
    file_name=memo_file_name(fields),
    mime="text/markdown",
    type="primary",
)
with st.expander("Preview the memo"):
    # Streamlit treats $...$ as maths, so escape dollar signs for display only.
    st.markdown(memo.replace("$", "\\$"))
