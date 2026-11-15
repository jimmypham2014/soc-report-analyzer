# SOC Report Analyzer

<img width="1482" height="1274" alt="image" src="https://github.com/user-attachments/assets/abbc1468-5c32-41f2-86be-0dfd399bcbae" />


A local tool that reads a SOC 1 or SOC 2 report (PDF) and pulls out what a
vendor-risk reviewer needs: report type, period, opinion, exceptions, CUECs,
subservice organizations, and review flags.

Everything runs on your machine. The only exception is the optional Claude
analysis button (stage 5), which sends selected pages to the Claude API only
when you click it.

**See the output without installing anything:** [sample review memo](docs/sample_review_memo.md),
generated from the fake report in `tests/fixtures/`.

> **Results are a first pass.** The tool finds text with pattern matching.
> Always verify findings against the report itself.

## Status

| Stage | What it adds                     | Status |
|-------|----------------------------------|--------|
| 1     | Setup + PDF text by page         | Done   |
| 2     | Rule-based field extraction      | Done   |
| 3     | Red / amber / green flags        | Done   |
| 4     | Streamlit web UI                 | Done   |
| 5     | Optional Claude analysis         | Done   |
| 6     | Reviewer checklist + memo export | Done   |

## Setup (one time)

You need Python 3.12 or 3.13 and Git.

### Mac / Linux

```bash
git clone https://github.com/jimmypham2014/soc-report-analyzer.git
cd soc-report-analyzer
python3 -m venv .venv            # create an isolated Python environment
source .venv/bin/activate        # turn it on for this terminal
pip install -r requirements.txt  # install the libraries
```

Run `source .venv/bin/activate` again each time you open a new terminal.

### Windows (PowerShell)

When installing Python from python.org, tick **"Add python.exe to PATH"**.
If `python` opens the Microsoft Store, use `py` instead.

```powershell
cd $HOME
git clone https://github.com/jimmypham2014/soc-report-analyzer.git
cd soc-report-analyzer
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Your prompt starts with `(.venv)` once activation works. Run
`.venv\Scripts\Activate.ps1` again each time you open PowerShell.

**"Running scripts is disabled on this system"?** That's a Windows security
setting, common on work laptops. Either skip activation and prefix commands
with the venv's Python (changes no settings):

```powershell
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m pytest
.venv\Scripts\python -m streamlit run app.py
```

or allow local scripts for your user only (check with IT on a work machine):

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## Run the web app

```bash
streamlit run app.py
```

Open http://localhost:8501, then upload a SOC report PDF or tick
"try the built-in fake sample report". Press Ctrl+C in the terminal to stop.

### Optional: Claude analysis

The "Run Claude analysis" button needs an Anthropic API key (from
https://console.anthropic.com, billed separately from a claude.ai plan). Set
it as an environment variable **before** starting the app - never put it in
a file in this repo.

```powershell
$env:ANTHROPIC_API_KEY = "your-key"          # PowerShell, this window only
```

```bash
export ANTHROPIC_API_KEY="your-key"          # Mac / Linux, this terminal only
```

Everything else works without a key. A run on the fake sample report costs
roughly $0.05; a full-size report with the 100k-character cap, a few times that.

## Try the pieces from the command line

```bash
python pdf_text.py path/to/report.pdf       # print page count + page starts
python extract.py path/to/report.pdf        # print every extracted field
python flags.py path/to/report.pdf          # print the review flags
python ai_analysis.py path/to/report.pdf    # Claude analysis as JSON (needs key, costs money)
python tools/make_sample_pdf.py             # rebuild the fake test PDFs
pytest                                      # run all tests
```

## Project layout

```
soc-analyzer/
├── pdf_text.py              # Stage 1: PDF -> list of pages (number + text)
├── extract.py               # Stage 2: pages -> report facts (regex)
├── flags.py                 # Stage 3: facts -> red / amber / green flags
├── app.py                   # Stage 4: Streamlit web page
├── ai_analysis.py           # Stage 5: optional Claude analysis
├── review.py                # Stage 6: reviewer checklist + Markdown memo
├── .streamlit/config.toml   # local-only, no telemetry, no Deploy button
├── tools/
│   └── make_sample_pdf.py   # builds fake PDFs for testing
├── tests/
│   ├── fixtures/
│   │   ├── fake_soc2_report.txt   # fake SOC 2 report, pages split by a marker
│   │   ├── fake_soc2_report.pdf   # same report as a PDF (generated)
│   │   └── fake_scanned.pdf       # a PDF with no text, imitating a scan
│   ├── test_pdf_text.py
│   ├── test_extract.py
│   ├── test_flags.py
│   ├── test_app.py
│   ├── test_ai_analysis.py
│   └── test_review.py
├── docs/
│   └── sample_review_memo.md     # example memo from the fake report
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

### `app.py`: the web page

Streamlit re-runs the whole script on every click, top to bottom. The page:

1. Takes an uploaded PDF (or the fake sample).
2. Calls `analyze()`, which reads the PDF and runs `extract_all()` and
   `build_flags()`. It is wrapped in `@st.cache_data`, so a file is only
   read once, not on every click.
3. Stops with a clear message for unreadable PDFs (`PdfReadError`) and
   scanned PDFs (`looks_scanned`), suggesting OCR.
4. Shows a "verify in the report" warning, the overall level, tiles, the
   flags, and expandable evidence: each excerpt with its PDF page number.
   Exceptions are shown next to the management response for the same
   control ID.

