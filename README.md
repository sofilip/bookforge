# bookforge

```
  ____              _    ______
 |  _ \            | |  |  ____|
 | |_) | ___   ___ | | _| |__ ___  _ __ __ _  ___
 |  _ < / _ \ / _ \| |/ /  __/ _ \| '__/ _` |/ _ \
 | |_) | (_) | (_) |   <| | | (_) | | | (_| |  __/
 |____/ \___/ \___/|_|\_\_|  \___/|_|  \__, |\___|
                                         __/ |
                                        |___/
```

You have a PDF of a book — maybe a scanned copy from a library, maybe a digital file with a text layer somebody emailed you. Either way, it's a mess: broken hyphens across pages, OCR artifacts where kappa became chi, footnote digits glued to words, missing accents on half the vocabulary. You want a clean, typeset e-book out the other end. That's what this does.

BookForge is a command-line tool that takes a PDF and a small config file describing the book's structure (which pages are which parts, how many sections each part has), and runs it through a fully automated publishing pipeline: text extraction, linguistic proofreading, XeLaTeX PDF typesetting, and EPUB generation. It was originally built for Greek books — polytonic and monotonic — but the architecture is language-agnostic.

## data

The tool needs two inputs:

1. **A PDF file** — either a digitally-born PDF with an embedded text layer, or a scanned PDF (in which case you'll need Tesseract installed for OCR).
2. **A TOML config file** (`book.toml`) describing the book structure: title, author, language, and the page ranges for each part/chapter.

That's it. No databases, no API keys, no cloud services.

An example config file is included in `examples/example_config.toml`. Copy it, fill in your book's details, and point the CLI at your PDF.

## what it actually produces

Given a PDF and a config, BookForge outputs up to three formats:

- **PDF** — a publisher-grade typeset book compiled with XeLaTeX. A5 paper, GFS Didot (or any font you specify), drop capitals, table of contents, proper headers/footers, zero overfull hbox warnings.
- **EPUB** — a standards-compliant e-book with embedded fonts, custom CSS typography, cover image extracted from the PDF, and a navigable table of contents. Works on Kindle, Kobo, Apple Books, and every EPUB reader.
- **TXT** — clean plain text with all OCR errors corrected and hyphens rejoined, organized by part and section.

Plus a detailed **audit report** (Markdown and JSON) documenting every single correction the proofreader made — what was wrong, what it was changed to, and why.

## user model

- **what you can do:** feed it any book PDF and get back a clean, typeset e-book in multiple formats without touching LaTeX or Pandoc yourself
- **what you get:** publisher-grade output with an auditable correction trail — every OCR error logged and explained
- **what you're trying to win:** time. stop manually fixing broken hyphens and chi-for-kappa substitutions across 300 pages

So it's someone with a PDF, working from a terminal, trying to produce a clean e-book. The pipeline exists because that's what actually needs to happen.

## how the pipeline actually goes

When you run `bookforge run`, here's the journey your PDF takes:

**1. it parses the config file**

- Reads `book.toml` to understand the book structure: how many parts, which pages belong to which part, expected section count per part, language, font, and output preferences.

**2. it extracts text from the PDF**

- Uses PyMuPDF (`fitz`) to pull the embedded text layer page by page.
- Strips trailing page numbers and single-character scanner artifacts.
- Rejoins words hyphenated across line breaks and page boundaries using language-aware regex patterns.
- If the PDF is scanned (no text layer), falls back to parallel Tesseract OCR with checkpoint/resume support.

**3. it splits the text into sections**

- Based on the section numbering style in the config (numeric `1, 2, 3` or Roman `I, II, III`), it splits each part's extracted text into individual sections.
- Validates the count against the expected number in the config.

**4. it runs the second auditor**

- A multi-pass regex-based proofreading engine scans every section for:
  - Unicode confusable characters (micro sign to mu, Greek question mark to semicolon)
  - Stray footnote digit artifacts glued to words or punctuation
  - Missing spaces after punctuation, before quotes
  - Known Greek optical misrecognitions: chi/kappa confusion, digit-6-for-beta, missing accents
  - Spacing normalization around em-dashes and dialogue markers
- Every correction is logged with the original text, the replacement, and a human-readable explanation.

**5. it typesets the PDF with XeLaTeX**

- Generates a complete LaTeX document with Polyglossia language support, configurable font, A5 (or A4/Letter) geometry, `\emergencystretch=3em` for zero overflow, drop capitals via Lettrine, table of contents, and professional headers/footers.
- Compiles with two XeLaTeX passes (one for content, one for TOC and cross-references).

**6. it builds the EPUB with Pandoc**

- Generates a Pandoc-compatible Markdown intermediate with YAML front matter.
- Extracts a cover image from the first page of the generated PDF.
- Compiles to EPUB with embedded font, custom CSS, and a navigable table of contents.

## directory structure

| folder / file | what it does |
|---|---|
| `bookforge/__init__.py` | package init with version string |
| `bookforge/cli.py` | the command-line entry point with four subcommands |
| `bookforge/config.py` | TOML config parser for book structure and metadata |
| `bookforge/extractor.py` | PDF text extraction, de-hyphenation, and optional OCR |
| `bookforge/auditor.py` | the Second Auditor: multi-pass linguistic proofreader |
| `bookforge/typesetter.py` | XeLaTeX document generation and PDF compilation |
| `bookforge/epub_builder.py` | Markdown generation and Pandoc EPUB compilation |
| `bookforge/templates/epub_style.css` | default CSS stylesheet for EPUB readers |
| `examples/example_config.toml` | sample config file you can copy and adapt |
| `showcase/lorem_ipsum_showcase.pdf` | sample typeset output PDF built with lorem ipsum |
| `showcase/showcase.toml` | config used to generate the showcase PDF |
| `pyproject.toml` | package metadata and dependencies for uv |

## installation

It's set up to work with **`uv`**, the python package installer:

```bash
# install it as a global tool
uv tool install .
```

That's it for the tool itself. You'll also need these system dependencies:

- **XeLaTeX** — for PDF compilation. Install with `sudo apt install texlive-xetex texlive-latex-extra texlive-fonts-extra` on Debian/Ubuntu.
- **Pandoc** — for EPUB generation. Install with `sudo apt install pandoc`.
- **Tesseract** *(optional)* — only needed for scanned PDFs without a text layer. Install with `sudo apt install tesseract-ocr tesseract-ocr-ell`.
- **GFS Didot font** *(recommended)* — the default serif font. Install with `sudo apt install fonts-gfs-didot`.

## how to run it

You can run the entire pipeline in a single command:

```bash
# full pipeline: extract, audit, and publish
bookforge run --pdf mybook.pdf --config book.toml --format pdf,epub,txt
```

If you don't want to run the whole pipeline at once, you can run the individual steps manually:

**1. extract text from the PDF**

```bash
bookforge extract --pdf mybook.pdf --config book.toml --output text/
```

**2. run the proofreader on extracted text**

```bash
bookforge audit --input text/ --config book.toml --output audited/
```

**3. typeset the audited text into final formats**

```bash
bookforge publish --input audited/ --config book.toml --format pdf,epub
```

## system requirements

The tool itself is pure Python with one dependency (`pymupdf`). The heavy lifting is done by system tools:

- **XeLaTeX** (`texlive-xetex`) — required for PDF output
- **Pandoc** — required for EPUB output
- **Tesseract** — optional, only for scanned PDFs
- **Python 3.10+** — required

All of these are free, open-source, and available in every major Linux distribution's package manager.

## disclaimer

> [!NOTE]
> This is a **vibe coded** project. It was built iteratively through conversation with an AI assistant, shaped by feel and intent rather than a formal software engineering process. Expect rough edges, opinionated defaults, and the occasional regex that looks like it was written at 3 AM. Because it was.

## limitations

This is a text extraction and typesetting pipeline. It assumes you have a source PDF to work from.

- **the config is manual.** you need to know which pages belong to which part of the book. There's no magic chapter detection — you open the PDF, note down the page ranges, and write them in the config file.
- **the auditor rules are Greek-focused.** the built-in correction rules target Greek OCR artifacts (chi/kappa confusion, missing accents, etc.). For other languages, you'll need to extend the auditor with your own rules.
- **XeLaTeX is required for PDF output.** if you don't have a working TeX installation, the PDF step will fail. You can still generate TXT and EPUB without it.
- **Pandoc is required for EPUB output.** no Pandoc, no EPUB. You can still generate PDF and TXT.
- **font availability matters.** the default font is GFS Didot. If it's not installed, XeLaTeX will fall back to whatever it can find, which may not look great.

