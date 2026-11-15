# SOC Report Analyzer

A local tool that reads a SOC 1 or SOC 2 report (PDF) and pulls out what a
vendor-risk reviewer needs: report type, period, opinion, exceptions, CUECs,
subservice organizations, and review flags.

Everything runs on your machine. The only exception is the optional Claude
analysis step (stage 5), which sends selected excerpts to the Claude API.

> **Results are a first pass.** The tool finds text with pattern matching.
> Always verify findings against the report itself.

## Status

| Stage | What it adds                     | Status |
|-------|----------------------------------|--------|
| 1     | Setup + PDF text by page         | Done   |
| 2     | Rule-based field extraction      | Done   |
| 3     | Red / amber / green flags        | Done   |
| 4     | Streamlit web UI                 | Todo   |
| 5     | Optional Claude analysis         | Todo   |
| 6     | Reviewer checklist + memo export | Todo   |

## Setup (one time)

```bash
cd soc-analyzer
python3 -m venv .venv            # create an isolated Python environment
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt  # install the libraries
```

Run `source .venv/bin/activate` again each time you open a new terminal.

## Try it

```bash
python pdf_text.py path/to/report.pdf       # print page count + page starts
python extract.py path/to/report.pdf        # print every extracted field
python flags.py path/to/report.pdf          # print the review flags
python tools/make_sample_pdf.py             # rebuild the fake test PDFs
pytest                                      # run all tests
```

## Project layout

```
soc-analyzer/
├── pdf_text.py              # Stage 1: PDF -> list of pages (number + text)
├── extract.py               # Stage 2: pages -> report facts (regex)
├── flags.py                 # Stage 3: facts -> red / amber / green flags
├── tools/
│   └── make_sample_pdf.py   # builds fake PDFs for testing
├── tests/
│   ├── fixtures/
│   │   ├── fake_soc2_report.txt   # fake SOC 2 report, pages split by a marker
│   │   ├── fake_soc2_report.pdf   # same report as a PDF (generated)
│   │   └── fake_scanned.pdf       # a PDF with no text, imitating a scan
│   ├── test_pdf_text.py
│   ├── test_extract.py
│   └── test_flags.py
├── requirements.txt
└── pytest.ini
```

## How each piece works

### `pdf_text.py`: reading the report

- `extract_pages_from_pdf(source)` opens a PDF with pdfplumber and returns a
  list of `Page(number, text)`. Page numbers start at 1, so they match what
  you see in a PDF viewer. `source` can be a file path or an open file.
- `load_pages_from_text(path)` does the same for `.txt` test fixtures, where
  pages are separated by a line reading `=== PAGE BREAK ===`.
- `looks_scanned(pages)` returns True when the pages average fewer than 50
  characters of text. That means the PDF is probably scanned images, so
  run OCR on it first (for example with `ocrmypdf`).
- A corrupt or password-protected PDF raises `PdfReadError` with a readable
  message instead of crashing.

### `extract.py`: finding the facts

One small function per field. Each returns a `Finding(value, page, excerpt)`
(or a list of them), so every result can be traced back to a page.

| Function | Finds | How |
|---|---|---|
| `report_type` | SOC 1 / SOC 2 | Counts "SOC 1" vs "SOC 2", most common wins; falls back on "trust services criteria" / "internal control over financial reporting" |
| `report_kind` | Type I / Type II | Counts "Type 1/I/2/II"; falls back on "operating effectively throughout the period" vs "as of" |
| `service_organization` | Audited company | Name before 's in "Report on X's Description" / "We have examined X's" |
| `audit_firm` | CPA firm | A line ending LLP / LLC / P.C. / CPAs; the last one on the auditor's report pages (the signature) |
| `review_period` | Start and end dates | "period X to/through Y"; Type I falls back to "as of X" |
| `months_covered`, `days_since_period_end` | Numbers for flags | Date arithmetic (`days / 30.44`, rounded) |
| `opinion` | Unmodified / Qualified / Adverse / Disclaimer | Checks the headings in that order; "In our opinion" alone = Unmodified |
| `basis_for_opinion` | The "Basis for..." paragraph | Text from the heading to the next opinion heading |
| `trust_services_criteria` | Categories in scope | "relevant to Security, Availability..."; ignores the AICPA standard's title, which lists all five |
| `exceptions` | Each exception + page + control ID | "exception(s)/deviation(s) noted/identified/found", **skipping** ones preceded by no / not / without / the / any |
| `management_responses` | Each response + control ID | "Management's response:" up to the next one |
| `subservice_method` | Carve-out / Inclusive | "carve-out" / "carved out" vs "inclusive method" |
| `subservice_organizations` | Subservice org names | "subservice organization, Name..." plus a list of well-known providers |
| `cuecs`, `csocs` | Each listed control | Items (CUEC-1, 1., bullets) under the heading, until the next section |
| `extract_all` | Everything | Runs all of the above; returns a dictionary |

### `flags.py`: what needs attention

Each rule is one function returning a `Flag(level, topic, reason, page)`.
`build_flags()` runs them all and sorts worst first; `overall_level()`
returns the worst level (one red makes the report red).

| Rule | Red | Amber | Green |
|---|---|---|---|
| Opinion | Qualified, Adverse, Disclaimer | Not found | Unmodified |
| Report type | | Type I, or not found | Type II |
| Period length (Type II only) | | Under 6 months, or not found | 6+ months |
| Period currency | Over 365 days since end: stale | Over 90 days: request a bridge letter; or not found | 90 days or less |
| Exceptions | | Any found | None found (verify) |
| Subservice orgs | | Carve-out, or orgs with unclear method | Inclusive, or none |
| CUECs | | Any found | None found (verify) |

**If something can't be found, the flag is amber, never green.** Thresholds
are constants at the top of `flags.py`; change them to match your policy.

## Limitations

- **Page numbers are PDF page numbers**, not the numbers printed in the
  report's footer. Reports often start numbering after the cover and table
  of contents, so the two can differ.
- **Tables lose their columns.** pdfplumber reads tables row by row, left to
  right, so text from neighbouring columns ends up on the same line. Later
  stages are written with this in mind. Exception excerpts therefore read
  as a jumble of columns; open the page to read the actual result.
- **Wording varies by audit firm.** The patterns cover standard AICPA wording.
  Unusual phrasing can be missed: an exception written as "2 of 25 samples
  lacked approval" with no "exception"/"deviation" word won't be found.
- **Management responses inside a table column**, with no "Management's
  response:" label, won't be found.
- **Subservice org names** come from one sentence pattern plus a list of
  known providers (`KNOWN_PROVIDERS` in `extract.py`). Add to the list as
  you meet new ones.