`tests/test_app.py` drives the page with Streamlit's `AppTest` (no browser).
`AppTest` can't upload files, so uploads (normal, scanned, and a corrupt
file) were also checked in a real browser.

### `ai_analysis.py`: the optional Claude step

- **What's sent:** `pages_to_send()` lists the pages the regex stage found
  relevant, most important first: opinion, basis, scope, exceptions,
  management responses, subservice orgs, CUECs, CSOCs. `build_excerpts()`
  joins whole pages, each labelled `--- PDF page N ---`, up to 100,000
  characters, and reports any pages left out. The page shows exactly what
  will be sent before you click.
- **The answer's shape:** Pydantic classes (`SocAnalysis` and friends)
  describe the JSON: exceptions with a High/Medium/Low severity and reason,
  CUECs with a suggested owner, subservice orgs, an overall rating, and
  vendor questions (trimmed to 8). `client.beta.messages.parse()` asks
  Claude for that shape and validates the answer; anything that doesn't
  match is rejected with a clear message.
- **Prompt-injection guard:** report text goes inside `<report_excerpts>`
  tags, and the system prompt says to treat it as data, never instructions.
- **Model and settings:** `claude-opus-5-5`, effort `high`, and server-side
  refusal fallbacks (if a safety check declines, the API retries on another
  model).
- **Errors** (bad key, rate limit, network, refusal, cut-off answer) become
  plain-English `AnalysisError` messages.
- **In the app**, results are stored in `st.session_state` per file, so
  clicking anything else neither loses them nor calls (and bills) the API again.
- **Tests never call the real API.** They swap the SDK's network layer for a
  local function returning canned answers, so they're free and need no key.

### `review.py`: checklist and memo

- `CHECKLIST` holds the 9 reviewer questions: scope, period, opinion,
  criteria, exceptions, CUECs, subservice reports, bridge letter, and
  licensed CPA firm.
- `checklist_hints()` shows what the tool found for each item ("Tool says:
  period ended 138 days ago..."). **It never sets a status**: every item
  starts as "Not reviewed" and only the reviewer changes it.
- `build_memo()` writes one Markdown document: summary table, flags, the
  checklist with statuses and notes (and how many items are still
  unreviewed), the Basis for Opinion, each exception with its management
  response, subservice orgs, CUECs, CSOCs, and the Claude analysis if it was
  run (labelled AI-generated). `md_cell()` escapes `|` and line breaks so
  notes can't break the tables.
- In the app, each dropdown and notes box has a `key` that includes the
  file's fingerprint, so answers survive re-runs and stay separate per report.
  "Download review memo" saves the `.md` file to your browser's downloads.

### `.streamlit/config.toml`: privacy settings

- `address = "localhost"`: only this computer can open the page.
- `gatherUsageStats = false`: no usage statistics sent to Streamlit.
- `toolbarMode = "minimal"`: hides the "Deploy" button.

## What I learned

I work in GRC and built this to learn how to make my own tools. Things I
took away, in no particular order:

**About building it**

- **PDFs don't contain tables.** They store words at positions on a page, so
  a test-results table comes out with its columns jumbled together. I
  designed around that: match on phrases like "Exception noted", keep the
  page number attached to every piece of text from the very first step, and
  always point the reviewer back to the page.
- **Regex is a good first pass, and the edge cases are where the work is.**
  The hard parts weren't finding "exception noted" - they were *not* counting
  "No exceptions noted", not reading "unqualified" as "qualified", and not
  treating the AICPA standard's title (which lists all five Trust Services
  Criteria) as the report's scope.
- **A test only proves something if it fails when the code is wrong.** I
  deliberately broke the "No exceptions noted" check to confirm the tests
  caught it. I also learned to test boundaries (90 vs 91 days, 5 vs 6
  months) and to use mocks so the Claude tests run free, offline, with no key.
- **Streamlit re-runs the whole script on every click.** That keeps the code
  simple, but it means caching slow work, keeping results in
  `st.session_state` (or a re-run would call the paid API again), and giving
  widgets keys so checklist answers survive.
- **Using an LLM safely in a tool:** send only the pages that matter and show
  the user exactly what will be sent; ask for a fixed JSON schema and reject
  answers that don't match it; wrap document text so it's treated as data,
  not instructions (prompt injection); keep the API key in an environment
  variable, never in code.

**About GRC tooling**

- **"Not found" is not "clean."** If the tool can't find the opinion or the
  period, the flag is amber, never green. A scanned PDF stops with an OCR
  message instead of showing zero exceptions.
- **Automation should support the reviewer, not sign off.** The checklist
  shows what the tool found, but every item starts as "Not reviewed" and only
  a person changes it. The memo says how many items are still open.
- **Privacy by default.** The app only listens on localhost, Streamlit's
  usage statistics and Deploy button are off, and `.gitignore` blocks every
  PDF except the fake test reports - important with a public repo.
- **Writing the rules down made me understand them better.** Turning review
  steps into code forced precise answers: what exactly counts as stale, when
  a bridge letter is needed, why a carve-out means requesting the
  subservice org's own SOC report, and what CUECs and CSOCs ask of each side.

**What I'd do next:** test it against real reports (public SOC 3s are a start)
to find wording the patterns miss, add more fake reports covering clean and
SOC 1 cases, and measure how often the regex and the Claude analysis agree.

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
