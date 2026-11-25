"""
PDF text extractor for BookForge.

Extracts the text layer from a PDF using PyMuPDF, strips page numbers,
and rejoins words hyphenated across line and page boundaries.
Optionally runs Tesseract OCR for scanned PDFs without a text layer.
"""

import os
import re
import sys
import subprocess
import shutil
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

import fitz  # PyMuPDF


# ---------------------------------------------------------------------------
# Text-layer extraction (digital PDFs)
# ---------------------------------------------------------------------------

_GREEK_LETTER = r"[\u0370-\u03FF\u1F00-\u1FFF]"
_LETTER = rf"(?:{_GREEK_LETTER}|[a-zA-Z])"


def extract_text_layer(
    pdf_path: Path,
    start_page: int,
    end_page: int,
) -> str:
    """
    Extract the embedded text layer from *pdf_path* for pages
    [start_page, end_page] (1-based inclusive).
    Returns de-hyphenated, cleaned text.
    """
    doc = fitz.open(str(pdf_path))
    pages_text = []

    for p_idx in range(start_page - 1, min(end_page, len(doc))):
        txt = doc[p_idx].get_text()
        lines = [line.strip() for line in txt.splitlines()]

        # Strip trailing page number
        if lines and re.match(r"^\d{1,4}$", lines[-1]):
            lines = lines[:-1]
        # Strip stray single-character artifact before page number
        if (
            len(lines) >= 2
            and len(lines[-2]) <= 2
            and re.match(r"^\d{1,4}$", lines[-1])
        ):
            lines = lines[:-2]

        pages_text.append("\n".join(lines))

    doc.close()

    combined = "\n".join(pages_text)
    combined = _dehyphenate(combined)
    return combined


def _dehyphenate(text: str) -> str:
    """Rejoin words split by hyphens across line breaks."""
    text = re.sub(
        rf"({_LETTER}+)\s*[-\u2013\u2014\xad^]\s*\n\s*({_LETTER}+)",
        r"\1\2",
        text,
    )
    text = re.sub(
        rf"({_LETTER}+)[-\xad]\s+({_LETTER}+)",
        r"\1\2",
        text,
    )
    text = text.replace("\xad", "")
    return text


def extract_part(
    pdf_path: Path,
    start_page: int,
    end_page: int,
    expected_sections: int = 0,
    section_style: str = "numeric",
) -> dict:
    """
    Extract a single part/chapter from *pdf_path*.

    Returns a dict with keys:
      - 'raw': the full extracted text
      - 'sections': dict mapping section_num -> section_text
                    (empty if section_style is 'none')
    """
    raw = extract_text_layer(pdf_path, start_page, end_page)

    sections = {}
    if section_style == "numeric" and expected_sections > 0:
        parts = re.split(r"(?:^|\n)\s*(\d{1,3})\s*\n", raw)
        for i in range(1, len(parts), 2):
            sec_num = int(parts[i])
            sec_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections[sec_num] = sec_text
    elif section_style == "roman" and expected_sections > 0:
        parts = re.split(
            r"(?:^|\n)\s*((?:X{0,3})(?:IX|IV|V?I{0,3}))\s*\n",
            raw,
            flags=re.IGNORECASE,
        )
        roman_map = {
            "I": 1, "II": 2, "III": 3, "IV": 4, "V": 5,
            "VI": 6, "VII": 7, "VIII": 8, "IX": 9, "X": 10,
            "XI": 11, "XII": 12, "XIII": 13, "XIV": 14, "XV": 15,
        }
        for i in range(1, len(parts), 2):
            numeral = parts[i].strip().upper()
            sec_num = roman_map.get(numeral, i // 2 + 1)
            sec_text = parts[i + 1].strip() if i + 1 < len(parts) else ""
            sections[sec_num] = sec_text

    if expected_sections and len(sections) != expected_sections:
        print(
            f"  Warning: expected {expected_sections} sections, "
            f"found {len(sections)}",
            file=sys.stderr,
        )

    return {"raw": raw, "sections": sections}


# ---------------------------------------------------------------------------
# OCR extraction (scanned PDFs without text layer)
# ---------------------------------------------------------------------------

def _find_tesseract() -> str | None:
    """Locate the tesseract binary."""
    return shutil.which("tesseract")


def ocr_single_page(
    pdf_path: str,
    page_index: int,
    dpi: int,
    lang: str,
    tesseract_bin: str,
) -> tuple[int, str]:
    """
    Render a single PDF page at *dpi* and run Tesseract OCR.
    Returns (page_number_1based, extracted_text).
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc[page_index]
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        doc.close()

        cmd = [
            tesseract_bin,
            "stdin", "stdout",
            "-l", lang,
            "--oem", "1",
            "--psm", "3",
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = proc.communicate(input=img_bytes)

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            return page_index + 1, f"[OCR ERROR on page {page_index + 1}: {err}]"

        return page_index + 1, stdout.decode("utf-8", errors="replace")

    except Exception as exc:
        return page_index + 1, f"[EXCEPTION on page {page_index + 1}: {exc}]"


def ocr_pages(
    pdf_path: Path,
    page_indices: list[int],
    lang: str = "ell",
    dpi: int = 300,
    workers: int | None = None,
    cache_dir: Path | None = None,
) -> dict[int, str]:
    """
    Run parallel OCR on the given 0-based page indices.
    Returns a dict mapping 1-based page numbers to extracted text.
    """
    tesseract_bin = _find_tesseract()
    if not tesseract_bin:
        print(
            "Error: tesseract not found. Install it with your package manager.",
            file=sys.stderr,
        )
        sys.exit(1)

    if workers is None or workers <= 0:
        workers = min(os.cpu_count() or 4, 6)

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)

    # Check cache
    pending = []
    results: dict[int, str] = {}
    for idx in page_indices:
        p_num = idx + 1
        if cache_dir:
            cf = cache_dir / f"page_{p_num:05d}.txt"
            if cf.exists():
                results[p_num] = cf.read_text(encoding="utf-8")
                continue
        pending.append(idx)

    if pending:
        with ProcessPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    ocr_single_page,
                    str(pdf_path),
                    idx,
                    dpi,
                    lang,
                    tesseract_bin,
                ): idx
                for idx in pending
            }
            for future in as_completed(futures):
                p_num, text = future.result()
                text = _dehyphenate(text)
                results[p_num] = text
                if cache_dir:
                    (cache_dir / f"page_{p_num:05d}.txt").write_text(
                        text, encoding="utf-8"
                    )

    return results

