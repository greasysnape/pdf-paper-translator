# pdf-paper-translator

Translate academic papers (PDF) into another language **while keeping the original layout**.
Text blocks are extracted with PyMuPDF, translated with an LLM, and written back into
the same positions. Equations, figures and tables are left untouched.

Two output files are produced:

| file | description |
|---|---|
| `<name>.mono.pdf` | translated text replaces the original text |
| `<name>.dual.pdf` | original page and translated page side by side |

## Features

- Layout-preserving: each paragraph is redrawn inside its original bounding box
- Math-aware: blocks that look like equations are skipped and kept as-is
- Batch requests with JSON output to keep API calls low
- Local SQLite cache so re-running on the same paper costs nothing
- Page ranges, custom glossary, and a `dummy` engine for offline testing

## Installation

```bash
git clone <repository-url>
cd pdf-paper-translator
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

Set an API key for the Gemini engine:

```bash
cp .env.example .env
# then edit .env and set GEMINI_API_KEY
```

## Usage

```bash
# translate to Korean (default target)
pdftrans paper.pdf

# Japanese, pages 1-5 only, output to ./out
pdftrans paper.pdf --lang ja --pages 1-5 -o out

# use a glossary to pin terminology
pdftrans paper.pdf --glossary glossary.example.tsv

# no API calls, just check the layout pipeline
pdftrans paper.pdf --engine dummy
```

You can also run it as a module:

```bash
python -m translator paper.pdf --lang ko
```

### Options

```
positional:
  input                 input PDF

options:
  -o, --output DIR      output directory (default: next to the input)
  -l, --lang LANG       target language code (default: ko)
  --source-lang LANG    source language code (default: en)
  --engine NAME         gemini | dummy (default: gemini)
  --model NAME          model name for the engine (default: $PDFTRANS_MODEL or gemini-2.5-flash)
  --pages RANGE         e.g. "1-3,7"
  --batch-size N        blocks per request (default: 20)
  --glossary FILE       TSV file: source<TAB>target per line
  --no-cache            ignore the translation cache
  --mono-only / --dual-only
  -v, --verbose
```

## How it works

1. `pdf_io.extract_blocks` reads every text block with its bbox and dominant font size.
2. `math_guard.should_translate` drops blocks that are mostly math symbols, numbers,
   references like `[12]`, or very short labels.
3. Remaining blocks are sent to the engine in batches. The engine returns a JSON array
   aligned with the input.
4. `render.write_mono` covers each original block with a white box and inserts the
   translation with `insert_htmlbox`, which shrinks the text to fit and picks
   a font that supports the target script.
5. `render.write_dual` places the original and the translated page next to each other.

## Cache

Translations are stored in `~/.cache/pdf-paper-translator/cache.sqlite3`
(override with `PDFTRANS_CACHE_DIR`). Delete the file to clear it, or pass `--no-cache`.

## Limitations

- Scanned PDFs (images only) are not supported; run OCR first.
- Multi-column layouts work at block level; occasionally a block spans two columns.
- Very long translations are shrunk to fit and may become small.

## Tests

```bash
pip install -e ".[dev]"
pytest
```
