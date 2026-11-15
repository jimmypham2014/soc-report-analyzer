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
| 2     | Rule-based field extraction      | Todo   |
| 3     | Red / amber / green flags        | Todo   |
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
python tools/make_sample_pdf.py             # rebuild the fake test PDFs
pytest                                      # run all tests
```

## Project layout

```
soc-analyzer/
├── pdf_text.py              # Stage 1: PDF -> list of pages (number + text)
├── tools/
│   └── make_sample_pdf.py   # builds fake PDFs for testing
├── tests/
│   ├── fixtures/
│   │   ├── fake_soc2_report.txt   # fake SOC 2 report, pages split by a marker
│   │   ├── fake_soc2_report.pdf   # same report as a PDF (generated)
│   │   └── fake_scanned.pdf       # a PDF with no text, imitating a scan
│   └── test_pdf_text.py
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

## Limitations

- **Page numbers are PDF page numbers**, not the numbers printed in the
  report's footer. Reports often start numbering after the cover and table
  of contents, so the two can differ.
- **Tables lose their columns.** pdfplumber reads tables row by row, left to
  right, so text from neighbouring columns ends up on the same line. Later
  stages are written with this in mind.
